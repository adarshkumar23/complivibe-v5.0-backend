import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.legal_matter import LegalMatter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.legal_matter import (
    LegalMatterCloseRequest,
    LegalMatterControlLinkRead,
    LegalMatterCreate,
    LegalMatterEvidenceLinkRead,
    LegalMatterLinkControlRequest,
    LegalMatterLinkEvidenceRequest,
    LegalMatterLinkIssueRequest,
    LegalMatterLinkRiskRequest,
    LegalMatterResponse,
    LegalMatterStatusChangeRequest,
    LegalMatterUpdate,
)
from app.services.legal_matter_service import LegalMatterService

router = APIRouter(prefix="/legal-matters", tags=["legal-matters"])


def _read(db: Session, org_id: uuid.UUID, row: LegalMatter) -> LegalMatterResponse:
    service = LegalMatterService(db)
    return LegalMatterResponse(
        **LegalMatterResponse.model_validate(row).model_dump(
            exclude={"risk_escalated_since_linked", "open_linked_issue_warning", "linked_evidence_count", "linked_control_count"}
        ),
        risk_escalated_since_linked=service.get_escalation_status(org_id, row),
        open_linked_issue_warning=service.get_open_linked_issue_warning(org_id, row),
        linked_evidence_count=service.count_linked_evidence(org_id, row.id),
        linked_control_count=service.count_linked_controls(org_id, row.id),
    )


@router.post("", response_model=LegalMatterResponse, status_code=status.HTTP_201_CREATED)
def create_legal_matter(
    payload: LegalMatterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).create_matter(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.get("", response_model=list[LegalMatterResponse])
def list_legal_matters(
    status_filter: str | None = Query(default=None, alias="status"),
    matter_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:read")),
) -> list[LegalMatterResponse]:
    rows = LegalMatterService(db).list_matters(
        organization.id,
        status_value=status_filter,
        matter_type=matter_type,
        skip=skip,
        limit=limit,
    )
    return [_read(db, organization.id, row) for row in rows]


@router.get("/{matter_id}", response_model=LegalMatterResponse)
def get_legal_matter(
    matter_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:read")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).get_matter(organization.id, matter_id)
    return _read(db, organization.id, row)


@router.patch("/{matter_id}", response_model=LegalMatterResponse)
def update_legal_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).update_matter(organization.id, matter_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.post("/{matter_id}/link-risk", response_model=LegalMatterResponse)
def link_risk_to_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterLinkRiskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).link_risk(organization.id, matter_id, payload.risk_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.delete("/{matter_id}/link-risk", response_model=LegalMatterResponse)
def unlink_risk_from_matter(
    matter_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).unlink_risk(organization.id, matter_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.post("/{matter_id}/link-issue", response_model=LegalMatterResponse)
def link_issue_to_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterLinkIssueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).link_issue(organization.id, matter_id, payload.issue_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.delete("/{matter_id}/link-issue", response_model=LegalMatterResponse)
def unlink_issue_from_matter(
    matter_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).unlink_issue(organization.id, matter_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.post("/{matter_id}/link-evidence", response_model=LegalMatterEvidenceLinkRead, status_code=status.HTTP_201_CREATED)
def link_evidence_to_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterLinkEvidenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterEvidenceLinkRead:
    link = LegalMatterService(db).link_evidence(organization.id, matter_id, payload.evidence_id, current_user.id)
    db.commit()
    db.refresh(link)
    return LegalMatterEvidenceLinkRead.model_validate(link)


@router.delete("/{matter_id}/link-evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_evidence_from_matter(
    matter_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> None:
    LegalMatterService(db).unlink_evidence(organization.id, matter_id, evidence_id, current_user.id)
    db.commit()


@router.get("/{matter_id}/link-evidence", response_model=list[LegalMatterEvidenceLinkRead])
def list_matter_linked_evidence(
    matter_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:read")),
) -> list[LegalMatterEvidenceLinkRead]:
    rows = LegalMatterService(db).list_linked_evidence(organization.id, matter_id)
    return [LegalMatterEvidenceLinkRead.model_validate(row) for row in rows]


@router.post("/{matter_id}/link-control", response_model=LegalMatterControlLinkRead, status_code=status.HTTP_201_CREATED)
def link_control_to_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterLinkControlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterControlLinkRead:
    link = LegalMatterService(db).link_control(organization.id, matter_id, payload.control_id, current_user.id)
    db.commit()
    db.refresh(link)
    return LegalMatterControlLinkRead.model_validate(link)


@router.delete("/{matter_id}/link-control/{control_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_control_from_matter(
    matter_id: uuid.UUID,
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> None:
    LegalMatterService(db).unlink_control(organization.id, matter_id, control_id, current_user.id)
    db.commit()


@router.get("/{matter_id}/link-control", response_model=list[LegalMatterControlLinkRead])
def list_matter_linked_controls(
    matter_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:read")),
) -> list[LegalMatterControlLinkRead]:
    rows = LegalMatterService(db).list_linked_controls(organization.id, matter_id)
    return [LegalMatterControlLinkRead.model_validate(row) for row in rows]


@router.post("/{matter_id}/status", response_model=LegalMatterResponse)
def change_legal_matter_status(
    matter_id: uuid.UUID,
    payload: LegalMatterStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).change_status(organization.id, matter_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)


@router.post("/{matter_id}/close", response_model=LegalMatterResponse)
def close_legal_matter(
    matter_id: uuid.UUID,
    payload: LegalMatterCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("legal_matters:write")),
) -> LegalMatterResponse:
    row = LegalMatterService(db).close_matter(organization.id, matter_id, confirm=payload.confirm, actor_id=current_user.id)
    db.commit()
    db.refresh(row)
    return _read(db, organization.id, row)
