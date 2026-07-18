import uuid

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.policy_derivation import (
    ChainVerificationResponse,
    CheckActionRequest,
    CheckActionResponse,
    DerivedGuardrailCreate,
    DerivedGuardrailRead,
    DerivedGuardrailRecompile,
    ReceiptChainRead,
    ReceiptRead,
)
from app.ai_governance.services.policy_derivation_service import PolicyDerivationService
from app.core.deps import get_current_organization, get_db, require_permission
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/policy-derivation", tags=["ai-governance-policy-derivation"])


@router.post(
    "/ai-systems/{ai_system_id}/guardrails",
    response_model=DerivedGuardrailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_derived_guardrail(
    ai_system_id: uuid.UUID,
    payload: DerivedGuardrailCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_guardrail:create")),
) -> DerivedGuardrailRead:
    row = PolicyDerivationService(db).create_guardrail(
        organization.id,
        ai_system_id,
        name=payload.name,
        description=payload.description,
        obligations=[o.to_record() for o in payload.obligations],
        actor_user_id=membership.user_id,
    )
    db.commit()
    db.refresh(row)
    return DerivedGuardrailRead.model_validate(row)


@router.post("/guardrails/{guardrail_id}/recompile", response_model=DerivedGuardrailRead)
def recompile_derived_guardrail(
    guardrail_id: uuid.UUID,
    payload: DerivedGuardrailRecompile,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_guardrail:recompile")),
) -> DerivedGuardrailRead:
    row = PolicyDerivationService(db).recompile_guardrail(
        organization.id,
        guardrail_id,
        obligations=payload.obligations,
        actor_user_id=membership.user_id,
    )
    db.commit()
    db.refresh(row)
    return DerivedGuardrailRead.model_validate(row)


@router.post("/ai-systems/{ai_system_id}/guardrails/check", response_model=CheckActionResponse)
@rate_limiter.limiter.limit("60/minute")
def check_action(
    ai_system_id: uuid.UUID,
    payload: CheckActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_guardrail:check")),
    x_guardrail_signing_key: str | None = Header(default=None, alias="X-Guardrail-Signing-Key"),
) -> CheckActionResponse:
    event = PolicyDerivationService(db).check_action(
        organization.id,
        ai_system_id,
        raw_action=payload.model_dump(),
        actor_user_id=membership.user_id,
        signing_key_hex=x_guardrail_signing_key,
    )
    db.commit()
    return CheckActionResponse(
        allowed=event.decision == "allow",
        reason=event.reason or "",
        receipt_id=event.receipt_id,
    )


@router.get("/ai-systems/{ai_system_id}/receipt-chain", response_model=ReceiptChainRead)
def get_receipt_chain(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_guardrail:read")),
) -> ReceiptChainRead:
    receipts = PolicyDerivationService(db).get_receipt_chain(organization.id, ai_system_id)
    return ReceiptChainRead(
        ai_system_id=ai_system_id,
        receipts=[ReceiptRead(**r.__dict__) for r in receipts],
    )


@router.post("/ai-systems/{ai_system_id}/verify-chain", response_model=ChainVerificationResponse)
def verify_receipt_chain(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_guardrail:read")),
) -> ChainVerificationResponse:
    result = PolicyDerivationService(db).verify_receipt_chain(organization.id, ai_system_id)
    return ChainVerificationResponse(
        passed=result.passed,
        verified_count=result.verified_count,
        failure_index=result.failure_index,
        failure_reason=result.failure_reason,
    )


@router.get("/sdk-snippet")
def sdk_snippet() -> dict:
    # Customer-facing: generic terms only, zero mention of any third-party
    # toolkit/package name (see PATENT.md branding boundary).
    snippet = '''\
# Integrating your agent framework with the policy enforcement runtime

import httpx

def check_action(action: dict, *, org_id: str, user_id: str, ai_system_id: str) -> dict:
    """Call this before executing an agent action, from within your own
    agent framework's pre-execution hook."""
    response = httpx.post(
        f"https://your-deployment.example.com/api/v1/ai-governance/policy-derivation"
        f"/ai-systems/{ai_system_id}/guardrails/check",
        json=action,
        headers={"X-Organization-ID": org_id, "Authorization": "Bearer <token>"},
        timeout=2.0,
    )
    response.raise_for_status()
    decision = response.json()
    if not decision["allowed"]:
        raise PermissionError(f"action denied: {decision['reason']}")
    return decision
'''
    return {"language": "python", "snippet": snippet}
