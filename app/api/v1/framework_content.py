import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db, require_permission
from app.models.membership import Membership
from app.models.user import User
from app.schemas.framework import (
    FrameworkContentPackApplyRequest,
    FrameworkContentPackValidationResponse,
    GlobalFrameworkCoverageItem,
    LocalFrameworkPackRead,
)
from app.services.audit_service import AuditService
from app.services.framework_content_pack_service import FrameworkContentPackService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/framework-content", tags=["framework-content"])


@router.get("/packs", response_model=list[LocalFrameworkPackRead])
def list_local_content_packs(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[LocalFrameworkPackRead]:
    SeedService.ensure_framework_versions(db)
    db.commit()
    return [LocalFrameworkPackRead(**row) for row in FrameworkContentPackService(db).list_packs()]


@router.post("/packs/{pack_key}/validate", response_model=FrameworkContentPackValidationResponse)
def validate_local_content_pack(
    pack_key: str,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:activate")),
) -> FrameworkContentPackValidationResponse:
    SeedService.ensure_framework_versions(db)
    db.commit()
    result = FrameworkContentPackService(db).validate_pack(pack_key)
    return FrameworkContentPackValidationResponse(
        valid=result["valid"],
        pack_key=result["pack_key"],
        framework_code=result["framework_code"],
        framework_name=result["framework_name"],
        coverage_level=result["coverage_level"],
        review_status=result["review_status"],
        caveat=result["caveat"],
        counts=result["counts"],
        validation_errors=result["validation_errors"],
        warnings=result["warnings"],
        persisted=False,
    )


@router.post("/packs/{pack_key}/apply", response_model=FrameworkContentPackValidationResponse)
def apply_local_content_pack(
    pack_key: str,
    payload: FrameworkContentPackApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("frameworks:activate")),
) -> FrameworkContentPackValidationResponse:
    SeedService.ensure_framework_versions(db)
    db.commit()
    result = FrameworkContentPackService(db).apply_pack(
        pack_key=pack_key,
        actor_user_id=current_user.id,
        organization_id=membership.organization_id,
        dry_run=payload.dry_run,
        force_update=payload.force_update,
    )

    if result["persisted"]:
        AuditService(db).write_audit_log(
            action="framework_content_pack.applied",
            entity_type="framework_content_import",
            entity_id=uuid.UUID(result["import_id"]),
            organization_id=membership.organization_id,
            actor_user_id=current_user.id,
            after_json={
                "pack_key": result["pack_key"],
                "framework_code": result["framework_code"],
                "counts": result["counts"],
            },
            metadata_json={"source": "api", "dry_run": payload.dry_run},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()

    return FrameworkContentPackValidationResponse(
        valid=result["valid"],
        pack_key=result["pack_key"],
        framework_code=result["framework_code"],
        framework_name=result["framework_name"],
        coverage_level=result["coverage_level"],
        review_status=result["review_status"],
        caveat=result["caveat"],
        counts=result["counts"],
        validation_errors=result["validation_errors"],
        warnings=result["warnings"],
        persisted=result["persisted"],
    )


@router.get("/coverage-summary", response_model=list[GlobalFrameworkCoverageItem])
def global_framework_coverage_summary(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("frameworks:read")),
) -> list[GlobalFrameworkCoverageItem]:
    SeedService.ensure_starter_obligations(db)
    SeedService.ensure_framework_versions(db)
    db.commit()
    rows = FrameworkContentPackService(db).global_coverage_summary()
    return [GlobalFrameworkCoverageItem(**item) for item in rows]
