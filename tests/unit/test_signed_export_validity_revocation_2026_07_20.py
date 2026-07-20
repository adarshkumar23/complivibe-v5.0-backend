"""Regression: signed exports were unrevocable and never expired (2026-07-20).

Before the fix, ExportService.verify_job recomputed purely from SECRET_KEY: it ignored
the attestation status="revoked" flag entirely (a revoked attestation still validated
cryptographically forever) and there was no validity window at all (a signature from any
date verified indefinitely).

Now every signed export carries a validity window (valid_from/not_after, embedded in the
signed payload so it is tamper-evident), verify_job enforces expiry and attestation
revocation with distinct reasons, and it recomputes under the recorded signing_key_id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.export_job import ExportJob
from app.services.export_service import ExportService
from tests.helpers.auth_org import bootstrap_org_user


def _completed_export(client, org_headers: dict[str, str]) -> str:
    job = client.post(
        "/api/v1/exports/jobs",
        headers=org_headers,
        json={"export_type": "task_execution_json", "title": "Validity Export"},
    )
    assert job.status_code == 201, job.text
    export_id = job.json()["id"]
    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=org_headers)
    assert run.status_code == 200, run.text
    assert run.json()["job"]["status"] == "completed"
    return export_id


def test_fresh_export_verifies_successfully(client, db_session):
    """No over-correction: a freshly signed, non-revoked, non-expired export is valid."""
    org = bootstrap_org_user(client, email_prefix="exp-valid")
    export_id = _completed_export(client, org["org_headers"])

    verify = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=org["org_headers"])
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["valid"] is True
    assert body["checksum_match"] is True
    assert body["signature_match"] is True
    assert body["reason"] == "valid"
    assert body["revoked"] is False
    assert body["expired"] is False
    # The export was actually stamped with a ~1-year window.
    row = db_session.execute(select(ExportJob).where(ExportJob.id == uuid.UUID(export_id))).scalar_one()
    assert row.not_after is not None and row.valid_from is not None
    assert timedelta(days=364) < (row.not_after - row.valid_from) < timedelta(days=366)


def test_revoked_attestation_fails_verification(client, db_session):
    """A revoked attestation makes the export fail verification -- not just a DB flag."""
    org = bootstrap_org_user(client, email_prefix="exp-revoke")
    export_id = _completed_export(client, org["org_headers"])

    created = client.post(
        f"/api/v1/exports/jobs/{export_id}/attestations",
        headers=org["org_headers"],
        json={"attestation_type": "internal_review", "statement": "reviewed"},
    )
    assert created.status_code == 201, created.text
    att_id = created.json()["id"]

    # Before revocation it verifies fine.
    assert client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=org["org_headers"]).json()["valid"] is True

    revoked = client.post(
        f"/api/v1/attestations/{att_id}/revoke",
        headers=org["org_headers"],
        json={"revocation_reason": "signed off in error"},
    )
    assert revoked.status_code == 200, revoked.text

    verify = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=org["org_headers"])
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["valid"] is False
    assert body["revoked"] is True
    assert body["reason"] == "revoked"
    # The cryptography itself is still intact -- it fails on revocation, not a bad signature.
    assert body["checksum_match"] is True
    assert body["signature_match"] is True


def test_export_signed_more_than_a_year_ago_fails_as_expired(client, db_session):
    """An export whose not_after has passed fails verification with a distinct 'expired'
    reason -- and, because the window is embedded in the signature, it still verifies
    cryptographically (so 'expired' is separable from 'invalid signature')."""
    org = bootstrap_org_user(client, email_prefix="exp-expired")
    export_id = _completed_export(client, org["org_headers"])

    # Re-sign the export as if it had been produced >1 year ago (window now in the past),
    # signing over the SAME checksum verify recomputes so the signature stays valid.
    service = ExportService(db_session)
    row = db_session.execute(select(ExportJob).where(ExportJob.id == uuid.UUID(export_id))).scalar_one()
    past_from = datetime.now(UTC) - timedelta(days=400)
    past_not_after = datetime.now(UTC) - timedelta(days=35)
    row.valid_from = past_from
    row.not_after = past_not_after
    row.integrity_signature = service.compute_integrity_signature(
        row.checksum_sha256, valid_from=past_from, not_after=past_not_after, key_id=row.signing_key_id
    )
    db_session.commit()

    verify = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=org["org_headers"])
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["valid"] is False
    assert body["expired"] is True
    assert body["reason"] == "expired"
    assert body["checksum_match"] is True
    assert body["signature_match"] is True  # cryptographically intact, just expired


def test_tampering_the_window_breaks_the_signature(client, db_session):
    """The validity window is tamper-evident: changing not_after in the DB without
    re-signing invalidates the signature (reason 'invalid_signature', not silently
    accepted or mislabeled 'expired')."""
    org = bootstrap_org_user(client, email_prefix="exp-tamper")
    export_id = _completed_export(client, org["org_headers"])

    row = db_session.execute(select(ExportJob).where(ExportJob.id == uuid.UUID(export_id))).scalar_one()
    # Push not_after far into the future WITHOUT re-signing.
    row.not_after = datetime.now(UTC) + timedelta(days=3650)
    db_session.commit()

    verify = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=org["org_headers"])
    body = verify.json()
    assert body["valid"] is False
    assert body["signature_match"] is False
    assert body["reason"] == "invalid_signature"
