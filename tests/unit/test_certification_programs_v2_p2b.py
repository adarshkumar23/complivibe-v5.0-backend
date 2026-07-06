from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.certification_program_activation import CertificationProgramActivation
from app.models.compliance_deadline import ComplianceDeadline
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user


def test_v2_certification_program_activate_and_progress(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v2-cert")

    programs_resp = client.get("/api/v1/certification-programs", headers=org["org_headers"])
    assert programs_resp.status_code == 200
    programs = programs_resp.json()
    assert len(programs) >= 5
    target = next(row for row in programs if row["name"] == "SOC2-TypeI-8wk")

    activate_resp = client.post(
        f"/api/v1/certification-programs/{target['id']}/activate",
        headers=org["org_headers"],
        json={},
    )
    assert activate_resp.status_code == 201
    payload = activate_resp.json()
    assert payload["created_tasks"] > 0
    assert payload["created_evidence_requests"] > 0
    assert payload["created_deadlines"] > 0
    activation_id = UUID(payload["activation_id"])

    activation = db_session.execute(
        select(CertificationProgramActivation).where(CertificationProgramActivation.id == activation_id)
    ).scalar_one_or_none()
    assert activation is not None
    assert activation.organization_id == UUID(org["organization_id"])
    assert activation.status == "active"

    tasks = db_session.execute(
        select(Task).where(
            Task.organization_id == UUID(org["organization_id"]),
            Task.linked_entity_type == "certification_program",
            Task.linked_entity_id == activation_id,
        )
    ).scalars().all()
    assert any(row.task_type == "certification_task" for row in tasks)
    assert any(row.task_type == "evidence_request" for row in tasks)

    deadlines = db_session.execute(
        select(ComplianceDeadline).where(
            ComplianceDeadline.organization_id == UUID(org["organization_id"]),
            ComplianceDeadline.linked_entity_type == "certification_program",
            ComplianceDeadline.linked_entity_id == activation_id,
        )
    ).scalars().all()
    assert len(deadlines) > 0

    duplicate_resp = client.post(
        f"/api/v1/certification-programs/{target['id']}/activate",
        headers=org["org_headers"],
        json={},
    )
    assert duplicate_resp.status_code == 409

    progress_resp = client.get(
        f"/api/v1/certification-programs/{target['id']}/progress",
        headers=org["org_headers"],
    )
    assert progress_resp.status_code == 200
    progress = progress_resp.json()
    assert progress["activation_id"] == str(activation_id)
    assert len(progress["weekly_progress"]) == int(target["duration_weeks"])


def test_v2_certification_program_progress_detects_overdue_blocker(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v2-cert-block")
    programs_resp = client.get("/api/v1/certification-programs", headers=org["org_headers"])
    target = next(row for row in programs_resp.json() if row["name"] == "GDPR-Baseline-30day")

    activate_resp = client.post(
        f"/api/v1/certification-programs/{target['id']}/activate",
        headers=org["org_headers"],
        json={},
    )
    assert activate_resp.status_code == 201
    activation_id = UUID(activate_resp.json()["activation_id"])

    evidence_task = db_session.execute(
        select(Task).where(
            Task.organization_id == UUID(org["organization_id"]),
            Task.linked_entity_id == activation_id,
            Task.task_type == "evidence_request",
        )
    ).scalars().first()
    assert evidence_task is not None
    evidence_task.due_date = datetime.now(UTC) - timedelta(days=2)
    evidence_task.status = "open"
    db_session.commit()

    progress_resp = client.get(
        f"/api/v1/certification-programs/{target['id']}/progress",
        headers=org["org_headers"],
    )
    assert progress_resp.status_code == 200
    blockers = progress_resp.json()["blockers"]
    assert any("overdue task" in item.lower() for item in blockers)
