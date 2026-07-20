"""Export signature validity window is stored but not surfaced (2026-07-20).

Migration 0318 gave export_jobs and export_attestations a signed validity window
(valid_from / not_after), and the signature covers both — changing either invalidates
it. But only ExportVerifyResponse exposed not_after, and nothing exposed valid_from at
all. A client could therefore see that a signature had expired only by asking the
verify endpoint; it could never see when the window opened or when it closes while
reading the job or the attestation itself.

These tests pin the fields onto the read schemas and onto the responses that build them.
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.exports import (
    ExportAttestationRead,
    ExportJobRead,
    ExportPackageResponse,
    ExportVerifyResponse,
)
from tests.helpers.auth_org import bootstrap_org_user

EXPORT_JOBS = "/api/v1/exports/jobs"


def _field_type(model, name):
    assert name in model.model_fields, f"{model.__name__} is missing {name}"
    return model.model_fields[name].annotation


def test_export_read_schemas_declare_the_validity_window():
    for model in (ExportJobRead, ExportAttestationRead):
        _field_type(model, "valid_from")
        _field_type(model, "not_after")


def test_not_after_is_consistent_across_every_export_read_schema():
    """not_after was present only on the verify response. Anything that reports a
    signature must also report when that signature stops being good."""
    for model in (ExportJobRead, ExportAttestationRead, ExportPackageResponse, ExportVerifyResponse):
        _field_type(model, "not_after")


def _create_completed_job(client, headers) -> dict:
    created = client.post(
        EXPORT_JOBS,
        headers=headers,
        json={"export_type": "evidence_manifest_json", "title": "Validity window export"},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    run = client.post(f"{EXPORT_JOBS}/{job_id}/run", headers=headers)
    assert run.status_code == 200, run.text
    detail = client.get(f"{EXPORT_JOBS}/{job_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    return detail.json()["job"]


def test_export_job_response_reports_the_window_it_was_signed_with(client):
    org = bootstrap_org_user(client, email_prefix="exp-window-job")
    job = _create_completed_job(client, org["org_headers"])

    assert job["integrity_signature"], "premise: the job is signed"
    assert job["valid_from"] is not None, "a signed export must report when its window opens"
    assert job["not_after"] is not None, "a signed export must report when its window closes"
    valid_from = datetime.fromisoformat(job["valid_from"])
    not_after = datetime.fromisoformat(job["not_after"])
    assert not_after > valid_from

    # The verify endpoint's not_after is the same window, not a second opinion.
    verify = client.post(f"{EXPORT_JOBS}/{job['id']}/verify", headers=org["org_headers"])
    assert verify.status_code == 200, verify.text
    assert verify.json()["not_after"] is not None
    assert datetime.fromisoformat(verify.json()["not_after"]) == not_after


def test_export_package_response_reports_the_window(client):
    org = bootstrap_org_user(client, email_prefix="exp-window-pkg")
    job = _create_completed_job(client, org["org_headers"])

    package = client.get(f"{EXPORT_JOBS}/{job['id']}/package", headers=org["org_headers"])
    assert package.status_code == 200, package.text
    body = package.json()
    assert body["integrity_signature"], "premise: the package is signed"
    assert body["valid_from"] is not None
    assert body["not_after"] is not None


def test_attestation_response_reports_its_own_window(client):
    org = bootstrap_org_user(client, email_prefix="exp-window-att")
    job = _create_completed_job(client, org["org_headers"])

    created = client.post(
        f"{EXPORT_JOBS}/{job['id']}/attestations",
        headers=org["org_headers"],
        json={"attestation_type": "internal_review", "statement": "Reviewed and accurate."},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["attestation_signature"], "premise: the attestation is signed"
    assert body["valid_from"] is not None, "the attestation signs its own window; it must report it"
    assert body["not_after"] is not None

    listed = client.get(f"{EXPORT_JOBS}/{job['id']}/attestations", headers=org["org_headers"])
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["valid_from"] == body["valid_from"]
    assert listed.json()[0]["not_after"] == body["not_after"]

    detail = client.get(f"/api/v1/attestations/{body['id']}", headers=org["org_headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["valid_from"] == body["valid_from"]
    assert detail.json()["not_after"] == body["not_after"]
