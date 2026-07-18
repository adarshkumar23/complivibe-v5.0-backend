from __future__ import annotations

"""
Agentic policy-derivation (patent P3) -- Postgres integration/E2E test.

Runs against a real PostgreSQL DB built with `alembic upgrade head` (so the real
0310 tables exist). STANDING RULE: uses the dedicated `complivibe_test_user`,
never `complivibe_user`.

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_policy_derivation_test \
    PATH=$HOME/.local/bin:$PATH PYTHONPATH=. .venv/bin/pytest tests/integration/test_policy_derivation_pg.py -m postgres_smoke -v

OPA evaluation on the hot check-action path is exercised through the REAL
OpaClient HTTP code path, bridged to the vendored `opa eval` CLI via an
httpx.MockTransport (standing up a live clustered OPA server with dynamic policy
loading is out of scope per PATENT.md 0 -- the real HTTP request/response path
is still exercised end to end). Ed25519 receipt signing, DB-backed hash
chaining, and provenance persistence are all REAL against real Postgres.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (register all models)

REPO_ROOT = Path(__file__).resolve().parents[2]
OPA = shutil.which("opa")

pytestmark = pytest.mark.skipif(OPA is None, reason="opa CLI not on PATH")

_SIGNING_KEY = "ab" * 32  # 32-byte customer-side signing seed (test only)


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
        c.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=:n AND pid<>pg_backend_pid()"
            ),
            {"n": name},
        )
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


@pytest.fixture(scope="module")
def engine():
    raw = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; skipping policy-derivation PG test")
    url = make_url(raw)
    if not url.get_backend_name().startswith("postgresql"):
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not PostgreSQL; skipping")
    _assert_safe(url)
    _recreate(url)

    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": raw},
        check=True,
        capture_output=True,
    )
    eng = sa.create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# --------------------------------------------------------------------------- #
# Seed helpers
# --------------------------------------------------------------------------- #
def _seed_org_system(db: Session):
    from app.models.ai_system import AISystem
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name=f"Org {uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    user = User(email=f"u-{uuid.uuid4().hex[:10]}@example.com", hashed_password="x", is_active=True, status="active")
    db.add(user)
    db.flush()
    system = AISystem(organization_id=org.id, name=f"Sys {uuid.uuid4().hex[:6]}", system_type="application")
    db.add(system)
    db.flush()
    db.commit()
    return org.id, user.id, system.id


# --------------------------------------------------------------------------- #
# OPA CLI bridge: exercises the real OpaClient HTTP path against `opa eval`
# --------------------------------------------------------------------------- #
def _cli_opa_factory(rego_package, rego_policy, *, sign_receipt_fn, previous_receipt_hash):
    from app.ai_governance.services.policy_derivation.opa_client import OpaClient
    from app.ai_governance.services.policy_derivation.policy_provider import CompliVibePolicyProvider

    rego_file = tempfile.NamedTemporaryFile(mode="w", suffix=".rego", delete=False)
    rego_file.write(rego_policy)
    rego_file.close()

    def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        input_data = body.get("input", {})
        rel = request.url.path[len("/v1/data/"):]
        query = "data." + rel.replace("/", ".")
        proc = subprocess.run(
            ["opa", "eval", "--format", "json", "--input", "/dev/stdin", "--data", rego_file.name, query],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return httpx.Response(500, text=proc.stderr)
        result = json.loads(proc.stdout)
        exprs = result.get("result", [{}])[0].get("expressions", [{}])
        return httpx.Response(200, json={"result": exprs[0].get("value") if exprs else None})

    client = OpaClient(base_url="http://local-opa.test", client=httpx.Client(transport=httpx.MockTransport(_handler)))
    return CompliVibePolicyProvider(
        client, rego_package, sign_receipt_fn=sign_receipt_fn, previous_receipt_hash=previous_receipt_hash
    )


# --------------------------------------------------------------------------- #
# Test app / client
# --------------------------------------------------------------------------- #
def _client(session, org_id, user_id, monkeypatch, *, allowed_perms):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.ai_governance.routers import policy_derivation as pd
    from app.ai_governance.services import policy_derivation_service as pds
    from app.core.deps import (
        get_current_active_user,
        get_current_organization,
        get_db,
        require_org_membership,
    )
    from app.core.rate_limiter import rate_limiter
    from app.models.membership import Membership
    from app.services.rbac_service import RBACService

    # OPA on the check path goes through the real OpaClient bridged to `opa eval`.
    monkeypatch.setattr(pds, "_default_policy_provider_factory", _cli_opa_factory)
    # Focus this test on the feature, not the rate limiter middleware.
    monkeypatch.setattr(rate_limiter.limiter, "enabled", False)

    app = FastAPI()
    app.include_router(pd.router, prefix="/api/v1")

    fake_user = SimpleNamespace(id=user_id)
    fake_org = SimpleNamespace(id=org_id)
    fake_membership = Membership(organization_id=org_id, user_id=user_id)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_active_user] = lambda: fake_user
    app.dependency_overrides[get_current_organization] = lambda: fake_org
    app.dependency_overrides[require_org_membership] = lambda: fake_membership
    # Exercise the REAL require_permission gate; only the terminal RBAC lookup is
    # stubbed, differentiated per permission code.
    monkeypatch.setattr(
        RBACService,
        "user_has_permission",
        staticmethod(lambda db, uid, oid, code: code in allowed_perms),
    )
    return TestClient(app)


_ALL_PERMS = {"ai_guardrail:read", "ai_guardrail:create", "ai_guardrail:recompile", "ai_guardrail:check"}

_RBI_OBLIGATION = {
    "id": "obl-rbi-2018-dpss",
    "text": (
        "All data relating to payment systems shall be stored only in India; this data "
        "shall not leave the territory of India, and personal data collected from customers "
        "is prohibited from being transferred outside the territory of India."
    ),
    "jurisdiction": "India",
}


def _create_guardrail(client, ai_system_id):
    return client.post(
        f"/api/v1/ai-governance/policy-derivation/ai-systems/{ai_system_id}/guardrails",
        json={"name": "RBI localization", "obligations": [_RBI_OBLIGATION]},
    )


# --------------------------------------------------------------------------- #
# Claim 1 -- derived guardrail persists provenance
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_create_guardrail_persists_provenance(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL_PERMS)

    resp = _create_guardrail(client, system_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    from app.ai_governance.services.policy_derivation.derivation_engine import rego_package_slug

    assert body["source_obligation_ids"] == ["obl-rbi-2018-dpss"]  # provenance
    assert body["rego_package"] == f"complivibe.guardrails.org_{rego_package_slug(str(org_id))}"
    assert "package complivibe.guardrails.org_" in body["rego_policy"]
    assert body["constraint_spec_json"]["data_scope"]["cross_border_transfer_allowed"] is False

    # persisted to the real table
    from app.models.ai_derived_guardrail import AiDerivedGuardrail

    row = session.get(AiDerivedGuardrail, uuid.UUID(body["id"]))
    assert row is not None and row.source_obligation_ids == ["obl-rbi-2018-dpss"]


# --------------------------------------------------------------------------- #
# Claim 3 + Claim 4 -- enforcement + signed receipt, key-free verify, tamper
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_check_action_deny_and_allow_with_signed_receipts(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL_PERMS)
    assert _create_guardrail(client, system_id).status_code == 201

    base = f"/api/v1/ai-governance/policy-derivation/ai-systems/{system_id}"
    hdr = {"X-Guardrail-Signing-Key": _SIGNING_KEY}

    # Cross-border PII to Singapore -> denied by the derived Rego (Claim 3).
    deny = client.post(
        f"{base}/guardrails/check",
        headers=hdr,
        json={
            "action_id": "act-1", "ai_system_id": str(system_id), "organization_id": str(org_id),
            "action_type": "transfer", "cross_border": True, "data_categories": ["pii"],
            "destination_region": "Singapore", "timestamp": "2026-07-18T00:00:00+00:00",
        },
    )
    assert deny.status_code == 200, deny.text
    assert deny.json()["allowed"] is False
    assert deny.json()["receipt_id"] is not None

    # Domestic India transfer -> allowed.
    allow = client.post(
        f"{base}/guardrails/check",
        headers=hdr,
        json={
            "action_id": "act-2", "ai_system_id": str(system_id), "organization_id": str(org_id),
            "action_type": "transfer", "cross_border": False, "data_categories": ["pii"],
            "destination_region": "India", "timestamp": "2026-07-18T00:00:01+00:00",
        },
    )
    assert allow.status_code == 200 and allow.json()["allowed"] is True

    # Receipt chain of 2, and verify-chain passes (Claim 4).
    chain = client.get(f"{base}/receipt-chain").json()
    assert len(chain["receipts"]) == 2
    verify = client.post(f"{base}/verify-chain").json()
    assert verify["passed"] is True and verify["verified_count"] == 2

    # Claim 4: core stored the receipts but NEVER the private signing key.
    from app.models.ai_guardrail_receipt import AiGuardrailReceipt

    for r in session.query(AiGuardrailReceipt).all():
        assert _SIGNING_KEY not in json.dumps({c.name: str(getattr(r, c.name)) for c in r.__table__.columns})
        assert r.public_key_hex and r.signature  # public material + signature only


@pytest.mark.postgres_smoke
def test_verify_chain_detects_tamper(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)
    client = _client(session, org_id, user_id, monkeypatch, allowed_perms=_ALL_PERMS)
    assert _create_guardrail(client, system_id).status_code == 201
    base = f"/api/v1/ai-governance/policy-derivation/ai-systems/{system_id}"
    client.post(
        f"{base}/guardrails/check",
        headers={"X-Guardrail-Signing-Key": _SIGNING_KEY},
        json={
            "action_id": "act-1", "ai_system_id": str(system_id), "organization_id": str(org_id),
            "action_type": "transfer", "cross_border": False, "data_categories": [],
            "destination_region": "India", "timestamp": "2026-07-18T00:00:00+00:00",
        },
    )
    assert client.post(f"{base}/verify-chain").json()["passed"] is True

    # Tamper with the stored decision after signing -> chain must fail.
    from app.models.ai_guardrail_receipt import AiGuardrailReceipt

    r = (
        session.query(AiGuardrailReceipt)
        .filter(AiGuardrailReceipt.ai_system_id == system_id)
        .first()
    )
    r.decision = "deny" if r.decision == "allow" else "allow"
    session.commit()

    verdict = client.post(f"{base}/verify-chain").json()
    assert verdict["passed"] is False and verdict["failure_index"] == 0


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_cross_tenant_is_404_never_leaks(session, monkeypatch):
    org_a, user_a, sys_a = _seed_org_system(session)
    org_b, user_b, sys_b = _seed_org_system(session)

    client_a = _client(session, org_a, user_a, monkeypatch, allowed_perms=_ALL_PERMS)
    assert _create_guardrail(client_a, sys_a).status_code == 201

    # Org B principal asking about Org A's ai_system -> 404 (never 403, no leak).
    client_b = _client(session, org_b, user_b, monkeypatch, allowed_perms=_ALL_PERMS)
    resp = client_b.get(f"/api/v1/ai-governance/policy-derivation/ai-systems/{sys_a}/receipt-chain")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Permission enforcement (real require_permission gate)
# --------------------------------------------------------------------------- #
@pytest.mark.postgres_smoke
def test_permission_enforcement_403_and_200(session, monkeypatch):
    org_id, user_id, system_id = _seed_org_system(session)

    # Read-only principal: has ai_guardrail:read, lacks ai_guardrail:create.
    ro = _client(session, org_id, user_id, monkeypatch, allowed_perms={"ai_guardrail:read"})
    denied = _create_guardrail(ro, system_id)
    assert denied.status_code == 403
    assert "ai_guardrail:create" in denied.json()["detail"]

    # Read endpoint is allowed for the same read-only principal.
    ok = ro.get(f"/api/v1/ai-governance/policy-derivation/ai-systems/{system_id}/receipt-chain")
    assert ok.status_code == 200
