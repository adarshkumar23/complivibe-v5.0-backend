"""Evidence-vault Cloudflare R2 file storage — real behavior tests.

Uses `moto` (in-process S3-compatible mock) for a genuine end-to-end exercise of
the boto3 code path: put_object, checksum, org-scoped key, presigned URL. What
still needs a LIVE R2 credential to verify (documented, same honesty as the Azure
gpt-5.1 live-test gap): that Cloudflare's real endpoint accepts our SigV4 signing
and that a presigned URL actually downloads the object over the network. moto
validates the S3 API contract and our wrapper's correctness, not Cloudflare's
production surface.
"""

from __future__ import annotations

import boto3
import pytest
from botocore.config import Config
from moto.server import ThreadedMotoServer

from app.core.config import get_settings
from tests.helpers.auth_org import bootstrap_org_user

BUCKET = "complivibe-evidence-test"
PDF_BYTES = b"%PDF-1.4 fake but non-empty evidence document bytes"


@pytest.fixture(scope="module")
def moto_endpoint():
    """A real in-process S3-compatible server. The app makes genuine HTTP+SigV4
    calls to it via R2_ENDPOINT_URL -- exercising the true boto3 code path against
    a real endpoint (no in-process patching), which is the honest analogue of
    Cloudflare R2's S3 surface."""
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def r2_configured(monkeypatch, moto_endpoint):
    """Point the app's R2 settings at the local S3 server (is_configured -> True)
    and create the target bucket there."""
    s = get_settings()
    monkeypatch.setattr(s, "R2_ACCOUNT_ID", "test-account", raising=False)
    monkeypatch.setattr(s, "R2_ACCESS_KEY_ID", "testing", raising=False)
    monkeypatch.setattr(s, "R2_SECRET_ACCESS_KEY", "testing", raising=False)
    monkeypatch.setattr(s, "R2_BUCKET_NAME", BUCKET, raising=False)
    monkeypatch.setattr(s, "R2_ENDPOINT_URL", moto_endpoint, raising=False)
    _admin_client(moto_endpoint).create_bucket(Bucket=BUCKET)
    yield s


def _admin_client(endpoint):
    # us-east-1 for the test's bucket-admin/verification client: the moto server
    # rejects a bucket create sent to a region-specific endpoint with no location
    # constraint (real R2 accepts "auto"). The APP under test still uses "auto".
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


def _make_evidence(client, headers, title="R2 Evidence"):
    r = client.post("/api/v1/evidence", headers=headers, json={"title": title, "evidence_type": "document"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ── 1. Full upload + retrieve E2E against a mock S3 ──────────────────────────
def test_upload_stores_bytes_computes_checksum_and_sets_provider(client, db_session, r2_configured):
    import hashlib

    
    org = bootstrap_org_user(client, email_prefix="r2-up")
    ev_id = _make_evidence(client, org["org_headers"])

    resp = client.post(
        f"/api/v1/evidence/{ev_id}/file",
        headers=org["org_headers"],
        files={"file": ("audit-report.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # server-computed checksum from ACTUAL bytes (not client-supplied)
    assert body["checksum_sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["storage_provider"] == "cloudflare_r2"
    # org-scoped key prefix -> tenant isolation lives in the path
    assert body["storage_key"].startswith(f"org/{org['organization_id']}/evidence/{ev_id}/")

    # the bytes really landed in (mock) storage
    stored = _admin_client(r2_configured.R2_ENDPOINT_URL).get_object(Bucket=BUCKET, Key=body["storage_key"])
    assert stored["Body"].read() == PDF_BYTES

    # retrieval returns a presigned URL that references the object + expiry
    url_resp = client.get(f"/api/v1/evidence/{ev_id}/file-url", headers=org["org_headers"])
    assert url_resp.status_code == 200, url_resp.text
    assert body["storage_key"] in url_resp.json()["url"]
    assert url_resp.json()["expires_in_seconds"] == 300


# ── 2. EVIDENCE_UPLOADED domain event is emitted (the audit-flagged gap) ─────
def test_upload_emits_evidence_uploaded_event(client, db_session, r2_configured):
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.domain_event import DomainEvent

    org = bootstrap_org_user(client, email_prefix="r2-evt")
    ev_id = _make_evidence(client, org["org_headers"])
    client.post(
        f"/api/v1/evidence/{ev_id}/file",
        headers=org["org_headers"],
        files={"file": ("f.pdf", PDF_BYTES, "application/pdf")},
    ).raise_for_status()

    rows = db_session.execute(
        select(DomainEvent).where(
            DomainEvent.event_type == "evidence.uploaded",
            DomainEvent.entity_id == _uuid.UUID(ev_id),
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].organization_id == _uuid.UUID(org["organization_id"])


# ── 3. Graceful-inert: no R2 creds -> metadata path works, file upload 503 ───
def test_inert_without_credentials(client, db_session):
    # No r2_configured fixture -> settings have blank R2 creds.
    org = bootstrap_org_user(client, email_prefix="r2-inert")
    # metadata/URL path must remain fully functional
    ev_id = _make_evidence(client, org["org_headers"], title="Metadata only evidence")
    assert ev_id

    # a file upload attempt returns a clear 503, not a crash
    resp = client.post(
        f"/api/v1/evidence/{ev_id}/file",
        headers=org["org_headers"],
        files={"file": ("f.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


# ── 4. Tenant isolation: org A cannot get a URL for org B's evidence file ────
def test_org_a_cannot_get_signed_url_for_org_b_file(client, db_session, r2_configured):
    
    org_b = bootstrap_org_user(client, email_prefix="r2-tenant-b")
    ev_b = _make_evidence(client, org_b["org_headers"], title="Org B secret evidence")
    client.post(
        f"/api/v1/evidence/{ev_b}/file",
        headers=org_b["org_headers"],
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")},
    ).raise_for_status()

    org_a = bootstrap_org_user(client, email_prefix="r2-tenant-a")
    # org A asks for org B's evidence file URL -> 404 (not found in A's org scope)
    resp = client.get(f"/api/v1/evidence/{ev_b}/file-url", headers=org_a["org_headers"])
    assert resp.status_code == 404, resp.text


# ── 5. File-type allowlist: reject disallowed extensions ─────────────────────
@pytest.mark.parametrize("name,ctype", [("payload.exe", "application/octet-stream"), ("run.sh", "text/x-sh")])
def test_rejects_disallowed_file_types(client, db_session, r2_configured, name, ctype):
    org = bootstrap_org_user(client, email_prefix="r2-type")
    ev_id = _make_evidence(client, org["org_headers"])
    resp = client.post(
        f"/api/v1/evidence/{ev_id}/file",
        headers=org["org_headers"],
        files={"file": (name, b"#!/bin/sh\nevil", ctype)},
    )
    assert resp.status_code == 415, resp.text
    # and nothing was written to the evidence row
    url_resp = client.get(f"/api/v1/evidence/{ev_id}/file-url", headers=org["org_headers"])
    assert url_resp.status_code == 404


# ── 6. Size limit: reject oversized files ────────────────────────────────────
def test_rejects_oversized_file(client, db_session, r2_configured, monkeypatch):
    monkeypatch.setattr(r2_configured, "EVIDENCE_MAX_UPLOAD_BYTES", 1024, raising=False)
    org = bootstrap_org_user(client, email_prefix="r2-size")
    ev_id = _make_evidence(client, org["org_headers"])
    big = b"A" * 2048  # 2KB > 1KB cap
    resp = client.post(
        f"/api/v1/evidence/{ev_id}/file",
        headers=org["org_headers"],
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert resp.status_code == 413, resp.text
