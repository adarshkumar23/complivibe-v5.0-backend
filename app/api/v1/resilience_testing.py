from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.resilience_testing import ResilienceTest
from app.models.user import User
from app.schemas.resilience_testing import (
    ResilienceTestCompleteRequest,
    ResilienceTestCompleteResponse,
    ResilienceTestCreate,
    ResilienceTestOverdueStatus,
    ResilienceTestRead,
    ResilienceTestUpdate,
)
from app.services.resilience_testing_service import ResilienceTestingService

router = APIRouter(prefix="/resilience-tests", tags=["resilience-testing"])


def _test_read(test: ResilienceTest, context_flags: list[str] | None = None) -> ResilienceTestRead:
    result = ResilienceTestRead.model_validate(test)
    result.context_flags = context_flags or []
    return result


@router.post("", response_model=ResilienceTestRead, status_code=status.HTTP_201_CREATED)
def create_resilience_test(
    payload: ResilienceTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:manage")),
) -> ResilienceTestRead:
    service = ResilienceTestingService(db)
    test = service.create_test(
        organization_id=organization.id,
        test_type=payload.test_type,
        scope=payload.scope,
        scheduled_date=payload.scheduled_date,
        owner_team=payload.owner_team,
        created_by_user_id=current_user.id,
    )
    db.commit()
    db.refresh(test)
    return _test_read(test)


@router.get("", response_model=list[ResilienceTestRead])
def list_resilience_tests(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:read")),
) -> list[ResilienceTestRead]:
    service = ResilienceTestingService(db)
    return [
        _test_read(test, service.build_test_context(organization.id, test))
        for test in service.list_tests(organization.id)
    ]


@router.get("/overdue", response_model=list[ResilienceTestOverdueStatus])
def get_overdue_resilience_tests(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:read")),
) -> list[ResilienceTestOverdueStatus]:
    service = ResilienceTestingService(db)
    return [ResilienceTestOverdueStatus(**entry) for entry in service.compute_overdue(organization.id)]


@router.get("/{test_id}", response_model=ResilienceTestRead)
def get_resilience_test(
    test_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:read")),
) -> ResilienceTestRead:
    service = ResilienceTestingService(db)
    test = service.get_test(organization.id, test_id)
    return _test_read(test, service.build_test_context(organization.id, test))


@router.patch("/{test_id}", response_model=ResilienceTestRead)
def update_resilience_test(
    test_id: uuid.UUID,
    payload: ResilienceTestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:manage")),
) -> ResilienceTestRead:
    service = ResilienceTestingService(db)
    test = service.update_test(
        organization_id=organization.id,
        test_id=test_id,
        scope=payload.scope,
        scheduled_date=payload.scheduled_date,
        owner_team=payload.owner_team,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(test)
    return _test_read(test)


@router.post("/{test_id}/complete", response_model=ResilienceTestCompleteResponse)
def complete_resilience_test(
    test_id: uuid.UUID,
    payload: ResilienceTestCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("resilience_testing:manage")),
) -> ResilienceTestCompleteResponse:
    service = ResilienceTestingService(db)
    try:
        test, issues_created = service.complete_test(
            organization_id=organization.id,
            test_id=test_id,
            completed_by_user_id=current_user.id,
            results=payload.results_json.model_dump(mode="json"),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    db.refresh(test)
    context_flags = service.build_test_context(organization.id, test)
    return ResilienceTestCompleteResponse(test=_test_read(test, context_flags), issues_created=issues_created)
