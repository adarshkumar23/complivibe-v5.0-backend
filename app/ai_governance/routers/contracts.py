from fastapi import APIRouter, Depends

from app.ai_governance.contracts.ai_contracts import AI_GOVERNANCE_CONTRACTS
from app.core.deps import get_current_organization, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance", tags=["ai-governance-contracts"])


@router.get("/contracts")
def get_ai_governance_contracts(
    _organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> dict:
    """Describe the AI-governance API surface: endpoint groups and their invariants.

    The payload is a module-level constant and is identical for every tenant, so these
    dependencies are an authorization gate rather than a scoping mechanism. It is gated
    because the manifest enumerates the platform's AI-governance endpoint layout and its
    enforcement invariants -- reconnaissance material that should not be served to an
    unauthenticated caller.
    """
    return AI_GOVERNANCE_CONTRACTS
