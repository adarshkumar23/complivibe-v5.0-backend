from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.processing_activity import ProcessingActivity
from app.models.user import User
from app.privacy.schemas.ccpa import CCPAOptOutRequest, CCPAOptOutResponse
from app.privacy.services.consent_service import ConsentService
from app.privacy.services.dsar_service import DSARService

router = APIRouter(prefix="/privacy/ccpa", tags=["privacy-ccpa"])

_PUBLIC_LIMIT_WINDOW = timedelta(minutes=1)
_PUBLIC_LIMIT_COUNT = 10
_PUBLIC_INTAKE_HISTORY: defaultdict[str, deque[datetime]] = defaultdict(deque)


def _check_public_rate_limit(client_ip: str) -> None:
    now = datetime.now(UTC)
    bucket = _PUBLIC_INTAKE_HISTORY[client_ip]
    cutoff = now - _PUBLIC_LIMIT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _PUBLIC_LIMIT_COUNT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    bucket.append(now)


def _resolve_org_by_slug(db: Session, org_slug: str) -> Organization:
    org = db.execute(select(Organization).where(Organization.slug == org_slug, Organization.is_active.is_(True))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


def _resolve_actor_user_id(db: Session, org_id: uuid.UUID) -> uuid.UUID:
    row = db.execute(
        select(User.id)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == org_id,
            Membership.status == "active",
            User.is_active.is_(True),
            User.status == "active",
            # Unauthenticated public intake picks an acting user; it must be a person.
            User.is_system_account.is_(False),
        )
        .order_by(Membership.created_at.asc())
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No active organization user available")
    return row


def _resolve_or_create_ccpa_processing_activity(db: Session, org_id: uuid.UUID, actor_user_id: uuid.UUID) -> ProcessingActivity:
    existing = db.execute(
        select(ProcessingActivity).where(
            ProcessingActivity.organization_id == org_id,
            ProcessingActivity.name == "CCPA Opt-Out Preference Management",
            ProcessingActivity.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    row = ProcessingActivity(
        organization_id=org_id,
        name="CCPA Opt-Out Preference Management",
        description="Consumer opt-out and sensitive PI limitation preferences under CCPA/CPRA.",
        purpose="Record and enforce CCPA consumer preference signals.",
        legal_basis="consent",
        legitimate_interest_justification=None,
        data_categories=["personal_data", "sensitive_personal_data"],
        special_categories=[],
        data_subject_types=["consumers"],
        retention_period="2 years",
        retention_basis=None,
        recipients=["internal"],
        international_transfers=False,
        transfer_destinations=[],
        transfer_safeguards=None,
        controller_name=None,
        controller_contact=None,
        dpo_contact=None,
        status="active",
        risk_level="medium",
        requires_dpia=False,
        linked_dpia_id=None,
        linked_data_asset_ids=[],
        linked_subprocessor_ids=[],
        owner_id=actor_user_id,
        created_by=actor_user_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    db.add(row)
    db.flush()
    return row


@router.post("/opt-out", response_model=CCPAOptOutResponse, status_code=status.HTTP_201_CREATED)
@rate_limiter.limiter.limit("120/minute")
def submit_ccpa_opt_out(
    payload: CCPAOptOutRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> CCPAOptOutResponse:
    client_ip = request.client.host if request.client else "unknown"
    _check_public_rate_limit(client_ip)

    org = _resolve_org_by_slug(db, payload.org_slug)
    actor_user_id = _resolve_actor_user_id(db, org.id)

    dsr_row = DSARService(db).create_request(
        org.id,
        {
            "request_type": "opt_out_of_sale",
            "subject_name": payload.subject_name,
            "subject_email": str(payload.subject_email),
            "description": "Public CCPA opt-out request",
            "regulatory_framework": "ccpa",
            "deadline_days": 15,
        },
        created_by=None,
    )

    activity = _resolve_or_create_ccpa_processing_activity(db, org.id, actor_user_id)
    ConsentService(db).record_consent(
        org.id,
        activity.id,
        {
            "subject_identifier": str(payload.subject_email).lower(),
            "consent_mechanism": "ccpa_opt_out",
            "granted": False,
            "withdrawal_reason": "ccpa_opt_out",
            "metadata": {"source": "public_ccpa_opt_out", "request_ref": dsr_row.request_ref},
        },
        granted=False,
        actor_user_id=None,
    )

    db.commit()
    return CCPAOptOutResponse(
        request_ref=dsr_row.request_ref,
        response_deadline=dsr_row.response_deadline,
        message="Opt-out request received. We will process within 15 business days.",
    )
