import uuid

from app.core.security import get_password_hash
from app.models.export_job import ExportJob
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def test_export_permissions_seeded(client, db_session):
    owner = _register(client, "p30-owner1@example.com", "Pass1234!@", "P30 Org1")
    org = _org_id(client, owner)

    cm_user = _create_active_user_with_role(db_session, org, "p30-cm@example.com", "compliance_manager")
    auditor_user = _create_active_user_with_role(db_session, org, "p30-aud@example.com", "auditor")
    cm_token = _login(client, cm_user.email, "Pass1234!@")
    auditor_token = _login(client, auditor_user.email, "Pass1234!@")

    cm_perms = client.get("/api/v1/auth/permissions", headers=_headers(cm_token, org)).json()["permission_codes"]
    assert "exports:read" in cm_perms
    assert "exports:write" in cm_perms
    assert "exports:run" in cm_perms
    assert "exports:verify" in cm_perms

    aud_perms = client.get("/api/v1/auth/permissions", headers=_headers(auditor_token, org)).json()["permission_codes"]
    assert "exports:read" in aud_perms
    assert "exports:verify" in aud_perms


def test_export_job_create_list_tenant_scope_and_validation(client):
    owner1 = _register(client, "p30-owner2@example.com", "Pass1234!@", "P30 Org2")
    owner2 = _register(client, "p30-owner3@example.com", "Pass1234!@", "P30 Org3")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    framework_id = client.get("/api/v1/frameworks", headers=_headers(owner1)).json()[0]["id"]
    bad_framework_job = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner1, org1),
        json={"export_type": "framework_readiness_json", "framework_id": framework_id},
    )
    assert bad_framework_job.status_code == 400

    create = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner1, org1),
        json={"export_type": "task_execution_json", "title": "Tasks Export"},
    )
    assert create.status_code == 201
    export_id = create.json()["id"]
    assert create.json()["status"] == "queued"

    list_org1 = client.get("/api/v1/exports/jobs", headers=_headers(owner1, org1))
    list_org2 = client.get("/api/v1/exports/jobs", headers=_headers(owner2, org2))
    assert list_org1.status_code == 200
    assert list_org2.status_code == 200
    assert any(item["id"] == export_id for item in list_org1.json()["jobs"])
    assert all(item["id"] != export_id for item in list_org2.json()["jobs"])


def test_run_compliance_report_export_and_verify_and_tamper_detection(client, db_session):
    owner = _register(client, "p30-owner4@example.com", "Pass1234!@", "P30 Org4")
    org = _org_id(client, owner)

    report = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "executive_summary", "dry_run": False},
    )
    assert report.status_code == 200
    source_report_id = report.json()["report"]["id"]

    create_job = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner, org),
        json={
            "export_type": "compliance_report_json",
            "source_report_id": source_report_id,
            "title": "Compliance Report Export",
        },
    )
    assert create_job.status_code == 201
    export_id = create_job.json()["id"]

    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=_headers(owner, org))
    assert run.status_code == 200
    assert run.json()["job"]["status"] == "completed"
    assert run.json()["job"]["checksum_sha256"] is not None
    assert run.json()["job"]["signature_algorithm"] == "HMAC-SHA256"

    package = client.get(f"/api/v1/exports/jobs/{export_id}/package", headers=_headers(owner, org))
    manifest = client.get(f"/api/v1/exports/jobs/{export_id}/manifest", headers=_headers(owner, org))
    assert package.status_code == 200
    assert manifest.status_code == 200
    assert package.json()["package_json"]["manifest"]["package_checksum_sha256"] == run.json()["job"]["checksum_sha256"]
    assert "sections" in package.json()["package_json"]["data"]

    verify_ok = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=_headers(owner, org))
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True
    assert verify_ok.json()["checksum_match"] is True
    assert verify_ok.json()["signature_match"] is True

    row = db_session.query(ExportJob).filter(ExportJob.id == uuid.UUID(export_id)).one()
    tampered = dict(row.package_json or {})
    tampered["title"] = "tampered"
    row.package_json = tampered
    db_session.commit()

    verify_bad = client.post(f"/api/v1/exports/jobs/{export_id}/verify", headers=_headers(owner, org))
    assert verify_bad.status_code == 200
    assert verify_bad.json()["valid"] is False
    assert verify_bad.json()["checksum_match"] is False


def test_framework_readiness_and_evidence_manifest_exports(client):
    owner = _register(client, "p30-owner5@example.com", "Pass1234!@", "P30 Org5")
    org = _org_id(client, owner)
    framework_id = client.get("/api/v1/frameworks", headers=_headers(owner)).json()[0]["id"]

    activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(owner, org),
        json={"notes": "activate for export"},
    )
    assert activate.status_code == 200

    readiness_job = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner, org),
        json={"export_type": "framework_readiness_json", "framework_id": framework_id},
    )
    assert readiness_job.status_code == 201
    readiness_id = readiness_job.json()["id"]
    readiness_run = client.post(f"/api/v1/exports/jobs/{readiness_id}/run", headers=_headers(owner, org))
    assert readiness_run.status_code == 200
    readiness_package = client.get(f"/api/v1/exports/jobs/{readiness_id}/package", headers=_headers(owner, org)).json()
    assert readiness_package["package_json"]["data"]["framework"]["id"] == framework_id

    evidence_create = client.post(
        "/api/v1/evidence",
        headers=_headers(owner, org),
        json={"title": "Export Evidence", "evidence_type": "attestation"},
    )
    assert evidence_create.status_code == 201

    evidence_job = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner, org),
        json={"export_type": "evidence_manifest_json"},
    )
    assert evidence_job.status_code == 201
    evidence_id = evidence_job.json()["id"]
    evidence_run = client.post(f"/api/v1/exports/jobs/{evidence_id}/run", headers=_headers(owner, org))
    assert evidence_run.status_code == 200
    evidence_package = client.get(f"/api/v1/exports/jobs/{evidence_id}/package", headers=_headers(owner, org))
    assert evidence_package.status_code == 200
    evidence_rows = evidence_package.json()["package_json"]["data"]["evidence_items"]
    assert len(evidence_rows) >= 1
    assert "storage_key" not in evidence_rows[0]
    assert "review_status" in evidence_rows[0]


def test_export_cancellation_archive_status_rules_and_summary(client):
    owner = _register(client, "p30-owner6@example.com", "Pass1234!@", "P30 Org6")
    org = _org_id(client, owner)

    queued = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner, org),
        json={"export_type": "task_execution_json"},
    )
    assert queued.status_code == 201
    queued_id = queued.json()["id"]

    cancel = client.post(f"/api/v1/exports/jobs/{queued_id}/cancel", headers=_headers(owner, org), json={"reason": "not needed"})
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    completed = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner, org),
        json={"export_type": "task_execution_json"},
    )
    assert completed.status_code == 201
    completed_id = completed.json()["id"]
    run = client.post(f"/api/v1/exports/jobs/{completed_id}/run", headers=_headers(owner, org))
    assert run.status_code == 200
    assert run.json()["job"]["status"] == "completed"

    cancel_completed = client.post(f"/api/v1/exports/jobs/{completed_id}/cancel", headers=_headers(owner, org), json={"reason": "late"})
    assert cancel_completed.status_code == 400

    archive = client.post(f"/api/v1/exports/jobs/{completed_id}/archive", headers=_headers(owner, org))
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    summary = client.get("/api/v1/exports/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_exports"] >= 2
    assert payload["completed_exports"] >= 0
    assert payload["archived_exports"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org))
    actions = [item["action"] for item in logs.json()]
    assert "export_job.created" in actions
    assert "export_job.completed" in actions
    assert "export_job.archived" in actions


def test_package_and_manifest_require_completed_and_source_report_org_validation(client):
    owner1 = _register(client, "p30-owner7@example.com", "Pass1234!@", "P30 Org7")
    owner2 = _register(client, "p30-owner8@example.com", "Pass1234!@", "P30 Org8")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    report_org2 = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner2, org2),
        json={"report_type": "executive_summary", "dry_run": False},
    )
    assert report_org2.status_code == 200
    report2_id = report_org2.json()["report"]["id"]

    bad_source = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner1, org1),
        json={"export_type": "compliance_report_json", "source_report_id": report2_id},
    )
    assert bad_source.status_code == 400

    queued = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(owner1, org1),
        json={"export_type": "task_execution_json"},
    )
    assert queued.status_code == 201
    queued_id = queued.json()["id"]

    package = client.get(f"/api/v1/exports/jobs/{queued_id}/package", headers=_headers(owner1, org1))
    manifest = client.get(f"/api/v1/exports/jobs/{queued_id}/manifest", headers=_headers(owner1, org1))
    assert package.status_code == 400
    assert manifest.status_code == 400
