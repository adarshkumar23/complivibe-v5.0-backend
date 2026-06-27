from fastapi import APIRouter

from app.ai_governance.contracts.ai_contracts import AI_GOVERNANCE_CONTRACTS

router = APIRouter(prefix="/ai-governance", tags=["ai-governance-contracts"])


@router.get("/contracts")
def get_ai_governance_contracts() -> dict:
    return AI_GOVERNANCE_CONTRACTS
