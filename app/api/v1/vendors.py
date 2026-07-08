import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.ai_governance.schemas.third_party_model_card_aibom import (
    ThirdPartyAIAssessmentCreate,
    ThirdPartyAIAssessmentRead,
)
from app.ai_governance.services.third_party_ai_service import ThirdPartyAIService
from app.models.vendor_control_link import VendorControlLink
from app.models.vendor_risk_score import VendorRiskScore
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_assessment_question import VendorAssessmentQuestion
from app.schemas.vendor_assessment import (
    VendorAssessmentCancelRequest,
    VendorAssessmentCompleteRequest,
    VendorAssessmentCreate,
    VendorAssessmentQuestionAnswerRequest,
    VendorAssessmentQuestionCreate,
    VendorAssessmentQuestionRead,
    VendorAssessmentQuestionUpdate,
    VendorAssessmentRead,
    VendorAssessmentSummary,
    VendorAssessmentUpdate,
)
from app.schemas.vendor_risk import (
    VendorControlLinkCreate,
    VendorControlLinkRead,
    VendorControlUnlinkRequest,
    VendorLinksSummary,
    VendorRiskScoreCreate,
    VendorRiskScoreRead,
)
from app.schemas.vendor_criticality import (
    VendorCriticalityProfileRead,
    VendorCriticalityProfileUpdate,
    VendorCriticalitySettingRead,
    VendorCriticalitySettingUpdate,
)
from app.services.vendor_criticality_service import VendorCriticalityService
from app.services.vendor_risk_service import VendorRiskService
from app.schemas.vendor import VendorArchiveRequest, VendorCreate, VendorRead, VendorSummary, VendorUpdate
from app.services.vendor_assessment_service import VendorAssessmentService
from app.services.audit_service import AuditService
from app.services.vendor_concentration_risk_service import VendorConcentrationRiskService
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/compliance/vendors", tags=["vendors"])


def _refresh_concentration_risk(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    trigger: str,
) -> None:
    """Keep T1-6 concentration detection current when a vendor's criticality or
    status changes (T1-4). No-ops for organizations that have never opted into
    concentration monitoring (no detection row yet).
    """
    outcome = VendorConcentrationRiskService(db).recompute_if_tracked(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    if outcome is None:
        return
    detection, risk_created, state_changed = outcome
    if not state_changed:
        return
    AuditService(db).write_audit_log(
        action="vendor_concentration_risk.recomputed",
        entity_type="vendor_concentration_risk_detection",
        entity_id=detection.id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        after_json={
            "status": detection.status,
            "hhi_score": detection.hhi_score,
            "risk_id": str(detection.risk_id) if detection.risk_id else None,
        },
        metadata_json={"source": trigger, "risk_created": risk_created},
    )


def _vendor_read(row: Vendor, *, has_overdue_assessment: bool = False) -> VendorRead:
    return VendorRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        vendor_type=row.vendor_type,
        website=row.website,
        primary_contact_name=row.primary_contact_name,
        primary_contact_email=row.primary_contact_email,
        risk_tier=row.risk_tier,
        status=row.status,
        owner_user_id=row.owner_user_id,
        data_access=row.data_access,
        processes_personal_data=row.processes_personal_data,
        sub_processor=row.sub_processor,
        nth_party_risk_flag=row.nth_party_risk_flag,
        nth_party_risk_severity=row.nth_party_risk_severity,
        nth_party_risk_signal_type=row.nth_party_risk_signal_type,
        nth_party_risk_updated_at=row.nth_party_risk_updated_at,
        tags_json=row.tags_json,
        notes=row.notes,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        archive_reason=row.archive_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        has_overdue_assessment=has_overdue_assessment,
    )


def _assessment_read(row: VendorAssessment) -> VendorAssessmentRead:
    return VendorAssessmentRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        title=row.title,
        assessment_type=row.assessment_type,
        status=row.status,
        assigned_to_user_id=row.assigned_to_user_id,
        due_date=row.due_date,
        started_at=row.started_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        cancellation_reason=row.cancellation_reason,
        findings_summary=row.findings_summary,
        overall_rating=row.overall_rating,
        notes=row.notes,
        tags_json=row.tags_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_overdue=VendorAssessmentService.is_overdue(row),
        risk_id=row.risk_id,
    )


def _assessment_question_read(row: VendorAssessmentQuestion) -> VendorAssessmentQuestionRead:
    return VendorAssessmentQuestionRead(
        id=row.id,
        organization_id=row.organization_id,
        assessment_id=row.assessment_id,
        question_text=row.question_text,
        question_category=row.question_category,
        response_text=row.response_text,
        response_status=row.response_status,
        answered_by_user_id=row.answered_by_user_id,
        answered_at=row.answered_at,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_score_read(row: VendorRiskScore, vendor: Vendor | None = None) -> VendorRiskScoreRead:
    recalculated_since_update = False
    stale_reason: str | None = None
    if vendor is not None:
        if vendor.nth_party_risk_updated_at is not None and vendor.nth_party_risk_updated_at > row.created_at:
            recalculated_since_update = True
            stale_reason = (
                "Vendor's nth-party risk signal changed "
                f"({vendor.nth_party_risk_severity or 'unspecified'} severity) after this score was computed"
            )
        elif vendor.risk_tier != row.risk_level:
            # The vendor's cached tier no longer matches this score's own risk_level,
            # meaning a later score (or a sanctions/questionnaire-driven escalation)
            # has already superseded this one.
            recalculated_since_update = True
            stale_reason = (
                f"Vendor's current risk_tier ('{vendor.risk_tier}') no longer matches this "
                f"score's risk_level ('{row.risk_level}'); a newer signal has superseded it"
            )
    return VendorRiskScoreRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        assessment_id=row.assessment_id,
        likelihood=row.likelihood,
        impact=row.impact,
        inherent_risk_score=row.inherent_risk_score,
        risk_level=row.risk_level,
        score_explanation_json=row.score_explanation_json,
        scored_by_user_id=row.scored_by_user_id,
        notes=row.notes,
        created_at=row.created_at,
        recalculated_since_update=recalculated_since_update,
        stale_reason=stale_reason,
    )


def _vendor_control_link_read(row: VendorControlLink) -> VendorControlLinkRead:
    return VendorControlLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        control_id=row.control_id,
        link_reason=row.link_reason,
        status=row.status,
        linked_by_user_id=row.linked_by_user_id,
        unlinked_at=row.unlinked_at,
        unlinked_by_user_id=row.unlinked_by_user_id,
        unlink_reason=row.unlink_reason,
        created_at=row.created_at,
    )


def _vendor_criticality_setting_read(row, organization_id: uuid.UUID) -> VendorCriticalitySettingRead:
    if row is None:
        return VendorCriticalitySettingRead(
            id=None,
            organization_id=organization_id,
            is_default=True,
        )
    return VendorCriticalitySettingRead(
        id=row.id,
        organization_id=row.organization_id,
        revenue_dependency_weight=row.revenue_dependency_weight,
        data_volume_weight=row.data_volume_weight,
        operational_criticality_weight=row.operational_criticality_weight,
        substitutability_weight=row.substitutability_weight,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_default=False,
    )


def _vendor_criticality_profile_read(row, payload: dict | None = None, priority_context: dict | None = None) -> VendorCriticalityProfileRead:
    if payload is not None:
        return VendorCriticalityProfileRead(**payload)
    staleness = VendorCriticalityService.staleness_context(row.updated_at)
    context_flags: list[str] = []
    if staleness["is_stale"]:
        context_flags.append("profile_stale")
    return VendorCriticalityProfileRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        revenue_dependency_pct=row.revenue_dependency_pct,
        data_volume_tier=row.data_volume_tier,
        operational_criticality=row.operational_criticality,
        substitutability_score=row.substitutability_score,
        criticality_score=row.criticality_score,
        criticality_tier=row.criticality_tier,
        score_explanation_json=row.score_explanation_json,
        priority_context=priority_context or {},
        notes=row.notes,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_default=False,
        profile_age_days=staleness["profile_age_days"],
        is_stale=staleness["is_stale"],
        stale_after_days=staleness["stale_after_days"],
        context_flags=context_flags,
    )


def _third_party_ai_assessment_read(row) -> ThirdPartyAIAssessmentRead:
    return ThirdPartyAIAssessmentRead.model_validate(row)


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
def create_vendor(
    payload: VendorCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorRead:
    service = VendorService(db)
    service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)
    service.ensure_unique_vendor_name(organization.id, payload.name)

    if payload.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New vendors cannot start in archived status")

    row = Vendor(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        vendor_type=payload.vendor_type,
        website=payload.website,
        primary_contact_name=payload.primary_contact_name,
        primary_contact_email=str(payload.primary_contact_email) if payload.primary_contact_email else None,
        risk_tier=payload.risk_tier,
        status=payload.status,
        owner_user_id=payload.owner_user_id,
        data_access=payload.data_access,
        processes_personal_data=payload.processes_personal_data,
        sub_processor=payload.sub_processor,
        tags_json=payload.tags_json,
        notes=payload.notes,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.created",
        entity_type="vendor",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "vendor_type": row.vendor_type,
            "risk_tier": row.risk_tier,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if row.risk_tier in ("critical", "high") and row.status == "active":
        _refresh_concentration_risk(
            db,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            trigger="vendor.created",
        )

    db.commit()
    db.refresh(row)
    return _vendor_read(row)


@router.get("/summary", response_model=VendorSummary)
def vendors_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorSummary:
    return VendorSummary(**VendorService(db).summary(organization.id))


@router.get("/criticality/settings", response_model=VendorCriticalitySettingRead)
def get_vendor_criticality_settings(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_criticality:read")),
) -> VendorCriticalitySettingRead:
    row = VendorCriticalityService(db).get_settings(organization.id)
    return _vendor_criticality_setting_read(row, organization.id)


@router.put("/criticality/settings", response_model=VendorCriticalitySettingRead)
def upsert_vendor_criticality_settings(
    payload: VendorCriticalitySettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_criticality:manage")),
) -> VendorCriticalitySettingRead:
    row = VendorCriticalityService(db).upsert_settings(
        organization_id=organization.id,
        payload=payload,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _vendor_criticality_setting_read(row, organization.id)


@router.get("", response_model=list[VendorRead])
def list_vendors(
    status_filter: str | None = Query(default=None, alias="status"),
    risk_tier: str | None = Query(default=None),
    vendor_type: str | None = Query(default=None),
    data_access: bool | None = Query(default=None),
    business_unit_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> list[VendorRead]:
    stmt = select(Vendor).where(Vendor.organization_id == organization.id)

    if status_filter is not None:
        stmt = stmt.where(Vendor.status == status_filter)
    if risk_tier is not None:
        stmt = stmt.where(Vendor.risk_tier == risk_tier)
    if vendor_type is not None:
        stmt = stmt.where(Vendor.vendor_type == vendor_type)
    if data_access is not None:
        stmt = stmt.where(Vendor.data_access == data_access)
    if business_unit_id is not None:
        stmt = stmt.where(Vendor.business_unit_id == business_unit_id)
    if not include_archived:
        stmt = stmt.where(Vendor.status != "archived")

    rows = db.execute(
        stmt.order_by(Vendor.created_at.desc(), Vendor.id.desc()).offset(skip).limit(limit)
    ).scalars().all()
    overdue_vendor_ids = VendorAssessmentService(db).overdue_vendor_ids(organization.id)
    return [_vendor_read(row, has_overdue_assessment=row.id in overdue_vendor_ids) for row in rows]


@router.get("/{vendor_id}", response_model=VendorRead)
def get_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorRead:
    row = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    is_stale = row.id in VendorAssessmentService(db).overdue_vendor_ids(organization.id)
    return _vendor_read(row, has_overdue_assessment=is_stale)


@router.get("/{vendor_id}/criticality", response_model=VendorCriticalityProfileRead)
def get_vendor_criticality_profile(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_criticality:read")),
) -> VendorCriticalityProfileRead:
    service = VendorCriticalityService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    row = service.get_profile(organization.id, vendor_id)
    if row is None:
        return _vendor_criticality_profile_read(None, service.default_profile_payload(organization.id, vendor))
    priority_context = service.build_priority_context(vendor, row.criticality_tier)
    return _vendor_criticality_profile_read(row, priority_context=priority_context)


@router.put("/{vendor_id}/criticality", response_model=VendorCriticalityProfileRead)
def upsert_vendor_criticality_profile(
    vendor_id: uuid.UUID,
    payload: VendorCriticalityProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_criticality:manage")),
) -> VendorCriticalityProfileRead:
    service = VendorCriticalityService(db)
    row = service.upsert_profile(
        organization_id=organization.id,
        vendor_id=vendor_id,
        payload=payload,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    priority_context = service.build_priority_context(vendor, row.criticality_tier)
    return _vendor_criticality_profile_read(row, priority_context=priority_context)


@router.patch("/{vendor_id}", response_model=VendorRead)
def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorRead:
    service = VendorService(db)
    row = service.require_vendor_in_org(organization.id, vendor_id)
    changes = payload.model_dump(exclude_unset=True)

    if row.status == "archived":
        disallowed = sorted([field for field in changes if field not in {"notes", "tags_json"}])
        if disallowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived vendors can only update notes and tags_json",
            )

    if "owner_user_id" in changes:
        owner_user_id = changes["owner_user_id"]
        if owner_user_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_user_id is required")
        service.ensure_owner_is_active_member(organization.id, owner_user_id)

    if "name" in changes:
        service.ensure_unique_vendor_name(organization.id, changes["name"], exclude_id=vendor_id)

    if "status" in changes and changes["status"] == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use archive endpoint to archive vendors")

    before = {
        "name": row.name,
        "vendor_type": row.vendor_type,
        "risk_tier": row.risk_tier,
        "status": row.status,
        "owner_user_id": str(row.owner_user_id),
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }

    for field, value in changes.items():
        if field == "primary_contact_email" and value is not None:
            value = str(value)
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.updated",
        entity_type="vendor",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "vendor_type": row.vendor_type,
            "risk_tier": row.risk_tier,
            "status": row.status,
            "owner_user_id": str(row.owner_user_id),
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if "risk_tier" in changes or "status" in changes:
        _refresh_concentration_risk(
            db,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            trigger="vendor.updated",
        )

    db.commit()
    db.refresh(row)
    return _vendor_read(row)


@router.post("/{vendor_id}/archive", response_model=VendorRead)
def archive_vendor(
    vendor_id: uuid.UUID,
    payload: VendorArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:admin")),
) -> VendorRead:
    service = VendorService(db)
    row = service.require_vendor_in_org(organization.id, vendor_id)

    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor is already archived")

    service.check_archive_eligibility(organization.id, vendor_id)

    before = {
        "status": row.status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        "archive_reason": row.archive_reason,
    }

    row.status = "archived"
    row.archived_at = service.utcnow()
    row.archived_by_user_id = current_user.id
    row.archive_reason = payload.reason
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.archived",
        entity_type="vendor",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
            "archive_reason": row.archive_reason,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    _refresh_concentration_risk(
        db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        trigger="vendor.archived",
    )

    db.commit()
    db.refresh(row)
    return _vendor_read(row)


@router.post("/{vendor_id}/assessments", response_model=VendorAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_vendor_assessment(
    vendor_id: uuid.UUID,
    payload: VendorAssessmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentRead:
    service = VendorAssessmentService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot create new assessments")

    if payload.assigned_to_user_id is not None:
        service.ensure_active_member(organization.id, payload.assigned_to_user_id, field_name="assigned_to_user_id")

    row = VendorAssessment(
        organization_id=organization.id,
        vendor_id=vendor_id,
        title=payload.title,
        assessment_type=payload.assessment_type,
        status="draft",
        assigned_to_user_id=payload.assigned_to_user_id,
        due_date=payload.due_date,
        findings_summary=payload.findings_summary,
        overall_rating=payload.overall_rating,
        notes=payload.notes,
        tags_json=payload.tags_json,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor_assessment.created",
        entity_type="vendor_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor_id),
            "title": row.title,
            "assessment_type": row.assessment_type,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    service.sync_staleness(organization.id, vendor, row, actor_user_id=current_user.id)

    db.commit()
    db.refresh(row)
    return _assessment_read(row)


@router.post("/{vendor_id}/ai-model-assessments", response_model=ThirdPartyAIAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_vendor_ai_model_assessment(
    vendor_id: uuid.UUID,
    payload: ThirdPartyAIAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
    __: Membership = Depends(require_permission("ai_governance:write")),
) -> ThirdPartyAIAssessmentRead:
    row = ThirdPartyAIService(db).create_assessment(organization.id, vendor_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _third_party_ai_assessment_read(row)


@router.get("/{vendor_id}/ai-model-assessments", response_model=list[ThirdPartyAIAssessmentRead])
def list_vendor_ai_model_assessments(
    vendor_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    __: Membership = Depends(require_permission("ai_governance:read")),
) -> list[ThirdPartyAIAssessmentRead]:
    rows = ThirdPartyAIService(db).list_assessments(
        organization.id,
        vendor_id=vendor_id,
        status_filter=status_filter,
        risk_level=risk_level,
    )
    return [_third_party_ai_assessment_read(row) for row in rows]


@router.get("/{vendor_id}/assessments/summary", response_model=VendorAssessmentSummary)
def vendor_assessment_summary(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorAssessmentSummary:
    service = VendorAssessmentService(db)
    _ = service.require_vendor_in_org(organization.id, vendor_id)
    return VendorAssessmentSummary(**service.summary(organization.id, vendor_id))


@router.get("/{vendor_id}/assessments", response_model=list[VendorAssessmentRead])
def list_vendor_assessments(
    vendor_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    assessment_type: str | None = Query(default=None),
    assigned_to_user_id: uuid.UUID | None = Query(default=None, alias="assigned_to"),
    include_cancelled: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> list[VendorAssessmentRead]:
    service = VendorAssessmentService(db)
    _ = service.require_vendor_in_org(organization.id, vendor_id)

    stmt = select(VendorAssessment).where(
        VendorAssessment.organization_id == organization.id,
        VendorAssessment.vendor_id == vendor_id,
    )
    if status_filter is not None:
        stmt = stmt.where(VendorAssessment.status == status_filter)
    if assessment_type is not None:
        stmt = stmt.where(VendorAssessment.assessment_type == assessment_type)
    if assigned_to_user_id is not None:
        stmt = stmt.where(VendorAssessment.assigned_to_user_id == assigned_to_user_id)
    if not include_cancelled:
        stmt = stmt.where(VendorAssessment.status != "cancelled")

    rows = db.execute(stmt.order_by(VendorAssessment.created_at.desc())).scalars().all()
    return [_assessment_read(row) for row in rows]


@router.get("/{vendor_id}/assessments/{assessment_id}", response_model=VendorAssessmentRead)
def get_vendor_assessment(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorAssessmentRead:
    row = VendorAssessmentService(db).require_assessment_in_org(organization.id, vendor_id, assessment_id)
    return _assessment_read(row)


@router.patch("/{vendor_id}/assessments/{assessment_id}", response_model=VendorAssessmentRead)
def update_vendor_assessment(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    payload: VendorAssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentRead:
    service = VendorAssessmentService(db)
    row = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)
    changes = payload.model_dump(exclude_unset=True)

    if "assigned_to_user_id" in changes and changes["assigned_to_user_id"] is not None:
        service.ensure_active_member(organization.id, changes["assigned_to_user_id"], field_name="assigned_to_user_id")

    if "status" in changes:
        status_value = changes["status"]
        if status_value in {"completed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use lifecycle endpoints for completed/cancelled transitions")

    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    service.sync_staleness(organization.id, vendor, row, actor_user_id=current_user.id)

    db.commit()
    db.refresh(row)
    return _assessment_read(row)


@router.post("/{vendor_id}/assessments/{assessment_id}/start", response_model=VendorAssessmentRead)
def start_vendor_assessment(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentRead:
    service = VendorAssessmentService(db)
    row = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)

    if row.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft assessments can be started")

    row.status = "in_progress"
    row.started_at = service.utcnow()
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor_assessment.started",
        entity_type="vendor_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"vendor_id": str(vendor_id), "status": row.status, "started_at": row.started_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assessment_read(row)


@router.post("/{vendor_id}/assessments/{assessment_id}/complete", response_model=VendorAssessmentRead)
def complete_vendor_assessment(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    request: Request,
    payload: VendorAssessmentCompleteRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentRead:
    service = VendorAssessmentService(db)
    row = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)

    if row.status not in {"in_progress", "under_review"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only in_progress or under_review assessments can be completed",
        )

    if payload is not None:
        if payload.overall_rating is not None:
            row.overall_rating = payload.overall_rating
        if payload.findings_summary is not None:
            row.findings_summary = payload.findings_summary
    row.status = "completed"
    row.completed_at = service.utcnow()
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor_assessment.completed",
        entity_type="vendor_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor_id),
            "status": row.status,
            "completed_at": row.completed_at.isoformat(),
            "overall_rating": row.overall_rating,
            "findings_summary": row.findings_summary,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assessment_read(row)


@router.post("/{vendor_id}/assessments/{assessment_id}/cancel", response_model=VendorAssessmentRead)
def cancel_vendor_assessment(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    payload: VendorAssessmentCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentRead:
    service = VendorAssessmentService(db)
    row = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)

    if row.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completed assessments cannot be cancelled")
    if row.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment is already cancelled")

    row.status = "cancelled"
    row.cancelled_at = service.utcnow()
    row.cancellation_reason = payload.cancellation_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor_assessment.cancelled",
        entity_type="vendor_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"vendor_id": str(vendor_id), "status": row.status, "cancelled_at": row.cancelled_at.isoformat()},
        metadata_json={"source": "api", "cancellation_reason": payload.cancellation_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assessment_read(row)


@router.post("/{vendor_id}/assessments/{assessment_id}/questions", response_model=VendorAssessmentQuestionRead, status_code=status.HTTP_201_CREATED)
def create_vendor_assessment_question(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    payload: VendorAssessmentQuestionCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentQuestionRead:
    service = VendorAssessmentService(db)
    assessment = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)
    service.ensure_assessment_mutable(assessment)

    row = VendorAssessmentQuestion(
        organization_id=organization.id,
        assessment_id=assessment_id,
        question_text=payload.question_text,
        question_category=payload.question_category,
        response_text=payload.response_text,
        response_status=payload.response_status,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _assessment_question_read(row)


@router.get("/{vendor_id}/assessments/{assessment_id}/questions", response_model=list[VendorAssessmentQuestionRead])
def list_vendor_assessment_questions(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> list[VendorAssessmentQuestionRead]:
    service = VendorAssessmentService(db)
    _ = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)
    rows = db.execute(
        select(VendorAssessmentQuestion)
        .where(
            VendorAssessmentQuestion.organization_id == organization.id,
            VendorAssessmentQuestion.assessment_id == assessment_id,
        )
        .order_by(VendorAssessmentQuestion.sort_order.asc(), VendorAssessmentQuestion.created_at.asc())
    ).scalars().all()
    return [_assessment_question_read(row) for row in rows]


@router.patch("/{vendor_id}/assessments/{assessment_id}/questions/{question_id}", response_model=VendorAssessmentQuestionRead)
def update_vendor_assessment_question(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: VendorAssessmentQuestionUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentQuestionRead:
    service = VendorAssessmentService(db)
    assessment = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)
    service.ensure_assessment_mutable(assessment)
    row = service.require_question_in_org(organization.id, assessment_id, question_id)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _assessment_question_read(row)


@router.post("/{vendor_id}/assessments/{assessment_id}/questions/{question_id}/answer", response_model=VendorAssessmentQuestionRead)
def answer_vendor_assessment_question(
    vendor_id: uuid.UUID,
    assessment_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: VendorAssessmentQuestionAnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorAssessmentQuestionRead:
    service = VendorAssessmentService(db)
    assessment = service.require_assessment_in_org(organization.id, vendor_id, assessment_id)
    service.ensure_assessment_mutable(assessment)
    row = service.require_question_in_org(organization.id, assessment_id, question_id)

    row.response_text = payload.response_text
    row.response_status = "answered"
    row.answered_by_user_id = current_user.id
    row.answered_at = service.utcnow()
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor_assessment_question.answered",
        entity_type="vendor_assessment_question",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor_id),
            "assessment_id": str(assessment_id),
            "response_status": row.response_status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assessment_question_read(row)


@router.post("/{vendor_id}/risk-scores", response_model=VendorRiskScoreRead, status_code=status.HTTP_201_CREATED)
def create_vendor_risk_score(
    vendor_id: uuid.UUID,
    payload: VendorRiskScoreCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorRiskScoreRead:
    service = VendorRiskService(db)
    row, _ = service.create_risk_score(
        organization_id=organization.id,
        vendor_id=vendor_id,
        assessment_id=payload.assessment_id,
        likelihood=payload.likelihood,
        impact=payload.impact,
        notes=payload.notes,
        scored_by_user_id=current_user.id,
        triggered_by="user_action",
    )

    AuditService(db).write_audit_log(
        action="vendor_risk_score.created",
        entity_type="vendor_risk_score",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor_id),
            "assessment_id": str(payload.assessment_id) if payload.assessment_id else None,
            "inherent_risk_score": row.inherent_risk_score,
            "risk_level": row.risk_level,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    return _risk_score_read(row, vendor)


@router.get("/{vendor_id}/risk-scores", response_model=list[VendorRiskScoreRead])
def list_vendor_risk_scores(
    vendor_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> list[VendorRiskScoreRead]:
    service = VendorRiskService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    rows = db.execute(
        select(VendorRiskScore)
        .where(
            VendorRiskScore.organization_id == organization.id,
            VendorRiskScore.vendor_id == vendor_id,
        )
        .order_by(VendorRiskScore.created_at.desc(), VendorRiskScore.id.desc())
        .offset(skip)
        .limit(limit)
    ).scalars().all()
    return [_risk_score_read(row, vendor) for row in rows]


@router.get("/{vendor_id}/risk-scores/latest", response_model=VendorRiskScoreRead)
def get_latest_vendor_risk_score(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorRiskScoreRead:
    service = VendorRiskService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(VendorRiskScore)
        .where(
            VendorRiskScore.organization_id == organization.id,
            VendorRiskScore.vendor_id == vendor_id,
        )
        .order_by(VendorRiskScore.created_at.desc(), VendorRiskScore.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor risk score not found")
    return _risk_score_read(row, vendor)


@router.get("/{vendor_id}/risk-scores/{score_id}", response_model=VendorRiskScoreRead)
def get_vendor_risk_score(
    vendor_id: uuid.UUID,
    score_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorRiskScoreRead:
    service = VendorRiskService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(VendorRiskScore).where(
            VendorRiskScore.id == score_id,
            VendorRiskScore.organization_id == organization.id,
            VendorRiskScore.vendor_id == vendor_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor risk score not found")
    return _risk_score_read(row, vendor)


@router.post("/{vendor_id}/links/controls", response_model=VendorControlLinkRead, status_code=status.HTTP_201_CREATED)
def link_control_to_vendor(
    vendor_id: uuid.UUID,
    payload: VendorControlLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorControlLinkRead:
    service = VendorRiskService(db)
    vendor = service.require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot accept new control links")
    service.require_control_in_org(organization.id, payload.control_id)

    link = db.execute(
        select(VendorControlLink).where(
            VendorControlLink.organization_id == organization.id,
            VendorControlLink.vendor_id == vendor_id,
            VendorControlLink.control_id == payload.control_id,
        )
    ).scalar_one_or_none()

    if link is not None and link.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active vendor-control link already exists")

    if link is None:
        link = VendorControlLink(
            organization_id=organization.id,
            vendor_id=vendor_id,
            control_id=payload.control_id,
            link_reason=payload.link_reason,
            status="active",
            linked_by_user_id=current_user.id,
        )
        db.add(link)
    else:
        link.status = "active"
        link.link_reason = payload.link_reason
        link.unlinked_at = None
        link.unlinked_by_user_id = None
        link.unlink_reason = None
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.control_linked",
        entity_type="vendor_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"vendor_id": str(vendor_id), "control_id": str(payload.control_id), "status": link.status},
        metadata_json={"source": "api", "link_reason": payload.link_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _vendor_control_link_read(link)


@router.get("/{vendor_id}/links/controls", response_model=list[VendorControlLinkRead])
def list_vendor_control_links(
    vendor_id: uuid.UUID,
    include_unlinked: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> list[VendorControlLinkRead]:
    service = VendorRiskService(db)
    _ = service.require_vendor_in_org(organization.id, vendor_id)
    stmt = select(VendorControlLink).where(
        VendorControlLink.organization_id == organization.id,
        VendorControlLink.vendor_id == vendor_id,
    )
    if not include_unlinked:
        stmt = stmt.where(VendorControlLink.status == "active")
    rows = db.execute(stmt.order_by(VendorControlLink.created_at.desc())).scalars().all()
    return [_vendor_control_link_read(row) for row in rows]


@router.post("/{vendor_id}/links/controls/{link_id}/unlink", response_model=VendorControlLinkRead)
def unlink_control_from_vendor(
    vendor_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: VendorControlUnlinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> VendorControlLinkRead:
    service = VendorRiskService(db)
    _ = service.require_vendor_in_org(organization.id, vendor_id)
    link = db.execute(
        select(VendorControlLink).where(
            VendorControlLink.id == link_id,
            VendorControlLink.organization_id == organization.id,
            VendorControlLink.vendor_id == vendor_id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor-control link not found")
    if link.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor-control link is not active")

    before = {"status": link.status}
    link.status = "unlinked"
    link.unlinked_at = VendorService.utcnow()
    link.unlinked_by_user_id = current_user.id
    link.unlink_reason = payload.unlink_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.control_unlinked",
        entity_type="vendor_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"vendor_id": str(vendor_id), "control_id": str(link.control_id), "status": link.status},
        metadata_json={"source": "api", "unlink_reason": payload.unlink_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _vendor_control_link_read(link)


@router.get("/{vendor_id}/links/summary", response_model=VendorLinksSummary)
def vendor_links_summary(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> VendorLinksSummary:
    service = VendorRiskService(db)
    _ = service.require_vendor_in_org(organization.id, vendor_id)

    active_control_links = int(
        db.execute(
            select(func.count(VendorControlLink.id)).where(
                VendorControlLink.organization_id == organization.id,
                VendorControlLink.vendor_id == vendor_id,
                VendorControlLink.status == "active",
            )
        ).scalar_one()
    )
    unlinked_control_links = int(
        db.execute(
            select(func.count(VendorControlLink.id)).where(
                VendorControlLink.organization_id == organization.id,
                VendorControlLink.vendor_id == vendor_id,
                VendorControlLink.status == "unlinked",
            )
        ).scalar_one()
    )
    return VendorLinksSummary(
        active_control_links=active_control_links,
        unlinked_control_links=unlinked_control_links,
        total_active_links=active_control_links,
        total_unlinked_links=unlinked_control_links,
    )
