from __future__ import annotations

"""
P2 governance knowledge-graph -- Postgres integration/E2E test.

Real Postgres via alembic upgrade head, dedicated complivibe_test_user. Exercises
the patent's EU-India biometric benchmark against the now-UUID-native core (naive
lookup misses 10/11 vs. graph traversal's complete set), the "Satellites Compute,
Core Decides" contract (core re-derives via its own recursive CTE and flags
mismatches rather than writing them), tenant isolation, human-endpoint permission
enforcement, and scoped-key auth on the satellite endpoints.

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_governance_graph_test \
    PYTHONPATH=. .venv/bin/pytest tests/integration/test_governance_graph_p2_pg.py -m postgres_smoke -v
"""

import os
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---- EU-India biometric benchmark data (patent Workstream M) ----
OBLIGATIONS = [
    "gdpr_data_subject_rights", "gdpr_breach_notification", "gdpr_controller_accountability",
    "gdpr_processor_data_processing_agreement", "euaiact_transparency_notice",
    "euaiact_conformity_assessment", "euaiact_human_oversight", "euaiact_biometric_accuracy_and_bias_testing",
    "dpdp_consent_notice", "dpdp_data_principal_rights", "dpdp_processor_contractual_terms",
]
CONTROLS = [
    "access_control", "audit_logging", "records_of_processing_control", "data_processing_agreement_control",
    "transparency_documentation", "bias_and_accuracy_testing", "consent_management",
]
# Naive first-jurisdiction+first-category lookup -> (EU, biometric) -> 1 of 11.
NAIVE_RESULT = ["euaiact_transparency_notice"]


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
def engine():
    raw = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; skipping governance-graph PG test")
    url = make_url(raw)
    if not url.get_backend_name().startswith("postgresql"):
        pytest.skip("not PostgreSQL")
    _assert_safe(url)
    _recreate(url)
    subprocess.run([".venv/bin/alembic", "upgrade", "head"], cwd=REPO_ROOT,
                   env={**os.environ, "DATABASE_URL": raw}, check=True, capture_output=True)
    eng = sa.create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# ---- seed helpers ----
def _seed_org_system(db: Session):
    from app.models.ai_system import AISystem
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name=f"Org {uuid.uuid4().hex[:8]}")
    db.add(org); db.flush()
    user = User(email=f"u-{uuid.uuid4().hex[:10]}@example.com", hashed_password="x", is_active=True, status="active")
    db.add(user); db.flush()
    system = AISystem(organization_id=org.id, name="GlobalID Biometric", system_type="application",
                      geographic_scope="EU", data_categories_json=["biometric", "employment_data", "health"], risk_tier="high")
    db.add(system); db.flush(); db.commit()
    return org.id, user.id, system.id


def _load_eu_india_graph(db: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID):
    """Build the EU-India biometric graph directly via the repository so a CTE
    traversal from the ai_system node reaches all 11 obligations + 7 controls."""
    from app.ai_governance.services.governance_graph.repository import upsert_graph_structure

    N = lambda t, k: SimpleNamespace(node_type=t, node_key=k, properties={})
    E = lambda st, sk, tt, tk, et: SimpleNamespace(
        source_node_type=st, source_node_key=sk, target_node_type=tt, target_node_key=tk,
        edge_type=et, is_active=True, weight=1.0, properties={})

    sys_key = str(ai_system_id)
    nodes = [N("ai_system", sys_key), N("jurisdiction", "EU"), N("jurisdiction", "IN"),
             N("data_category", "biometric"), N("data_category", "employment_data"), N("data_category", "health"),
             N("risk_tier", "high"), N("regulation", "GDPR"), N("regulation", "EU_AI_ACT"), N("regulation", "DPDP")]
    nodes += [N("obligation", o) for o in OBLIGATIONS] + [N("control_type", c) for c in CONTROLS]

    edges = [
        E("ai_system", sys_key, "jurisdiction", "EU", "system_deploys_in"),
        E("ai_system", sys_key, "jurisdiction", "IN", "system_deploys_in"),
        E("ai_system", sys_key, "data_category", "biometric", "system_uses"),
        E("ai_system", sys_key, "data_category", "employment_data", "system_uses"),
        E("ai_system", sys_key, "data_category", "health", "system_uses"),
        E("ai_system", sys_key, "risk_tier", "high", "system_classified_as"),
        E("jurisdiction", "EU", "regulation", "GDPR", "jurisdiction_has"),
        E("jurisdiction", "EU", "regulation", "EU_AI_ACT", "jurisdiction_has"),
        E("jurisdiction", "IN", "regulation", "DPDP", "jurisdiction_has"),
        E("regulation", "GDPR", "obligation", "gdpr_data_subject_rights", "regulation_requires"),
        E("regulation", "GDPR", "obligation", "gdpr_breach_notification", "regulation_requires"),
        E("regulation", "GDPR", "obligation", "gdpr_controller_accountability", "regulation_requires"),
        E("regulation", "GDPR", "obligation", "gdpr_processor_data_processing_agreement", "regulation_requires"),
        E("regulation", "EU_AI_ACT", "obligation", "euaiact_transparency_notice", "regulation_requires"),
        E("regulation", "DPDP", "obligation", "dpdp_consent_notice", "regulation_requires"),
        E("regulation", "DPDP", "obligation", "dpdp_data_principal_rights", "regulation_requires"),
        E("regulation", "DPDP", "obligation", "dpdp_processor_contractual_terms", "regulation_requires"),
        E("risk_tier", "high", "obligation", "euaiact_conformity_assessment", "risk_tier_adds"),
        E("risk_tier", "high", "obligation", "euaiact_human_oversight", "risk_tier_adds"),
        E("risk_tier", "high", "obligation", "euaiact_biometric_accuracy_and_bias_testing", "risk_tier_adds"),
        E("obligation", "gdpr_data_subject_rights", "control_type", "access_control", "obligation_needs"),
        E("obligation", "gdpr_breach_notification", "control_type", "audit_logging", "obligation_needs"),
        E("obligation", "gdpr_controller_accountability", "control_type", "records_of_processing_control", "obligation_needs"),
        E("obligation", "gdpr_processor_data_processing_agreement", "control_type", "data_processing_agreement_control", "obligation_needs"),
        E("obligation", "euaiact_transparency_notice", "control_type", "transparency_documentation", "obligation_needs"),
        E("obligation", "euaiact_biometric_accuracy_and_bias_testing", "control_type", "bias_and_accuracy_testing", "obligation_needs"),
        E("obligation", "dpdp_consent_notice", "control_type", "consent_management", "obligation_needs"),
    ]
    upsert_graph_structure(db, org_id, nodes, edges)
    db.commit()


def _client(session, org_id, user_id, monkeypatch, *, allowed_perms):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.ai_governance.routers import governance_graph as gg
    from app.ai_governance.routers import patent_ingest_p2 as ingest
    from app.core.deps import get_current_active_user, get_current_organization, get_db, require_org_membership
    from app.core.rate_limiter import rate_limiter
    from app.models.membership import Membership
    from app.services.rbac_service import RBACService

    monkeypatch.setattr(rate_limiter.limiter, "enabled", False)
    app = FastAPI()
    app.include_router(gg.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")

    fake_user = SimpleNamespace(id=user_id)
    fake_org = SimpleNamespace(id=org_id)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_active_user] = lambda: fake_user
    app.dependency_overrides[get_current_organization] = lambda: fake_org
    app.dependency_overrides[require_org_membership] = lambda: Membership(organization_id=org_id, user_id=user_id)
    monkeypatch.setattr(RBACService, "user_has_permission", staticmethod(lambda db, uid, oid, code: code in allowed_perms))
    return TestClient(app)


_ALL = {"governance_graph:read", "governance_graph:write"}


def _derivation_payload(ai_system_id, obligations, controls):
    return {
        "ai_system_id": str(ai_system_id), "derived_obligations": obligations, "derived_controls": controls,
        "graph_path": None, "methodology_version": "sat-v1", "trigger_reason": "event", "derivation_hash": "h1",
    }


# --------------------------------------------------------------------------- #
# Benchmark: naive misses 10/11, graph traversal returns the complete set
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_benchmark_traversal_beats_naive_lookup(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL)

    resp = client.post(f"/api/v1/ai-governance/knowledge-graph/systems/{system_id}/derive-obligations")
    assert resp.status_code == 200, resp.text
    derived = set(resp.json()["derived_obligations"])
    assert derived == set(OBLIGATIONS), f"missing: {set(OBLIGATIONS) - derived}"
    assert set(resp.json()["derived_controls"]) == set(CONTROLS)
    # Naive lookup is a strict, tiny subset (misses 10 of 11).
    assert set(NAIVE_RESULT) < derived
    assert len(derived) - len(NAIVE_RESULT) == 10
    # spans all three regulations + both role-specific obligations
    assert {"gdpr_controller_accountability", "gdpr_processor_data_processing_agreement",
            "dpdp_processor_contractual_terms"} <= derived


# --------------------------------------------------------------------------- #
# Satellites Compute, Core Decides
# --------------------------------------------------------------------------- #
def _ingest_key(session, org_id):
    from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
    key = PatentScopedKeyService(session).provision_key(org_id, "ingest", None)
    session.commit()
    return key


@pytest.mark.postgres_smoke
def test_core_decides_validates_match_writes_links(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    raw_key = _ingest_key(session, org_id)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL)

    # Satellite submits a derivation that MATCHES core's own re-derivation.
    resp = client.post("/api/v1/patent-ingest/p2/obligation-derivation",
                       headers={"Authorization": f"Bearer {raw_key}"},
                       json=_derivation_payload(system_id, OBLIGATIONS, CONTROLS))
    assert resp.status_code == 200, resp.text
    assert resp.json()["validation_status"] == "validated"

    from app.models.ai_system_obligation_link import AiSystemObligationLink
    links = session.query(AiSystemObligationLink).filter(AiSystemObligationLink.ai_system_id == system_id).all()
    assert len({l.link_key for l in links if l.link_kind == "obligation"}) == 11  # links written on match


@pytest.mark.postgres_smoke
def test_core_decides_flags_mismatch_and_writes_no_links(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    raw_key = _ingest_key(session, org_id)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL)

    # Submit a VALID-but-incomplete set (all ids are in the catalog, but the set
    # != core's re-derivation) -> flagged_mismatch, and NO links written.
    partial = OBLIGATIONS[:5]
    resp = client.post("/api/v1/patent-ingest/p2/obligation-derivation",
                       headers={"Authorization": f"Bearer {raw_key}"},
                       json=_derivation_payload(system_id, partial, CONTROLS))
    assert resp.status_code == 200, resp.text
    assert resp.json()["validation_status"] == "flagged_mismatch"

    from app.models.ai_system_obligation_link import AiSystemObligationLink
    links = session.query(AiSystemObligationLink).filter(AiSystemObligationLink.ai_system_id == system_id).all()
    assert links == []  # mismatch is flagged, never silently written


@pytest.mark.postgres_smoke
def test_ingest_rejects_unknown_obligation_ids(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    raw_key = _ingest_key(session, org_id)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL)
    resp = client.post("/api/v1/patent-ingest/p2/obligation-derivation",
                       headers={"Authorization": f"Bearer {raw_key}"},
                       json=_derivation_payload(system_id, ["not_a_real_obligation"], []))
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "unknown_or_inactive_obligation_control_ids"


# --------------------------------------------------------------------------- #
# Scoped-key auth
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_scoped_key_auth_enforced(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    _ingest_key(session, org_id)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL)
    # Missing key -> 401; wrong key -> 403.
    assert client.post("/api/v1/patent-ingest/p2/obligation-derivation",
                       json=_derivation_payload(system_id, OBLIGATIONS, CONTROLS)).status_code == 401
    assert client.post("/api/v1/patent-ingest/p2/obligation-derivation",
                       headers={"Authorization": "Bearer wrong-key"},
                       json=_derivation_payload(system_id, OBLIGATIONS, CONTROLS)).status_code == 403


# --------------------------------------------------------------------------- #
# Tenant isolation + human-endpoint permission enforcement
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_cross_tenant_derivation_is_404(session, monkeypatch):
    org_a, user_a, sys_a = _seed_org_system(session)
    _load_eu_india_graph(session, org_a, sys_a)
    org_b, user_b, _sys_b = _seed_org_system(session)
    # Org B principal asks to derive over Org A's system -> 404 (no graph node in B).
    client_b = _client(session, org_b, user_b, monkeypatch, allowed_perms=_ALL)
    resp = client_b.post(f"/api/v1/ai-governance/knowledge-graph/systems/{sys_a}/derive-obligations")
    assert resp.status_code == 404


@pytest.mark.postgres_smoke
def test_write_endpoint_requires_write_permission(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    _load_eu_india_graph(session, org_id, system_id)
    # Read-only principal: has :read, lacks :write -> manual-edge POST is 403.
    ro = _client(session, org_id, user_id, monkeypatch, allowed_perms={"governance_graph:read"})
    resp = ro.post("/api/v1/ai-governance/knowledge-graph/edges",
                   json={"source_node_id": str(uuid.uuid4()), "target_node_id": str(uuid.uuid4()),
                         "edge_type": "obligation_needs"})
    assert resp.status_code == 403
    assert "governance_graph:write" in resp.json()["detail"]
    # Sync (also :write) -> 403 too.
    assert ro.post(f"/api/v1/ai-governance/knowledge-graph/systems/{system_id}/sync").status_code == 403
