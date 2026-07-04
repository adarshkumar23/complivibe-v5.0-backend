import json
from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.framework import Framework
from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.applicability_evaluation_run import ApplicabilityEvaluationRun
from app.models.framework_pack_coverage_report import FrameworkPackCoverageReport
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_content_version import ObligationContentVersion
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.obligation_evidence_requirement import ObligationEvidenceRequirement
from app.models.organization_applicability_answer import OrganizationApplicabilityAnswer
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.user import User
from app.schemas.framework import (
    ApplicabilityQuestionCreate,
    ApplicabilityQuestionRead,
    ContentImportPreviewResponse,
    ContentImportRequest,
    FrameworkActivationRequest,
    FrameworkCoverageGapsResponse,
    FrameworkCoverageReportRead,
    FrameworkCoverageReportRequest,
    FrameworkContentSummary,
    FrameworkDetail,
    FrameworkApplicabilityAssessmentRequest,
    FrameworkApplicabilityAssessmentResponse,
    FrameworkRead,
    FrameworkSectionCreate,
    FrameworkSectionRead,
    FrameworkVersionCreate,
    FrameworkVersionRead,
    OrganizationFrameworkRead,
)
from app.schemas.applicability import (
    ApplicabilityAnswerSubmitRequest,
    ApplicabilityEvaluationResponse,
    ApplicabilityEvaluationResultRead,
    ApplicabilityEvaluationRunDetail,
    ApplicabilityEvaluationRunRead,
    ApplicabilityEvaluateRequest,
    ApplicabilitySummaryResponse,
    OrganizationApplicabilityAnswerRead,
)
from app.schemas.obligation import ObligationRead, OrganizationObligationStateRead
from app.repositories.applicability_repository import ApplicabilityRepository
from app.services.applicability_service import ApplicabilityService
from app.services.audit_service import AuditService
from app.services.framework_content_service import FrameworkContentService
from app.services.framework_content_pack_service import FrameworkContentPackService
from app.services.rbac_service import RBACService
from app.services.seed_service import SeedService
from app.ai_governance.services.semantic_mapping_service import SemanticMappingService

router = APIRouter(prefix="/frameworks", tags=["frameworks"])
compliance_router = APIRouter(prefix="/compliance/frameworks", tags=["frameworks"])
semantic_router = APIRouter(prefix="/compliance/semantic", tags=["frameworks"])


class SemanticDiscoverRequest(BaseModel):
    target_framework_id: uuid.UUID
    min_score: float = Field(default=0.75, ge=0.0, le=1.0)


def _framework_read(framework: Framework) -> FrameworkRead:
    return FrameworkRead(
        id=framework.id,
        code=framework.code,
        name=framework.name,
        description=framework.description,
        category=framework.category,
        jurisdiction=framework.jurisdiction,
        authority=framework.authority,
        version=framework.version,
        status=framework.status,
        coverage_level=framework.coverage_level,
        source_url=framework.source_url,
        effective_date=framework.effective_date,
        created_at=framework.created_at,
        updated_at=framework.updated_at,
    )


def _framework_version_read(row: FrameworkVersion) -> FrameworkVersionRead:
    return FrameworkVersionRead(
        id=row.id,
        framework_id=row.framework_id,
        version_label=row.version_label,
        source_url=row.source_url,
        source_reference=row.source_reference,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        status=row.status,
        coverage_level=row.coverage_level,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _framework_section_read(row: FrameworkSection) -> FrameworkSectionRead:
    return FrameworkSectionRead(
        id=row.id,
        framework_id=row.framework_id,
        framework_version_id=row.framework_version_id,
        parent_section_id=row.parent_section_id,
        section_code=row.section_code,
        title=row.title,
        description=row.description,
        sort_order=row.sort_order,
        status=row.status,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _question_read(row: ObligationApplicabilityQuestion) -> ApplicabilityQuestionRead:
    return ApplicabilityQuestionRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        question_key=row.question_key,
        question_text=row.question_text,
        help_text=row.help_text,
        answer_type=row.answer_type,
        required=row.required,
        sort_order=row.sort_order,
        status=row.status,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _answer_read(row: OrganizationApplicabilityAnswer) -> OrganizationApplicabilityAnswerRead:
    return OrganizationApplicabilityAnswerRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        question_id=row.question_id,
        answer_value_json=row.answer_value_json,
        answer_text=row.answer_text,
        status=row.status,
        answered_by_user_id=row.answered_by_user_id,
        answered_at=row.answered_at,
        superseded_at=row.superseded_at,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_read(row: ApplicabilityEvaluationRun) -> ApplicabilityEvaluationRunRead:
    return ApplicabilityEvaluationRunRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        dry_run=row.dry_run,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        evaluated_obligations_count=row.evaluated_obligations_count,
        applicable_count=row.applicable_count,
        not_applicable_count=row.not_applicable_count,
        needs_review_count=row.needs_review_count,
        unknown_count=row.unknown_count,
        states_updated_count=row.states_updated_count,
        summary_json=row.summary_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _result_read(row: ApplicabilityEvaluationResult) -> ApplicabilityEvaluationResultRead:
    return ApplicabilityEvaluationResultRead(
        id=row.id,
        organization_id=row.organization_id,
        evaluation_run_id=row.evaluation_run_id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        suggested_applicability=row.suggested_applicability,
        previous_applicability=row.previous_applicability,
        state_updated=row.state_updated,
        matched_rules_json=row.matched_rules_json,
        missing_answers_json=row.missing_answers_json,
        rationale=row.rationale,
        provenance_json=row.provenance_json,
        created_at=row.created_at,
    )


def _coverage_report_read(row: FrameworkPackCoverageReport) -> FrameworkCoverageReportRead:
    coverage_percent_estimate = float(row.report_json.get("coverage_percent_estimate", 0.0)) if row.report_json else 0.0
    caveat = (
        row.report_json.get("caveat")
        if row.report_json and isinstance(row.report_json.get("caveat"), str)
        else "Coverage values reflect CompliVibe content metadata only and do not represent legal completeness or regulatory approval."
    )
    return FrameworkCoverageReportRead(
        id=row.id,
        framework_id=row.framework_id,
        framework_version_id=row.framework_version_id,
        pack_key=row.pack_key,
        coverage_level=row.coverage_level,
        review_status=row.review_status,
        total_sections=row.total_sections,
        total_obligations=row.total_obligations,
        obligations_with_content=row.obligations_with_content,
        obligations_with_questions=row.obligations_with_questions,
        obligations_with_evidence_requirements=row.obligations_with_evidence_requirements,
        obligations_with_control_suggestions=row.obligations_with_control_suggestions,
        missing_content_count=row.missing_content_count,
        missing_question_count=row.missing_question_count,
        missing_evidence_requirement_count=row.missing_evidence_requirement_count,
        missing_control_suggestion_count=row.missing_control_suggestion_count,
        coverage_percent_estimate=coverage_percent_estimate,
        report_json=row.report_json,
        generated_at=row.generated_at,
        created_by_user_id=row.created_by_user_id,
        caveat=caveat,
    )


def _organization_framework_read(db: Session, org_framework: OrganizationFramework) -> OrganizationFrameworkRead:
    framework = db.execute(select(Framework).where(Framework.id == org_framework.framework_id)).scalar_one()
    return OrganizationFrameworkRead(
        id=org_framework.id,
        organization_id=org_framework.organization_id,
        framework_id=org_framework.framework_id,
        status=org_framework.status,
        activated_by_user_id=org_framework.activated_by_user_id,
        activated_at=org_framework.activated_at,
        deactivated_by_user_id=org_framework.deactivated_by_user_id,
        deactivated_at=org_framework.deactivated_at,
        notes=org_framework.notes,
        framework=_framework_read(framework),
    )


def _parse_optional_org(
    db: Session,
    current_user: User,
    x_organization_id: str | None,
) -> Organization | None:
    if not x_organization_id:
        return None

    try:
        organization_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Organization-ID header") from exc

    organization = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if not RBACService.user_has_permission(db, current_user.id, organization.id, "frameworks:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: frameworks:read")

    return organization


@router.get("", response_model=list[FrameworkRead])
def list_framework_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> list[FrameworkRead]:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()

    frameworks = db.execute(select(Framework).order_by(Framework.name.asc())).scalars().all()
    return [_framework_read(framework) for framework in frameworks]


@router.get("/active", response_model=list[OrganizationFrameworkRead])
def list_active_organization_frameworks(
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("frameworks:read")),
) -> list[OrganizationFrameworkRead]:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()

    stmt = (
        select(OrganizationFramework)
        .where(
            OrganizationFramework.organization_id == membership.organization_id,
            OrganizationFramework.status == "active",
        )
        .order_by(OrganizationFramework.activated_at.desc())
    )
    org_frameworks = db.execute(stmt).scalars().all()
    return [_organization_framework_read(db, item) for item in org_frameworks]


@router.post("/{framework_id}/activate", response_model=OrganizationFrameworkRead)
def activate_framework(
    framework_id: uuid.UUID,
    payload: FrameworkActivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> OrganizationFrameworkRead:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    framework = db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
    if framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

    stmt = select(OrganizationFramework).where(
        OrganizationFramework.organization_id == membership.organization_id,
        OrganizationFramework.framework_id == framework_id,
    )
    org_framework = db.execute(stmt).scalar_one_or_none()

    now = datetime.now(UTC)
    if org_framework is None:
        org_framework = OrganizationFramework(
            organization_id=membership.organization_id,
            framework_id=framework_id,
            status="active",
            activated_by_user_id=current_user.id,
            activated_at=now,
            notes=payload.notes,
        )
        db.add(org_framework)
    elif org_framework.status != "active":
        org_framework.status = "active"
        org_framework.activated_by_user_id = current_user.id
        org_framework.activated_at = now
        org_framework.deactivated_by_user_id = None
        org_framework.deactivated_at = None
        if payload.notes is not None:
            org_framework.notes = payload.notes

    db.flush()

    AuditService(db).write_audit_log(
        action="framework.activated",
        entity_type="organization_framework",
        entity_id=org_framework.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "status": org_framework.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(org_framework)
    return _organization_framework_read(db, org_framework)


@router.post("/{framework_id}/deactivate", response_model=OrganizationFrameworkRead)
def deactivate_framework(
    framework_id: uuid.UUID,
    payload: FrameworkActivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> OrganizationFrameworkRead:
    stmt = select(OrganizationFramework).where(
        OrganizationFramework.organization_id == membership.organization_id,
        OrganizationFramework.framework_id == framework_id,
    )
    org_framework = db.execute(stmt).scalar_one_or_none()
    if org_framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization framework not found")

    now = datetime.now(UTC)
    org_framework.status = "inactive"
    org_framework.deactivated_by_user_id = current_user.id
    org_framework.deactivated_at = now
    if payload.notes is not None:
        org_framework.notes = payload.notes

    db.flush()

    AuditService(db).write_audit_log(
        action="framework.deactivated",
        entity_type="organization_framework",
        entity_id=org_framework.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        before_json={"status": "active"},
        after_json={"status": "inactive", "framework_id": str(framework_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(org_framework)
    return _organization_framework_read(db, org_framework)


@router.get("/{framework_id}", response_model=FrameworkDetail)
def get_framework_detail(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> FrameworkDetail:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()

    framework = db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
    if framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

    obligation_count = int(db.execute(select(func.count(Obligation.id)).where(Obligation.framework_id == framework.id)).scalar_one())
    active_obligation_count = int(
        db.execute(
            select(func.count(Obligation.id)).where(
                Obligation.framework_id == framework.id,
                Obligation.status == "active",
            )
        ).scalar_one()
    )

    base = _framework_read(framework)
    return FrameworkDetail(**base.model_dump(), obligation_count=obligation_count, active_obligation_count=active_obligation_count)


@router.get("/{framework_id}/versions", response_model=list[FrameworkVersionRead])
def list_framework_versions(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[FrameworkVersionRead]:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    rows = service.list_versions(framework_id)
    return [_framework_version_read(row) for row in rows]


@router.post("/{framework_id}/versions", response_model=FrameworkVersionRead, status_code=status.HTTP_201_CREATED)
def create_framework_version(
    framework_id: uuid.UUID,
    payload: FrameworkVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> FrameworkVersionRead:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    row = service.create_version(
        framework_id=framework_id,
        version_label=payload.version_label,
        source_url=payload.source_url,
        source_reference=payload.source_reference,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        status_value=payload.status,
        coverage_level=payload.coverage_level,
        notes=payload.notes,
    )

    AuditService(db).write_audit_log(
        action="framework_version.created",
        entity_type="framework_version",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "version_label": row.version_label, "coverage_level": row.coverage_level},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _framework_version_read(row)


@router.get("/{framework_id}/sections", response_model=list[FrameworkSectionRead])
def list_framework_sections(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[FrameworkSectionRead]:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    rows = service.list_sections(framework_id)
    return [_framework_section_read(row) for row in rows]


@router.post("/{framework_id}/sections", response_model=FrameworkSectionRead, status_code=status.HTTP_201_CREATED)
def create_framework_section(
    framework_id: uuid.UUID,
    payload: FrameworkSectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> FrameworkSectionRead:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    row = service.create_section(
        framework_id=framework_id,
        framework_version_id=payload.framework_version_id,
        parent_section_id=payload.parent_section_id,
        section_code=payload.section_code,
        title=payload.title,
        description=payload.description,
        sort_order=payload.sort_order,
        status_value=payload.status,
        metadata_json=payload.metadata_json,
    )

    AuditService(db).write_audit_log(
        action="framework_section.created",
        entity_type="framework_section",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "section_code": row.section_code},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _framework_section_read(row)


@router.post("/{framework_id}/applicability-questions", response_model=ApplicabilityQuestionRead, status_code=status.HTTP_201_CREATED)
def create_applicability_question(
    framework_id: uuid.UUID,
    payload: ApplicabilityQuestionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ApplicabilityQuestionRead:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    service.validate_answer_type(payload.answer_type)
    if payload.status not in {"active", "inactive", "archived"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid question status")

    if payload.obligation_id is not None:
        obligation = db.execute(select(Obligation).where(Obligation.id == payload.obligation_id)).scalar_one_or_none()
        if obligation is None or obligation.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid obligation_id")

    row = ObligationApplicabilityQuestion(
        organization_id=None,
        framework_id=framework_id,
        obligation_id=payload.obligation_id,
        question_key=payload.question_key,
        question_text=payload.question_text,
        help_text=payload.help_text,
        answer_type=payload.answer_type,
        required=payload.required,
        sort_order=payload.sort_order,
        status=payload.status,
        metadata_json=payload.metadata_json,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="obligation_applicability_question.created",
        entity_type="obligation_applicability_question",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "obligation_id": str(row.obligation_id) if row.obligation_id else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _question_read(row)


@router.get("/{framework_id}/applicability-questions", response_model=list[ApplicabilityQuestionRead])
def list_applicability_questions(
    framework_id: uuid.UUID,
    obligation_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ApplicabilityQuestionRead]:
    FrameworkContentService(db).require_framework(framework_id)
    stmt = select(ObligationApplicabilityQuestion).where(ObligationApplicabilityQuestion.framework_id == framework_id)
    if obligation_id is not None:
        stmt = stmt.where(ObligationApplicabilityQuestion.obligation_id == obligation_id)
    rows = db.execute(stmt.order_by(ObligationApplicabilityQuestion.sort_order.asc())).scalars().all()
    return [_question_read(row) for row in rows]


@compliance_router.get("/{framework_id}/applicability-questions", response_model=list[ApplicabilityQuestionRead])
def list_applicability_questions_compliance(
    framework_id: uuid.UUID,
    obligation_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ApplicabilityQuestionRead]:
    FrameworkContentService(db).require_framework(framework_id)
    stmt = select(ObligationApplicabilityQuestion).where(ObligationApplicabilityQuestion.framework_id == framework_id)
    if obligation_id is not None:
        stmt = stmt.where(ObligationApplicabilityQuestion.obligation_id == obligation_id)
    rows = db.execute(stmt.order_by(ObligationApplicabilityQuestion.sort_order.asc())).scalars().all()
    return [_question_read(row) for row in rows]


@compliance_router.post("/{framework_id}/assess-applicability", response_model=FrameworkApplicabilityAssessmentResponse)
def assess_framework_applicability(
    framework_id: uuid.UUID,
    payload: FrameworkApplicabilityAssessmentRequest,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> FrameworkApplicabilityAssessmentResponse:
    framework = FrameworkContentService(db).require_framework(framework_id)
    questions = db.execute(
        select(ObligationApplicabilityQuestion).where(
            ObligationApplicabilityQuestion.framework_id == framework_id,
            ObligationApplicabilityQuestion.organization_id.is_(None),
            ObligationApplicabilityQuestion.status == "active",
        )
    ).scalars().all()
    active_obligations = db.execute(
        select(Obligation).where(
            Obligation.framework_id == framework_id,
            Obligation.status == "active",
        ).order_by(Obligation.reference_code.asc())
    ).scalars().all()
    section_by_id = {
        row.id: row.section_code
        for row in db.execute(select(FrameworkSection).where(FrameworkSection.framework_id == framework_id)).scalars().all()
    }

    applies = True
    ig_scope = None
    nist_impact_scope = None
    pii_role = None
    for question in questions:
        answer = payload.answers.get(question.question_key)
        if answer is None:
            continue
        triggers_scope = (question.metadata_json or {}).get("triggers_scope", "all")
        if question.question_key == "implementation_group" and isinstance(answer, str):
            candidate = answer.strip().upper()
            if candidate in {"IG1", "IG2", "IG3"}:
                ig_scope = candidate
                continue
        if question.question_key == "impact_level" and isinstance(answer, str):
            candidate = answer.strip().upper()
            if candidate in {"LOW", "MODERATE", "HIGH"}:
                nist_impact_scope = candidate
                continue
        if question.question_key == "pii_role" and isinstance(answer, str):
            candidate = answer.strip().lower()
            if candidate in {"controller", "processor", "both"}:
                pii_role = candidate
                continue
        if triggers_scope == "all" and isinstance(answer, bool) and answer is False:
            applies = False
            break
    obligations_payload: list[dict] = []
    if applies:
        filtered = list(active_obligations)
        if framework.name == "CIS Controls" and ig_scope is not None:
            if ig_scope == "IG1":
                filtered = [row for row in filtered if row.ig_level == "IG1"]
            elif ig_scope == "IG2":
                filtered = [row for row in filtered if row.ig_level in {"IG1", "IG2"}]
        if framework.name == "NIST SP 800-53" and nist_impact_scope is not None:
            if nist_impact_scope == "LOW":
                filtered = [row for row in filtered if row.baseline == "LOW"]
            else:
                scoped: list[Obligation] = []
                for row in filtered:
                    baselines: list[str] = []
                    if row.embedding_json:
                        try:
                            payload = json.loads(row.embedding_json)
                            raw_baselines = payload.get("fedramp_rev4_baselines", [])
                            if isinstance(raw_baselines, list):
                                baselines = [str(item).upper() for item in raw_baselines]
                        except (TypeError, ValueError, json.JSONDecodeError):
                            baselines = []
                    if nist_impact_scope in baselines:
                        scoped.append(row)
                filtered = scoped
        if framework.name == "ISO 27701" and pii_role is not None:
            if pii_role == "controller":
                filtered = [row for row in filtered if row.reference_code.startswith("27701-7.")]
            elif pii_role == "processor":
                filtered = [row for row in filtered if row.reference_code.startswith("27701-8.")]
        obligations_payload = [
            {
                "id": str(item.id),
                "reference_code": item.reference_code,
                "title": item.title,
                "section_code": section_by_id.get(item.framework_section_id),
            }
            for item in filtered
        ]
    return FrameworkApplicabilityAssessmentResponse(
        framework_id=framework_id,
        applicable_obligation_count=len(obligations_payload),
        obligations=obligations_payload,
    )


@compliance_router.get("/{framework_id}/cross-mappings", response_model=list[dict])
def list_framework_cross_mappings(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[dict]:
    FrameworkContentService(db).require_framework(framework_id)
    mappings = db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    obligations = {
        row.id: row
        for row in db.execute(select(Obligation)).scalars().all()
    }
    payload: list[dict] = []
    for mapping in mappings:
        source = obligations.get(mapping.source_obligation_id)
        target = obligations.get(mapping.target_obligation_id)
        if source is None or target is None:
            continue
        if source.framework_id != framework_id:
            continue
        payload.append(
            {
                "id": str(mapping.id),
                "source_obligation_id": str(mapping.source_obligation_id),
                "source_reference_code": source.reference_code,
                "target_obligation_id": str(mapping.target_obligation_id),
                "target_reference_code": target.reference_code,
                "mapping_type": mapping.mapping_type,
                "notes": mapping.notes,
            }
        )
    return payload


@router.post("/{framework_id}/applicability-answers", response_model=list[OrganizationApplicabilityAnswerRead], status_code=status.HTTP_201_CREATED)
def submit_applicability_answers(
    framework_id: uuid.UUID,
    payload: ApplicabilityAnswerSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
    organization: Organization = Depends(get_current_organization),
) -> list[OrganizationApplicabilityAnswerRead]:
    service = ApplicabilityService(db)
    rows = service.submit_answers(
        organization_id=organization.id,
        framework_id=framework_id,
        answers=[item.model_dump() for item in payload.answers],
        actor_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="applicability_answer.submitted",
        entity_type="organization_applicability_answer",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "answer_count": len(rows)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return [_answer_read(row) for row in rows]


@router.get("/{framework_id}/applicability-answers", response_model=list[OrganizationApplicabilityAnswerRead])
def list_applicability_answers(
    framework_id: uuid.UUID,
    active_only: bool = Query(default=True),
    question_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[OrganizationApplicabilityAnswerRead]:
    ApplicabilityService(db).ensure_framework_active_for_org(organization_id=organization.id, framework_id=framework_id)
    rows = ApplicabilityRepository(db).list_answers(
        organization_id=organization.id,
        framework_id=framework_id,
        active_only=active_only,
        question_id=question_id,
    )
    return [_answer_read(row) for row in rows]


@router.post("/{framework_id}/applicability/evaluate", response_model=ApplicabilityEvaluationResponse)
def evaluate_framework_applicability(
    framework_id: uuid.UUID,
    payload: ApplicabilityEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> ApplicabilityEvaluationResponse:
    if payload.update_obligation_states and payload.dry_run:
        payload.update_obligation_states = False
    if payload.update_obligation_states and not RBACService.user_has_permission(db, current_user.id, organization.id, "frameworks:activate"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: frameworks:activate")

    run_row, results_payload, summary = ApplicabilityService(db).evaluate_framework(
        organization_id=organization.id,
        framework_id=framework_id,
        actor_user_id=current_user.id,
        dry_run=payload.dry_run,
        update_obligation_states=payload.update_obligation_states,
    )

    AuditService(db).write_audit_log(
        action="applicability_evaluation.completed",
        entity_type="applicability_evaluation_run",
        entity_id=run_row.id if run_row else None,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "dry_run": payload.dry_run, "summary": summary},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    run_schema = _run_read(run_row) if run_row else None
    results_schema = [ApplicabilityEvaluationResultRead(**item) for item in results_payload]
    return ApplicabilityEvaluationResponse(run=run_schema, results=results_schema, dry_run=payload.dry_run)


@router.get("/{framework_id}/applicability/evaluations", response_model=list[ApplicabilityEvaluationRunRead])
def list_applicability_evaluation_runs(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ApplicabilityEvaluationRunRead]:
    rows = ApplicabilityRepository(db).list_runs(organization_id=organization.id, framework_id=framework_id)
    return [_run_read(row) for row in rows]


@router.get("/{framework_id}/applicability/evaluations/{run_id}", response_model=ApplicabilityEvaluationRunDetail)
def get_applicability_evaluation_run_detail(
    framework_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> ApplicabilityEvaluationRunDetail:
    repo = ApplicabilityRepository(db)
    run = repo.get_run(run_id)
    if run is None or run.organization_id != organization.id or run.framework_id != framework_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applicability evaluation run not found")
    results = repo.list_results_for_run(organization_id=organization.id, run_id=run.id)
    return ApplicabilityEvaluationRunDetail(run=_run_read(run), results=[_result_read(row) for row in results])


@router.get("/{framework_id}/applicability/summary", response_model=ApplicabilitySummaryResponse)
def applicability_summary(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> ApplicabilitySummaryResponse:
    summary = ApplicabilityService(db).evaluation_summary(organization_id=organization.id, framework_id=framework_id)
    return ApplicabilitySummaryResponse(**summary)


@router.get("/{framework_id}/content-summary", response_model=FrameworkContentSummary)
def framework_content_summary(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> FrameworkContentSummary:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    return FrameworkContentSummary(**service.content_summary(framework_id))


@router.post("/{framework_id}/coverage-report", response_model=FrameworkCoverageReportRead)
def generate_framework_coverage_report(
    framework_id: uuid.UUID,
    payload: FrameworkCoverageReportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:read")),
) -> FrameworkCoverageReportRead:
    pack_service = FrameworkContentPackService(db)
    FrameworkContentService(db).require_framework(framework_id)
    details = pack_service.coverage_details(framework_id)

    if payload.persist:
        report_row = pack_service.create_coverage_report(framework_id=framework_id, actor_user_id=current_user.id)
        AuditService(db).write_audit_log(
            action="framework_coverage_report.generated",
            entity_type="framework_pack_coverage_report",
            entity_id=report_row.id,
            organization_id=membership.organization_id,
            actor_user_id=current_user.id,
            after_json={"framework_id": str(framework_id), "coverage_percent_estimate": details["coverage_percent_estimate"]},
            metadata_json={"source": "api", "persist": True},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        db.refresh(report_row)
        return _coverage_report_read(report_row)

    return FrameworkCoverageReportRead(
        id=None,
        framework_id=framework_id,
        framework_version_id=details["framework_version_id"],
        pack_key=details["pack_key"],
        coverage_level=details["coverage_level"],
        review_status=details["review_status"],
        total_sections=details["total_sections"],
        total_obligations=details["total_obligations"],
        obligations_with_content=details["obligations_with_content"],
        obligations_with_questions=details["obligations_with_questions"],
        obligations_with_evidence_requirements=details["obligations_with_evidence_requirements"],
        obligations_with_control_suggestions=details["obligations_with_control_suggestions"],
        missing_content_count=details["missing_content_count"],
        missing_question_count=details["missing_question_count"],
        missing_evidence_requirement_count=details["missing_evidence_requirement_count"],
        missing_control_suggestion_count=details["missing_control_suggestion_count"],
        coverage_percent_estimate=details["coverage_percent_estimate"],
        report_json={
            "gaps": {
                "obligations_missing_content": details["obligations_missing_content"],
                "obligations_missing_applicability_questions": details["obligations_missing_applicability_questions"],
                "obligations_missing_evidence_requirements": details["obligations_missing_evidence_requirements"],
                "obligations_missing_control_suggestions": details["obligations_missing_control_suggestions"],
                "sections_without_obligations": details["sections_without_obligations"],
                "obligations_without_sections": details["obligations_without_sections"],
            },
            "coverage_percent_estimate": details["coverage_percent_estimate"],
            "caveat": details["caveat"],
        },
        generated_at=details["generated_at"],
        created_by_user_id=current_user.id,
        caveat=details["caveat"],
    )


@router.get("/{framework_id}/coverage-reports", response_model=list[FrameworkCoverageReportRead])
def list_framework_coverage_reports(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[FrameworkCoverageReportRead]:
    FrameworkContentService(db).require_framework(framework_id)
    rows = FrameworkContentPackService(db).list_coverage_reports(framework_id)
    return [_coverage_report_read(row) for row in rows]


@router.get("/{framework_id}/coverage-gaps", response_model=FrameworkCoverageGapsResponse)
def framework_coverage_gaps(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> FrameworkCoverageGapsResponse:
    FrameworkContentService(db).require_framework(framework_id)
    details = FrameworkContentPackService(db).coverage_details(framework_id)
    return FrameworkCoverageGapsResponse(
        framework_id=framework_id,
        obligations_missing_content=details["obligations_missing_content"],
        obligations_missing_applicability_questions=details["obligations_missing_applicability_questions"],
        obligations_missing_evidence_requirements=details["obligations_missing_evidence_requirements"],
        obligations_missing_control_suggestions=details["obligations_missing_control_suggestions"],
        sections_without_obligations=details["sections_without_obligations"],
        obligations_without_sections=details["obligations_without_sections"],
        caveat=details["caveat"],
    )


@router.post("/{framework_id}/content-imports/preview", response_model=ContentImportPreviewResponse)
def framework_content_import_preview(
    framework_id: uuid.UUID,
    payload: ContentImportRequest,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:activate")),
) -> ContentImportPreviewResponse:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    service.validate_coverage_level(payload.coverage_level)
    counts, errors = service.validate_import_payload(framework_id=framework_id, payload_json=payload.payload_json)
    return ContentImportPreviewResponse(valid=len(errors) == 0, counts=counts, validation_errors=errors)


@router.post("/{framework_id}/content-imports/apply", response_model=ContentImportPreviewResponse)
def framework_content_import_apply(
    framework_id: uuid.UUID,
    payload: ContentImportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ContentImportPreviewResponse:
    service = FrameworkContentService(db)
    service.require_framework(framework_id)
    service.validate_coverage_level(payload.coverage_level)

    counts, errors = service.validate_import_payload(framework_id=framework_id, payload_json=payload.payload_json)
    if errors:
        return ContentImportPreviewResponse(valid=False, counts=counts, validation_errors=errors)

    import_row = service.apply_import(
        framework_id=framework_id,
        organization_id=membership.organization_id,
        import_type=payload.import_type,
        coverage_level=payload.coverage_level,
        source_name=payload.source_name,
        source_reference=payload.source_reference,
        payload_json=payload.payload_json,
        imported_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="framework_content_import.applied",
        entity_type="framework_content_import",
        entity_id=import_row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "import_type": payload.import_type, "counts": counts},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return ContentImportPreviewResponse(valid=True, counts=counts, validation_errors=[])


@router.get("/{framework_id}/obligations", response_model=list[ObligationRead])
def list_framework_obligations(
    framework_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    jurisdiction: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ObligationRead]:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()

    framework = db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
    if framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

    organization = _parse_optional_org(db, current_user, x_organization_id)

    stmt = select(Obligation).where(Obligation.framework_id == framework_id)
    if status_filter:
        stmt = stmt.where(Obligation.status == status_filter)
    if jurisdiction:
        stmt = stmt.where(Obligation.jurisdiction == jurisdiction)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Obligation.title.ilike(like), Obligation.reference_code.ilike(like), Obligation.description.ilike(like)))

    stmt = stmt.order_by(Obligation.reference_code.asc()).offset(offset).limit(limit)
    obligations = db.execute(stmt).scalars().all()

    state_map: dict[uuid.UUID, OrganizationObligationState] = {}
    if organization is not None and obligations:
        state_stmt = select(OrganizationObligationState).where(
            OrganizationObligationState.organization_id == organization.id,
            OrganizationObligationState.obligation_id.in_([item.id for item in obligations]),
        )
        state_rows = db.execute(state_stmt).scalars().all()
        state_map = {row.obligation_id: row for row in state_rows}

    response: list[ObligationRead] = []
    for item in obligations:
        row = ObligationRead(
            id=item.id,
            framework_id=item.framework_id,
            framework_section_id=item.framework_section_id,
            reference_code=item.reference_code,
            title=item.title,
            description=item.description,
            plain_language_summary=item.plain_language_summary,
            obligation_type=item.obligation_type,
            jurisdiction=item.jurisdiction,
            source_url=item.source_url,
            version=item.version,
            status=item.status,
            effective_date=item.effective_date,
            parent_obligation_id=item.parent_obligation_id,
            created_at=item.created_at,
            updated_at=item.updated_at,
            organization_state=None,
        )
        state = state_map.get(item.id)
        if state is not None:
            row.organization_state = OrganizationObligationStateRead(
                id=state.id,
                organization_id=state.organization_id,
                obligation_id=state.obligation_id,
                applicability_status=state.applicability_status,
                implementation_status=state.implementation_status,
                owner_user_id=state.owner_user_id,
                justification=state.justification,
                created_at=state.created_at,
                updated_at=state.updated_at,
            )
        response.append(row)

    return response


@compliance_router.post("/{source_framework_id}/discover-mappings")
def discover_semantic_mappings(
    source_framework_id: uuid.UUID,
    payload: SemanticDiscoverRequest,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:write")),
) -> dict[str, object]:
    source_exists = db.execute(select(Framework).where(Framework.id == source_framework_id)).scalar_one_or_none()
    if source_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source framework not found")

    target_exists = db.execute(select(Framework).where(Framework.id == payload.target_framework_id)).scalar_one_or_none()
    if target_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target framework not found")

    result = SemanticMappingService().auto_discover_mappings(
        source_framework_id=source_framework_id,
        target_framework_id=payload.target_framework_id,
        db=db,
        min_score=payload.min_score,
        mapping_type_label="semantic",
    )
    db.commit()
    return result


@compliance_router.post("/{framework_id}/embed")
def embed_framework_obligations(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:write")),
) -> dict[str, object]:
    framework = db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
    if framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

    result = SemanticMappingService().batch_embed_framework(framework_id=framework_id, db=db)
    db.commit()
    return result


@semantic_router.get("/status")
def get_semantic_status(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict[str, object]:
    status_payload = SemanticMappingService().status(db)
    return {
        "pgvector_available": status_payload.pgvector_available,
        "embedding_model": status_payload.embedding_model,
        "total_embedded": status_payload.total_embedded,
        "total_obligations": status_payload.total_obligations,
        "coverage_pct": status_payload.coverage_pct,
    }
