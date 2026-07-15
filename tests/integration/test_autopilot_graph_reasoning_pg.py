from __future__ import annotations

"""Phase 5 -- Autopilot graph-dependency source (Source B) + tenant isolation.

Source B uses Phase 2's recursive-CTE graph traversal (Postgres-only), so it is
tested against a real PostgreSQL DB built with `alembic upgrade head`, using the
dedicated complivibe_test_user (standing rule). The rest of the phase is covered
on SQLite in tests/unit/test_autopilot_graph_reasoning.py.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.services.ai_system_risk_assessment_service import AISystemRiskAssessmentService

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pg_sessionmaker():
    db_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL not set; skipping autopilot graph-dependency PG test")
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


def _org(db):
    from app.models.organization import Organization
    from app.models.organization_governance_setting import OrganizationGovernanceSetting
    from app.models.user import User

    org = Organization(name=f"Org {uuid.uuid4().hex[:8]}"); db.add(org); db.flush()
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", is_active=True, status="active")
    db.add(user); db.flush()
    db.add(OrganizationGovernanceSetting(organization_id=org.id, autopilot_graph_reasoning_enabled=True))
    db.flush()
    return org, user


def _stale_vendor_dependency(db, org, user):
    """A vendor with an overdue assessment, graph-connected to an open high risk."""
    from app.models.control import Control
    from app.models.risk import Risk
    from app.models.risk_control_link import RiskControlLink
    from app.models.vendor import Vendor
    from app.models.vendor_assessment import VendorAssessment
    from app.models.vendor_control_link import VendorControlLink

    vendor = Vendor(organization_id=org.id, name="V", vendor_type="saas", owner_user_id=user.id,
                    status="active", risk_tier="high")
    db.add(vendor); db.flush()
    db.add(VendorAssessment(organization_id=org.id, vendor_id=vendor.id, title="A", assessment_type="periodic",
                            created_by_user_id=user.id, status="in_progress", due_date=date.today() - timedelta(days=60)))
    control = Control(organization_id=org.id, title="C", status="failed"); db.add(control); db.flush()
    risk = Risk(organization_id=org.id, title="R", severity="critical", status="in_treatment"); db.add(risk); db.flush()
    db.add(VendorControlLink(organization_id=org.id, vendor_id=vendor.id, control_id=control.id,
                             status="active", linked_by_user_id=user.id))
    db.add(RiskControlLink(organization_id=org.id, risk_id=risk.id, control_id=control.id, status="active"))
    db.flush()
    return vendor, control, risk


@pytest.mark.postgres_smoke
def test_source_b_graph_dependency_generates_flag_and_routes_to_approval(db):
    org, user = _org(db)
    vendor, control, risk = _stale_vendor_dependency(db, org, user)
    db.commit()

    svc = AISystemRiskAssessmentService(db)
    candidates = svc.generate_cross_domain_candidate_actions(organization_id=org.id)
    b = [c for c in candidates if c["candidate_source"] == "graph_dependency"]
    assert len(b) == 1
    assert b[0]["action_key"] == "flag_stale_evidence"      # allow-listed low-risk action
    assert str(b[0]["target_entity_id"]) == str(vendor.id)  # via org-scoped graph traversal

    intent = svc.create_cross_domain_execution_intent(
        organization_id=org.id, candidate_action_json=b[0], actor_user_id=user.id,
    )
    db.commit()
    assert intent.source_type == "cross_domain_candidate_action"
    assert intent.intent_status == "approval_required"     # NEVER auto-executed
    assert intent.plan_payload_json["candidate_action"]["risk_tier"] == "low"


@pytest.mark.postgres_smoke
def test_tenant_isolation_shared_vendor_does_not_leak(db):
    """Reuses Phase 2's shared-vendor isolation: Org B cannot generate a candidate
    about Org A's stale vendor even if B's control links to the same vendor id."""
    from app.models.control import Control
    from app.models.risk_control_link import RiskControlLink
    from app.models.risk import Risk
    from app.models.vendor_control_link import VendorControlLink

    org_a, user_a = _org(db)
    vendor, ctrl_a, risk_a = _stale_vendor_dependency(db, org_a, user_a)

    org_b, user_b = _org(db)
    # Org B references the SAME vendor id in ITS OWN edge rows + its own control/risk.
    ctrl_b = Control(organization_id=org_b.id, title="Cb", status="failed"); db.add(ctrl_b); db.flush()
    risk_b = Risk(organization_id=org_b.id, title="Rb", severity="critical", status="in_treatment"); db.add(risk_b); db.flush()
    db.add(VendorControlLink(organization_id=org_b.id, vendor_id=vendor.id, control_id=ctrl_b.id,
                             status="active", linked_by_user_id=user_b.id))
    db.add(RiskControlLink(organization_id=org_b.id, risk_id=risk_b.id, control_id=ctrl_b.id, status="active"))
    db.commit()

    svc = AISystemRiskAssessmentService(db)
    a_candidates = svc.generate_cross_domain_candidate_actions(organization_id=org_a.id)
    assert any(c["candidate_source"] == "graph_dependency" for c in a_candidates)

    # Org B has NO overdue vendor assessment of its own (the vendor + its assessment
    # belong to Org A), so it generates ZERO graph-dependency candidates -- no leak.
    b_candidates = svc.generate_cross_domain_candidate_actions(organization_id=org_b.id)
    assert [c for c in b_candidates if c["candidate_source"] == "graph_dependency"] == []
