import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.compliance.schemas.pbc_audit_findings import (
    PBCBulkCreateRequest,
    PBCBulkCreateResponse,
    PBCRejectRequest,
    PBCRequestResponse,
    PBCSubmitRequest,
)

router = APIRouter(prefix="/compliance", tags=["pbc_requests_v2"])

# --------------------------------------------------------------------------
# Deprecation notice
# --------------------------------------------------------------------------
#
# This surface was built on the ``pbc_requests`` table, a second, parallel PBC
# (Provided-By-Client) model alongside ``pbc_items``  -- the same "two
# disconnected data stores silently disagreeing" bug pattern already fixed
# once for policy-issue-links (see app/api/v1/policy_issue_links.py) and for
# the common-controls/obligations mapping split. Only ``pbc_items`` has a real
# dashboard summary endpoint, soft-delete, and an acceptance-override-reason
# field, and the frontend's Audit Pack dashboard already reads exclusively
# from it -- so any PBC request created through this ``pbc_requests`` surface
# was real data that never showed up anywhere a user could see it.
#
# Migration 0301_pbc_requests_backfill_into_pbc_items backfilled every
# existing ``pbc_requests`` row into ``pbc_items`` (preserving original
# timestamps and status) the one time this ran. Rather than leave this
# surface live to silently diverge again, every endpoint below now returns a
# clear 410 Gone pointing callers at the ``/compliance/pbc-items`` (tag
# ``pbc-items``, app/api/v1/pbc_items.py) equivalent to use instead.

_DEPRECATION_DETAIL = (
    "This pbc_requests_v2 endpoint is deprecated and no longer usable: it wrote to a second, "
    "parallel PBC model that the dashboard and reporting surfaces never read from. All existing "
    "pbc_requests data was backfilled into pbc_items (migration 0301). Use {replacement} instead."
)


def _deprecated(replacement: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=_DEPRECATION_DETAIL.format(replacement=replacement),
    )


@router.post("/audits/{audit_id}/pbc-requests/bulk", response_model=PBCBulkCreateResponse, status_code=status.HTTP_201_CREATED)
def bulk_create_pbc_requests(audit_id: uuid.UUID, payload: PBCBulkCreateRequest) -> PBCBulkCreateResponse:
    _deprecated("POST /compliance/pbc-items (once per item; there is no bulk-create on pbc-items)")


@router.get("/audits/{audit_id}/pbc-requests", response_model=list[PBCRequestResponse])
def list_pbc_requests_for_audit(
    audit_id: uuid.UUID,
    status_value: str | None = Query(default=None, alias="status"),
    assigned_to: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> list[PBCRequestResponse]:
    _deprecated("GET /compliance/pbc-items/engagement/{engagement_id}")


@router.get("/pbc-requests/{request_id}", response_model=PBCRequestResponse)
def get_pbc_request(request_id: uuid.UUID) -> PBCRequestResponse:
    _deprecated("GET /compliance/pbc-items/{item_id}")


@router.post("/pbc-requests/{request_id}/submit", response_model=PBCRequestResponse)
def submit_pbc_request(request_id: uuid.UUID, payload: PBCSubmitRequest) -> PBCRequestResponse:
    _deprecated("POST /compliance/pbc-items/{item_id}/submit")


@router.post("/pbc-requests/{request_id}/accept", response_model=PBCRequestResponse)
def accept_pbc_request(request_id: uuid.UUID) -> PBCRequestResponse:
    _deprecated("POST /compliance/pbc-items/{item_id}/accept")


@router.post("/pbc-requests/{request_id}/reject", response_model=PBCRequestResponse)
def reject_pbc_request(request_id: uuid.UUID, payload: PBCRejectRequest) -> PBCRequestResponse:
    _deprecated("POST /compliance/pbc-items/{item_id}/reject")
