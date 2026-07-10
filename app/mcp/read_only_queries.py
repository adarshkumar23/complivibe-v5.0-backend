"""Read-only query functions backing the MCP server (app.mcp.server). Every function
here only reads from the database — no inserts, updates, or deletes — per the narrow,
read-only scope agreed for the MCP integration (framework status, obligation counts, risk
summary). These reuse existing services rather than duplicating their logic."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.board_scorecard_service import BoardScorecardService
from app.models.framework import Framework
from app.services.applicability_service import ApplicabilityService


def _require_framework_by_code(db: Session, framework_code: str) -> Framework:
    framework = db.execute(select(Framework).where(Framework.code == framework_code)).scalar_one_or_none()
    if framework is None:
        raise ValueError(f"No framework found with code '{framework_code}'")
    return framework


def get_framework_status(db: Session, organization_id: uuid.UUID, framework_code: str) -> dict:
    framework = _require_framework_by_code(db, framework_code)
    try:
        summary = ApplicabilityService(db).evaluation_summary(organization_id=organization_id, framework_id=framework.id)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
    return {
        "framework_code": framework.code,
        "framework_name": framework.name,
        "framework_status": framework.status,
        "framework_version": framework.version,
        "coverage_level": framework.coverage_level,
        "jurisdiction": framework.jurisdiction,
        **summary,
    }


def get_obligation_counts(db: Session, organization_id: uuid.UUID, framework_code: str) -> dict:
    framework = _require_framework_by_code(db, framework_code)
    try:
        summary = ApplicabilityService(db).evaluation_summary(organization_id=organization_id, framework_id=framework.id)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
    return {
        "framework_code": framework.code,
        "total_obligations": summary["total_obligations"],
        "applicable_obligations": summary["applicable_obligations"],
        "not_applicable_obligations": summary["not_applicable_obligations"],
        "needs_review_obligations": summary["needs_review_obligations"],
        "unknown_obligations": summary["unknown_obligations"],
    }


def get_risk_summary(db: Session, organization_id: uuid.UUID, business_unit_id: uuid.UUID | None = None) -> dict:
    return BoardScorecardService(db)._build_posture_summary(organization_id, business_unit_id)
