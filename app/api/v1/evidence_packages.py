import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.evidence_package_service import EvidencePackageService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.evidence_package import EvidencePackage
from app.models.evidence_package_item import EvidencePackageItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.evidence_package import (
    EvidencePackageAddItem,
    EvidencePackageCompleteness,
    EvidencePackageCreate,
    EvidencePackageItemRead,
    EvidencePackageManifest,
    EvidencePackageRead,
)

router = APIRouter(prefix="/compliance/evidence-packages", tags=["evidence-packages"])


def _package_read(row: EvidencePackage, service: EvidencePackageService) -> EvidencePackageRead:
    return EvidencePackageRead(
        id=row.id,
        organization_id=row.organization_id,
        audit_engagement_id=row.audit_engagement_id,
        title=row.title,
        scope_framework_ids=[uuid.UUID(item) for item in (row.scope_framework_ids or [])],
        cover_sheet_data=row.cover_sheet_data or {},
        chain_of_custody=list(row.chain_of_custody or []),
        status=row.status,
        assembled_at=row.assembled_at,
        assembled_by=row.assembled_by,
        exported_at=row.exported_at,
        item_count=row.item_count,
        scope_changed_since_creation=service.scope_changed_since_creation(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item_read(row: EvidencePackageItem) -> EvidencePackageItemRead:
    return EvidencePackageItemRead(
        id=row.id,
        package_id=row.package_id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        evidence_id=row.evidence_id,
        framework_requirement_ref=row.framework_requirement_ref,
        display_order=row.display_order,
        added_at=row.added_at,
        added_by=row.added_by,
    )


@router.post("", response_model=EvidencePackageRead, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: EvidencePackageCreate,
    engagement_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.create_package(organization.id, engagement_id, payload, current_user)
    db.commit()
    db.refresh(row)
    return _package_read(row, service)


@router.get("", response_model=list[EvidencePackageRead])
def list_packages(
    engagement_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[EvidencePackageRead]:
    service = EvidencePackageService(db)
    rows = service.list_packages(
        organization.id,
        engagement_id=engagement_id,
        status_value=status_filter,
        skip=skip,
        limit=limit,
    )
    return [_package_read(row, service) for row in rows]


@router.get("/engagement/{engagement_id}", response_model=list[EvidencePackageRead])
def list_packages_for_engagement(
    engagement_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[EvidencePackageRead]:
    service = EvidencePackageService(db)
    rows = service.list_packages(organization.id, engagement_id=engagement_id, skip=skip, limit=limit)
    return [_package_read(row, service) for row in rows]


@router.get("/{package_id}", response_model=EvidencePackageRead)
def get_package(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.get_package(organization.id, package_id)
    return _package_read(row, service)


@router.get("/{package_id}/manifest", response_model=EvidencePackageManifest)
def get_package_manifest(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> EvidencePackageManifest:
    payload = EvidencePackageService(db).get_manifest(organization.id, package_id)
    return EvidencePackageManifest(**payload)


@router.get("/{package_id}/completeness", response_model=EvidencePackageCompleteness)
def get_package_completeness(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> EvidencePackageCompleteness:
    payload = EvidencePackageService(db).get_completeness(organization.id, package_id)
    return EvidencePackageCompleteness(**payload)


@router.post("/{package_id}/items", response_model=EvidencePackageItemRead, status_code=status.HTTP_201_CREATED)
def add_package_item(
    package_id: uuid.UUID,
    payload: EvidencePackageAddItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageItemRead:
    row = EvidencePackageService(db).add_item(organization.id, package_id, payload, current_user)
    db.commit()
    db.refresh(row)
    return _item_read(row)


@router.delete("/{package_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_package_item(
    package_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> None:
    EvidencePackageService(db).remove_item(organization.id, package_id, item_id, current_user)
    db.commit()


@router.post("/{package_id}/assemble", response_model=EvidencePackageRead)
def assemble_package(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.assemble_package(organization.id, package_id, current_user)
    db.commit()
    db.refresh(row)
    return _package_read(row, service)


@router.post("/{package_id}/export", response_model=EvidencePackageRead)
def export_package(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.mark_exported(organization.id, package_id, current_user)
    db.commit()
    db.refresh(row)
    return _package_read(row, service)


@router.post("/{package_id}/archive", response_model=EvidencePackageRead)
def archive_package(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.archive_package(organization.id, package_id, current_user)
    db.commit()
    db.refresh(row)
    return _package_read(row, service)


@router.delete("/{package_id}", response_model=EvidencePackageRead)
def delete_package(
    package_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> EvidencePackageRead:
    service = EvidencePackageService(db)
    row = service.soft_delete_package(organization.id, package_id, current_user)
    db.commit()
    return _package_read(row, service)
