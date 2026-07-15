from __future__ import annotations

"""
Compound-exposure recommendation engine -- Postgres integration/E2E test.

Runs against a real PostgreSQL DB built with `alembic upgrade head` (so the real
0304 tables + all entity/edge tables exist). STANDING RULE: uses the dedicated
`complivibe_test_user`, never `complivibe_user`.

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_compound_insight_test \
    PYTHONPATH=. .venv/bin/pytest tests/integration/test_compound_insight_engine.py -m postgres_smoke -v

The AI narrative layer is monkeypatched in every test so the suite is fully
offline and deterministic -- no live Groq call is made here (the live-model check
was done separately). This exercises the templated-first / AI-upgrade contract
without network flakiness or TPM limits.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.compliance.services.compound_insight_detector import CompoundInsightDetector
from app.compliance.services.compound_pattern_registry import PATTERN_A, PATTERN_B, PATTERN_C

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# DB fixture: real schema via alembic upgrade head
# --------------------------------------------------------------------------- #
def _assert_safe(url: URL) -> None:
    name = (url.database or "").strip()
    if not name or name == "complivibe":
        raise AssertionError("Refusing to run against production database name")
    if "test" not in name and "smoke" not in name:
        raise AssertionError(f"Must target a dedicated test DB (got '{name}')")
    if (url.username or "") == "complivibe_user":
        raise AssertionError("Refusing to run as live role complivibe_user")


def _recreate(url: URL) -> None:
    admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = url.database
    with admin.connect() as c:
        c.execute(sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"), {"n": name})
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


@pytest.fixture(scope="module")
def pg_sessionmaker():
    db_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL not set; skipping compound-insight PG test")
    url = make_url(db_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("not PostgreSQL")
    _assert_safe(url)
    _recreate(url)

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "."
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"alembic upgrade head failed:\n{proc.stdout}\n{proc.stderr}"

    engine = sa.create_engine(db_url)
    # Seed the global email templates (incl. compound_insight_surfaced) once.
    from app.services.seed_service import SeedService
    with Session(engine) as s:
        SeedService.ensure_global_email_templates(s)
        s.commit()
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()
        admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"), {"n": url.database})
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{url.database}"'))
        admin.dispose()


@pytest.fixture
def db(pg_sessionmaker):
    session = pg_sessionmaker()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# --------------------------------------------------------------------------- #
# Seed helpers -- real ORM rows. Each test uses a fresh org (isolation).
# --------------------------------------------------------------------------- #
def _new_org(db: Session):
    from app.models.organization import Organization
    from app.models.role import Role
    from app.models.user import User
    from app.models.membership import Membership

    org = Organization(name=f"Org {uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    user = User(email=f"u-{uuid.uuid4().hex[:10]}@example.com", hashed_password="x", is_active=True, status="active")
    db.add(user)
    db.flush()
    role = Role(name="admin", organization_id=org.id, is_system_role=True)
    db.add(role)
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role_id=role.id, status="active"))
    db.flush()
    return org, user


def _control(db, org, user, *, status="failed", title="Ctrl"):
    from app.models.control import Control
    c = Control(organization_id=org.id, title=title, status=status)
    db.add(c); db.flush(); return c


def _vendor(db, org, user, *, name="Vendor"):
    from app.models.vendor import Vendor
    v = Vendor(organization_id=org.id, name=name, vendor_type="saas", owner_user_id=user.id, status="active", risk_tier="high")
    db.add(v); db.flush(); return v


def _overdue_assessment(db, org, user, vendor, *, days_overdue=60):
    from app.models.vendor_assessment import VendorAssessment
    a = VendorAssessment(
        organization_id=org.id, vendor_id=vendor.id, title="Annual", assessment_type="periodic",
        created_by_user_id=user.id, status="in_progress",
        due_date=date.today() - timedelta(days=days_overdue),
    )
    db.add(a); db.flush(); return a


def _risk(db, org, *, severity="critical", status="in_treatment", title="Risk"):
    from app.models.risk import Risk
    r = Risk(organization_id=org.id, title=title, severity=severity, status=status)
    db.add(r); db.flush(); return r


def _evidence(db, org, *, freshness="expired", title="Ev"):
    from app.models.evidence_item import EvidenceItem
    e = EvidenceItem(
        organization_id=org.id, title=title, status="active",
        freshness_status=freshness, valid_until=datetime.now(UTC) - timedelta(days=5),
    )
    db.add(e); db.flush(); return e


def _issue(db, org, user, *, severity="critical", status="open", title="Incident"):
    from app.models.issue import Issue
    i = Issue(
        organization_id=org.id, title=title, description="d", issue_type="security_incident",
        severity=severity, status=status, owner_id=user.id, created_by=user.id,
    )
    db.add(i); db.flush(); return i


def _link_risk_control(db, org, risk, control):
    from app.models.risk_control_link import RiskControlLink
    db.add(RiskControlLink(organization_id=org.id, risk_id=risk.id, control_id=control.id, status="active")); db.flush()


def _link_vendor_control(db, org, user, vendor, control):
    from app.models.vendor_control_link import VendorControlLink
    db.add(VendorControlLink(organization_id=org.id, vendor_id=vendor.id, control_id=control.id, status="active", linked_by_user_id=user.id)); db.flush()


def _link_evidence_control(db, org, evidence, control):
    from app.models.evidence_control_link import EvidenceControlLink
    db.add(EvidenceControlLink(organization_id=org.id, evidence_item_id=evidence.id, control_id=control.id, link_status="active")); db.flush()


def _link_issue_control(db, org, user, issue, control):
    from app.models.issue_control_link import IssueControlLink
    db.add(IssueControlLink(
        organization_id=org.id, issue_id=issue.id, control_id=control.id,
        failure_type="control_failed", linked_by=user.id, linked_at=datetime.now(UTC),
    )); db.flush()


def _seed_pattern_a(db):
    """Failed control + stale vendor + open critical risk, all connected."""
    org, user = _new_org(db)
    control = _control(db, org, user, status="failed")
    vendor = _vendor(db, org, user)
    _overdue_assessment(db, org, user, vendor)
    risk = _risk(db, org, severity="critical", status="in_treatment")
    _link_vendor_control(db, org, user, vendor, control)
    _link_risk_control(db, org, risk, control)
    db.commit()
    return org, user, control, vendor, risk


def _force_ai_fail(monkeypatch, exc=RuntimeError("forced groq failure")):
    from app.ai_governance.services.ai_provider_service import AIProviderService

    def _boom(self, *, org_id, pattern_payload):
        raise exc
    monkeypatch.setattr(AIProviderService, "generate_compound_narrative", _boom)


# --------------------------------------------------------------------------- #
# Required evidence tests
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_end_to_end_detection_persist_notify_audit_and_dedup(db, monkeypatch):
    _force_ai_fail(monkeypatch)  # deterministic template fallback (no network)
    org, user, control, vendor, risk = _seed_pattern_a(db)

    detector = CompoundInsightDetector(db)
    insight, created = detector.detect_and_surface(org.id, PATTERN_A, control.id)
    db.commit()

    # (1) detection fired + persisted with templated narrative
    assert created is True and insight is not None
    assert insight.pattern_id == PATTERN_A.pattern_id
    assert insight.severity == "critical"
    assert insight.status == "surfaced"
    assert insight.narrative_source == "template"          # AI failed -> template kept
    assert insight.templated_narrative and control.title in insight.templated_narrative
    nodes = insight.matched_nodes_json
    assert set(nodes.keys()) == {"anchor", "stale_vendor", "open_risk"}
    assert nodes["anchor"]["entity_id"] == str(control.id)
    assert nodes["stale_vendor"]["entity_id"] == str(vendor.id)
    assert nodes["open_risk"]["entity_id"] == str(risk.id)

    # (2) audit-log entry written
    from app.models.audit_log import AuditLog
    audits = db.execute(sa.select(AuditLog).where(
        AuditLog.organization_id == org.id, AuditLog.action == "compound_insight.surfaced"
    )).scalars().all()
    assert len(audits) == 1 and audits[0].entity_id == insight.id

    # (3) human notification queued (EmailOutbox) to the governance member
    from app.models.email_outbox import EmailOutbox
    emails = db.execute(sa.select(EmailOutbox).where(EmailOutbox.organization_id == org.id)).scalars().all()
    assert len(emails) == 1
    assert emails[0].recipient_user_id == user.id

    # (4) dedup: a second identical detection must NOT create a new insight or re-notify
    from app.models.compound_insight import CompoundInsight
    insight2, created2 = detector.detect_and_surface(org.id, PATTERN_A, control.id)
    db.commit()
    assert created2 is False
    org_insights = db.execute(
        sa.select(CompoundInsight).where(CompoundInsight.organization_id == org.id)
    ).scalars().all()
    assert len(org_insights) == 1
    assert org_insights[0].detection_count == 2            # bumped, not duplicated
    emails_after = db.execute(sa.select(EmailOutbox).where(EmailOutbox.organization_id == org.id)).scalars().all()
    assert len(emails_after) == 1                          # no re-notification


@pytest.mark.postgres_smoke
def test_auto_resolve_when_conjunction_breaks(db, monkeypatch):
    _force_ai_fail(monkeypatch)
    org, user, control, vendor, risk = _seed_pattern_a(db)
    detector = CompoundInsightDetector(db)
    insight, created = detector.detect_and_surface(org.id, PATTERN_A, control.id)
    db.commit()
    assert created and insight.status == "surfaced"

    # Break the conjunction: control is remediated (no longer failed).
    control.status = "implemented"
    db.commit()

    resolved = detector.auto_resolve_org(org.id)
    db.commit()
    assert resolved == 1
    db.refresh(insight)
    assert insight.status == "auto_resolved"
    assert insight.resolved_at is not None


@pytest.mark.postgres_smoke
def test_ai_failure_still_surfaces_with_templated_narrative(db, monkeypatch):
    # Force a timeout-like failure in the AI layer; the detection must still surface.
    _force_ai_fail(monkeypatch, exc=TimeoutError("groq timeout"))
    org, user, control, vendor, risk = _seed_pattern_a(db)
    detector = CompoundInsightDetector(db)
    insight, created = detector.detect_and_surface(org.id, PATTERN_A, control.id)
    db.commit()
    assert created and insight is not None
    assert insight.narrative_source == "template"
    assert insight.narrative_headline is None
    assert insight.templated_narrative


@pytest.mark.postgres_smoke
def test_ai_success_upgrades_narrative(db, monkeypatch):
    from app.ai_governance.services.ai_provider_service import AIProviderService

    def _ok(self, *, org_id, pattern_payload):
        return ({"headline": "Compounding exposure", "summary": "Three connected weaknesses.",
                 "recommended_actions": ["Re-test the control", "Reassess the vendor"]}, "groq", False)
    monkeypatch.setattr(AIProviderService, "generate_compound_narrative", _ok)

    org, user, control, vendor, risk = _seed_pattern_a(db)
    detector = CompoundInsightDetector(db)
    insight, created = detector.detect_and_surface(org.id, PATTERN_A, control.id)
    db.commit()
    assert created
    assert insight.narrative_source == "ai"
    assert insight.narrative_headline == "Compounding exposure"
    assert insight.provider_used == "groq"
    assert insight.recommended_actions_json == ["Re-test the control", "Reassess the vendor"]


@pytest.mark.postgres_smoke
def test_tenant_isolation_shared_vendor_does_not_cross(db, monkeypatch):
    _force_ai_fail(monkeypatch)
    # Org A: full pattern A. Org B: its own control + risk, referencing the SAME
    # vendor id in its own edge rows (the shared-entity hazard).
    org_a, user_a = _new_org(db)
    ctrl_a = _control(db, org_a, user_a, status="failed", title="A-ctrl")
    vendor = _vendor(db, org_a, user_a, name="SharedVendor")
    _overdue_assessment(db, org_a, user_a, vendor)
    risk_a = _risk(db, org_a, title="A-risk")
    _link_vendor_control(db, org_a, user_a, vendor, ctrl_a)
    _link_risk_control(db, org_a, risk_a, ctrl_a)

    org_b, user_b = _new_org(db)
    ctrl_b = _control(db, org_b, user_b, status="failed", title="B-ctrl")
    risk_b = _risk(db, org_b, title="B-risk")
    # Org B references the SAME vendor uuid in its own edge row + its own risk.
    _link_vendor_control(db, org_b, user_b, vendor, ctrl_b)
    _link_risk_control(db, org_b, risk_b, ctrl_b)
    db.commit()

    detector = CompoundInsightDetector(db)
    insight_a, created_a = detector.detect_and_surface(org_a.id, PATTERN_A, ctrl_a.id)
    db.commit()
    assert created_a
    ids_a = {n["entity_id"] for n in insight_a.matched_nodes_json.values()}
    assert str(risk_b.id) not in ids_a and str(ctrl_b.id) not in ids_a  # no org-B bleed

    # Org B's control has NO overdue vendor of its OWN (the vendor belongs to org A);
    # loading vendor under org B returns None -> pattern must NOT match for org B.
    insight_b, created_b = detector.detect_and_surface(org_b.id, PATTERN_A, ctrl_b.id)
    db.commit()
    assert created_b is False and insight_b is None


@pytest.mark.postgres_smoke
def test_event_listener_flags_candidate_without_traversal_or_ai(db, monkeypatch):
    """The event-bus hook must ONLY flag a candidate (flush-only) -- no insight,
    no email, no AI -- inside the publisher's transaction. The heavy work happens
    later in the drain, in its own session."""
    from app.core.event_bus import EventBus, EventPayload, EventType
    from app.compliance.services.compound_pattern_candidate_listener import CompoundPatternCandidateListener
    from app.models.compound_insight import CompoundInsight, CompoundInsightCandidate
    from app.models.email_outbox import EmailOutbox

    # A live AI patch that would BLOW UP if the listener ever called it.
    def _must_not_call(self, *, org_id, pattern_payload):
        raise AssertionError("listener must not invoke the AI layer")
    from app.ai_governance.services.ai_provider_service import AIProviderService
    monkeypatch.setattr(AIProviderService, "generate_compound_narrative", _must_not_call)

    org, user, control, vendor, risk = _seed_pattern_a(db)

    bus = EventBus.get_instance()
    bus.clear_listeners()
    CompoundPatternCandidateListener().register(bus)

    # Emit within THIS session (the publisher's transaction).
    bus.emit(
        EventType.CONTROL_STATUS_CHANGED,
        EventPayload(
            org_id=org.id, entity_type="control", entity_id=control.id,
            event_type=EventType.CONTROL_STATUS_CHANGED,
            previous_value="in_progress", new_value="failed", triggered_by="test", db=db,
        ),
    )

    # Inside the publisher txn: exactly one candidate, and NOTHING heavy happened.
    cand = db.execute(sa.select(CompoundInsightCandidate).where(CompoundInsightCandidate.organization_id == org.id)).scalars().all()
    assert len(cand) == 1 and cand[0].entity_id == control.id and cand[0].processed_at is None
    assert db.execute(sa.select(CompoundInsight).where(CompoundInsight.organization_id == org.id)).scalars().all() == []
    assert db.execute(sa.select(EmailOutbox).where(EmailOutbox.organization_id == org.id)).scalars().all() == []
    db.commit()

    # Now the drain (separate step / own session semantics) does the real work.
    from app.compliance.services.compound_insight_sweep_service import run_compound_insight_candidate_drain
    _force_ai_fail(monkeypatch)  # keep the drain offline/deterministic
    result = run_compound_insight_candidate_drain(db)
    db.commit()
    assert result["created"] >= 1
    insights = db.execute(sa.select(CompoundInsight).where(CompoundInsight.organization_id == org.id)).scalars().all()
    assert len(insights) == 1
    cand_after = db.execute(sa.select(CompoundInsightCandidate).where(CompoundInsightCandidate.organization_id == org.id)).scalars().all()
    assert cand_after[0].processed_at is not None  # candidate marked processed

    bus.clear_listeners()


@pytest.mark.postgres_smoke
def test_concurrent_drains_cannot_duplicate_insight(pg_sessionmaker, monkeypatch):
    """Two scheduler runs racing on the same anchor must yield exactly ONE
    insight -- the (org, dedup_key) unique constraint + savepoint guard hold."""
    import threading

    _force_ai_fail(monkeypatch)  # offline + deterministic across both threads

    setup = pg_sessionmaker()
    org, user, control, vendor, risk = _seed_pattern_a(setup)
    org_id, control_id = org.id, control.id  # capture before the session closes
    setup.close()

    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    results: list[bool] = []

    def worker():
        s = pg_sessionmaker()
        try:
            barrier.wait(timeout=10)
            _, created = CompoundInsightDetector(s).detect_and_surface(org_id, PATTERN_A, control_id)
            s.commit()
            results.append(created)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            s.rollback()
        finally:
            s.close()

    t1, t2 = threading.Thread(target=worker), threading.Thread(target=worker)
    t1.start(); t2.start(); t1.join(); t2.join()

    assert errors == [], f"concurrent surface raised: {errors}"
    from app.models.compound_insight import CompoundInsight
    check = pg_sessionmaker()
    try:
        rows = check.execute(sa.select(CompoundInsight).where(CompoundInsight.organization_id == org_id)).scalars().all()
        assert len(rows) == 1, f"expected exactly 1 insight, got {len(rows)}"
        assert rows[0].detection_count == 2  # both runs counted, no duplicate row
    finally:
        check.close()
    # exactly one worker created it; the other deduped
    assert sorted(results) == [False, True]


@pytest.mark.postgres_smoke
def test_pattern_b_expired_evidence_and_pattern_c_incident(db, monkeypatch):
    """Smoke that B and C also detect (not just A)."""
    _force_ai_fail(monkeypatch)
    detector = CompoundInsightDetector(db)

    # Pattern B: implemented control + expired evidence + open critical risk.
    org, user = _new_org(db)
    ctrl = _control(db, org, user, status="implemented", title="B-ctrl")
    ev = _evidence(db, org, freshness="expired")
    risk = _risk(db, org, severity="high", status="assessing")
    _link_evidence_control(db, org, ev, ctrl)
    _link_risk_control(db, org, risk, ctrl)
    db.commit()
    ib, cb = detector.detect_and_surface(org.id, PATTERN_B, ctrl.id)
    db.commit()
    assert cb and ib.pattern_id == PATTERN_B.pattern_id and ib.severity == "high"

    # Pattern C: active critical incident + failed control + stale vendor behind it.
    org2, user2 = _new_org(db)
    ctrl2 = _control(db, org2, user2, status="failed", title="C-ctrl")
    vendor2 = _vendor(db, org2, user2, name="C-vendor")
    _overdue_assessment(db, org2, user2, vendor2)
    issue = _issue(db, org2, user2, severity="critical", status="open")
    _link_issue_control(db, org2, user2, issue, ctrl2)
    _link_vendor_control(db, org2, user2, vendor2, ctrl2)
    db.commit()
    ic, cc = detector.detect_and_surface(org2.id, PATTERN_C, issue.id)
    db.commit()
    assert cc and ic.pattern_id == PATTERN_C.pattern_id
    assert set(ic.matched_nodes_json.keys()) == {"anchor", "failed_control", "stale_vendor"}
