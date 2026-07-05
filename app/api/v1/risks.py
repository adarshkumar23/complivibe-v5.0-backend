import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.compliance.services.risk_graph_service import RiskGraphService
from app.compliance.services.risk_scoring_service import RiskScoringService
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.task import Task
from app.models.user import User
from app.repositories.risk_control_link_repository import RiskControlLinkRepository
from app.repositories.risk_evidence_link_repository import RiskEvidenceLinkRepository
from app.repositories.risk_repository import RiskRepository
from app.schemas.risk import (
    RiskAcceptRequest,
    RiskControlLinkCreate,
    RiskControlLinkRead,
    RiskControlSummary,
    RiskCreate,
    RiskDetail,
    RiskEvidenceLinkCreate,
    RiskEvidenceLinkRead,
    RiskEvidenceSummary,
    RiskHeatmap,
    RiskHeatmapCell,
    RiskRead,
    RiskSummary,
    RiskUpdate,
)
from app.schemas.task import RiskTreatmentTaskCreate, TaskRead
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.services.seed_service import SeedService
from app.services.task_service import TaskService

router = APIRouter(prefix="/risks", tags=["risks"])


def _risk_read(risk: Risk) -> RiskRead:
    return RiskRead(
        id=risk.id,
        organization_id=risk.organization_id,
        title=risk.title,
        description=risk.description,
        category=risk.category,
        status=risk.status,
        severity=risk.severity,
        likelihood=risk.likelihood,
        impact=risk.impact,
        inherent_score=risk.inherent_score,
        financial_impact=risk.financial_impact,
        brand_impact=risk.brand_impact,
        operational_impact=risk.operational_impact,
        composite_score_method=risk.composite_score_method,
        residual_likelihood=risk.residual_likelihood,
        residual_impact=risk.residual_impact,
        residual_score=risk.residual_score,
        treatment_strategy=risk.treatment_strategy,
        treatment_option=risk.treatment_option,
        risk_context_internal=risk.risk_context_internal,
        risk_context_external=risk.risk_context_external,
        residual_risk_acceptable=risk.residual_risk_acceptable,
        risk_communication_plan=risk.risk_communication_plan,
        owner_user_id=risk.owner_user_id,
        business_unit_id=risk.business_unit_id,
        target_date=risk.target_date,
        accepted_by_user_id=risk.accepted_by_user_id,
        accepted_at=risk.accepted_at,
        acceptance_reason=risk.acceptance_reason,
        review_due_at=risk.review_due_at,
        metadata_json=risk.metadata_json,
        created_by_user_id=risk.created_by_user_id,
        created_at=risk.created_at,
        updated_at=risk.updated_at,
    )


def _risk_control_link_read(link: RiskControlLink) -> RiskControlLinkRead:
    return RiskControlLinkRead(
        id=link.id,
        organization_id=link.organization_id,
        risk_id=link.risk_id,
        control_id=link.control_id,
        link_type=link.link_type,
        status=link.status,
        rationale=link.rationale,
        linked_by_user_id=link.linked_by_user_id,
        linked_at=link.linked_at,
        unlinked_at=link.unlinked_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _risk_evidence_link_read(link: RiskEvidenceLink) -> RiskEvidenceLinkRead:
    return RiskEvidenceLinkRead(
        id=link.id,
        organization_id=link.organization_id,
        risk_id=link.risk_id,
        evidence_item_id=link.evidence_item_id,
        link_type=link.link_type,
        status=link.status,
        rationale=link.rationale,
        linked_by_user_id=link.linked_by_user_id,
        linked_at=link.linked_at,
        unlinked_at=link.unlinked_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _get_risk_or_404(db: Session, organization_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
    risk = RiskRepository(db).get_by_id(risk_id)
    if risk is None or risk.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    return risk


def _recompute_residual(db: Session, organization_id: uuid.UUID, risk: Risk) -> None:
    """Refresh residual_likelihood/impact/score from currently linked active controls.

    Linking or unlinking a control is a direct trigger, distinct from the control's own
    status changing later (which RiskRecalculationListener handles via the event bus).
    """
    linked_controls = list(
        db.execute(
            select(Control)
            .join(RiskControlLink, RiskControlLink.control_id == Control.id)
            .where(
                RiskControlLink.organization_id == organization_id,
                RiskControlLink.risk_id == risk.id,
                RiskControlLink.status == "active",
            )
        ).scalars().all()
    )
    residual_likelihood, residual_impact, residual_score = RiskScoringService.compute_residual(
        risk, linked_controls, risk.inherent_score
    )
    risk.residual_likelihood = residual_likelihood
    risk.residual_impact = residual_impact
    risk.residual_score = residual_score


def _task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        organization_id=task.organization_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        task_type=task.task_type,
        owner_user_id=task.owner_user_id,
        created_by_user_id=task.created_by_user_id,
        due_date=task.due_date,
        completed_at=task.completed_at,
        completed_by_user_id=task.completed_by_user_id,
        cancelled_at=task.cancelled_at,
        cancelled_by_user_id=task.cancelled_by_user_id,
        linked_entity_type=task.linked_entity_type,
        linked_entity_id=task.linked_entity_id,
        source=task.source,
        reminder_status=task.reminder_status,
        last_reminder_at=task.last_reminder_at,
        metadata_json=task.metadata_json,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _ensure_factor_based_fields(
    *,
    method: str,
    financial_impact: int | None,
    brand_impact: int | None,
    operational_impact: int | None,
) -> None:
    if method != "factor_based":
        return
    if financial_impact is None or brand_impact is None or operational_impact is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Factor-based scoring requires financial_impact, "
                "brand_impact, and operational_impact to be set."
            ),
        )


@router.get("/summary", response_model=RiskSummary)
def risk_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> RiskSummary:
    return RiskSummary(**RiskService(db).summary(organization.id))


@router.get("/heatmap", response_model=RiskHeatmap)
def risk_heatmap(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> RiskHeatmap:
    cells = [RiskHeatmapCell(**cell) for cell in RiskService(db).heatmap(organization.id)]
    return RiskHeatmap(matrix=cells)


@router.get("", response_model=list[RiskRead])
def list_risks(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    business_unit_id: uuid.UUID | None = Query(default=None),
    treatment_strategy: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> list[RiskRead]:
    rows = RiskRepository(db).list_by_organization(
        organization.id,
        status=status,
        category=category,
        severity=severity,
        owner_user_id=owner_user_id,
        business_unit_id=business_unit_id,
        treatment_strategy=treatment_strategy,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [_risk_read(r) for r in rows]


@router.get("/{risk_id}/score-breakdown", response_model=dict)
def get_risk_score_breakdown(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> dict:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    settings = RiskScoringService.get_or_create_org_settings(organization.id, db)
    return RiskScoringService.compute_breakdown(risk, settings)


@router.get("/{risk_id}/graph", response_model=dict)
def get_risk_graph(
    risk_id: uuid.UUID,
    depth: int = Query(default=1, ge=1, le=2),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> dict:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    return RiskGraphService.build(risk_id=risk.id, org_id=organization.id, depth=depth, db=db)


@router.post("", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
def create_risk(
    payload: RiskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskRead:
    service = RiskService(db)
    _ensure_factor_based_fields(
        method=payload.composite_score_method,
        financial_impact=payload.financial_impact,
        brand_impact=payload.brand_impact,
        operational_impact=payload.operational_impact,
    )

    risk = service.create_risk_from_service(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        likelihood=payload.likelihood,
        impact=payload.impact,
        financial_impact=payload.financial_impact,
        brand_impact=payload.brand_impact,
        operational_impact=payload.operational_impact,
        composite_score_method=payload.composite_score_method,
        treatment_strategy=payload.treatment_strategy,
        treatment_option=payload.treatment_option,
        risk_context_internal=payload.risk_context_internal,
        risk_context_external=payload.risk_context_external,
        residual_risk_acceptable=payload.residual_risk_acceptable,
        risk_communication_plan=payload.risk_communication_plan,
        owner_user_id=payload.owner_user_id,
        business_unit_id=payload.business_unit_id,
        target_date=payload.target_date,
        metadata_json=payload.metadata_json,
        created_by_user_id=current_user.id,
        audit_source="api",
        audit_ip_address=request.client.host if request.client else None,
        audit_user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(risk)
    return _risk_read(risk)


@router.get("/{risk_id}", response_model=RiskDetail)
def get_risk_detail(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> RiskDetail:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    control_links = RiskControlLinkRepository(db).list_for_risk(organization.id, risk.id)
    evidence_links = RiskEvidenceLinkRepository(db).list_for_risk(organization.id, risk.id)

    control_ids = [link.control_id for link in control_links]
    evidence_ids = [link.evidence_item_id for link in evidence_links]

    controls: list[Control] = []
    if control_ids:
        controls = db.execute(
            select(Control).where(Control.organization_id == organization.id, Control.id.in_(control_ids))
        ).scalars().all()

    evidence_items: list[EvidenceItem] = []
    if evidence_ids:
        evidence_items = db.execute(
            select(EvidenceItem).where(EvidenceItem.organization_id == organization.id, EvidenceItem.id.in_(evidence_ids))
        ).scalars().all()

    control_map = {c.id: c for c in controls}
    linked_controls = [
        RiskControlSummary(control_id=c.id, title=c.title, status=c.status)
        for link in control_links
        if (c := control_map.get(link.control_id)) is not None
    ]

    evidence_map = {e.id: e for e in evidence_items}
    linked_evidence = [
        RiskEvidenceSummary(
            evidence_item_id=e.id,
            title=e.title,
            review_status=e.review_status,
            freshness_status=e.freshness_status,
        )
        for link in evidence_links
        if (e := evidence_map.get(link.evidence_item_id)) is not None
    ]

    return RiskDetail(**_risk_read(risk).model_dump(), linked_controls=linked_controls, linked_evidence=linked_evidence)


@router.patch("/{risk_id}", response_model=RiskRead)
def update_risk(
    risk_id: uuid.UUID,
    payload: RiskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    service = RiskService(db)

    if payload.owner_user_id is not None:
        service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)
    if "business_unit_id" in payload.model_fields_set:
        service.ensure_business_unit_in_org(organization.id, payload.business_unit_id)

    before = {
        "title": risk.title,
        "description": risk.description,
        "category": risk.category,
        "status": risk.status,
        "severity": risk.severity,
        "likelihood": risk.likelihood,
        "impact": risk.impact,
        "inherent_score": risk.inherent_score,
        "financial_impact": risk.financial_impact,
        "brand_impact": risk.brand_impact,
        "operational_impact": risk.operational_impact,
        "composite_score_method": risk.composite_score_method,
        "residual_likelihood": risk.residual_likelihood,
        "residual_impact": risk.residual_impact,
        "residual_score": risk.residual_score,
        "treatment_strategy": risk.treatment_strategy,
        "treatment_option": risk.treatment_option,
        "risk_context_internal": risk.risk_context_internal,
        "risk_context_external": risk.risk_context_external,
        "residual_risk_acceptable": risk.residual_risk_acceptable,
        "risk_communication_plan": risk.risk_communication_plan,
        "owner_user_id": str(risk.owner_user_id) if risk.owner_user_id else None,
        "business_unit_id": str(risk.business_unit_id) if risk.business_unit_id else None,
    }

    for field in [
        "title",
        "description",
        "category",
        "status",
        "likelihood",
        "impact",
        "financial_impact",
        "brand_impact",
        "operational_impact",
        "composite_score_method",
        "residual_likelihood",
        "residual_impact",
        "treatment_strategy",
        "treatment_option",
        "risk_context_internal",
        "risk_context_external",
        "residual_risk_acceptable",
        "risk_communication_plan",
        "owner_user_id",
        "business_unit_id",
        "target_date",
        "review_due_at",
        "metadata_json",
    ]:
        value = getattr(payload, field)
        if field in payload.model_fields_set:
            setattr(risk, field, value)

    _ensure_factor_based_fields(
        method=risk.composite_score_method or "standard",
        financial_impact=risk.financial_impact,
        brand_impact=risk.brand_impact,
        operational_impact=risk.operational_impact,
    )

    settings = RiskScoringService.get_or_create_org_settings(organization.id, db)
    inherent_score = RiskScoringService.compute_score(risk, settings)
    severity = service.score_to_severity(inherent_score)
    _, _, residual_score = service.calculate_scores(
        likelihood=risk.likelihood,
        impact=risk.impact,
        residual_likelihood=risk.residual_likelihood,
        residual_impact=risk.residual_impact,
    )
    # residual_score is derived from likelihood*impact, which is independent of
    # inherent_score for factor_based risks (a weighted financial/brand/operational
    # formula) -- residual can never exceed inherent risk by definition, so clamp it.
    if residual_score is not None:
        residual_score = min(residual_score, inherent_score)
    risk.inherent_score = inherent_score
    risk.severity = severity
    risk.residual_score = residual_score

    db.flush()

    after = {
        "title": risk.title,
        "status": risk.status,
        "severity": risk.severity,
        "likelihood": risk.likelihood,
        "impact": risk.impact,
        "inherent_score": risk.inherent_score,
        "financial_impact": risk.financial_impact,
        "brand_impact": risk.brand_impact,
        "operational_impact": risk.operational_impact,
        "composite_score_method": risk.composite_score_method,
        "residual_score": risk.residual_score,
        "treatment_strategy": risk.treatment_strategy,
        "treatment_option": risk.treatment_option,
        "risk_context_internal": risk.risk_context_internal,
        "risk_context_external": risk.risk_context_external,
        "residual_risk_acceptable": risk.residual_risk_acceptable,
        "risk_communication_plan": risk.risk_communication_plan,
        "owner_user_id": str(risk.owner_user_id) if risk.owner_user_id else None,
        "business_unit_id": str(risk.business_unit_id) if risk.business_unit_id else None,
    }

    AuditService(db).write_audit_log(
        action="risk.updated",
        entity_type="risk",
        entity_id=risk.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json=after,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if before["composite_score_method"] != risk.composite_score_method:
        AuditService(db).write_audit_log(
            action="risk.score_method_changed",
            entity_type="risk",
            entity_id=risk.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            before_json={
                "composite_score_method": before["composite_score_method"],
                "inherent_score": before["inherent_score"],
            },
            after_json={
                "composite_score_method": risk.composite_score_method,
                "inherent_score": risk.inherent_score,
            },
            metadata_json={
                "source": "api",
                "context_json": {
                    "risk_id": str(risk.id),
                    "previous_method": before["composite_score_method"],
                    "new_method": risk.composite_score_method,
                    "previous_score": before["inherent_score"],
                    "new_score": risk.inherent_score,
                },
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    service.check_appetite_breach(organization_id=organization.id, risk=risk, actor_user_id=current_user.id)

    db.commit()
    db.refresh(risk)
    return _risk_read(risk)


@router.patch("/{risk_id}/archive", response_model=RiskRead)
def archive_risk(
    risk_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    before_status = risk.status
    risk.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="risk.archived",
        entity_type="risk",
        entity_id=risk.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": risk.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(risk)
    return _risk_read(risk)


@router.post("/{risk_id}/controls", response_model=RiskControlLinkRead)
def link_risk_to_control(
    risk_id: uuid.UUID,
    payload: RiskControlLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskControlLinkRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    service = RiskService(db)
    service.require_control_in_org(organization.id, payload.control_id)

    repo = RiskControlLinkRepository(db)
    link = repo.get(organization.id, risk.id, payload.control_id)
    now = datetime.now(UTC)
    if link is None:
        link = RiskControlLink(
            organization_id=organization.id,
            risk_id=risk.id,
            control_id=payload.control_id,
            link_type=payload.link_type,
            status="active",
            rationale=payload.rationale,
            linked_by_user_id=current_user.id,
            linked_at=now,
        )
        db.add(link)
    elif link.status != "active":
        link.status = "active"
        link.link_type = payload.link_type
        link.rationale = payload.rationale
        link.linked_by_user_id = current_user.id
        link.linked_at = now
        link.unlinked_at = None

    db.flush()
    _recompute_residual(db, organization.id, risk)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk.control_linked",
        entity_type="risk_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"risk_id": str(risk.id), "control_id": str(payload.control_id), "status": link.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _risk_control_link_read(link)


@router.delete("/{risk_id}/controls/{control_id}", response_model=RiskControlLinkRead)
def unlink_risk_from_control(
    risk_id: uuid.UUID,
    control_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskControlLinkRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    repo = RiskControlLinkRepository(db)
    link = repo.get(organization.id, risk.id, control_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk-control link not found")

    before = {"status": link.status}
    link.status = "inactive"
    link.unlinked_at = datetime.now(UTC)
    db.flush()
    _recompute_residual(db, organization.id, risk)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk.control_unlinked",
        entity_type="risk_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": link.status, "control_id": str(control_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _risk_control_link_read(link)


@router.post("/{risk_id}/evidence", response_model=RiskEvidenceLinkRead)
def link_risk_to_evidence(
    risk_id: uuid.UUID,
    payload: RiskEvidenceLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskEvidenceLinkRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    service = RiskService(db)
    service.require_evidence_in_org(organization.id, payload.evidence_item_id)

    repo = RiskEvidenceLinkRepository(db)
    link = repo.get(organization.id, risk.id, payload.evidence_item_id)
    now = datetime.now(UTC)
    if link is None:
        link = RiskEvidenceLink(
            organization_id=organization.id,
            risk_id=risk.id,
            evidence_item_id=payload.evidence_item_id,
            link_type=payload.link_type,
            status="active",
            rationale=payload.rationale,
            linked_by_user_id=current_user.id,
            linked_at=now,
        )
        db.add(link)
    elif link.status != "active":
        link.status = "active"
        link.link_type = payload.link_type
        link.rationale = payload.rationale
        link.linked_by_user_id = current_user.id
        link.linked_at = now
        link.unlinked_at = None

    db.flush()

    AuditService(db).write_audit_log(
        action="risk.evidence_linked",
        entity_type="risk_evidence_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"risk_id": str(risk.id), "evidence_item_id": str(payload.evidence_item_id), "status": link.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _risk_evidence_link_read(link)


@router.delete("/{risk_id}/evidence/{evidence_id}", response_model=RiskEvidenceLinkRead)
def unlink_risk_from_evidence(
    risk_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskEvidenceLinkRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    repo = RiskEvidenceLinkRepository(db)
    link = repo.get(organization.id, risk.id, evidence_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk-evidence link not found")

    before = {"status": link.status}
    link.status = "inactive"
    link.unlinked_at = datetime.now(UTC)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk.evidence_unlinked",
        entity_type="risk_evidence_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": link.status, "evidence_item_id": str(evidence_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _risk_evidence_link_read(link)


@router.post("/{risk_id}/accept", response_model=RiskRead)
def accept_risk(
    risk_id: uuid.UUID,
    payload: RiskAcceptRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)

    before = {
        "status": risk.status,
        "treatment_strategy": risk.treatment_strategy,
        "accepted_at": risk.accepted_at.isoformat() if risk.accepted_at else None,
    }

    risk.status = "accepted"
    if risk.treatment_strategy in {None, "undecided", "mitigate", "transfer", "avoid"}:
        risk.treatment_strategy = "accept"
    if risk.treatment_option is None:
        risk.treatment_option = "retain"
    risk.acceptance_reason = payload.acceptance_reason
    risk.accepted_by_user_id = current_user.id
    risk.accepted_at = datetime.now(UTC)
    if payload.review_due_at is not None:
        risk.review_due_at = payload.review_due_at

    db.flush()

    AuditService(db).write_audit_log(
        action="risk.accepted",
        entity_type="risk",
        entity_id=risk.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": risk.status,
            "treatment_strategy": risk.treatment_strategy,
            "accepted_at": risk.accepted_at.isoformat() if risk.accepted_at else None,
            "review_due_at": risk.review_due_at.isoformat() if risk.review_due_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(risk)
    return _risk_read(risk)


@router.post("/{risk_id}/treatment-task", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_risk_treatment_task(
    risk_id: uuid.UUID,
    payload: RiskTreatmentTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
    __: Membership = Depends(require_permission("tasks:write")),
) -> TaskRead:
    risk = _get_risk_or_404(db, organization.id, risk_id)
    task_service = TaskService(db)

    owner_user_id = payload.owner_user_id or risk.owner_user_id
    owner_user = task_service.ensure_owner_is_active_member(organization.id, owner_user_id)

    title = payload.title or f"Risk treatment: {risk.title}"
    task = Task(
        organization_id=organization.id,
        title=title,
        description=payload.description,
        status="open",
        priority=payload.priority,
        task_type="risk_treatment",
        owner_user_id=owner_user_id,
        created_by_user_id=current_user.id,
        due_date=payload.due_date,
        linked_entity_type="risk",
        linked_entity_id=risk.id,
        source="risk_workflow",
        reminder_status="none",
        metadata_json={"risk_id": str(risk.id)},
    )
    db.add(task)
    db.flush()

    outbox_id = None
    if payload.notify_assignee and owner_user is not None:
        SeedService.ensure_global_email_templates(db)
        outbox_id = task_service.queue_task_notification(
            organization_id=organization.id,
            created_by_user_id=current_user.id,
            owner_user=owner_user,
            task_title=task.title,
            template_key="task_assigned",
            event_type="task.assigned",
        )

    AuditService(db).write_audit_log(
        action="risk.treatment_task_created",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "risk_id": str(risk.id),
            "task_type": task.task_type,
            "status": task.status,
            "priority": task.priority,
        },
        metadata_json={"source": "api", "notification_outbox_id": str(outbox_id) if outbox_id else None},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(task)
    return _task_read(task)
