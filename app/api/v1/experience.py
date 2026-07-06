from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.experience import (
    CommandPaletteExecuteRequest,
    CommandPaletteExecuteResponse,
    CommandPaletteQueryResponse,
)
from app.services.experience_service import CommandPaletteService

router = APIRouter(tags=["experience"])


@router.get("/command-palette/query", response_model=CommandPaletteQueryResponse)
def command_palette_query(
    q: str = Query(..., min_length=1, max_length=256),
    entity_types: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("command_palette:search")),
) -> CommandPaletteQueryResponse:
    return CommandPaletteService(db).query(
        organization_id=organization.id,
        query=q,
        entity_types=entity_types,
        limit=limit,
    )


@router.post("/command-palette/execute", response_model=CommandPaletteExecuteResponse)
def command_palette_execute(
    payload: CommandPaletteExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("command_palette:execute")),
) -> CommandPaletteExecuteResponse:
    result = CommandPaletteService(db).execute(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    db.commit()
    return result
