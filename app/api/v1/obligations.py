import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.obligation_content_version import ObligationContentVersion
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.obligation_evidence_requirement import ObligationEvidenceRequirement
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.organization import Organization
from app.models.user import User
from app.schemas.control import ControlRead
from app.schemas.framework import ApplicabilityQuestionRead
from app.schemas.obligation import (
    ObligationContentVersionCreate,
    ObligationContentVersionRead,
    ObligationControlSuggestionCreate,
    ObligationControlSuggestionRead,
    ObligationEvidenceRequirementCreate,
    ObligationEvidenceRequirementRead,
    ObligationRead,
    ObligationStateUpdateRequest,
    OrganizationObligationStateRead,
)
from app.schemas.applicability import (
    APPLICABILITY_CAVEAT,
    ObligationApplicabilityRuleCreate,
    ObligationApplicabilityRuleRead,
    ObligationApplicabilityStatusResponse,
)
from app.repositories.applicability_repository import ApplicabilityRepository
from app.services.applicability_service import ApplicabilityService
from app.services.audit_service import AuditService
from app.services.control_service import ControlService
from app.services.framework_content_service import FrameworkContentService
from app.services.rbac_service import RBACService
from app.services.seed_service import SeedService
from app.data_observability.services.data_obligation_service import DataObligationService
from app.ai_governance.services.semantic_mapping_service import SemanticMappingService

router = APIRouter(prefix="/obligations", tags=["obligations"])
compliance_router = APIRouter(prefix="/compliance/obligations", tags=["obligations"])


def _content_version_read(row: ObligationContentVersion) -> ObligationContentVersionRead:
    return ObligationContentVersionRead(
        id=row.id,
        obligation_id=row.obligation_id,
        version_label=row.version_label,
        obligation_text=row.obligation_text,
        normalized_summary=row.normalized_summary,
        source_reference=row.source_reference,
        source_url=row.source_url,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        coverage_level=row.coverage_level,
        review_status=row.review_status,
        reviewed_by_user_id=row.reviewed_by_user_id,
        reviewed_at=row.reviewed_at,
        superseded_by_version_id=row.superseded_by_version_id,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


def _evidence_requirement_read(row: ObligationEvidenceRequirement) -> ObligationEvidenceRequirementRead:
    return ObligationEvidenceRequirementRead(
        id=row.id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        requirement_key=row.requirement_key,
        title=row.title,
        description=row.description,
        evidence_type=row.evidence_type,
        required=row.required,
        frequency=row.frequency,
        status=row.status,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _control_suggestion_read(row: ObligationControlSuggestion) -> ObligationControlSuggestionRead:
    return ObligationControlSuggestionRead(
        id=row.id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        control_title=row.control_title,
        control_description=row.control_description,
        control_domain=row.control_domain,
        control_type=row.control_type,
        priority=row.priority,
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


def _rule_read(row: ObligationApplicabilityRule) -> ObligationApplicabilityRuleRead:
    return ObligationApplicabilityRuleRead(
        id=row.id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        question_id=row.question_id,
        rule_key=row.rule_key,
        operator=row.operator,
        expected_value_json=row.expected_value_json,
        result_applicability=row.result_applicability,
        rationale=row.rationale,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _ensure_active_org_user(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID | None, field_name: str) -> None:
    if user_id is None:
        return
    row = db.execute(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            User.status == "active",
            Membership.organization_id == organization_id,
            Membership.status == "active",
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be an active member of the organization",
        )


def _build_obligation_read(
    db: Session,
    obligation: Obligation,
    state: OrganizationObligationState | None,
    include_extended: bool = False,
) -> ObligationRead:
    state_schema = None
    if state is not None:
        state_schema = OrganizationObligationStateRead(
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

    framework = None
    section = None
    current_content_version = None
    coverage_level = None
    review_status = None
    evidence_requirements: list[ObligationEvidenceRequirementRead] = []
    control_suggestions: list[ObligationControlSuggestionRead] = []
    applicability_questions: list[ApplicabilityQuestionRead] = []

    if include_extended:
        framework_row = db.execute(select(Framework).where(Framework.id == obligation.framework_id)).scalar_one_or_none()
        if framework_row is not None:
            framework = {
                "id": str(framework_row.id),
                "code": framework_row.code,
                "name": framework_row.name,
                "coverage_level": framework_row.coverage_level,
            }

        if obligation.framework_section_id is not None:
            section_row = db.execute(select(FrameworkSection).where(FrameworkSection.id == obligation.framework_section_id)).scalar_one_or_none()
            if section_row is not None:
                section = {
                    "id": str(section_row.id),
                    "section_code": section_row.section_code,
                    "title": section_row.title,
                }

        latest_content = db.execute(
            select(ObligationContentVersion)
            .where(ObligationContentVersion.obligation_id == obligation.id)
            .order_by(ObligationContentVersion.created_at.desc())
        ).scalars().first()
        if latest_content is not None:
            current_content_version = _content_version_read(latest_content)
            coverage_level = latest_content.coverage_level
            review_status = latest_content.review_status

        evidence_requirements = [
            _evidence_requirement_read(item)
            for item in db.execute(
                select(ObligationEvidenceRequirement)
                .where(ObligationEvidenceRequirement.obligation_id == obligation.id)
                .order_by(ObligationEvidenceRequirement.created_at.asc())
            ).scalars().all()
        ]
        control_suggestions = [
            _control_suggestion_read(item)
            for item in db.execute(
                select(ObligationControlSuggestion)
                .where(ObligationControlSuggestion.obligation_id == obligation.id)
                .order_by(ObligationControlSuggestion.created_at.asc())
            ).scalars().all()
        ]
        applicability_questions = [
            _question_read(item)
            for item in db.execute(
                select(ObligationApplicabilityQuestion)
                .where(
                    ObligationApplicabilityQuestion.framework_id == obligation.framework_id,
                    (ObligationApplicabilityQuestion.obligation_id.is_(None)) | (ObligationApplicabilityQuestion.obligation_id == obligation.id),
                )
                .order_by(ObligationApplicabilityQuestion.sort_order.asc())
            ).scalars().all()
        ]

    return ObligationRead(
        id=obligation.id,
        framework_id=obligation.framework_id,
        framework_section_id=obligation.framework_section_id,
        reference_code=obligation.reference_code,
        title=obligation.title,
        description=obligation.description,
        plain_language_summary=obligation.plain_language_summary,
        obligation_type=obligation.obligation_type,
        jurisdiction=obligation.jurisdiction,
        source_url=obligation.source_url,
        version=obligation.version,
        ig_level=obligation.ig_level,
        status=obligation.status,
        effective_date=obligation.effective_date,
        parent_obligation_id=obligation.parent_obligation_id,
        created_at=obligation.created_at,
        updated_at=obligation.updated_at,
        organization_state=state_schema,
        framework=framework,
        section=section,
        current_content_version=current_content_version,
        coverage_level=coverage_level,
        review_status=review_status,
        evidence_requirements=evidence_requirements,
        control_suggestions=control_suggestions,
        applicability_questions=applicability_questions,
    )


def _control_read(control: Control) -> ControlRead:
    return ControlRead(
        id=control.id,
        organization_id=control.organization_id,
        title=control.title,
        description=control.description,
        control_code=control.control_code,
        control_type=control.control_type,
        status=control.status,
        criticality=control.criticality,
        owner_user_id=control.owner_user_id,
        testing_procedure=control.testing_procedure,
        implementation_notes=control.implementation_notes,
        source=control.source,
        created_by_user_id=control.created_by_user_id,
        created_at=control.created_at,
        updated_at=control.updated_at,
    )


@compliance_router.get("/{obligation_id}/data-assets", response_model=list[dict])
def list_obligation_data_assets(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[dict]:
    return DataObligationService(db).get_obligation_assets(organization.id, obligation_id)


@compliance_router.get("/{obligation_id}/semantic-similar", response_model=list[dict])
def list_semantic_similar_obligations(
    obligation_id: uuid.UUID,
    top_k: int = Query(default=10, ge=1, le=50),
    min_score: float = Query(default=0.70, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[dict]:
    return SemanticMappingService().find_similar_obligations(
        obligation_id=obligation_id,
        db=db,
        top_k=top_k,
        min_score=min_score,
        exclude_same_framework=True,
    )


@compliance_router.get("/{obligation_id}/cross-mappings", response_model=list[dict])
def list_obligation_cross_mappings(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[dict]:
    source = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    obligations = {
        row.id: row
        for row in db.execute(select(Obligation)).scalars().all()
    }
    mappings = db.execute(
        select(CrossFrameworkObligationMapping).where(
            CrossFrameworkObligationMapping.source_obligation_id == obligation_id
        )
    ).scalars().all()
    payload: list[dict] = []
    for mapping in mappings:
        target = obligations.get(mapping.target_obligation_id)
        if target is None:
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


@router.get("/{obligation_id}", response_model=ObligationRead)
def get_obligation_detail(
    obligation_id: uuid.UUID,
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ObligationRead:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()

    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    state: OrganizationObligationState | None = None
    if x_organization_id:
        try:
            organization_id = uuid.UUID(x_organization_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Organization-ID header") from exc

        organization = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
        if organization is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        if not RBACService.user_has_permission(db, current_user.id, organization.id, "frameworks:read"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: frameworks:read")

        state = db.execute(
            select(OrganizationObligationState).where(
                OrganizationObligationState.organization_id == organization.id,
                OrganizationObligationState.obligation_id == obligation.id,
            )
        ).scalar_one_or_none()

    return _build_obligation_read(db, obligation, state, include_extended=True)


@router.post("/{obligation_id}/content-versions", response_model=ObligationContentVersionRead, status_code=status.HTTP_201_CREATED)
def create_obligation_content_version(
    obligation_id: uuid.UUID,
    payload: ObligationContentVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ObligationContentVersionRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    service = FrameworkContentService(db)
    service.validate_coverage_level(payload.coverage_level)
    service.validate_review_status(payload.review_status)

    row = ObligationContentVersion(
        obligation_id=obligation.id,
        version_label=payload.version_label,
        obligation_text=payload.obligation_text,
        normalized_summary=payload.normalized_summary,
        source_reference=payload.source_reference,
        source_url=payload.source_url,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        coverage_level=payload.coverage_level,
        review_status=payload.review_status,
        metadata_json=payload.metadata_json,
        created_at=service.now(),
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="obligation_content_version.created",
        entity_type="obligation_content_version",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"obligation_id": str(obligation.id), "version_label": row.version_label, "coverage_level": row.coverage_level},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _content_version_read(row)


@router.get("/{obligation_id}/content-versions", response_model=list[ObligationContentVersionRead])
def list_obligation_content_versions(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ObligationContentVersionRead]:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    rows = db.execute(
        select(ObligationContentVersion)
        .where(ObligationContentVersion.obligation_id == obligation.id)
        .order_by(ObligationContentVersion.created_at.desc())
    ).scalars().all()
    return [_content_version_read(row) for row in rows]


@router.post("/{obligation_id}/evidence-requirements", response_model=ObligationEvidenceRequirementRead, status_code=status.HTTP_201_CREATED)
def create_obligation_evidence_requirement(
    obligation_id: uuid.UUID,
    payload: ObligationEvidenceRequirementCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ObligationEvidenceRequirementRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    FrameworkContentService.validate_evidence_type(payload.evidence_type)

    row = ObligationEvidenceRequirement(
        framework_id=obligation.framework_id,
        obligation_id=obligation.id,
        requirement_key=payload.requirement_key,
        title=payload.title,
        description=payload.description,
        evidence_type=payload.evidence_type,
        required=payload.required,
        frequency=payload.frequency,
        status=payload.status,
        metadata_json=payload.metadata_json,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="obligation_evidence_requirement.created",
        entity_type="obligation_evidence_requirement",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"obligation_id": str(obligation.id), "requirement_key": row.requirement_key},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _evidence_requirement_read(row)


@router.get("/{obligation_id}/evidence-requirements", response_model=list[ObligationEvidenceRequirementRead])
def list_obligation_evidence_requirements(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ObligationEvidenceRequirementRead]:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    rows = db.execute(
        select(ObligationEvidenceRequirement)
        .where(ObligationEvidenceRequirement.obligation_id == obligation.id)
        .order_by(ObligationEvidenceRequirement.created_at.asc())
    ).scalars().all()
    return [_evidence_requirement_read(row) for row in rows]


@router.post("/{obligation_id}/control-suggestions", response_model=ObligationControlSuggestionRead, status_code=status.HTTP_201_CREATED)
def create_obligation_control_suggestion(
    obligation_id: uuid.UUID,
    payload: ObligationControlSuggestionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ObligationControlSuggestionRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    FrameworkContentService.validate_priority(payload.priority)

    row = ObligationControlSuggestion(
        framework_id=obligation.framework_id,
        obligation_id=obligation.id,
        control_title=payload.control_title,
        control_description=payload.control_description,
        control_domain=payload.control_domain,
        control_type=payload.control_type,
        priority=payload.priority,
        status=payload.status,
        metadata_json=payload.metadata_json,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="obligation_control_suggestion.created",
        entity_type="obligation_control_suggestion",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"obligation_id": str(obligation.id), "control_title": row.control_title},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _control_suggestion_read(row)


@router.get("/{obligation_id}/control-suggestions", response_model=list[ObligationControlSuggestionRead])
def list_obligation_control_suggestions(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ObligationControlSuggestionRead]:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    rows = db.execute(
        select(ObligationControlSuggestion)
        .where(ObligationControlSuggestion.obligation_id == obligation.id)
        .order_by(ObligationControlSuggestion.created_at.asc())
    ).scalars().all()
    return [_control_suggestion_read(row) for row in rows]


@router.post(
    "/{obligation_id}/applicability-rules",
    response_model=ObligationApplicabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_obligation_applicability_rule(
    obligation_id: uuid.UUID,
    payload: ObligationApplicabilityRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ObligationApplicabilityRuleRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    row = ApplicabilityService(db).create_rule(
        framework_id=obligation.framework_id,
        obligation_id=obligation.id,
        question_id=payload.question_id,
        rule_key=payload.rule_key,
        operator=payload.operator,
        expected_value_json=payload.expected_value_json,
        result_applicability=payload.result_applicability,
        rationale=payload.rationale,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="obligation_applicability_rule.created",
        entity_type="obligation_applicability_rule",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={
            "obligation_id": str(obligation.id),
            "question_id": str(row.question_id) if row.question_id else None,
            "operator": row.operator,
            "result_applicability": row.result_applicability,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.get("/{obligation_id}/applicability-rules", response_model=list[ObligationApplicabilityRuleRead])
def list_obligation_applicability_rules(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[ObligationApplicabilityRuleRead]:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    rows = ApplicabilityRepository(db).list_rules_for_obligation(obligation_id=obligation.id, active_only=False)
    return [_rule_read(row) for row in rows]


@router.post("/{obligation_id}/applicability-rules/{rule_id}/archive", response_model=ObligationApplicabilityRuleRead)
def archive_obligation_applicability_rule(
    obligation_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> ObligationApplicabilityRuleRead:
    row = ApplicabilityService(db).archive_rule(obligation_id=obligation_id, rule_id=rule_id)
    AuditService(db).write_audit_log(
        action="obligation_applicability_rule.archived",
        entity_type="obligation_applicability_rule",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor_user_id=current_user.id,
        after_json={"obligation_id": str(obligation_id), "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.get("/{obligation_id}/applicability-status", response_model=ObligationApplicabilityStatusResponse)
def get_obligation_applicability_status(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> ObligationApplicabilityStatusResponse:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    repo = ApplicabilityRepository(db)
    latest = repo.latest_result_for_obligation(
        organization_id=organization.id,
        framework_id=obligation.framework_id,
        obligation_id=obligation.id,
    )
    state = db.execute(
        select(OrganizationObligationState).where(
            OrganizationObligationState.organization_id == organization.id,
            OrganizationObligationState.obligation_id == obligation.id,
        )
    ).scalar_one_or_none()

    return ObligationApplicabilityStatusResponse(
        obligation_id=obligation.id,
        framework_id=obligation.framework_id,
        organization_applicability=state.applicability_status if state else None,
        suggested_applicability=latest.suggested_applicability if latest else None,
        matched_rules_json=latest.matched_rules_json if latest else None,
        missing_answers_json=latest.missing_answers_json if latest else None,
        provenance_json=latest.provenance_json if latest else None,
        caveat=APPLICABILITY_CAVEAT,
    )


@router.post("/{obligation_id}/control-suggestions/{suggestion_id}/apply", response_model=ControlRead)
def apply_control_suggestion(
    obligation_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    org_framework = db.execute(
        select(OrganizationFramework).where(
            OrganizationFramework.organization_id == organization.id,
            OrganizationFramework.framework_id == obligation.framework_id,
            OrganizationFramework.status == "active",
        )
    ).scalar_one_or_none()
    if org_framework is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")

    suggestion = db.execute(select(ObligationControlSuggestion).where(ObligationControlSuggestion.id == suggestion_id)).scalar_one_or_none()
    if suggestion is None or suggestion.obligation_id != obligation.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control suggestion not found")

    existing_control = db.execute(
        select(Control).where(
            Control.organization_id == organization.id,
            Control.suggestion_source_id == suggestion.id,
        )
    ).scalar_one_or_none()

    if existing_control is None:
        criticality = "medium"
        if suggestion.priority == "high":
            criticality = "high"
        elif suggestion.priority == "critical":
            criticality = "critical"

        existing_control = Control(
            organization_id=organization.id,
            obligation_id=obligation.id,
            title=suggestion.control_title,
            description=suggestion.control_description,
            control_type=suggestion.control_type or "process",
            status="not_started",
            criticality=criticality,
            source="system_suggested",
            created_by_user_id=current_user.id,
            suggestion_source_id=suggestion.id,
            implementation_notes=f"Created from obligation control suggestion {suggestion.id}",
        )
        db.add(existing_control)
        db.flush()

    mapping = db.execute(
        select(ControlObligationMapping).where(
            ControlObligationMapping.organization_id == organization.id,
            ControlObligationMapping.control_id == existing_control.id,
            ControlObligationMapping.obligation_id == obligation.id,
        )
    ).scalar_one_or_none()
    if mapping is None:
        mapping = ControlObligationMapping(
            organization_id=organization.id,
            control_id=existing_control.id,
            obligation_id=obligation.id,
            mapping_type="supports",
            confidence="manual_confirmed",
            status="active",
            created_by_user_id=current_user.id,
        )
        db.add(mapping)
    elif mapping.status != "active":
        mapping.status = "active"

    db.flush()

    AuditService(db).write_audit_log(
        action="obligation_control_suggestion.applied",
        entity_type="control",
        entity_id=existing_control.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"obligation_id": str(obligation.id), "suggestion_id": str(suggestion.id), "control_id": str(existing_control.id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(existing_control)
    return _control_read(existing_control)


@router.patch("/{obligation_id}/state", response_model=ObligationRead)
def update_obligation_state(
    obligation_id: uuid.UUID,
    payload: ObligationStateUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
    organization: Organization = Depends(get_current_organization),
) -> ObligationRead:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    org_framework = db.execute(
        select(OrganizationFramework).where(
            OrganizationFramework.organization_id == organization.id,
            OrganizationFramework.framework_id == obligation.framework_id,
            OrganizationFramework.status == "active",
        )
    ).scalar_one_or_none()
    if org_framework is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")

    if payload.applicability_status == "not_applicable" and not (payload.justification and payload.justification.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Justification is required when applicability_status is not_applicable",
        )
    latest_suggestion = ApplicabilityRepository(db).latest_result_for_obligation(
        organization_id=organization.id,
        framework_id=obligation.framework_id,
        obligation_id=obligation.id,
    )
    latest_suggested_applicability = (
        latest_suggestion.suggested_applicability
        if latest_suggestion and latest_suggestion.suggested_applicability in {"applicable", "not_applicable", "needs_review"}
        else None
    )
    overriding_suggestion = (
        latest_suggested_applicability is not None and payload.applicability_status != latest_suggested_applicability
    )
    if overriding_suggestion and not (payload.justification and payload.justification.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Justification is required when overriding latest suggested applicability "
                f"({latest_suggested_applicability})"
            ),
        )
    _ensure_active_org_user(db, organization.id, payload.owner_user_id, "owner_user_id")

    state = db.execute(
        select(OrganizationObligationState).where(
            OrganizationObligationState.organization_id == organization.id,
            OrganizationObligationState.obligation_id == obligation.id,
        )
    ).scalar_one_or_none()

    before_json = None
    if state is None:
        state = OrganizationObligationState(
            organization_id=organization.id,
            obligation_id=obligation.id,
        )
        db.add(state)
    else:
        before_json = {
            "applicability_status": state.applicability_status,
            "implementation_status": state.implementation_status,
            "owner_user_id": str(state.owner_user_id) if state.owner_user_id else None,
            "justification": state.justification,
        }

    state.applicability_status = payload.applicability_status
    state.implementation_status = payload.implementation_status
    state.owner_user_id = payload.owner_user_id
    state.justification = payload.justification

    db.flush()

    AuditService(db).write_audit_log(
        action="obligation.state_updated",
        entity_type="organization_obligation_state",
        entity_id=state.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before_json,
        after_json={
            "obligation_id": str(obligation.id),
            "applicability_status": state.applicability_status,
            "implementation_status": state.implementation_status,
            "owner_user_id": str(state.owner_user_id) if state.owner_user_id else None,
            "justification": state.justification,
            "overrides_latest_suggestion": overriding_suggestion,
            "latest_suggested_applicability": latest_suggested_applicability,
            "latest_suggestion_stale_inputs": int((latest_suggestion.provenance_json or {}).get("stale_input_count", 0))
            if latest_suggestion
            else 0,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return _build_obligation_read(db, obligation, state, include_extended=True)


@router.get("/{obligation_id}/controls", response_model=list[ControlRead])
def list_controls_for_obligation(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlRead]:
    obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

    org_framework = db.execute(
        select(OrganizationFramework).where(
            OrganizationFramework.organization_id == organization.id,
            OrganizationFramework.framework_id == obligation.framework_id,
            OrganizationFramework.status == "active",
        )
    ).scalar_one_or_none()
    if org_framework is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")

    mappings = db.execute(
        select(ControlObligationMapping).where(
            ControlObligationMapping.organization_id == organization.id,
            ControlObligationMapping.obligation_id == obligation.id,
            ControlObligationMapping.status == "active",
        )
    ).scalars().all()

    control_ids = [m.control_id for m in mappings]
    if not control_ids:
        return []

    controls = db.execute(
        select(Control).where(
            Control.organization_id == organization.id,
            Control.id.in_(control_ids),
        )
    ).scalars().all()
    return [_control_read(control) for control in controls]
