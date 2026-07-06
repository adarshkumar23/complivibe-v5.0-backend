from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.certification_program import (
    CertificationProgramActivateRequest,
    CertificationProgramActivateResponse,
    CertificationProgramProgressResponse,
    CertificationProgramRead,
)
from app.services.certification_program_service import CertificationProgramService

router = APIRouter(prefix="/certification-programs", tags=["certification-programs"])


def _program_read(row) -> CertificationProgramRead:
    return CertificationProgramRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        name=row.name,
        target_framework=row.target_framework,
        duration_weeks=row.duration_weeks,
        weeks_json=list(row.weeks_json or []),
        prerequisites_json=row.prerequisites_json or {},
        evidence_templates_json=list(row.evidence_templates_json or []),
        description=row.description,
        status=row.status,
    )


@router.get("", response_model=list[CertificationProgramRead])
def list_certification_programs(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("certification_programs:read")),
) -> list[CertificationProgramRead]:
    rows = CertificationProgramService(db).list_programs()
    db.commit()
    return [_program_read(row) for row in rows]


@router.post("/{program_id}/activate", response_model=CertificationProgramActivateResponse, status_code=status.HTTP_201_CREATED)
def activate_certification_program(
    program_id: uuid.UUID,
    payload: CertificationProgramActivateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("certification_programs:activate")),
) -> CertificationProgramActivateResponse:
    result = CertificationProgramService(db).activate_program(
        organization_id=organization.id,
        program_id=program_id,
        actor_user_id=current_user.id,
        owner_user_id=payload.owner_user_id,
    )
    db.commit()
    return result


@router.get("/{program_id}/progress", response_model=CertificationProgramProgressResponse)
def certification_program_progress(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("certification_programs:read")),
) -> CertificationProgramProgressResponse:
    return CertificationProgramService(db).get_progress(organization_id=organization.id, program_id=program_id)
