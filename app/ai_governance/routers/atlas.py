from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_governance.services.atlas_assessment_service import ATLAS_TACTICS, AtlasAssessmentService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.atlas_technique import AtlasTechnique
from app.models.membership import Membership
from app.models.organization import Organization

atlas_router = APIRouter(prefix="/ai-governance/atlas", tags=["ai-governance-atlas"])
systems_router = APIRouter(prefix="/ai-governance/systems", tags=["ai-governance-atlas"])


def _technique_to_payload(row: AtlasTechnique) -> dict[str, object]:
    return {
        "id": str(row.id),
        "atlas_id": row.atlas_id,
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "tactic_code": row.tactic_code,
        "name": row.name,
        "description": row.description,
        "is_subtechnique": row.is_subtechnique,
        "mitigations": row.mitigations or [],
        "detection_signals": row.detection_signals or [],
        "case_studies": row.case_studies or [],
        "severity_indicator": row.severity_indicator,
    }


@atlas_router.get("/techniques")
def list_techniques(
    tactic_code: str | None = Query(default=None),
    include_sub: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[dict[str, object]]:
    rows = AtlasAssessmentService(db).list_techniques(tactic_code=tactic_code, include_subtechniques=include_sub)
    return [_technique_to_payload(row) for row in rows]


@atlas_router.get("/techniques/{technique_id}")
def get_technique(
    technique_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict[str, object]:
    row = AtlasAssessmentService(db).get_technique(technique_id)
    return _technique_to_payload(row)


@atlas_router.get("/tactics")
def get_tactics(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[dict[str, object]]:
    summary = AtlasAssessmentService(db).tactics_summary()
    known = {item["tactic_code"] for item in summary}
    for tactic in ATLAS_TACTICS:
        if tactic not in known:
            summary.append({"tactic_code": tactic, "technique_count": 0})
    summary.sort(key=lambda item: ATLAS_TACTICS.index(str(item["tactic_code"])))
    return summary


@systems_router.post("/{system_id}/atlas-assessment")
def assess_system_exposure(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> dict:
    # Mutating: persists ai_systems.atlas_risk_score and writes governance/audit
    # events, so this requires a write permission rather than compliance:read.
    return AtlasAssessmentService(db).assess_system_exposure(organization.id, system_id)


@systems_router.get("/{system_id}/atlas-mitigations")
def get_system_mitigations(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict:
    return AtlasAssessmentService(db).get_mitigations_for_system(organization.id, system_id)
