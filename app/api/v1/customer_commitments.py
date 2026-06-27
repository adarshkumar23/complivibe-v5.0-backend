import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.commitment_notification_log import CommitmentNotificationLog
from app.models.customer_commitment import CustomerCommitment
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.customer_commitment import (
    CommitmentNotificationLogRead,
    CustomerCommitmentCreate,
    CustomerCommitmentDashboard,
    CustomerCommitmentFulfillRequest,
    CustomerCommitmentRead,
    CustomerCommitmentUpdate,
    CustomerCommitmentWaiveRequest,
)

router = APIRouter(prefix="/compliance/customer-commitments", tags=["customer-commitments"])


def _commitment_read(row: CustomerCommitment) -> CustomerCommitmentRead:
    return CustomerCommitmentRead(
        id=row.id,
        organization_id=row.organization_id,
        customer_name=row.customer_name,
        customer_email=row.customer_email,
        commitment_type=row.commitment_type,
        title=row.title,
        description=row.description,
        trigger_condition=row.trigger_condition,
        trigger_date=row.trigger_date,
        notification_days_before=row.notification_days_before,
        sla_hours=row.sla_hours,
        status=row.status,
        linked_contract_ref=row.linked_contract_ref,
        assigned_owner_id=row.assigned_owner_id,
        triggered_at=row.triggered_at,
        fulfilled_at=row.fulfilled_at,
        fulfilled_by=row.fulfilled_by,
        fulfillment_notes=row.fulfillment_notes,
        waived_at=row.waived_at,
        waived_by=row.waived_by,
        waiver_reason=row.waiver_reason,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _notification_read(row: CommitmentNotificationLog) -> CommitmentNotificationLogRead:
    return CommitmentNotificationLogRead(
        id=row.id,
        organization_id=row.organization_id,
        commitment_id=row.commitment_id,
        notification_type=row.notification_type,
        queued_at=row.queued_at,
        recipient_user_ids=row.recipient_user_ids,
        message_preview=row.message_preview,
        triggered_by=row.triggered_by,
    )


@router.post("", response_model=CustomerCommitmentRead, status_code=status.HTTP_201_CREATED)
def create_customer_commitment(
    payload: CustomerCommitmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).create_commitment(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.get("", response_model=list[CustomerCommitmentRead])
def list_customer_commitments(
    commitment_type: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    customer_name: str | None = Query(default=None),
    assigned_owner_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[CustomerCommitmentRead]:
    rows = CustomerCommitmentService(db).list_commitments(
        organization.id,
        commitment_type=commitment_type,
        status_value=status_value,
        customer_name=customer_name,
        assigned_owner_id=assigned_owner_id,
        skip=skip,
        limit=limit,
    )
    return [_commitment_read(row) for row in rows]


@router.get("/dashboard", response_model=CustomerCommitmentDashboard)
def customer_commitment_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> CustomerCommitmentDashboard:
    payload = CustomerCommitmentService(db).get_commitment_dashboard(organization.id)
    return CustomerCommitmentDashboard(**payload)


@router.get("/{commitment_id}", response_model=CustomerCommitmentRead)
def get_customer_commitment(
    commitment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).get_commitment(organization.id, commitment_id)
    return _commitment_read(row)


@router.patch("/{commitment_id}", response_model=CustomerCommitmentRead)
def update_customer_commitment(
    commitment_id: uuid.UUID,
    payload: CustomerCommitmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).update_commitment(
        organization.id,
        commitment_id,
        payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.post("/{commitment_id}/trigger", response_model=CustomerCommitmentRead)
def trigger_customer_commitment(
    commitment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).trigger_commitment(
        organization.id,
        commitment_id,
        current_user.id,
        triggered_by="manual",
    )
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.post("/{commitment_id}/fulfill", response_model=CustomerCommitmentRead)
def fulfill_customer_commitment(
    commitment_id: uuid.UUID,
    payload: CustomerCommitmentFulfillRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).fulfill_commitment(
        organization.id,
        commitment_id,
        current_user.id,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.post("/{commitment_id}/waive", response_model=CustomerCommitmentRead)
def waive_customer_commitment(
    commitment_id: uuid.UUID,
    payload: CustomerCommitmentWaiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).waive_commitment(
        organization.id,
        commitment_id,
        current_user.id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.delete("/{commitment_id}", response_model=CustomerCommitmentRead)
def delete_customer_commitment(
    commitment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> CustomerCommitmentRead:
    row = CustomerCommitmentService(db).soft_delete_commitment(organization.id, commitment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _commitment_read(row)


@router.get("/{commitment_id}/notifications", response_model=list[CommitmentNotificationLogRead])
def list_commitment_notifications(
    commitment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[CommitmentNotificationLogRead]:
    rows = CustomerCommitmentService(db).list_notification_logs(organization.id, commitment_id)
    return [_notification_read(row) for row in rows]
