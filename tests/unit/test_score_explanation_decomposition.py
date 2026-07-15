from __future__ import annotations

"""PG-free guards for causal score explanation.

Covers the exact arithmetic decomposition (Layer 1) for every leaf score type and
the design-§5.4 structural guarantee that a framework PATH leg can never be
presented as a precise numeric delta. Event-enrichment, framework graph paths,
composite recursion, and tenant isolation are covered on real Postgres in
tests/integration/test_score_explanation_engine.py.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.compliance.services.score_explanation_service import (
    LEAF_DECOMPOSITION,
    ScoreExplanationService,
)


def _svc():
    return ScoreExplanationService(None)  # leaf decomposition needs no DB


# The real scoring_service.py leaf formulas (clamped [0,100], rounded).
def _real_score(snapshot_type, r):
    if snapshot_type == "control_health":
        raw = (r["implemented_ratio"] * 0.55 + r["latest_test_pass_ratio"] * 0.45
               - r["needs_review_ratio"] * 0.2 - r["open_high_critical_issue_ratio"] * 0.3) * 100
    elif snapshot_type == "evidence_readiness":
        raw = r["verified_coverage_ratio"] * 100 - r["expired_control_ratio"] * 35 - r["needs_review_evidence_ratio"] * 20
    elif snapshot_type == "risk_posture":
        raw = (100 - r["critical_high_ratio"] * 50 - r["without_owner_ratio"] * 25
               - r["without_controls_ratio"] * 25 + r["accepted_or_mitigated_ratio"] * 10)
    elif snapshot_type == "task_hygiene":
        raw = (r["completion_ratio"] * 0.6 + max(0, 1 - r["overdue_open_ratio"]) * 0.25
               + max(0, 1 - r["urgent_open_ratio"]) * 0.15) * 100
    return raw


_SAMPLES = {
    "control_health": (
        {"implemented_ratio": 0.8, "latest_test_pass_ratio": 0.5, "needs_review_ratio": 0.1, "open_high_critical_issue_ratio": 0.0},
        {"implemented_ratio": 0.4, "latest_test_pass_ratio": 0.5, "needs_review_ratio": 0.2, "open_high_critical_issue_ratio": 0.1},
    ),
    "evidence_readiness": (
        {"verified_coverage_ratio": 0.9, "expired_control_ratio": 0.0, "needs_review_evidence_ratio": 0.1},
        {"verified_coverage_ratio": 0.6, "expired_control_ratio": 0.2, "needs_review_evidence_ratio": 0.3},
    ),
    "risk_posture": (
        {"critical_high_ratio": 0.1, "without_owner_ratio": 0.0, "without_controls_ratio": 0.1, "accepted_or_mitigated_ratio": 0.2},
        {"critical_high_ratio": 0.4, "without_owner_ratio": 0.2, "without_controls_ratio": 0.1, "accepted_or_mitigated_ratio": 0.0},
    ),
    "task_hygiene": (
        {"completion_ratio": 0.8, "overdue_open_ratio": 0.1, "urgent_open_ratio": 0.0},
        {"completion_ratio": 0.5, "overdue_open_ratio": 0.3, "urgent_open_ratio": 0.2},
    ),
}


@pytest.mark.parametrize("snapshot_type", sorted(LEAF_DECOMPOSITION))
def test_raw_score_reproduces_the_real_formula(snapshot_type):
    for ratios in _SAMPLES[snapshot_type]:
        assert abs(ScoreExplanationService.raw_score(snapshot_type, ratios) - _real_score(snapshot_type, ratios)) < 1e-9


@pytest.mark.parametrize("snapshot_type", sorted(LEAF_DECOMPOSITION))
def test_decomposition_sums_exactly_to_the_raw_delta(snapshot_type):
    bd_from, bd_to = _SAMPLES[snapshot_type]
    contribs = _svc()._decompose(snapshot_type, bd_from, bd_to, datetime.now(UTC), datetime.now(UTC), uuid.uuid4())
    total = sum(c.points_delta for c in contribs)
    raw_delta = ScoreExplanationService.raw_score(snapshot_type, bd_to) - ScoreExplanationService.raw_score(snapshot_type, bd_from)
    assert abs(total - raw_delta) < 1e-9  # Σ wᵢ·Δrᵢ == actual delta


def test_framework_path_can_never_be_a_precise_delta():
    """§5.4 structural guarantee: the path-leg schema has no points_delta; the
    precise-contribution schema requires one."""
    from app.compliance.schemas.score_explanation import ContributionOut, FrameworkPathOut

    assert "points_delta" not in FrameworkPathOut.model_fields
    assert FrameworkPathOut.model_fields["kind"].default == "graph_path"
    assert "points_delta" in ContributionOut.model_fields
    # points_delta is required on a contribution (no default) -> a precise leg
    # must always carry a number; a path leg structurally cannot.
    assert ContributionOut.model_fields["points_delta"].is_required()


def test_permission_scope_no_creep():
    from app.services.seed_service import PERMISSIONS, ROLE_PERMISSION_MAP

    assert "score_attribution:read" in PERMISSIONS
    granting = {r for r, codes in ROLE_PERMISSION_MAP.items() if "score_attribution:read" in codes}
    assert granting == {"owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"}


def test_endpoint_registered_and_requires_auth(client):
    # Missing X-Organization-ID -> 400 (route exists + resolves org first, like siblings).
    resp = client.get("/api/v1/scoring/snapshots/control_health/explain-change")
    assert resp.status_code in (400, 401)
    assert client.get("/api/v1/scoring/snapshots/control_health/explain-change/extra-nope").status_code == 404
