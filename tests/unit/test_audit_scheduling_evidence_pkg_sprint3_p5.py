from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.compliance.services.audit_schedule_service import AuditScheduleService
from app.exports.services.export_content_builder import ExportContentBuilder
from app.models.audit_engagement import AuditEngagement
from app.models.audit_log import AuditLog
from app.models.audit_schedule import AuditSchedule
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_obligation_state import OrganizationObligationState
from tests.helpers.auth_org import bootstrap_org_user

import pytest

# The framework catalogue and starter obligations used to be seeded lazily by the
# framework/obligation GET handlers -- i.e. a read endpoint that wrote rows and
# committed. Those handlers are now side-effect-free, so any test that needs the
# catalogue present must declare that dependency explicitly.
pytestmark = pytest.mark.usefixtures("seeded_reference_data")



def _framework_id(client, headers: dict[str, str]) -> uuid.UUID:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload
    return uuid.UUID(payload[0]["id"])


def _create_audit(client, headers: dict[str, str], framework_id: uuid.UUID, title: str = "Scheduled Audit") -> dict:
    payload = {
        "title": title,
        "audit_type": "internal_readiness",
        "scope_framework_ids": [str(framework_id)],
        "assigned_auditor_ids": [],
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "test",
    }
    response = client.post("/api/v1/compliance/audit-engagements", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], title: str, review_status: str = "verified") -> uuid.UUID:
    payload = {"title": title, "description": "evidence", "evidence_type": "document", "source": "manual"}
    response = client.post("/api/v1/evidence", headers=headers, json=payload)
    assert response.status_code == 201
    evidence_id = uuid.UUID(response.json()["id"])
    return evidence_id


def test_s3_p5_audit_scheduling_creation_update_idempotency_and_logs(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p5-sched")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    framework_id = _framework_id(client, org["headers"])

    service = AuditScheduleService(db_session)
    created = service.create_schedule(
        org_id=org_id,
        title="Annual SOC 2 Audit",
        recurrence="annual",
        lead_time_days=30,
        audit_type="internal_readiness",
        framework_id=framework_id,
        assigned_lead_auditor_id=user_id,
        created_by=user_id,
    )
    db_session.commit()
    db_session.refresh(created)

    # (a) annual due date should be ~1 year from today.
    delta_days = (created.next_due_date - date.today()).days
    assert 360 <= delta_days <= 370

    # (d) beyond window should not trigger.
    not_triggered = service.run_scheduled_audit_creation(org_id)
    db_session.commit()
    assert not_triggered == 0

    # Force due date into lead-time window for trigger tests.
    created.next_due_date = date.today() + timedelta(days=3)
    created.next_audit_date = created.next_due_date
    db_session.commit()

    # (b) creates engagement + deadline.
    triggered = service.run_scheduled_audit_creation(org_id)
    db_session.commit()
    assert triggered == 1

    engagement = (
        db_session.query(AuditEngagement)
        .filter(AuditEngagement.organization_id == org_id, AuditEngagement.title.like("Annual SOC 2 Audit - %"))
        .order_by(AuditEngagement.created_at.desc())
        .first()
    )
    assert engagement is not None

    deadline = (
        db_session.query(ComplianceDeadline)
        .filter(
            ComplianceDeadline.organization_id == org_id,
            ComplianceDeadline.linked_entity_type == "audit_engagement",
            ComplianceDeadline.linked_entity_id == engagement.id,
        )
        .first()
    )
    assert deadline is not None
    assert deadline.title.startswith("Audit Due: Annual SOC 2 Audit")

    # (c) idempotent for same due date.
    second = service.run_scheduled_audit_creation(org_id)
    db_session.commit()
    assert second == 0

    # (e) recurrence update recomputes due date.
    old_due = created.next_due_date
    updated = service.update_schedule(org_id, created.id, recurrence="monthly")
    db_session.commit()
    assert updated.recurrence == "monthly"
    assert updated.next_due_date != old_due

    # (f) audit logs for created + auto-created engagement.
    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == org_id).all()
    }
    assert "audit_schedule.created" in actions
    assert "audit_schedule.engagement_auto_created" in actions


def test_s3_p5_evidence_package_builder_and_export_endpoint(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p5-evidence")
    org_b = bootstrap_org_user(client, email_prefix="s3p5-evidence-b")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    framework_id = _framework_id(client, org["headers"])
    activate = client.post(f"/api/v1/frameworks/{framework_id}/activate", headers=org["org_headers"], json={})
    assert activate.status_code == 200
    audit = _create_audit(client, org["org_headers"], framework_id, title="Evidence Audit")

    # Seed obligation -> control mapping in this org.
    obligation = Obligation(
        framework_id=framework_id,
        reference_code="CC-1.1",
        title="Obligation for export test",
        description="desc",
        obligation_type="control",
        jurisdiction="global",
        status="active",
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.add(
        OrganizationObligationState(
            organization_id=org_id,
            obligation_id=obligation.id,
            applicability_status="applicable",
            implementation_status="in_progress",
            owner_user_id=user_id,
        )
    )
    control = Control(
        organization_id=org_id,
        obligation_id=obligation.id,
        title="Control for Evidence Package",
        description="control desc",
        control_type="process",
        status="implemented",
        criticality="medium",
        owner_user_id=user_id,
        source="custom",
    )
    db_session.add(control)
    db_session.flush()
    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=control.id,
            obligation_id=obligation.id,
            mapping_type="supports",
            confidence="manual_confirmed",
            status="active",
            created_by_user_id=user_id,
        )
    )
    db_session.flush()

    verified_evidence_id = _create_evidence(client, org["org_headers"], "Verified Evidence")
    imported_verified_evidence_id = _create_evidence(client, org["org_headers"], "Imported Verified Evidence")
    pending_evidence_id = _create_evidence(client, org["org_headers"], "Pending Evidence")

    verified_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == verified_evidence_id).one()
    verified_row.review_status = "verified"
    verified_row.status = "active"
    verified_row.reviewed_at = datetime.now(UTC)
    verified_row.collected_at = datetime(2026, 5, 1, 11, 0, tzinfo=UTC)

    imported_verified_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == imported_verified_evidence_id).one()
    imported_verified_row.review_status = "verified"
    imported_verified_row.status = "active"
    imported_verified_row.reviewed_at = datetime.now(UTC)
    imported_verified_row.source = "imported"
    imported_verified_row.source_import_tool = "drata"
    imported_verified_row.original_created_at = datetime(2021, 1, 4, 15, 45, tzinfo=UTC)

    pending_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == pending_evidence_id).one()
    pending_row.review_status = "needs_review"
    pending_row.status = "active"

    db_session.add(
        EvidenceControlLink(
            organization_id=org_id,
            evidence_item_id=verified_evidence_id,
            control_id=control.id,
            link_status="active",
            confidence="manual_confirmed",
            linked_by_user_id=user_id,
            linked_at=datetime.now(UTC),
        )
    )
    db_session.add(
        EvidenceControlLink(
            organization_id=org_id,
            evidence_item_id=pending_evidence_id,
            control_id=control.id,
            link_status="active",
            confidence="manual_confirmed",
            linked_by_user_id=user_id,
            linked_at=datetime.now(UTC),
        )
    )
    db_session.add(
        EvidenceControlLink(
            organization_id=org_id,
            evidence_item_id=imported_verified_evidence_id,
            control_id=control.id,
            link_status="active",
            confidence="manual_confirmed",
            linked_by_user_id=user_id,
            linked_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    # (g) builder returns populated sections and correct summary counts.
    content = ExportContentBuilder(db_session).build_audit_evidence_package(
        org_id=org_id,
        audit_id=uuid.UUID(audit["id"]),
        framework_id=framework_id,
    )
    assert content.sections
    summary = {k: v for k, v in content.sections[0].rows}
    # Total Obligations now reflects the full real obligation catalog for the activated
    # framework (seeded starter obligations + the one manually added above), not just
    # obligations that happen to have an OrganizationObligationState row.
    real_obligation_count = db_session.query(Obligation).filter(Obligation.framework_id == framework_id).count()
    assert summary["Total Obligations"] == str(real_obligation_count)
    assert real_obligation_count > 1
    assert summary["Obligations With Verified Evidence"] == "1"
    assert summary["Total Controls"] == "1"
    assert summary["Controls With Verified Evidence"] == "1"
    assert summary["Total Evidence Items"] == "2"

    # (h) only verified evidence is included.
    flattened = "\\n".join(item for section in content.sections for item in section.items)
    assert "Verified Evidence" in flattened
    assert "Imported Verified Evidence" in flattened
    assert "Pending Evidence" not in flattened
    assert "Verified Evidence | source=manual | evidence_at=2026-05-01T11:00:00" in flattened
    assert "Imported Verified Evidence | source=imported | evidence_at=2021-01-04T15:45:00" in flattened

    # (i) PDF export non-empty and (j) DOCX export non-empty.
    pdf_resp = client.get(
        f"/api/v1/compliance/audits/{audit['id']}/evidence-package/export?format=pdf&framework_id={framework_id}",
        headers=org["org_headers"],
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")
    assert len(pdf_resp.content) > 100

    docx_resp = client.get(
        f"/api/v1/compliance/audits/{audit['id']}/evidence-package/export?format=docx&framework_id={framework_id}",
        headers=org["org_headers"],
    )
    assert docx_resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in docx_resp.headers["content-type"]
    assert len(docx_resp.content) > 100

    # (k) cross-org access blocked.
    forbidden = client.get(
        f"/api/v1/compliance/audits/{audit['id']}/evidence-package/export?format=pdf",
        headers=org_b["org_headers"],
    )
    assert forbidden.status_code == 404

    # (l) export audit logs are written.
    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == org_id).all()
    }
    assert "export.generated" in actions
