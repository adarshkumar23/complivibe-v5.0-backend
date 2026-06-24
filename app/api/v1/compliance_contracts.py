from fastapi import APIRouter, Depends

from app.core.deps import get_current_organization, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.services.compliance_contract_service import ComplianceContractService

router = APIRouter(prefix="/compliance/contracts", tags=["compliance_contracts"])


@router.get("")
def get_compliance_contract_registry(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict:
    _ = organization
    return ComplianceContractService().registry()
