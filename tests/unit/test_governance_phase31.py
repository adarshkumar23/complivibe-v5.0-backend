import uuid

from app.models.export_attestation import ExportAttestation
from app.models.export_job import ExportJob


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _completed_export(client, token: str, org: str) -> str:
    job = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(token, org),
        json={"export_type": "task_execution_json", "title": "Gov Export"},
    )
    assert job.status_code == 201
    export_id = job.json()["id"]
    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=_headers(token, org))
    assert run.status_code == 200
    assert run.json()["job"]["status"] == "completed"
    return export_id


def test_retention_and_attestation_permissions_seeded(client):
    owner = _register(client, "p31-owner1@example.com", "Pass1234!@", "P31 Org1")
    org = _org_id(client, owner)
    perms = client.get("/api/v1/auth/permissions", headers=_headers(owner, org))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert {"retention:read", "retention:write", "attestations:read", "attestations:write", "attestations:revoke"}.issubset(codes)


def test_retention_policy_crud_and_validation(client):
    owner = _register(client, "p31-owner2@example.com", "Pass1234!@", "P31 Org2")
    org = _org_id(client, owner)

    invalid_type = client.post(
        "/api/v1/governance/retention/policies",
        headers=_headers(owner, org),
        json={"name": "Bad", "entity_type": "unknown", "retention_days": 30, "lock_days": 7},
    )
    assert invalid_type.status_code == 400

    negative_days = client.post(
        "/api/v1/governance/retention/policies",
        headers=_headers(owner, org),
        json={"name": "Bad2", "entity_type": "export_job", "retention_days": -1, "lock_days": 0},
    )
    assert negative_days.status_code == 422

    created = client.post(
        "/api/v1/governance/retention/policies",
        headers=_headers(owner, org),
        json={"name": "Export policy", "entity_type": "export_job", "retention_days": 30, "lock_days": 7},
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    listed = client.get("/api/v1/governance/retention/policies", headers=_headers(owner, org))
    assert listed.status_code == 200
    assert any(row["id"] == policy_id for row in listed.json())

    updated = client.patch(
        f"/api/v1/governance/retention/policies/{policy_id}",
        headers=_headers(owner, org),
        json={"lock_days": 10, "legal_hold_default": True},
    )
    assert updated.status_code == 200
    assert updated.json()["lock_days"] == 10
    assert updated.json()["legal_hold_default"] is True

    archived = client.post(f"/api/v1/governance/retention/policies/{policy_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_export_lock_legal_hold_retention_evaluate_and_archive_blocking(client):
    owner = _register(client, "p31-owner3@example.com", "Pass1234!@", "P31 Org3")
    org = _org_id(client, owner)
    export_id = _completed_export(client, owner, org)

    apply_ret = client.post(
        f"/api/v1/exports/jobs/{export_id}/retention/apply",
        headers=_headers(owner, org),
        json={"lock_days": 5, "retention_days": 1},
    )
    assert apply_ret.status_code == 200
    assert apply_ret.json()["locked_until"] is not None
    assert apply_ret.json()["retention_until"] is not None

    blocked_archive = client.post(f"/api/v1/exports/jobs/{export_id}/archive", headers=_headers(owner, org))
    assert blocked_archive.status_code == 400

    legal_hold = client.post(
        f"/api/v1/exports/jobs/{export_id}/legal-hold",
        headers=_headers(owner, org),
        json={"enabled": True, "reason": "active investigation"},
    )
    assert legal_hold.status_code == 200
    assert legal_hold.json()["legal_hold"] is True

    still_blocked = client.post(f"/api/v1/exports/jobs/{export_id}/archive", headers=_headers(owner, org))
    assert still_blocked.status_code == 400

    evaluate = client.post(
        "/api/v1/governance/retention/evaluate",
        headers=_headers(owner, org),
        json={"entity_type": "export_job", "dry_run": True},
    )
    assert evaluate.status_code == 200
    body = evaluate.json()
    assert body["dry_run"] is True
    assert any(item["export_job_id"] == export_id for item in body["locked"])
    assert any(item["export_job_id"] == export_id for item in body["under_legal_hold"])


def test_attestation_create_scope_revoke_and_immutability(db_session, client):
    owner1 = _register(client, "p31-owner4@example.com", "Pass1234!@", "P31 Org4")
    owner2 = _register(client, "p31-owner5@example.com", "Pass1234!@", "P31 Org5")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    queued = client.post("/api/v1/exports/jobs", headers=_headers(owner1, org1), json={"export_type": "task_execution_json"})
    assert queued.status_code == 201
    queued_id = queued.json()["id"]
    bad_attest = client.post(
        f"/api/v1/exports/jobs/{queued_id}/attestations",
        headers=_headers(owner1, org1),
        json={"attestation_type": "internal_review", "statement": "not complete"},
    )
    assert bad_attest.status_code == 400

    export_id = _completed_export(client, owner1, org1)
    created = client.post(
        f"/api/v1/exports/jobs/{export_id}/attestations",
        headers=_headers(owner1, org1),
        json={"attestation_type": "internal_review", "statement": "reviewed internally"},
    )
    assert created.status_code == 201
    att_id = created.json()["id"]
    assert created.json()["export_checksum_sha256"] is not None
    assert created.json()["attestation_checksum_sha256"] is not None
    assert created.json()["attestation_signature"] is not None

    get_cross = client.get(f"/api/v1/attestations/{att_id}", headers=_headers(owner2, org2))
    assert get_cross.status_code == 404

    list_att = client.get(f"/api/v1/exports/jobs/{export_id}/attestations", headers=_headers(owner1, org1))
    assert list_att.status_code == 200
    assert any(row["id"] == att_id for row in list_att.json())

    revoke_missing_reason = client.post(
        f"/api/v1/attestations/{att_id}/revoke",
        headers=_headers(owner1, org1),
        json={"revocation_reason": ""},
    )
    assert revoke_missing_reason.status_code == 400

    revoked = client.post(
        f"/api/v1/attestations/{att_id}/revoke",
        headers=_headers(owner1, org1),
        json={"revocation_reason": "superseded"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert db_session.query(ExportAttestation).filter(ExportAttestation.id == uuid.UUID(att_id)).count() == 1

    export_row = db_session.query(ExportJob).filter(ExportJob.id == uuid.UUID(export_id)).one()
    assert export_row.package_json is not None
    assert export_row.manifest_json is not None


def test_verification_history_summary_and_audit_logs(client):
    owner = _register(client, "p31-owner6@example.com", "Pass1234!@", "P31 Org6")
    org = _org_id(client, owner)
    export_id = _completed_export(client, owner, org)

    verify1 = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=_headers(owner, org))
    verify2 = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=_headers(owner, org))
    assert verify1.status_code == 200
    assert verify2.status_code == 200

    history = client.get(f"/api/v1/exports/jobs/{export_id}/verification-history", headers=_headers(owner, org))
    assert history.status_code == 200
    assert len(history.json()["verifications"]) >= 2
    assert all(item["event_type"] == "export.verified" for item in history.json()["verifications"])

    summary = client.get("/api/v1/governance/retention/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    body = summary.json()
    assert "active_policies" in body
    assert "verifications_last_30d" in body

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org))
    actions = [item["action"] for item in logs.json()]
    assert "export_job.completed" in actions
    assert "export_job.verified" in actions
