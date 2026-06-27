import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.compliance.services.rca_service import RCAService
from app.compliance.services.sla_service import SLAService
from app.compliance.services.breach_notification_service import BreachNotificationService
from app.compliance.services.issue_policy_link_service import IssuePolicyLinkService
from app.compliance.services.issue_control_link_service import IssueControlLinkService
from app.compliance.services.remediation_service import RemediationService
from app.compliance.services.classification_service import ClassificationService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.issue import Issue
from app.models.issue_transition import IssueTransition
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.root_cause_analysis import RootCauseAnalysis
from app.models.user import User
from app.schemas.issue import (
    IssueAssignRequest,
    IssueCreate,
    IssueDashboard,
    IssueRead,
    IssueTransitionRead,
    IssueTransitionRequest,
    IssueUpdate,
)
from app.schemas.breach_notification import BreachNotificationCreate, BreachNotificationRead
from app.schemas.rca import RCACreate, RCARead, RCAUpdate
from app.schemas.sla import IssueSLABreachRead, IssueSLAStatusRead
from app.schemas.issue_links import (
    IssuePolicyLinkCreate,
    IssuePolicyLinkRead,
    IssueControlLinkCreate,
    IssueControlLinkRead,
)
from app.schemas.remediation import RemediationSuggestionRead
from app.schemas.incident_classification import IncidentClassificationOverrideRequest, IncidentClassificationRead

router = APIRouter(prefix="/compliance/issues", tags=["issues"])
remediation_router = APIRouter(prefix="/compliance/remediation-suggestions", tags=["issues"])


def _read(row: Issue) -> IssueRead:
    return IssueRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        issue_type=row.issue_type,
        severity=row.severity,
        source_type=row.source_type,
        source_id=row.source_id,
        status=row.status,
        owner_id=row.owner_id,
        assigned_to=row.assigned_to,
        created_by=row.created_by,
        resolution_note=row.resolution_note,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _transition_read(row: IssueTransition) -> IssueTransitionRead:
    return IssueTransitionRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        from_status=row.from_status,
        to_status=row.to_status,
        actor_id=row.actor_id,
        notes=row.notes,
        transitioned_at=row.transitioned_at,
    )


def _rca_read(row: RootCauseAnalysis) -> RCARead:
    return RCARead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        summary=row.summary,
        timeline_description=row.timeline_description,
        root_cause=row.root_cause,
        contributing_factors=list(row.contributing_factors or []),
        corrective_actions=list(row.corrective_actions or []),
        preventive_measures=list(row.preventive_measures or []),
        authored_by=row.authored_by,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _breach_read(row) -> BreachNotificationRead:
    return BreachNotificationRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        breach_type=row.breach_type,
        personal_data_affected=row.personal_data_affected,
        estimated_affected_count=row.estimated_affected_count,
        regulatory_notification_required=row.regulatory_notification_required,
        regulatory_framework=row.regulatory_framework,
        regulatory_notification_hours=row.regulatory_notification_hours,
        regulatory_notification_deadline=row.regulatory_notification_deadline,
        supervisory_authority=row.supervisory_authority,
        regulatory_notified_at=row.regulatory_notified_at,
        subject_notification_required=row.subject_notification_required,
        subjects_notified_at=row.subjects_notified_at,
        data_subjects_affected_count=row.data_subjects_affected_count,
        special_category_data_involved=row.special_category_data_involved,
        article33_notification_text=row.article33_notification_text,
        article34_required=row.article34_required,
        subjects_notification_text=row.subjects_notification_text,
        dpa_reference_number=row.dpa_reference_number,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_link_read(row) -> IssuePolicyLinkRead:
    return IssuePolicyLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        policy_id=row.policy_id,
        link_type=row.link_type,
        linked_by=row.linked_by,
        linked_at=row.linked_at,
    )


def _control_link_read(row) -> IssueControlLinkRead:
    return IssueControlLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        control_id=row.control_id,
        failure_type=row.failure_type,
        linked_by=row.linked_by,
        linked_at=row.linked_at,
    )


def _remediation_read(row) -> RemediationSuggestionRead:
    return RemediationSuggestionRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        suggestion_text=row.suggestion_text,
        suggestion_source=row.suggestion_source,
        source_key=row.source_key,
        applied=row.applied,
        dismissed=row.dismissed,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _classification_read(row) -> IncidentClassificationRead:
    return IncidentClassificationRead(
        id=row.id,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        category=row.category,
        sub_category=row.sub_category,
        regulatory_implications=list(row.regulatory_implications or []),
        notification_required=row.notification_required,
        auto_classified=row.auto_classified,
        classification_by=row.classification_by,
        classified_at=row.classified_at,
        last_updated_at=row.last_updated_at,
    )


@router.post("", response_model=IssueRead, status_code=status.HTTP_201_CREATED)
def create_issue(
    payload: IssueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).create_issue(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("", response_model=list[IssueRead])
def list_issues(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssueRead]:
    rows = IssueService(db).list_issues(
        organization.id,
        status_value=status_filter,
        severity=severity,
        issue_type=issue_type,
        source_type=source_type,
        owner_id=owner_id,
        assigned_to=assigned_to,
        skip=skip,
        limit=limit,
    )
    return [_read(row) for row in rows]


@router.get("/dashboard", response_model=IssueDashboard)
def issue_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> IssueDashboard:
    payload = IssueService(db).get_issue_dashboard(organization.id)
    return IssueDashboard(**payload)


@router.get("/sla-breaches", response_model=list[IssueSLABreachRead])
def get_sla_breaches(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssueSLABreachRead]:
    rows = SLAService(db).get_sla_breaches(organization.id)
    return [IssueSLABreachRead(**row) for row in rows]


@router.get("/{issue_id}/sla-status", response_model=IssueSLAStatusRead)
def get_issue_sla_status(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> IssueSLAStatusRead:
    payload = SLAService(db).get_sla_status(organization.id, issue_id)
    return IssueSLAStatusRead(**payload)


@router.post("/{issue_id}/policy-links", response_model=IssuePolicyLinkRead, status_code=status.HTTP_201_CREATED)
def link_issue_to_policy(
    issue_id: uuid.UUID,
    payload: IssuePolicyLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssuePolicyLinkRead:
    row = IssuePolicyLinkService(db).link_issue_to_policy(
        organization.id,
        issue_id,
        payload.policy_id,
        payload.link_type,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _policy_link_read(row)


@router.get("/{issue_id}/policy-links", response_model=list[IssuePolicyLinkRead])
def get_issue_policy_links(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssuePolicyLinkRead]:
    rows = IssuePolicyLinkService(db).get_issue_policy_links(organization.id, issue_id)
    return [_policy_link_read(row) for row in rows]


@router.delete("/{issue_id}/policy-links/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_issue_from_policy(
    issue_id: uuid.UUID,
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> None:
    IssuePolicyLinkService(db).unlink_issue_from_policy(organization.id, issue_id, policy_id, current_user.id)
    db.commit()
    return None


@router.post("/{issue_id}/control-links", response_model=IssueControlLinkRead, status_code=status.HTTP_201_CREATED)
def link_issue_to_control(
    issue_id: uuid.UUID,
    payload: IssueControlLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueControlLinkRead:
    row = IssueControlLinkService(db).link_issue_to_control(
        organization.id,
        issue_id,
        payload.control_id,
        payload.failure_type,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _control_link_read(row)


@router.get("/{issue_id}/control-links", response_model=list[IssueControlLinkRead])
def get_issue_control_links(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssueControlLinkRead]:
    rows = IssueControlLinkService(db).get_issue_control_links(organization.id, issue_id)
    return [_control_link_read(row) for row in rows]


@router.delete("/{issue_id}/control-links/{control_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_issue_from_control(
    issue_id: uuid.UUID,
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> None:
    IssueControlLinkService(db).unlink_issue_from_control(organization.id, issue_id, control_id, current_user.id)
    db.commit()
    return None


@router.post("/{issue_id}/generate-suggestions", response_model=list[RemediationSuggestionRead])
def generate_issue_suggestions(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> list[RemediationSuggestionRead]:
    rows = RemediationService(db).generate_suggestions(organization.id, issue_id, current_user.id)
    db.commit()
    for row in rows:
        db.refresh(row)
    return [_remediation_read(row) for row in rows]


@router.get("/{issue_id}/suggestions", response_model=list[RemediationSuggestionRead])
def list_issue_suggestions(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[RemediationSuggestionRead]:
    rows = RemediationService(db).list_suggestions(organization.id, issue_id)
    return [_remediation_read(row) for row in rows]


@router.post("/{issue_id}/classification", response_model=IncidentClassificationRead)
def auto_classify_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IncidentClassificationRead:
    row = ClassificationService(db).auto_classify(organization.id, issue_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _classification_read(row)


@router.patch("/{issue_id}/classification", response_model=IncidentClassificationRead)
def override_issue_classification(
    issue_id: uuid.UUID,
    payload: IncidentClassificationOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IncidentClassificationRead:
    row = ClassificationService(db).override_classification(organization.id, issue_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _classification_read(row)


@router.get("/{issue_id}/classification", response_model=IncidentClassificationRead | None)
def get_issue_classification(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> IncidentClassificationRead | None:
    row = ClassificationService(db).get_classification(organization.id, issue_id)
    if row is None:
        return None
    return _classification_read(row)


@router.get("/{issue_id}", response_model=IssueRead)
def get_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> IssueRead:
    row = IssueService(db).get_issue(organization.id, issue_id)
    return _read(row)


@router.patch("/{issue_id}", response_model=IssueRead)
def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).update_issue(organization.id, issue_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{issue_id}/assign", response_model=IssueRead)
def assign_issue(
    issue_id: uuid.UUID,
    payload: IssueAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).assign_issue(organization.id, issue_id, payload.assigned_to, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{issue_id}/transition", response_model=IssueRead)
def transition_issue(
    issue_id: uuid.UUID,
    payload: IssueTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).transition_issue(
        organization.id,
        issue_id,
        payload.new_status,
        current_user.id,
        notes=payload.notes,
        resolution_note=payload.resolution_note,
    )
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{issue_id}/rca", response_model=RCARead, status_code=status.HTTP_201_CREATED)
def create_issue_rca(
    issue_id: uuid.UUID,
    payload: RCACreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> RCARead:
    row = RCAService(db).create_rca(organization.id, issue_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _rca_read(row)


@router.post("/{issue_id}/breach-notification", response_model=BreachNotificationRead, status_code=status.HTTP_201_CREATED)
def create_issue_breach_notification(
    issue_id: uuid.UUID,
    payload: BreachNotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    row = BreachNotificationService(db).create_breach_notification(organization.id, issue_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _breach_read(row)


@router.get("/{issue_id}/rca", response_model=RCARead)
def get_issue_rca(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> RCARead:
    row = RCAService(db).get_rca(organization.id, issue_id)
    return _rca_read(row)


@router.patch("/{issue_id}/rca", response_model=RCARead)
def update_issue_rca(
    issue_id: uuid.UUID,
    payload: RCAUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> RCARead:
    row = RCAService(db).update_rca(organization.id, issue_id, payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return _rca_read(row)


@router.post("/{issue_id}/rca/review", response_model=RCARead)
def review_issue_rca(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> RCARead:
    row = RCAService(db).review_rca(organization.id, issue_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _rca_read(row)


@router.get("/{issue_id}/transitions", response_model=list[IssueTransitionRead])
def get_issue_transitions(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssueTransitionRead]:
    rows = IssueService(db).get_transitions(organization.id, issue_id)
    return [_transition_read(row) for row in rows]


@router.delete("/{issue_id}", response_model=IssueRead)
def delete_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).soft_delete_issue(organization.id, issue_id, current_user.id)
    db.commit()
    return _read(row)


@remediation_router.post("/{suggestion_id}/apply", response_model=RemediationSuggestionRead)
def apply_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> RemediationSuggestionRead:
    row = RemediationService(db).apply_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _remediation_read(row)


@remediation_router.post("/{suggestion_id}/dismiss", response_model=RemediationSuggestionRead)
def dismiss_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> RemediationSuggestionRead:
    row = RemediationService(db).dismiss_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _remediation_read(row)
