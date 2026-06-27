from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import uuid

from app.models.audit_schedule import AuditSchedule
from app.models.compliance_deadline import ComplianceDeadline
from app.models.email_outbox import EmailOutbox
from tests.helpers.auth_org import bootstrap_org_user

SCHEDULE_BASE = "/api/v1/compliance/audit-schedules"
ENGAGEMENT_BASE = "/api/v1/compliance/audit-engagements"
PACKAGE_BASE = "/api/v1/compliance/evidence-packages"


def _framework_id(client, headers: dict[str, str]) -> str:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    frameworks = resp.json()
    assert frameworks
    return frameworks[0]["id"]


def _create_engagement(client, headers: dict[str, str], framework_id: str, auditor_user_id: str, title: str = "Audit") -> dict:
    resp = client.post(
        ENGAGEMENT_BASE,
        headers=headers,
        json={
            "title": title,
            "audit_type": "internal_readiness",
            "scope_framework_ids": [framework_id],
            "assigned_auditor_ids": [auditor_user_id],
            "start_date": (date.today() + timedelta(days=5)).isoformat(),
            "end_date": (date.today() + timedelta(days=20)).isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_schedule(
    client,
    headers: dict[str, str],
    *,
    framework_id: str,
    recurrence_pattern: str = "annual",
    next_audit_date: date | None = None,
    prep_days: int = 30,
    title: str = "Scheduled Audit",
) -> dict:
    resp = client.post(
        SCHEDULE_BASE,
        headers=headers,
        json={
            "title": title,
            "audit_type": "internal_readiness",
            "framework_id": framework_id,
            "recurrence_pattern": recurrence_pattern,
            "next_audit_date": (next_audit_date or date.today() + timedelta(days=5)).isoformat(),
            "preparation_reminder_days": prep_days,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_control(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "description": "desc",
            "control_type": "process",
            "criticality": "medium",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_evidence(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={"title": title, "evidence_type": "other"},
    )
    assert resp.status_code == 201
    return resp.json()


def _create_package(client, headers: dict[str, str], engagement_id: str, title: str = "Package") -> dict:
    resp = client.post(
        f"{PACKAGE_BASE}?engagement_id={engagement_id}",
        headers=headers,
        json={"title": title, "scope_framework_ids": []},
    )
    assert resp.status_code == 201
    return resp.json()


def test_a45_create_schedule_valid_recurrence_and_invalid_pattern(client):
    org = bootstrap_org_user(client, email_prefix="a45-create")
    framework_id = _framework_id(client, org["headers"])

    for pattern in ["annual", "semi_annual", "quarterly", "monthly"]:
        row = _create_schedule(client, org["org_headers"], framework_id=framework_id, recurrence_pattern=pattern, title=f"{pattern}")
        assert row["recurrence_pattern"] == pattern

    bad = client.post(
        SCHEDULE_BASE,
        headers=org["org_headers"],
        json={
            "title": "bad",
            "audit_type": "internal_readiness",
            "framework_id": framework_id,
            "recurrence_pattern": "weekly",
            "next_audit_date": (date.today() + timedelta(days=5)).isoformat(),
            "preparation_reminder_days": 30,
        },
    )
    assert bad.status_code == 422


def test_a45_status_transitions_and_cancelled_terminal(client):
    org = bootstrap_org_user(client, email_prefix="a45-status")
    framework_id = _framework_id(client, org["headers"])
    row = _create_schedule(client, org["org_headers"], framework_id=framework_id)

    paused = client.post(f"{SCHEDULE_BASE}/{row['id']}/status", headers=org["org_headers"], json={"new_status": "paused"})
    assert paused.status_code == 200
    active = client.post(f"{SCHEDULE_BASE}/{row['id']}/status", headers=org["org_headers"], json={"new_status": "active"})
    assert active.status_code == 200
    cancelled = client.post(f"{SCHEDULE_BASE}/{row['id']}/status", headers=org["org_headers"], json={"new_status": "cancelled"})
    assert cancelled.status_code == 200

    invalid = client.post(f"{SCHEDULE_BASE}/{row['id']}/status", headers=org["org_headers"], json={"new_status": "active"})
    assert invalid.status_code == 422


def test_a45_link_engagement_advances_next_audit_date_for_patterns(client):
    org = bootstrap_org_user(client, email_prefix="a45-link")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id, org["user_id"])
    base_date = date.today() + timedelta(days=10)

    offsets = {
        "annual": 365,
        "semi_annual": 182,
        "quarterly": 91,
        "monthly": 30,
    }

    for pattern, days in offsets.items():
        schedule = _create_schedule(
            client,
            org["org_headers"],
            framework_id=framework_id,
            recurrence_pattern=pattern,
            next_audit_date=base_date,
            title=f"{pattern}-schedule",
        )
        linked = client.post(
            f"{SCHEDULE_BASE}/{schedule['id']}/link-engagement",
            headers=org["org_headers"],
            json={"engagement_id": engagement["id"]},
        )
        assert linked.status_code == 200
        assert linked.json()["last_audit_engagement_id"] == engagement["id"]
        assert linked.json()["next_audit_date"] == (base_date + timedelta(days=days)).isoformat()


def test_a45_reminder_sweep_window_calendar_and_skip_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a45-sweep")
    framework_id = _framework_id(client, org["headers"])

    inside = _create_schedule(
        client,
        org["org_headers"],
        framework_id=framework_id,
        next_audit_date=date.today() + timedelta(days=2),
        prep_days=7,
        title="Inside window",
    )
    outside = _create_schedule(
        client,
        org["org_headers"],
        framework_id=framework_id,
        next_audit_date=date.today() + timedelta(days=40),
        prep_days=7,
        title="Outside window",
    )
    paused = _create_schedule(
        client,
        org["org_headers"],
        framework_id=framework_id,
        next_audit_date=date.today() + timedelta(days=2),
        prep_days=7,
        title="Paused schedule",
    )
    paused_set = client.post(f"{SCHEDULE_BASE}/{paused['id']}/status", headers=org["org_headers"], json={"new_status": "paused"})
    assert paused_set.status_code == 200

    recently_reminded = _create_schedule(
        client,
        org["org_headers"],
        framework_id=framework_id,
        next_audit_date=date.today() + timedelta(days=2),
        prep_days=7,
        title="Recently reminded",
    )
    reminded_row = db_session.query(AuditSchedule).filter_by(id=uuid.UUID(recently_reminded["id"])).one()
    reminded_row.last_reminder_sent_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    sweep = client.post(f"{SCHEDULE_BASE}/trigger-reminder-sweep", headers=org["org_headers"])
    assert sweep.status_code == 200
    payload = sweep.json()
    assert payload["processed"] >= 1
    assert payload["reminders_sent"] >= 1
    assert payload["calendars_created"] >= 1

    outbox_rows = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org["organization_id"])).all()
    assert any(row.event_type == "audit.schedule.reminder" for row in outbox_rows)

    deadline_rows = db_session.query(ComplianceDeadline).filter(
        ComplianceDeadline.organization_id == uuid.UUID(org["organization_id"]),
        ComplianceDeadline.linked_entity_type == "audit_schedule",
        ComplianceDeadline.linked_entity_id == uuid.UUID(inside["id"]),
    ).all()
    assert len(deadline_rows) == 1

    outside_deadline = db_session.query(ComplianceDeadline).filter(
        ComplianceDeadline.organization_id == uuid.UUID(org["organization_id"]),
        ComplianceDeadline.linked_entity_id == uuid.UUID(outside["id"]),
    ).all()
    assert len(outside_deadline) == 0


def test_a45_org_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="a45-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a45-org-b")
    framework_id = _framework_id(client, org_a["headers"])

    schedule = _create_schedule(client, org_a["org_headers"], framework_id=framework_id, title="Org A schedule")
    forbidden = client.get(f"{SCHEDULE_BASE}/{schedule['id']}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404


def test_a46_create_package_add_remove_manifest_and_duplicate_guard(client):
    org = bootstrap_org_user(client, email_prefix="a46-package")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id, org["user_id"], title="Evidence Audit")

    package = _create_package(client, org["org_headers"], engagement["id"], title="Package A")
    assert package["cover_sheet_data"]["organization_name"]
    assert package["cover_sheet_data"]["audit_title"] == "Evidence Audit"

    control1 = _create_control(client, org["org_headers"], "Control A")
    evidence1 = _create_evidence(client, org["org_headers"], "Evidence A")

    add1 = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={
            "control_id": control1["id"],
            "evidence_id": evidence1["id"],
            "framework_requirement_ref": "SOC2 CC6.1",
        },
    )
    assert add1.status_code == 201

    detail = client.get(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["item_count"] == 1
    assert len(detail.json()["chain_of_custody"]) >= 2

    dup = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={
            "control_id": control1["id"],
            "evidence_id": evidence1["id"],
            "framework_requirement_ref": "SOC2 CC6.1",
        },
    )
    assert dup.status_code == 422

    item_id = add1.json()["id"]
    remove = client.delete(f"{PACKAGE_BASE}/{package['id']}/items/{item_id}", headers=org["org_headers"])
    assert remove.status_code == 204

    detail2 = client.get(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"])
    assert detail2.status_code == 200
    assert detail2.json()["item_count"] == 0
    assert len(detail2.json()["chain_of_custody"]) >= 3


def test_a46_assemble_export_archive_flow_and_constraints(client):
    org = bootstrap_org_user(client, email_prefix="a46-flow")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id, org["user_id"])

    empty_package = _create_package(client, org["org_headers"], engagement["id"], title="Empty")
    empty_assemble = client.post(f"{PACKAGE_BASE}/{empty_package['id']}/assemble", headers=org["org_headers"])
    assert empty_assemble.status_code == 422

    package = _create_package(client, org["org_headers"], engagement["id"], title="Flow")
    control = _create_control(client, org["org_headers"], "Control Flow")
    evidence = _create_evidence(client, org["org_headers"], "Evidence Flow")

    added = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={"control_id": control["id"], "evidence_id": evidence["id"], "framework_requirement_ref": None},
    )
    assert added.status_code == 201

    assemble = client.post(f"{PACKAGE_BASE}/{package['id']}/assemble", headers=org["org_headers"])
    assert assemble.status_code == 200
    assembled_payload = assemble.json()
    assert assembled_payload["status"] == "assembled"
    assert assembled_payload["assembled_at"] is not None

    add_blocked = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={"control_id": control["id"], "evidence_id": _create_evidence(client, org["org_headers"], "extra")["id"]},
    )
    assert add_blocked.status_code == 422

    draft_export = client.post(f"{PACKAGE_BASE}/{empty_package['id']}/export", headers=org["org_headers"])
    assert draft_export.status_code == 422

    export = client.post(f"{PACKAGE_BASE}/{package['id']}/export", headers=org["org_headers"])
    assert export.status_code == 200
    assert export.json()["status"] == "exported"

    archive = client.post(f"{PACKAGE_BASE}/{package['id']}/archive", headers=org["org_headers"])
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"


def test_a46_manifest_grouping_custody_append_only_and_soft_delete_rule(client):
    org = bootstrap_org_user(client, email_prefix="a46-manifest")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id, org["user_id"])

    package = _create_package(client, org["org_headers"], engagement["id"], title="Manifest")
    control1 = _create_control(client, org["org_headers"], "Control 1")
    control2 = _create_control(client, org["org_headers"], "Control 2")
    ev1 = _create_evidence(client, org["org_headers"], "Evidence 1")
    ev2 = _create_evidence(client, org["org_headers"], "Evidence 2")

    add1 = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={"control_id": control1["id"], "evidence_id": ev1["id"], "framework_requirement_ref": "SOC2 CC6.1"},
    )
    assert add1.status_code == 201
    add2 = client.post(
        f"{PACKAGE_BASE}/{package['id']}/items",
        headers=org["org_headers"],
        json={"control_id": control2["id"], "evidence_id": ev2["id"], "framework_requirement_ref": None},
    )
    assert add2.status_code == 201

    before = client.get(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"]).json()["chain_of_custody"]

    assembled = client.post(f"{PACKAGE_BASE}/{package['id']}/assemble", headers=org["org_headers"])
    assert assembled.status_code == 200

    after = client.get(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"]).json()["chain_of_custody"]
    assert len(after) == len(before) + 1
    assert after[: len(before)] == before

    manifest = client.get(f"{PACKAGE_BASE}/{package['id']}/manifest", headers=org["org_headers"])
    assert manifest.status_code == 200
    body = manifest.json()
    assert "SOC2 CC6.1" in body["items_by_framework_ref"]
    assert len(body["items_by_framework_ref"]["SOC2 CC6.1"]) == 1
    assert len(body["items_ungrouped"]) == 1

    blocked_delete = client.delete(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"])
    assert blocked_delete.status_code == 422
