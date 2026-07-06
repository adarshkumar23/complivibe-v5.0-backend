from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.rate_limiter import rate_limiter
from app.platform.services.roi_calculator_service import ROICalculatorService
from app.schemas.roi_calculator import ROICalculatorRequest, ROICalculatorResponse

router = APIRouter(prefix="/roi-calculator", tags=["pricing"])


@router.post("", response_model=ROICalculatorResponse)
@rate_limiter.limiter.limit("10/minute")
def calculate_roi(payload: ROICalculatorRequest, request: Request, db: Session = Depends(get_db)) -> ROICalculatorResponse:
    result = ROICalculatorService(db).calculate_and_capture(payload)
    db.commit()
    return ROICalculatorResponse(**result)
