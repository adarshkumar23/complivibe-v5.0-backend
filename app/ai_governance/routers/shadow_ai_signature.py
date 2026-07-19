"""Signature-scored shadow-AI discovery endpoints (patent graft).

Mounted alongside -- not instead of -- core's existing shadow-AI router at
``/ai-governance/shadow-ai``. This router owns ``/ai-governance/shadow-ai-signatures``
and uses its own ``shadow_ai_signature:*`` permission codes, deliberately
distinct from the ``ai_systems:*`` codes that govern core's feature, so a grant
never silently spans both systems.

Every endpoint enforces a real permission via core's require_permission; the
upstream repo shipped an always-allow stub.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.shadow_ai_signature.detection_service import (
    ShadowAISignatureService,
)
from app.core.deps import get_current_organization, get_current_user, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.shadow_ai_signature import (
    ShadowAIFederatedObservation,
    ShadowAISignatureDetection,
    ShadowAISignatureRegistry,
)
from app.models.user import User

router = APIRouter(
    prefix="/ai-governance/shadow-ai-signatures", tags=["ai-governance-shadow-ai-signatures"]
)

_REVIEW_STATUSES = {"under_review", "confirmed", "dismissed", "escalated"}


class TelemetryIngestRequest(BaseModel):
    tier: int = Field(ge=1, le=3)
    event_type: str
    raw_signal: dict
    source_system_label: str | None = None
    matched_signature_id: uuid.UUID | None = None


class ReviewRequest(BaseModel):
    status: str
    reason: str | None = None


class SuppressRequest(BaseModel):
    signature_id: uuid.UUID
    reason: str


class FederatedSubmitRequest(BaseModel):
    hostname: str
    behavioral_score: float | None = Field(default=None, ge=0.0, le=1.0)


class IdpScanRequest(BaseModel):
    oauth_grants: list[dict]


@router.get("/signatures")
def list_signatures(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:read")),
) -> list[dict]:
    _ = organization, membership
    rows = db.execute(
        select(ShadowAISignatureRegistry).order_by(ShadowAISignatureRegistry.provider_name.asc())
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "slug": r.slug,
            "provider_name": r.provider_name,
            "category": r.category,
            "risk_level": r.risk_level,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/telemetry", status_code=status.HTTP_201_CREATED)
def ingest_telemetry(
    payload: TelemetryIngestRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:write")),
) -> dict:
    _ = membership
    event, duplicate = ShadowAISignatureService(db).ingest_telemetry(
        organization_id=organization.id,
        tier=payload.tier,
        event_type=payload.event_type,
        raw_signal=payload.raw_signal,
        source_system_label=payload.source_system_label,
        matched_signature_id=payload.matched_signature_id,
    )
    db.commit()
    return {"event_id": str(event.id) if event else None, "duplicate": duplicate}


@router.post("/rescan")
def rescan(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(require_permission("shadow_ai_signature:write")),
) -> dict:
    _ = membership
    result = ShadowAISignatureService(db).recompute_detections(
        organization_id=organization.id, actor_user_id=current_user.id
    )
    db.commit()
    return result


@router.post("/decay")
def run_decay(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:write")),
) -> dict:
    _ = membership
    result = ShadowAISignatureService(db).apply_decay(organization_id=organization.id)
    db.commit()
    return result


@router.get("/detections")
def list_detections(
    status_filter: str | None = Query(default=None, alias="status"),
    include_stale: bool = Query(default=True),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:read")),
) -> list[dict]:
    _ = membership
    stmt = select(ShadowAISignatureDetection).where(
        ShadowAISignatureDetection.organization_id == organization.id
    )
    if status_filter:
        stmt = stmt.where(ShadowAISignatureDetection.status == status_filter)
    if not include_stale:
        stmt = stmt.where(ShadowAISignatureDetection.is_stale.is_(False))
    rows = db.execute(stmt.order_by(ShadowAISignatureDetection.confidence_score.desc())).scalars().all()
    return [
        {
            "id": str(r.id),
            "provider_name": r.provider_name,
            "confidence_score": float(r.confidence_score),
            "confidence_band": r.confidence_band,
            "status": r.status,
            "event_count": r.event_count,
            "is_stale": r.is_stale,
            "first_detected_at": r.first_detected_at.isoformat(),
            "last_observed_at": r.last_observed_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/detections/{detection_id}")
def get_detection(
    detection_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:read")),
) -> dict:
    _ = membership
    row = db.execute(
        select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.id == detection_id,
            ShadowAISignatureDetection.organization_id == organization.id,
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return {
        "id": str(row.id),
        "provider_name": row.provider_name,
        "confidence_score": float(row.confidence_score),
        "confidence_band": row.confidence_band,
        "detection_basis": row.detection_basis_json,
        "status": row.status,
        "is_stale": row.is_stale,
    }


@router.post("/detections/{detection_id}/review")
def review_detection(
    detection_id: uuid.UUID,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(require_permission("shadow_ai_signature:review")),
) -> dict:
    _ = membership
    if payload.status not in _REVIEW_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {sorted(_REVIEW_STATUSES)}",
        )
    row = ShadowAISignatureService(db).review_detection(
        organization_id=organization.id,
        detection_id=detection_id,
        new_status=payload.status,
        actor_user_id=current_user.id,
        reason=payload.reason,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.post("/suppressions", status_code=status.HTTP_201_CREATED)
def suppress_signature(
    payload: SuppressRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(require_permission("shadow_ai_signature:review")),
) -> dict:
    _ = membership
    row = ShadowAISignatureService(db).suppress_signature(
        organization_id=organization.id,
        signature_id=payload.signature_id,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    db.commit()
    return {"id": str(row.id), "signature_id": str(row.signature_id)}


@router.post("/idp-connections/{connection_id}/scan")
def scan_idp_connection(
    connection_id: uuid.UUID,
    payload: IdpScanRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(require_permission("shadow_ai_signature:admin")),
) -> dict:
    _ = membership
    result = ShadowAISignatureService(db).record_idp_scan(
        organization_id=organization.id,
        connection_id=connection_id,
        oauth_grants=payload.oauth_grants,
        actor_user_id=current_user.id,
    )
    if result.get("error") == "connection_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IdP connection not found")
    db.commit()
    return result


@router.post("/federated/submit", status_code=status.HTTP_201_CREATED)
def submit_federated(
    payload: FederatedSubmitRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:write")),
) -> dict:
    _ = membership
    result = ShadowAISignatureService(db).submit_federated_observation(
        organization_id=organization.id,
        hostname=payload.hostname,
        behavioral_score=payload.behavioral_score,
    )
    db.commit()
    return result


@router.get("/federated/candidates")
def list_federated_candidates(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("shadow_ai_signature:admin")),
) -> list[dict]:
    _ = organization, membership
    rows = db.execute(
        select(ShadowAIFederatedObservation)
        .where(ShadowAIFederatedObservation.status == "candidate")
        .order_by(ShadowAIFederatedObservation.observation_count.desc())
    ).scalars().all()
    # Cross-tenant aggregate: hostname + distinct-org count only, never which orgs.
    return [
        {
            "hostname": r.hostname,
            "distinct_orgs": r.observation_count,
            "status": r.status,
            "first_observed_at": r.first_observed_at.isoformat(),
        }
        for r in rows
    ]
