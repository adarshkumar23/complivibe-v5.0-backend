from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import uuid

from app.models.audit_schedule import AuditSchedule
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.obligation import Obligation
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

    def _expected_next_date(pattern: str) -> date:
        if pattern == "annual":
            return base_date + timedelta(days=365)
        if pattern == "semi_annual":
            return base_date + timedelta(days=182)
        if pattern == "quarterly":
            month = base_date.month + 3
            year = base_date.year
            while month > 12:
                month -= 12
                year += 1
            return date(year, month, 1)
        year = base_date.year + (1 if base_date.month == 12 else 0)
        month = 1 if base_date.month == 12 else base_date.month + 1
        return date(year, month, 1)

    for pattern in ["annual", "semi_annual", "quarterly", "monthly"]:
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
        assert linked.json()["next_audit_date"] == _expected_next_date(pattern).isoformat()


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


def test_a46_completeness_flags_missing_expired_and_rejected_evidence(client, db_session):
    """Regression: an evidence package's "completeness" was only ever a bare item_count.
    This endpoint must instead say *which* specific controls in the package's framework
    scope are still missing usable evidence, and *why* (never added, evidence expired,
    or evidence rejected on review) -- not just a number."""
    org = bootstrap_org_user(client, email_prefix="a46-completeness")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id, org["user_id"])

    package = client.post(
        f"{PACKAGE_BASE}?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={"title": "Completeness pkg", "scope_framework_ids": [framework_id]},
    ).json()

    obligation = Obligation(
        framework_id=uuid.UUID(framework_id),
        reference_code="A46-COMPLETE",
        title="Obligation A46",
        description="seeded for test",
        jurisdiction="US",
        status="active",
    )
    db_session.add(obligation)
    db_session.commit()

    control_never_added = _create_control(client, org["org_headers"], "Never added control")
    control_expired = _create_control(client, org["org_headers"], "Expired evidence control")
    control_rejected = _create_control(client, org["org_headers"], "Rejected evidence control")
    control_ok = _create_control(client, org["org_headers"], "Compliant control")

    for c in (control_never_added, control_expired, control_rejected, control_ok):
        row = db_session.query(Control).filter_by(id=uuid.UUID(c["id"])).one()
        row.obligation_id = obligation.id
    db_session.commit()

    evidence_expired = _create_evidence(client, org["org_headers"], "Expired evidence")
    ev_row = db_session.query(EvidenceItem).filter_by(id=uuid.UUID(evidence_expired["id"])).one()
    ev_row.freshness_status = "expired"
    db_session.commit()

    evidence_rejected = _create_evidence(client, org["org_headers"], "Rejected evidence")
    ev_row2 = db_session.query(EvidenceItem).filter_by(id=uuid.UUID(evidence_rejected["id"])).one()
    ev_row2.review_status = "rejected"
    db_session.commit()

    evidence_ok = _create_evidence(client, org["org_headers"], "Good evidence")

    for control, evidence in (
        (control_expired, evidence_expired),
        (control_rejected, evidence_rejected),
        (control_ok, evidence_ok),
    ):
        resp = client.post(
            f"{PACKAGE_BASE}/{package['id']}/items",
            headers=org["org_headers"],
            json={"control_id": control["id"], "evidence_id": evidence["id"]},
        )
        assert resp.status_code == 201

    completeness = client.get(f"{PACKAGE_BASE}/{package['id']}/completeness", headers=org["org_headers"])
    assert completeness.status_code == 200
    body = completeness.json()
    assert body["total_controls_in_scope"] == 4
    assert body["controls_with_current_evidence"] == 1
    reasons_by_control = {row["control_id"]: row["reason"] for row in body["controls_missing_evidence"]}
    assert reasons_by_control[control_never_added["id"]] == "never_added"
    assert reasons_by_control[control_expired["id"]] == "evidence_expired"
    assert reasons_by_control[control_rejected["id"]] == "evidence_rejected"
    assert control_ok["id"] not in reasons_by_control
    assert body["scope_changed_since_creation"] is False


def test_a46_scope_changed_since_creation_flag_after_engagement_scope_narrows(client, db_session):
    """Regression: a package never signaled when the parent engagement's scope moved
    out from under it after evidence had already been selected. scope_changed_since_creation
    must flip to true (on both the package read and the completeness report) once the
    engagement's own scope_framework_ids no longer matches what the package snapshotted."""
    org = bootstrap_org_user(client, email_prefix="a46-scope-drift")
    resp = client.get("/api/v1/frameworks", headers=org["headers"])
    frameworks = resp.json()
    assert len(frameworks) >= 2
    fw1, fw2 = frameworks[0]["id"], frameworks[1]["id"]

    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])
    package = client.post(
        f"{PACKAGE_BASE}?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={"title": "Drift pkg", "scope_framework_ids": [fw1]},
    ).json()
    assert package["scope_changed_since_creation"] is False

    patch = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw2]},
    )
    assert patch.status_code == 200

    detail = client.get(f"{PACKAGE_BASE}/{package['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["scope_changed_since_creation"] is True

    completeness = client.get(f"{PACKAGE_BASE}/{package['id']}/completeness", headers=org["org_headers"])
    assert completeness.status_code == 200
    assert completeness.json()["scope_changed_since_creation"] is True
