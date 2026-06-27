from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai_governance.schemas.iso42001_nist_rmf import NISTRMFOrgSummaryRead
from app.ai_governance.services.nist_rmf_service import NISTRMFService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/nist-rmf", tags=["ai-governance-nist-rmf"])


@router.get("/org-summary", response_model=NISTRMFOrgSummaryRead)
def get_org_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> NISTRMFOrgSummaryRead:
    payload = NISTRMFService(db).get_org_summary(organization.id)
    return NISTRMFOrgSummaryRead(**payload)
