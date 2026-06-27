import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.ai_vendor_assessment_service import AIVendorAssessmentService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.ai_vendor_assessment import AIVendorAssessment
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.ai_vendor_assessment import (
    AIVendorAssessmentCreate,
    AIVendorAssessmentRead,
    AIVendorAssessmentSummary,
    AIVendorAssessmentUpdate,
)

router = APIRouter(prefix="/compliance/ai-vendor-assessments", tags=["ai-vendor-assessments"])


def _read(row: AIVendorAssessment) -> AIVendorAssessmentRead:
    return AIVendorAssessmentRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        assessor_id=row.assessor_id,
        status=row.status,
        ai_model_name=row.ai_model_name,
        ai_model_version=row.ai_model_version,
        ai_model_provider=row.ai_model_provider,
        model_type=row.model_type,
        training_data_source=row.training_data_source,
        training_data_governance=row.training_data_governance,
        data_exits_environment=row.data_exits_environment,
        data_exits_details=row.data_exits_details,
        bias_testing_performed=row.bias_testing_performed,
        bias_testing_method=row.bias_testing_method,
        bias_testing_frequency=row.bias_testing_frequency,
        explainability_approach=row.explainability_approach,
        human_oversight_required=row.human_oversight_required,
        human_oversight_details=row.human_oversight_details,
        output_used_for_decisions=row.output_used_for_decisions,
        decision_types=row.decision_types,
        regulatory_obligations=row.regulatory_obligations,
        vendor_ai_policy_url=row.vendor_ai_policy_url,
        incident_history=row.incident_history,
        overall_risk_level=row.overall_risk_level,
        risk_score=row.risk_score,
        assessor_notes=row.assessor_notes,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


@router.post("", response_model=AIVendorAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_assessment(
    vendor_id: uuid.UUID,
    payload: AIVendorAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> AIVendorAssessmentRead:
    row = AIVendorAssessmentService(db).create_assessment(organization.id, vendor_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("", response_model=list[AIVendorAssessmentRead])
def list_assessments(
    vendor_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[AIVendorAssessmentRead]:
    rows = AIVendorAssessmentService(db).list_assessments(
        organization.id,
        vendor_id=vendor_id,
        status_value=status_value,
        risk_level=risk_level,
        skip=skip,
        limit=limit,
    )
    return [_read(row) for row in rows]


@router.get("/summary", response_model=AIVendorAssessmentSummary)
def ai_risk_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> AIVendorAssessmentSummary:
    return AIVendorAssessmentSummary(**AIVendorAssessmentService(db).get_ai_risk_summary(organization.id))


@router.get("/{assessment_id}", response_model=AIVendorAssessmentRead)
def get_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> AIVendorAssessmentRead:
    row = AIVendorAssessmentService(db).get_assessment(organization.id, assessment_id)
    return _read(row)


@router.patch("/{assessment_id}", response_model=AIVendorAssessmentRead)
def update_assessment(
    assessment_id: uuid.UUID,
    payload: AIVendorAssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> AIVendorAssessmentRead:
    row = AIVendorAssessmentService(db).update_assessment(organization.id, assessment_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{assessment_id}/complete", response_model=AIVendorAssessmentRead)
def complete_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> AIVendorAssessmentRead:
    row = AIVendorAssessmentService(db).complete_assessment(organization.id, assessment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.delete("/{assessment_id}", response_model=AIVendorAssessmentRead)
def delete_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> AIVendorAssessmentRead:
    row = AIVendorAssessmentService(db).soft_delete_assessment(organization.id, assessment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)
