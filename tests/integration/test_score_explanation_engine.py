from __future__ import annotations

"""Causal score explanation -- Postgres integration/E2E test (complivibe_test_user).

Real schema via `alembic upgrade head`. Covers: Layer 2 event enrichment with a
real triggering entity; graceful no-fabrication fallback where no event exists;
the §5.4 framework graph-PATH leg (distinct from a precise delta); composite
recursion; arithmetic faithfulness to stored scores; and tenant isolation.

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_score_explain_test \
    PYTHONPATH=. .venv/bin/pytest tests/integration/test_score_explanation_engine.py -m postgres_smoke -v
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.compliance.services.score_explanation_service import ScoreExplanationService
from app.core.event_bus import EventType

REPO_ROOT = Path(__file__).resolve().parents[2]
T1 = datetime.now(UTC) - timedelta(hours=3)
T2 = datetime.now(UTC) - timedelta(hours=1)
T_EVENT = datetime.now(UTC) - timedelta(hours=2)  # strictly within (T1, T2]


@pytest.fixture(scope="module")
def pg_sessionmaker():
    db_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL not set; skipping score-explanation PG test")
    url = make_url(db_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("not PostgreSQL")
    name = url.database
    assert "test" in name and url.username != "complivibe_user"
    admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"), {"n": name})
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    env = os.environ.copy(); env["DATABASE_URL"] = db_url; env["PYTHONPATH"] = "."
    proc = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    engine = sa.create_engine(db_url)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()
        admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"), {"n": name})
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@pytest.fixture
def db(pg_sessionmaker):
    s = pg_sessionmaker()
    try:
        yield s
    finally:
        s.rollback(); s.close()


# ---- seed helpers ----
def _org(db):
    from app.models.organization import Organization
    o = Organization(name=f"Org {uuid.uuid4().hex[:8]}"); db.add(o); db.flush(); return o


def _ch_breakdown(impl=0.0, passing=0.0, nr=0.0, issue=0.0):
    return {"implemented_ratio": impl, "latest_test_pass_ratio": passing,
            "needs_review_ratio": nr, "open_high_critical_issue_ratio": issue}


def _ch_score(bd):
    return round(55 * bd["implemented_ratio"] + 45 * bd["latest_test_pass_ratio"]
                 - 20 * bd["needs_review_ratio"] - 30 * bd["open_high_critical_issue_ratio"])


def _snap(db, org, stype, breakdown, score, calc_at):
    from app.models.score_snapshot import ScoreSnapshot
    r = ScoreSnapshot(organization_id=org.id, snapshot_type=stype, score=score, grade="C",
                      inputs_json={}, breakdown_json=breakdown, calculated_at=calc_at)
    db.add(r); db.flush(); return r


def _control(db, org, status="failed"):
    from app.models.control import Control
    c = Control(organization_id=org.id, title="Ctrl", status=status); db.add(c); db.flush(); return c


def _event(db, org, etype, entity_type, entity_id, before, after, at=T_EVENT):
    from app.models.domain_event import DomainEvent
    e = DomainEvent(organization_id=org.id, event_type=etype, entity_type=entity_type, entity_id=entity_id,
                    previous_value=before, new_value=after, triggered_by="test", occurred_at=at)
    db.add(e); db.flush(); return e


def _framework_obligation_edge(db, org, control):
    from app.models.framework import Framework
    from app.models.obligation import Obligation
    from app.models.control_obligation_mapping import ControlObligationMapping
    fw = Framework(code="GDPR", name="GDPR", category="privacy", jurisdiction="EU"); db.add(fw); db.flush()
    ob = Obligation(framework_id=fw.id, reference_code="Art.32", title="Security", jurisdiction="EU")
    db.add(ob); db.flush()
    db.add(ControlObligationMapping(organization_id=org.id, control_id=control.id, obligation_id=ob.id, status="active"))
    db.flush()
    return fw, ob


# ---- tests ----
@pytest.mark.postgres_smoke
def test_layer2_event_coverage_enriches_with_real_entity_and_arithmetic_is_exact(db):
    org = _org(db)
    control = _control(db, org, status="failed")
    bd1, bd2 = _ch_breakdown(impl=0.8), _ch_breakdown(impl=0.4)
    _snap(db, org, "control_health", bd1, _ch_score(bd1), T1)   # score 44
    _snap(db, org, "control_health", bd2, _ch_score(bd2), T2)   # score 22
    _event(db, org, EventType.CONTROL_STATUS_CHANGED, "control", control.id, "implemented", "failed")
    db.commit()

    exp = ScoreExplanationService(db).explain_snapshot_change(org_id=org.id, snapshot_type="control_health")
    assert exp.observed_delta == -22.0
    # Σ contributions == raw_delta (exact); raw scores round-trip to stored ints.
    assert abs(sum(c.points_delta for c in exp.contributions) - exp.raw_delta) < 1e-9
    assert round(ScoreExplanationService.raw_score("control_health", bd1)) == 44
    assert round(ScoreExplanationService.raw_score("control_health", bd2)) == 22

    impl = next(c for c in exp.contributions if c.component == "implemented_ratio")
    assert impl.points_delta == pytest.approx(-22.0)
    event_causes = [c for c in impl.causes if c.cause_type == "event"]
    assert event_causes and event_causes[0].entity_id == control.id   # REAL triggering entity, not just arithmetic


@pytest.mark.postgres_smoke
def test_no_event_coverage_falls_back_without_fabricating_a_cause(db):
    org = _org(db)
    bd1 = _ch_breakdown(impl=0.6, issue=0.0)   # score 33
    bd2 = _ch_breakdown(impl=0.6, issue=0.2)   # score 27 (issue changes emit NO event)
    _snap(db, org, "control_health", bd1, _ch_score(bd1), T1)
    _snap(db, org, "control_health", bd2, _ch_score(bd2), T2)
    db.commit()

    exp = ScoreExplanationService(db).explain_snapshot_change(org_id=org.id, snapshot_type="control_health")
    issue = next(c for c in exp.contributions if c.component == "open_high_critical_issue_ratio")
    assert issue.causes and all(c.cause_type == "underlying_data_changed" for c in issue.causes)
    # NOT fabricated: the fallback names no specific triggering entity.
    assert all(c.entity_id is None and c.entity_type is None for c in issue.causes)


@pytest.mark.postgres_smoke
def test_framework_leg_is_a_graph_path_not_a_delta(db):
    org = _org(db)
    control = _control(db, org, status="failed")
    _framework_obligation_edge(db, org, control)
    bd1, bd2 = _ch_breakdown(impl=0.8), _ch_breakdown(impl=0.4)
    _snap(db, org, "control_health", bd1, _ch_score(bd1), T1)
    _snap(db, org, "control_health", bd2, _ch_score(bd2), T2)
    _event(db, org, EventType.CONTROL_STATUS_CHANGED, "control", control.id, "implemented", "failed")
    db.commit()

    exp = ScoreExplanationService(db).explain_snapshot_change(org_id=org.id, snapshot_type="control_health")
    impl = next(c for c in exp.contributions if c.component == "implemented_ratio")
    control_cause = next(c for c in impl.causes if c.entity_type == "control")
    assert control_cause.framework_paths, "expected a framework graph-path leg on the control cause"
    fp = control_cause.framework_paths[0]
    # §5.4: it is a PATH, clearly typed, with NO numeric delta.
    assert fp.kind == "graph_path"
    assert any(ob.get("reference_code") == "Art.32" for ob in fp.obligations)
    assert not hasattr(fp, "points_delta")           # the dataclass carries no delta
    assert isinstance(impl.points_delta, float)       # while the contribution IS a precise delta
    # And the serialized contract keeps them structurally distinct:
    from app.compliance.schemas.score_explanation import explanation_out
    out = explanation_out(exp)
    out_impl = next(c for c in out.contributions if c.component == "implemented_ratio")
    out_fp = next(c for c in out_impl.causes if c.entity_type == "control").framework_paths[0]
    assert "points_delta" not in out_fp.model_dump() and out_fp.kind == "graph_path"


@pytest.mark.postgres_smoke
def test_composite_recursion_decomposes_to_the_moved_leaf_term(db):
    org = _org(db)
    ch1, ch2 = _ch_breakdown(impl=0.8), _ch_breakdown(impl=0.4)   # control_health 44 -> 22
    _snap(db, org, "control_health", ch1, _ch_score(ch1), T1)
    _snap(db, org, "control_health", ch2, _ch_score(ch2), T2)
    comp1 = {"components": {"control_health": 44, "evidence_readiness": 50, "risk_posture": 60},
             "weights": {"control_health": 0.4, "evidence_readiness": 0.4, "risk_posture": 0.2}}
    comp2 = {"components": {"control_health": 22, "evidence_readiness": 50, "risk_posture": 60},
             "weights": {"control_health": 0.4, "evidence_readiness": 0.4, "risk_posture": 0.2}}
    _snap(db, org, "compliance_readiness", comp1, round(44 * .4 + 50 * .4 + 60 * .2), T1)
    _snap(db, org, "compliance_readiness", comp2, round(22 * .4 + 50 * .4 + 60 * .2), T2)
    db.commit()

    exp = ScoreExplanationService(db).explain_snapshot_change(org_id=org.id, snapshot_type="compliance_readiness")
    ch = next(c for c in exp.contributions if c.component == "control_health")
    assert ch.kind == "component_score" and ch.points_delta == pytest.approx(0.4 * (22 - 44))
    sub = next(s for s in ch.sub_contributions if s.component == "implemented_ratio")
    assert sub.points_delta == pytest.approx(-22.0)


@pytest.mark.postgres_smoke
def test_tenant_isolation(db):
    org_a, org_b = _org(db), _org(db)
    ctrl_a = _control(db, org_a); ctrl_b = _control(db, org_b)
    for org in (org_a, org_b):
        b1, b2 = _ch_breakdown(impl=0.8), _ch_breakdown(impl=0.4)
        _snap(db, org, "control_health", b1, _ch_score(b1), T1)
        _snap(db, org, "control_health", b2, _ch_score(b2), T2)
    _event(db, org_a, EventType.CONTROL_STATUS_CHANGED, "control", ctrl_a.id, "implemented", "failed")
    _event(db, org_b, EventType.CONTROL_STATUS_CHANGED, "control", ctrl_b.id, "implemented", "failed")
    db.commit()

    exp = ScoreExplanationService(db).explain_snapshot_change(org_id=org_a.id, snapshot_type="control_health")
    impl = next(c for c in exp.contributions if c.component == "implemented_ratio")
    reached = {c.entity_id for c in impl.causes if c.entity_id}
    assert ctrl_a.id in reached and ctrl_b.id not in reached   # no cross-org event bleed
