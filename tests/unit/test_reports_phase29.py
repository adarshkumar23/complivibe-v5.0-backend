import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.compliance_report import ComplianceReport
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

import pytest

# The framework catalogue and starter obligations used to be seeded lazily by the
# framework/obligation GET handlers -- i.e. a read endpoint that wrote rows and
# committed. Those handlers are now side-effect-free, so any test that needs the
# catalogue present must declare that dependency explicitly.
pytestmark = pytest.mark.usefixtures("seeded_reference_data")



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


def test_reports_permissions_seeded_and_readonly_cannot_generate(client, db_session):
    owner = _register(client, "p29-owner1@example.com", "Pass1234!@", "P29 Org1")
    org = _org_id(client, owner)

    cm_user = _create_active_user_with_role(db_session, org, "p29-cm@example.com", "compliance_manager")
    ro_user = _create_active_user_with_role(db_session, org, "p29-ro@example.com", "readonly")
    cm_token = _login(client, cm_user.email, "Pass1234!@")
    ro_token = _login(client, ro_user.email, "Pass1234!@")

    cm_perms = client.get("/api/v1/auth/permissions", headers=_headers(cm_token, org))
    assert cm_perms.status_code == 200
    cm_codes = set(cm_perms.json()["permission_codes"])
    assert "reports:read" in cm_codes
    assert "reports:write" in cm_codes
    assert "reports:generate" in cm_codes

    ro_perms = client.get("/api/v1/auth/permissions", headers=_headers(ro_token, org))
    assert ro_perms.status_code == 200
    ro_codes = set(ro_perms.json()["permission_codes"])
    assert "reports:read" in ro_codes
    assert "reports:generate" not in ro_codes

    denied = client.post(
        "/api/v1/reports/generate",
        headers=_headers(ro_token, org),
        json={"report_type": "executive_summary", "dry_run": True},
    )
    assert denied.status_code == 403


def test_report_generate_dry_run_does_not_persist_and_includes_caveat(client, db_session):
    owner = _register(client, "p29-owner2@example.com", "Pass1234!@", "P29 Org2")
    org = _org_id(client, owner)

    dry = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "executive_summary", "dry_run": True},
    )
    assert dry.status_code == 200
    body = dry.json()
    assert body["dry_run"] is True
    assert body["report"]["status"] == "draft"
    assert any(section["section_key"] == "caveats" for section in body["sections"])
    assert "does not constitute legal advice" in next(section for section in body["sections"] if section["section_key"] == "caveats")[
        "body_markdown"
    ]

    persisted_count = db_session.query(ComplianceReport).filter(ComplianceReport.organization_id == uuid.UUID(org)).count()
    assert persisted_count == 0


def test_live_report_persists_sections_provenance_and_tenant_scoping(client):
    owner1 = _register(client, "p29-owner3@example.com", "Pass1234!@", "P29 Org3")
    owner2 = _register(client, "p29-owner4@example.com", "Pass1234!@", "P29 Org4")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    materialize = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(owner1, org1),
        json={"dry_run": False, "snapshot_types": ["control_health"]},
    )
    assert materialize.status_code == 200

    generated = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner1, org1),
        json={"report_type": "executive_summary", "dry_run": False},
    )
    assert generated.status_code == 200
    report = generated.json()["report"]
    sections = generated.json()["sections"]
    report_id = report["id"]
    assert report["status"] == "generated"
    assert report["age_days"] == 0
    assert report["section_count"] >= 2
    assert report["is_archived"] is False
    assert report["is_stale"] is False
    assert "report_generated" in report["context_flags"]
    assert len(sections) >= 2
    snapshot_section = next(section for section in sections if section["section_key"] == "score_snapshot")
    assert len(snapshot_section["data_json"]["snapshots"]) >= 1

    listed = client.get("/api/v1/reports", headers=_headers(owner1, org1))
    assert listed.status_code == 200
    listed_row = next(row for row in listed.json()["reports"] if row["id"] == report_id)
    assert listed_row["section_count"] >= 2
    assert "report_generated" in listed_row["context_flags"]
    assert any(row["id"] == report_id for row in listed.json()["reports"])

    detail = client.get(f"/api/v1/reports/{report_id}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    assert len(detail.json()["sections"]) == len(sections)

    provenance = client.get(f"/api/v1/reports/{report_id}/provenance", headers=_headers(owner1, org1))
    assert provenance.status_code == 200
    assert "source_model_counts" in provenance.json()["provenance_json"]
    assert isinstance(provenance.json()["section_provenance"], list)

    cross_tenant = client.get(f"/api/v1/reports/{report_id}", headers=_headers(owner2, org2))
    assert cross_tenant.status_code == 404


def test_report_archive_and_summary_and_audit(client):
    owner = _register(client, "p29-owner5@example.com", "Pass1234!@", "P29 Org5")
    org = _org_id(client, owner)

    generated = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "task_execution", "dry_run": False},
    )
    assert generated.status_code == 200
    report_id = generated.json()["report"]["id"]

    archived = client.post(f"/api/v1/reports/{report_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["is_archived"] is True
    assert "report_archived" in archived.json()["context_flags"]

    logs_first = client.get("/api/v1/audit-logs", headers=_headers(owner, org))
    assert logs_first.status_code == 200
    first_archived_actions = [item["action"] for item in logs_first.json()].count("report.archived")

    archived_second = client.post(f"/api/v1/reports/{report_id}/archive", headers=_headers(owner, org))
    assert archived_second.status_code == 200
    assert archived_second.json()["status"] == "archived"

    logs_second = client.get("/api/v1/audit-logs", headers=_headers(owner, org))
    assert logs_second.status_code == 200
    second_archived_actions = [item["action"] for item in logs_second.json()].count("report.archived")
    assert second_archived_actions == first_archived_actions

    summary = client.get("/api/v1/reports/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_reports"] >= 1
    assert payload["generated_reports"] >= 0
    assert payload["archived_reports"] >= 1
    assert payload["reports_last_30d"] >= 1
    assert "stale_reports_30d" in payload
    assert "archived_ratio" in payload
    assert isinstance(payload["context_flags"], list)
    assert "latest_risk_posture_at" in payload

    actions = [item["action"] for item in logs_second.json()]
    assert "report.generated" in actions
    assert "report.archived" in actions


def test_framework_readiness_requires_active_framework_and_returns_data(client):
    owner = _register(client, "p29-owner6@example.com", "Pass1234!@", "P29 Org6")
    org = _org_id(client, owner)

    framework_id = client.get("/api/v1/frameworks", headers=_headers(owner)).json()[0]["id"]

    inactive = client.get(f"/api/v1/reports/frameworks/{framework_id}/readiness", headers=_headers(owner, org))
    assert inactive.status_code == 400

    activated = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(owner, org),
        json={"notes": "phase29 test"},
    )
    assert activated.status_code == 200

    active = client.get(f"/api/v1/reports/frameworks/{framework_id}/readiness", headers=_headers(owner, org))
    assert active.status_code == 200
    body = active.json()
    assert body["framework_id"] == framework_id
    assert "active_obligations" in body
    assert "obligations_with_controls" in body
    assert "latest_score_snapshots" in body


def test_deterministic_report_types_render_expected_sections(client):
    owner = _register(client, "p29-owner7@example.com", "Pass1234!@", "P29 Org7")
    org = _org_id(client, owner)

    evidence_report = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "evidence_readiness", "dry_run": True},
    )
    assert evidence_report.status_code == 200
    evidence_section_keys = {item["section_key"] for item in evidence_report.json()["sections"]}
    assert {"evidence_status", "expired_evidence", "evidence_needing_review", "controls_without_evidence", "caveats"}.issubset(
        evidence_section_keys
    )

    risk_report = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "risk_posture", "dry_run": True},
    )
    assert risk_report.status_code == 200
    risk_section_keys = {item["section_key"] for item in risk_report.json()["sections"]}
    assert {"risk_status", "critical_high_risks", "risks_without_controls", "accepted_risks", "caveats"}.issubset(risk_section_keys)


def test_report_generate_rejects_invalid_period_window(client):
    owner = _register(client, "p29-owner8@example.com", "Pass1234!@", "P29 Org8")
    org = _org_id(client, owner)
    now = datetime.now(UTC).replace(microsecond=0)

    invalid = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={
            "report_type": "executive_summary",
            "dry_run": True,
            "period_start": now.isoformat(),
            "period_end": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert invalid.status_code == 422
    assert "period_end" in invalid.json()["detail"]


def test_reports_summary_flags_stale_generated_reports(client, db_session):
    owner = _register(client, "p29-owner9@example.com", "Pass1234!@", "P29 Org9")
    org = _org_id(client, owner)

    generated = client.post(
        "/api/v1/reports/generate",
        headers=_headers(owner, org),
        json={"report_type": "task_execution", "dry_run": False},
    )
    assert generated.status_code == 200
    report_id = uuid.UUID(generated.json()["report"]["id"])

    row = db_session.query(ComplianceReport).filter(ComplianceReport.id == report_id).one()
    row.generated_at = datetime.now(UTC) - timedelta(days=45)
    db_session.commit()

    summary = client.get("/api/v1/reports/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["stale_reports_30d"] >= 1
    assert "stale_generated_reports_present" in payload["context_flags"]
