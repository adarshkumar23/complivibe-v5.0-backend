"""Evidence-vault AI-assist — end-to-end, fallback, isolation, tenant scoping.

The AI provider chain (Groq/Azure) is not reachable in tests, so the AI narrate
step is monkeypatched: the SUCCESS tests inject a canned structured assessment;
the FALLBACK test makes it raise to prove the unable_to_assess path. Everything
else is real: real R2 bytes via a local S3 server (moto), the real event ->
flush-only listener -> candidate queue, and the real drain that extracts text and
writes the assessment.
"""

from __future__ import annotations

import uuid

import boto3
import pytest
from botocore.config import Config
from moto.server import ThreadedMotoServer
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.evidence_ai_assessment import EvidenceAiAssessment, EvidenceAiAssessmentCandidate
from app.services import evidence_assessment_service as svc
from tests.helpers.auth_org import bootstrap_org_user

BUCKET = "complivibe-ai-assess-test"
DOC_TEXT = b"This SOC 2 Type II report covers access control CC6.1 for the audit period 2026."


@pytest.fixture(scope="module")
def moto_endpoint():
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


def _admin_client(endpoint):
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id="testing", aws_secret_access_key="testing",
        region_name="us-east-1", config=Config(signature_version="s3v4"),
    )


@pytest.fixture
def r2_configured(monkeypatch, moto_endpoint):
    s = get_settings()
    monkeypatch.setattr(s, "R2_ACCOUNT_ID", "test-account", raising=False)
    monkeypatch.setattr(s, "R2_ACCESS_KEY_ID", "testing", raising=False)
    monkeypatch.setattr(s, "R2_SECRET_ACCESS_KEY", "testing", raising=False)
    monkeypatch.setattr(s, "R2_BUCKET_NAME", BUCKET, raising=False)
    monkeypatch.setattr(s, "R2_ENDPOINT_URL", moto_endpoint, raising=False)
    _admin_client(moto_endpoint).create_bucket(Bucket=BUCKET)
    yield s


def _canned_assessment(status="suggested_valid"):
    def _fake(db, *, org_id, payload):
        return (
            {
                "ai_assessment_status": status,
                "appears_to_be": "a SOC 2 Type II report",
                "appears_to_cover": "access control CC6.1",
                "missing_or_mismatched": [],
                "explanation": "The document appears to support the linked control; suggestion only.",
            },
            "groq",
            False,
        )
    return _fake


def _upload_evidence_with_file(client, headers, filename="soc2.txt", ctype="text/plain", body=DOC_TEXT):
    ev_id = client.post(
        "/api/v1/evidence", headers=headers, json={"title": "SOC2 Report", "evidence_type": "document"}
    ).json()["id"]
    r = client.post(f"/api/v1/evidence/{ev_id}/file", headers=headers, files={"file": (filename, body, ctype)})
    assert r.status_code == 200, r.text
    return ev_id


# ── 1. Full E2E: upload -> event -> candidate -> drain -> assessment persisted ─
def test_e2e_upload_to_persisted_assessment(client, db_session, r2_configured, monkeypatch):
    monkeypatch.setattr(svc, "generate_evidence_assessment", _canned_assessment("suggested_valid"))
    org = bootstrap_org_user(client, email_prefix="aia-e2e")
    ev_id = _upload_evidence_with_file(client, org["org_headers"])

    # the flush-only listener queued a candidate (unprocessed)
    cand = db_session.execute(
        select(EvidenceAiAssessmentCandidate).where(
            EvidenceAiAssessmentCandidate.evidence_item_id == uuid.UUID(ev_id)
        )
    ).scalars().all()
    assert len(cand) == 1 and cand[0].processed_at is None

    # drain (what the APScheduler job calls) does extraction + assessment
    result = svc.run_evidence_assessment_candidate_drain(db_session)
    db_session.commit()
    assert result["created"] == 1

    row = db_session.execute(
        select(EvidenceAiAssessment).where(EvidenceAiAssessment.evidence_item_id == uuid.UUID(ev_id))
    ).scalar_one()
    assert row.ai_assessment_status == "suggested_valid"
    assert row.content_source == "r2_file"          # real bytes were pulled from (mock) R2
    assert row.extracted_text_chars > 0             # text really extracted
    assert row.provider_used == "groq"

    # read endpoint returns the suggestion
    resp = client.get(f"/api/v1/evidence/{ev_id}/ai-assessment", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["ai_assessment_status"] == "suggested_valid"
    # candidate is now marked processed
    db_session.refresh(cand[0])
    assert cand[0].processed_at is not None


# ── 2. AI-failure fallback: assessment records unable_to_assess, evidence intact ─
def test_ai_failure_falls_back_to_unable_to_assess(client, db_session, r2_configured, monkeypatch):
    def _boom(db, *, org_id, payload):
        raise RuntimeError("provider chain 502")

    monkeypatch.setattr(svc, "generate_evidence_assessment", _boom)
    org = bootstrap_org_user(client, email_prefix="aia-fail")
    ev_id = _upload_evidence_with_file(client, org["org_headers"])

    svc.run_evidence_assessment_candidate_drain(db_session)
    db_session.commit()

    row = db_session.execute(
        select(EvidenceAiAssessment).where(EvidenceAiAssessment.evidence_item_id == uuid.UUID(ev_id))
    ).scalar_one()
    assert row.ai_assessment_status == "unable_to_assess"
    assert row.explanation  # a reason is recorded
    # the evidence itself is untouched and still usable
    resp = client.get("/api/v1/evidence", headers=org["org_headers"])
    assert resp.status_code == 200
    assert any(e["id"] == ev_id for e in resp.json())


# ── 3. Isolation guarantee: drain writes ONLY the 2 new tables ───────────────
def test_isolation_drain_writes_only_its_own_tables(client, db_session, r2_configured, monkeypatch):
    from app.models.audit_log import AuditLog
    from app.models.domain_event import DomainEvent
    from app.models.evidence_control_link import EvidenceControlLink
    from app.models.evidence_item import EvidenceItem

    monkeypatch.setattr(svc, "generate_evidence_assessment", _canned_assessment("suggested_incomplete"))
    org = bootstrap_org_user(client, email_prefix="aia-iso")
    ev_id = _upload_evidence_with_file(client, org["org_headers"])

    def counts():
        return {
            "evidence_items": db_session.execute(select(func.count()).select_from(EvidenceItem)).scalar(),
            "evidence_control_links": db_session.execute(select(func.count()).select_from(EvidenceControlLink)).scalar(),
            "domain_events": db_session.execute(select(func.count()).select_from(DomainEvent)).scalar(),
            "audit_logs": db_session.execute(select(func.count()).select_from(AuditLog)).scalar(),
        }

    evidence_before = db_session.execute(select(EvidenceItem).where(EvidenceItem.id == uuid.UUID(ev_id))).scalar_one()
    review_status_before = evidence_before.review_status
    updated_at_before = evidence_before.updated_at
    before = counts()

    svc.run_evidence_assessment_candidate_drain(db_session)
    db_session.commit()

    after = counts()
    # every pre-existing table is byte-identical in row count -> no INSERT/DELETE elsewhere
    assert after == before, f"drain mutated other tables: {before} -> {after}"
    # the human-owned review_status (and the row) is untouched -> no UPDATE on evidence_items
    db_session.refresh(evidence_before)
    assert evidence_before.review_status == review_status_before
    assert evidence_before.updated_at == updated_at_before
    # only the feature's own table gained a row
    assert db_session.execute(select(func.count()).select_from(EvidenceAiAssessment)).scalar() == 1


# ── 4. Tenant scoping: org A cannot read org B's assessment ──────────────────
def test_tenant_scoping_on_assessment_read(client, db_session, r2_configured, monkeypatch):
    monkeypatch.setattr(svc, "generate_evidence_assessment", _canned_assessment("suggested_valid"))
    org_b = bootstrap_org_user(client, email_prefix="aia-b")
    ev_b = _upload_evidence_with_file(client, org_b["org_headers"])
    svc.run_evidence_assessment_candidate_drain(db_session)
    db_session.commit()

    # org B sees its own assessment
    assert client.get(f"/api/v1/evidence/{ev_b}/ai-assessment", headers=org_b["org_headers"]).status_code == 200

    org_a = bootstrap_org_user(client, email_prefix="aia-a")
    resp = client.get(f"/api/v1/evidence/{ev_b}/ai-assessment", headers=org_a["org_headers"])
    assert resp.status_code == 404, resp.text
