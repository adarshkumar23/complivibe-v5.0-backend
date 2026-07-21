"""Inbound push from the patent-P9 contract-obligation-extraction satellite.

The satellite reads an explicitly uploaded contract, segments it into clauses,
classifies each one deterministically (no LLM, no network -- that is the
patent's claim), and pushes the obligations it is confident about here. Core
turns each one into a Customer Commitment: a live monitoring rule that fires
when a matching incident is detected and notifies the customer it was promised
to.

WHY THIS LIVES UNDER app/compliance/routers RATHER THAN ai_governance
=====================================================================
P2 and P4 keep their ingest routes under app/ai_governance/routers because they
ARE AI-governance features. P9 is not: it writes customer_commitments, which is
a compliance-domain table, and it touches nothing in ai_governance. The
/patent-ingest/p9 prefix keeps it discoverable alongside its siblings in the API
surface, which is where that consistency actually matters.

AUTH, AND WHY THERE IS NO require_permission HERE
=================================================
Built on patent_ingest_p4 as the template: bearer scoped key, organisation
derived from the key, rate limiter, commit in the router. The scope is
'p9_ingest' -- its own, not P2's 'ingest' or P4's 'p4_ingest' -- so a key
leaked from one satellite cannot authenticate another. See migration 0328.

The upstream patch instead used a static Authorization: Bearer token plus
require_permission("compliance:write"). Both halves were wrong:

* The bearer path is disabled outright when APP_ENV == production
  (BearerOrSessionCookie, app/core/deps.py:53), so every production request
  would have fallen through to the session cookie and 401'd.
* require_permission needs a human Membership. A scoped-key caller has no user,
  and the system automation account deliberately holds ZERO permissions, so any
  permission gate on this route would fail closed on every request. RBAC is the
  wrong instrument here; the key's scope IS the authority, exactly as for P2 and
  P4. (The equivalent human path, app/api/v1/customer_commitments.py, keeps
  vendor:write and is unchanged.)

WHOSE NAME GOES ON THE ROW
==========================
customer_commitments.created_by is NOT NULL FK users.id, and there is no human
on a machine push. Rather than borrow the assigned owner's identity -- which
would misattribute a machine decision to a person -- the row is created by the
shared system automation account, the same pattern the governance workflow
engine uses. The assigned owner is still a real, validated, active member.

WHAT CORE DOES NOT TAKE THE SATELLITE'S WORD FOR
================================================
The satellite gates on its own confidence score and only pushes what clears its
threshold. Core re-checks that independently: a payload flagged
requires_human_review is REFUSED, not quietly stored, because a below-threshold
obligation must never become a live monitoring rule that notifies a customer.
obligation_type is likewise validated against core's own vocabulary.

KNOWN PRODUCT GAP: BREACH-NOTIFICATION OBLIGATIONS HAVE NO BREACH DETECTOR
=========================================================================
Recorded here rather than papered over, because it is the difference between
this integration working and appearing to work.

P9's flagship obligation is the breach-notification SLA -- "notify the customer
within 72 hours of a breach". Those register as commitment_type
'breach_notification' with triggering_incident_type 'data_breach', and core's
matcher does resolve that: CustomerCommitmentService.trigger_commitments_for_incident
aliases retention_violation -> data_breach and residency_violation -> data_breach.

The gap is upstream of the matcher. Core has NO breach detector. The only
detector types it emits automatically are:

    quality_breach       quality_service.py            -> service_incident
    anomaly_rule         access_monitoring_service.py  -> security_incident
    residency_violation  residency_service.py          -> data_breach

'retention_violation' and 'manual' are valid detector types but nothing emits
them automatically; they can only arrive through the human/API incident route.

So today a P9 breach-notification commitment fires automatically only when a
DATA-RESIDENCY violation is detected, or when somebody files a retention-violation
incident by hand. An actual security breach fires nothing: the closest signal,
anomaly_rule from access monitoring, aliases to 'security_incident', which is not
a trigger vocabulary P9 writes.

This is a missing detector, not a bug in this route, and the fix belongs in
data observability rather than here. Until it exists, do not describe the P9
breach-notification path as end-to-end automated. The path that IS proven
end-to-end is the residency/retention one, which is what the integration test
exercises deliberately.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.scope_deps import require_p9_ingest_scope
from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.core.deps import get_db
from app.core.rate_limiter import rate_limiter
from app.models.customer_commitment import CustomerCommitment
from app.schemas.customer_commitment import (
    COMMITMENT_TYPE_PATTERN,
    P9_OBLIGATION_TYPE_PATTERN,
    CustomerCommitmentCreate,
    CustomerCommitmentRead,
)
from app.services.audit_service import AuditService
from app.services.system_account_service import ensure_system_account_membership

router = APIRouter(prefix="/patent-ingest/p9", tags=["patent-ingest-p9"])


class P9CommitmentIngest(BaseModel):
    """Everything core's own create schema takes, plus the P9 columns.

    Field names and constraints mirror CustomerCommitmentCreate exactly, so a
    payload valid here is valid there. Note there is deliberately no
    organization_id: the org comes from the scoped key.
    """

    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    commitment_type: str = Field(pattern=COMMITMENT_TYPE_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    trigger_condition: str = Field(min_length=1)
    triggering_incident_type: str | None = Field(default=None, max_length=100)
    notification_days_before: int = Field(default=7, ge=1, le=90)
    sla_hours: int | None = None
    linked_contract_ref: str | None = Field(default=None, max_length=500)
    assigned_owner_id: uuid.UUID

    # -- added by migration 0327 -------------------------------------------
    obligation_type: str = Field(pattern=P9_OBLIGATION_TYPE_PATTERN)
    extracted_params: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = False
    source_clause_text: str = Field(min_length=1)


@router.post(
    "/commitments",
    response_model=CustomerCommitmentRead,
    status_code=status.HTTP_201_CREATED,
)
@rate_limiter.limiter.limit("120/minute")
def ingest_p9_commitment(
    payload: P9CommitmentIngest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[uuid.UUID, Depends(require_p9_ingest_scope())],
    x_p9_upload_id: Annotated[str | None, Header(alias="X-P9-Upload-Id")] = None,
) -> CustomerCommitmentRead:
    """Register one extracted contract obligation as a Customer Commitment."""

    # A below-threshold obligation must never become a live monitoring rule.
    # The satellite already gates on this; core does not take its word for it.
    if payload.requires_human_review:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Obligations flagged for human review cannot be auto-registered. "
                "Route them through the standard commitment creation endpoint "
                "after a reviewer has confirmed them."
            ),
        )

    # Idempotency: an upload retried after a network failure must not create
    # duplicate commitments for the same clause. Two rows are fetched rather
    # than one so the ambiguous case is a clear 409 -- scalar_one_or_none()
    # raised MultipleResultsFound here and surfaced as a 500.
    if x_p9_upload_id and payload.linked_contract_ref:
        existing = list(
            db.execute(
                select(CustomerCommitment)
                .where(
                    CustomerCommitment.organization_id == org_id,
                    CustomerCommitment.linked_contract_ref == payload.linked_contract_ref,
                    CustomerCommitment.source_clause_text == payload.source_clause_text,
                    CustomerCommitment.deleted_at.is_(None),
                )
                .order_by(CustomerCommitment.created_at)
                .limit(2)
            ).scalars().all()
        )
        if len(existing) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Ambiguous duplicate: more than one existing commitment matches this "
                    f"contract reference and clause in organisation {org_id}. Resolve the "
                    "duplicates before re-pushing this obligation."
                ),
            )
        if existing:
            response.status_code = status.HTTP_200_OK
            return CustomerCommitmentRead.model_validate(existing[0], from_attributes=True)

    # No human is on this request, and created_by is NOT NULL FK users.id.
    system_user = ensure_system_account_membership(db, org_id)

    service = CustomerCommitmentService(db)

    # Delegate to core's own creation path -- owner validation, the status
    # machine, and core's own audit entry all happen inside here, so a
    # machine-extracted commitment is created exactly like a human one.
    core_payload = CustomerCommitmentCreate(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        commitment_type=payload.commitment_type,
        title=payload.title,
        description=payload.description,
        trigger_condition=payload.trigger_condition,
        triggering_incident_type=payload.triggering_incident_type,
        trigger_date=None,
        notification_days_before=payload.notification_days_before,
        sla_hours=payload.sla_hours,
        linked_contract_ref=payload.linked_contract_ref,
        assigned_owner_id=payload.assigned_owner_id,
    )
    row = service.create_commitment(org_id, core_payload, system_user.id)

    # Then attach the P9 provenance columns.
    row.obligation_type = payload.obligation_type
    row.extracted_params = payload.extracted_params
    row.confidence_score = Decimal(str(payload.confidence_score))
    row.requires_human_review = payload.requires_human_review
    row.source_clause_text = payload.source_clause_text
    db.flush()

    # A second, P9-specific audit entry: core's own log records that a
    # commitment was created, but not that it was machine-extracted from a
    # contract clause. A compliance reviewer needs to tell the difference and to
    # see the evidence behind the classification.
    AuditService(db).write_audit_log(
        action="customer_commitment.p9_auto_registered",
        entity_type="customer_commitment",
        entity_id=row.id,
        organization_id=org_id,
        actor_user_id=system_user.id,
        after_json={
            "obligation_type": payload.obligation_type,
            "confidence_score": payload.confidence_score,
            "extracted_params": payload.extracted_params,
            "triggering_incident_type": payload.triggering_incident_type,
            "sla_hours": payload.sla_hours,
        },
        metadata_json={
            "source": "p9_contract_extraction_pipeline",
            "upload_id": x_p9_upload_id,
            "classification_engine": "deterministic-rule-based",
            "source_clause_text": payload.source_clause_text[:1000],
        },
    )
    db.commit()

    return CustomerCommitmentRead.model_validate(row, from_attributes=True)
