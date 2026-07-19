from __future__ import annotations

"""
Signature-scored shadow-AI discovery (patent graft) -- Postgres integration test.

Real Postgres via alembic upgrade head, dedicated complivibe_test_user. Exercises
the patent's three-tier weighted-inference algorithm against real data (its actual
scoring behaviour is characterised, including the finding that a lone signal scores
the same as full corroboration), the DISCARD floor, decay tracking, IdP scan,
federated distinct-tenant pooling, tenant isolation, and -- critically -- that
core's pre-existing shadow-AI feature is untouched and still works alongside.

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_shadow_ai_sig_test \
    PYTHONPATH=. .venv/bin/pytest tests/integration/test_shadow_ai_signature_pg.py -v
"""

import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.ai_governance.services.shadow_ai_signature.confidence_engine import (
    ShadowAIConfidenceEngine,
)
from app.ai_governance.services.shadow_ai_signature.detection_service import (
    ShadowAISignatureService,
)
from app.models.organization import Organization
from app.models.shadow_ai_detection import ShadowAIDetection  # core's EXISTING feature
from app.models.shadow_ai_signature import (
    ShadowAIFederatedObservation,
    ShadowAIIdpConnection,
    ShadowAISignatureDetection,
    ShadowAISignatureRegistry,
    ShadowAITelemetryEvent,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---- Patent benchmark: a real provider signature with weighted multi-tier signals ----
# Weights are the patent's per-signal weights; the algorithm is a weighted average.
BENCHMARK_WEIGHTS = {
    "endpoint_match": 0.40,
    "identity_match": 0.30,
    "volume_match": 0.20,
    "keyword_match": 0.10,
}


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
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; skipping shadow-AI signature PG test")
    url = make_url(raw)
    if not url.get_backend_name().startswith("postgresql"):
        pytest.skip("not PostgreSQL")
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
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# ---------------------------------------------------------------- seed helpers
def _org(db: Session, slug_hint: str) -> Organization:
    org = Organization(id=uuid.uuid4(), name=f"Org {slug_hint}", slug=f"org-{slug_hint}-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    return org


def _signature(db: Session, provider: str = "OpenAI") -> ShadowAISignatureRegistry:
    sig = ShadowAISignatureRegistry(
        id=uuid.uuid4(),
        slug=f"{provider.lower()}-{uuid.uuid4().hex[:6]}",
        provider_name=provider,
        category="llm",
        endpoint_patterns=json.dumps(["api.openai.com", "*.openai.com"]),
        keyword_patterns=json.dumps(["openai", "chatgpt"]),
        oauth_app_patterns=json.dumps(["ChatGPT", "openai-app"]),
        data_egress_indicators=json.dumps({"min_bytes": 1000, "max_bytes": 100000}),
        confidence_weights=json.dumps(BENCHMARK_WEIGHTS),
        risk_level="high",
        is_active=True,
    )
    db.add(sig)
    db.flush()
    return sig


def _event(db: Session, org, sig, *, event_type: str, raw: dict, label: str, when=None) -> None:
    now = when or datetime.now(UTC)
    db.add(
        ShadowAITelemetryEvent(
            id=uuid.uuid4(),
            organization_id=org.id,
            tier=1,
            event_type=event_type,
            source_system_label=label,
            matched_signature_id=sig.id,
            raw_signal_json=json.dumps(raw),
            signal_hash=ShadowAIConfidenceEngine.compute_signal_hash(org.id, sig.id, label, now.date()),
            observed_at=now,
            ingested_at=now,
        )
    )
    db.flush()


# ================================================================= PATENT BENCHMARK
def test_patent_benchmark_weighted_multi_tier_aggregation(session: Session):
    """The novel capability: weighted aggregation with a per-signal evidence trail.

    CHARACTERISED, NOT ASSUMED. The patent formula divides by the summed weight
    of *contributing* signals only, so a lone perfect match on the lowest-weighted
    axis (keyword, 0.10) scores 1.0 -- numerically identical to full four-tier
    corroboration. The weights therefore rank signals against each other *within*
    a scan; they do not damp a single uncorroborated signal. That is a real
    property of the patent algorithm and is asserted here rather than papered
    over; see the tracked follow-up in the build notes.

    What the graft genuinely adds over core's existing detector is the auditable
    per-signal breakdown and the DISCARD floor, both exercised below.
    """
    org = _org(session, "bench")
    sig = _signature(session)
    svc = ShadowAISignatureService(session)

    # --- Case A: single keyword signal ---
    _event(session, org, sig, event_type="text_mention",
           raw={"matched_keyword": "openai"}, label="questionnaire-a")
    svc.recompute_detections(organization_id=org.id)
    session.flush()

    lone = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org.id
        )
    ).scalars().one()
    assert float(lone.confidence_score) == 1.0
    assert lone.confidence_band == "high"
    lone_breakdown = json.loads(lone.detection_basis_json)
    # Only the keyword axis contributed; the other three are recorded as zero-weight
    # non-contributors, which is the auditable part.
    assert lone_breakdown["keyword_match"]["contribution"] > 0
    for absent in ("endpoint_match", "identity_match", "volume_match"):
        assert lone_breakdown[absent]["weight"] == 0.0
        assert lone_breakdown[absent]["contribution"] == 0.0

    # --- Case B: same provider corroborated across three more tiers ---
    _event(session, org, sig, event_type="endpoint_match",
           raw={"endpoint_matched": "api.openai.com"}, label="edge-b")
    _event(session, org, sig, event_type="identity_match",
           raw={"app_name": "ChatGPT", "scopes": "openid profile"}, label="idp-b")
    _event(session, org, sig, event_type="volume_match",
           raw={"volume_bytes": 50000}, label="edge-vol-b")
    svc.recompute_detections(organization_id=org.id)
    session.flush()

    detection = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org.id
        )
    ).scalars().one()

    assert detection.confidence_band == "high", "full corroboration must reach the HIGH band"
    assert float(detection.confidence_score) >= 0.70
    assert detection.event_count == 4
    # The distinguishing outcome: all four axes now carry real weight, so the
    # evidence trail shows *why* it is high rather than just that it is.
    full_breakdown = json.loads(detection.detection_basis_json)
    contributing = [k for k in ("endpoint_match", "identity_match", "volume_match", "keyword_match")
                    if full_breakdown[k]["weight"] > 0]
    assert len(contributing) == 4, "all four tiers must contribute after corroboration"
    assert sum(full_breakdown[k]["weight"] for k in contributing) == pytest.approx(1.0, abs=1e-6)

    # The evidence trail records every signal's weight and contribution -- this is
    # what a single coarse confidence string cannot express.
    breakdown = json.loads(detection.detection_basis_json)
    for signal in ("endpoint_match", "identity_match", "volume_match", "keyword_match"):
        assert signal in breakdown
        assert set(breakdown[signal]) == {"weight", "score", "contribution"}
    assert breakdown["final_score"] == float(detection.confidence_score)


def test_discard_band_never_creates_a_detection(session: Session):
    """Patent invariant: score < 0.40 must not be stored."""
    org = _org(session, "discard")
    sig = _signature(session, "Anthropic")
    # An endpoint signal that does not match -> 0.0 on the heaviest axis only.
    _event(session, org, sig, event_type="endpoint_match",
           raw={"endpoint_matched": "example.internal"}, label="edge-none")

    result = ShadowAISignatureService(session).recompute_detections(organization_id=org.id)
    session.flush()

    assert result["created"] == 0
    assert result["discarded"] == 1
    assert session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org.id
        )
    ).scalars().first() is None


def test_signal_hash_dedupes_repeat_ingest(session: Session):
    org = _org(session, "dedupe")
    sig = _signature(session, "Gemini")
    svc = ShadowAISignatureService(session)
    payload = {"matched_keyword": "gemini"}

    _, dup1 = svc.ingest_telemetry(
        organization_id=org.id, tier=1, event_type="text_mention",
        raw_signal=payload, source_system_label="survey", matched_signature_id=sig.id,
    )
    _, dup2 = svc.ingest_telemetry(
        organization_id=org.id, tier=1, event_type="text_mention",
        raw_signal=payload, source_system_label="survey", matched_signature_id=sig.id,
    )
    assert dup1 is False and dup2 is True


# ================================================================= DECAY
def test_decay_ages_confidence_and_marks_stale(session: Session):
    org = _org(session, "decay")
    sig = _signature(session, "Copilot")
    old = datetime.now(UTC) - timedelta(days=60)
    _event(session, org, sig, event_type="endpoint_match",
           raw={"endpoint_matched": "api.openai.com"}, label="edge-old", when=old)
    _event(session, org, sig, event_type="identity_match",
           raw={"app_name": "ChatGPT"}, label="idp-old", when=old)
    svc = ShadowAISignatureService(session)
    svc.recompute_detections(organization_id=org.id)
    session.flush()

    before = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org.id
        )
    ).scalars().one()
    original = float(before.confidence_score)
    assert before.is_stale is False

    result = svc.apply_decay(organization_id=org.id)
    session.flush()
    session.refresh(before)

    assert result["decayed"] >= 1
    assert float(before.confidence_score) < original, "60 days with no signal must decay the score"
    assert before.decayed_at is not None
    assert before.is_stale is True, "a decayed-out detection must be flagged stale, not deleted"
    assert before.base_confidence_score is not None, "the pre-decay score must be preserved"


# ================================================================= IdP SCAN
def test_idp_scan_creates_tier2_telemetry_and_sync_log(session: Session):
    org = _org(session, "idp")
    sig = _signature(session, "OpenAI")
    conn = ShadowAIIdpConnection(
        id=uuid.uuid4(), organization_id=org.id, idp_provider="okta",
        access_token_enc="enc", sync_status="pending", connected_by_user_id=None,
    )
    session.add(conn)
    session.flush()

    result = ShadowAISignatureService(session).record_idp_scan(
        organization_id=org.id,
        connection_id=conn.id,
        oauth_grants=[
            {"app_name": "ChatGPT", "app_id": "abc"},
            {"app_name": "InternalTool", "app_id": "xyz"},
        ],
    )
    session.flush()

    assert result["events_fetched"] == 2
    assert result["events_matched"] == 1, "only the AI OAuth grant should match a signature"
    assert result["signals_created"] == 1
    session.refresh(conn)
    assert conn.sync_status == "ok"
    assert conn.total_syncs == 1

    tier2 = session.execute(
        sa.select(ShadowAITelemetryEvent).where(
            ShadowAITelemetryEvent.organization_id == org.id,
            ShadowAITelemetryEvent.tier == 2,
        )
    ).scalars().all()
    assert len(tier2) == 1


def test_idp_scan_rejects_other_orgs_connection(session: Session):
    org_a, org_b = _org(session, "idp-a"), _org(session, "idp-b")
    conn = ShadowAIIdpConnection(
        id=uuid.uuid4(), organization_id=org_a.id, idp_provider="okta",
        access_token_enc="enc", sync_status="pending",
    )
    session.add(conn)
    session.flush()

    result = ShadowAISignatureService(session).record_idp_scan(
        organization_id=org_b.id, connection_id=conn.id, oauth_grants=[],
    )
    assert result == {"error": "connection_not_found"}


# ================================================================= FEDERATED
def test_federated_counts_distinct_tenants_not_hits(session: Session):
    """One noisy tenant must not promote a hostname on its own."""
    org_a, org_b = _org(session, "fed-a"), _org(session, "fed-b")
    svc = ShadowAISignatureService(session)

    first = svc.submit_federated_observation(organization_id=org_a.id, hostname="newai.example.com")
    assert first["distinct_orgs"] == 1
    assert first["status"] == "observed"

    # Same tenant submitting repeatedly must NOT increase the distinct-org count.
    for _ in range(5):
        again = svc.submit_federated_observation(organization_id=org_a.id, hostname="newai.example.com")
    assert again["distinct_orgs"] == 1
    assert again["was_duplicate"] is True
    assert again["status"] == "observed"

    # A second, genuinely different tenant promotes it to candidate.
    second = svc.submit_federated_observation(organization_id=org_b.id, hostname="newai.example.com")
    assert second["distinct_orgs"] == 2
    assert second["status"] == "candidate"


def test_federated_pool_stores_only_hostname_hash_per_tenant(session: Session):
    org = _org(session, "fed-hash")
    svc = ShadowAISignatureService(session)
    svc.submit_federated_observation(organization_id=org.id, hostname="Secret-Internal.example.com")
    session.flush()

    obs = session.execute(
        sa.select(ShadowAIFederatedObservation).where(
            ShadowAIFederatedObservation.hostname_hash
            == ShadowAISignatureService.hash_hostname("Secret-Internal.example.com")
        )
    ).scalars().one()
    assert len(obs.hostname_hash) == 64
    # Hash is case-insensitive and salted, so the same host from another tenant collides
    # deliberately (that is what makes pooling work) but is not reversible from the hash.
    assert obs.hostname_hash == ShadowAISignatureService.hash_hostname("secret-internal.EXAMPLE.com")


# ================================================================= TENANT ISOLATION
def test_detections_and_telemetry_are_tenant_isolated(session: Session):
    org_a, org_b = _org(session, "iso-a"), _org(session, "iso-b")
    sig = _signature(session, "Mistral")
    svc = ShadowAISignatureService(session)

    for org in (org_a, org_b):
        _event(session, org, sig, event_type="endpoint_match",
               raw={"endpoint_matched": "api.openai.com"}, label=f"edge-{org.slug}")
        _event(session, org, sig, event_type="identity_match",
               raw={"app_name": "ChatGPT"}, label=f"idp-{org.slug}")
    svc.recompute_detections(organization_id=org_a.id)
    session.flush()

    a_rows = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org_a.id
        )
    ).scalars().all()
    b_rows = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org_b.id
        )
    ).scalars().all()

    assert len(a_rows) == 1, "org A rescan must produce org A's detection"
    assert b_rows == [], "org A's rescan must not create anything for org B"

    # And org B's own telemetry is invisible to a scoped org-A read.
    a_events = session.execute(
        sa.select(ShadowAITelemetryEvent).where(
            ShadowAITelemetryEvent.organization_id == org_a.id
        )
    ).scalars().all()
    assert all(e.organization_id == org_a.id for e in a_events)


def test_suppression_blocks_redetection_for_that_org_only(session: Session):
    org_a, org_b = _org(session, "sup-a"), _org(session, "sup-b")
    sig = _signature(session, "Perplexity")
    svc = ShadowAISignatureService(session)

    for org in (org_a, org_b):
        _event(session, org, sig, event_type="endpoint_match",
               raw={"endpoint_matched": "api.openai.com"}, label=f"e-{org.slug}")
        _event(session, org, sig, event_type="identity_match",
               raw={"app_name": "ChatGPT"}, label=f"i-{org.slug}")

    svc.suppress_signature(
        organization_id=org_a.id, signature_id=sig.id,
        reason="approved vendor", actor_user_id=None,
    )
    session.flush()

    res_a = svc.recompute_detections(organization_id=org_a.id)
    res_b = svc.recompute_detections(organization_id=org_b.id)
    session.flush()

    assert res_a["created"] == 0 and res_a["suppressed_skipped"] == 1
    assert res_b["created"] == 1, "suppression must not leak to another tenant"


# ================================================================= COEXISTENCE
def test_core_shadow_ai_feature_is_untouched_and_still_works(session: Session):
    """Core's existing shadow_ai_detections must remain fully functional.

    Both systems may hold a row for the same tool; that is the intended graft
    outcome, and is tracked as a product-decision follow-up rather than resolved
    in code.
    """
    org = _org(session, "coexist")

    # Core's feature: its own table, its own columns, written directly.
    core_row = ShadowAIDetection(
        id=uuid.uuid4(),
        organization_id=org.id,
        detected_name="ChatGPT",
        detection_method="questionnaire",
        confidence="medium",
        status="new",
        detected_at=datetime.now(UTC),
    )
    session.add(core_row)
    session.flush()

    # New feature: its own table, scoring the same provider.
    sig = _signature(session, "OpenAI")
    _event(session, org, sig, event_type="endpoint_match",
           raw={"endpoint_matched": "api.openai.com"}, label="edge-co")
    _event(session, org, sig, event_type="identity_match",
           raw={"app_name": "ChatGPT"}, label="idp-co")
    ShadowAISignatureService(session).recompute_detections(organization_id=org.id)
    session.flush()

    core_rows = session.execute(
        sa.select(ShadowAIDetection).where(ShadowAIDetection.organization_id == org.id)
    ).scalars().all()
    new_rows = session.execute(
        sa.select(ShadowAISignatureDetection).where(
            ShadowAISignatureDetection.organization_id == org.id
        )
    ).scalars().all()

    assert len(core_rows) == 1, "core's detection must survive untouched"
    assert core_rows[0].detected_name == "ChatGPT"
    assert core_rows[0].confidence == "medium", "core's coarse confidence string is unchanged"
    assert len(new_rows) == 1, "the grafted system records its own scored detection"
    assert new_rows[0].provider_name == "OpenAI"
    # Two separate tables, two separate rows, no FK or write between them.
    assert core_rows[0].id != new_rows[0].id


def test_core_and_new_tables_are_physically_distinct(engine):
    """Schema-level proof the graft did not repurpose core's table."""
    insp = sa.inspect(engine)
    core_cols = {c["name"] for c in insp.get_columns("shadow_ai_detections")}
    new_cols = {c["name"] for c in insp.get_columns("shadow_ai_signature_detections")}

    # Core's distinctive columns must still exist and must NOT have been migrated.
    assert {"detected_name", "detection_method", "confidence"} <= core_cols
    # The grafted table has the patent schema instead.
    assert {"provider_name", "confidence_score", "confidence_band", "signature_id"} <= new_cols
    assert "detected_name" not in new_cols
    assert "confidence_score" not in core_cols
