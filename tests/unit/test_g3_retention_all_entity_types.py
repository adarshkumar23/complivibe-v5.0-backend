from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.compliance_report import ComplianceReport
from app.models.evidence_item import EvidenceItem
from app.models.score_snapshot import ScoreSnapshot
from tests.helpers.auth_org import bootstrap_org_user

RETENTION_BASE = "/api/v1/governance/retention"


def _create_policy(client, headers, *, entity_type: str, retention_days: int = 1):
    resp = client.post(
        f"{RETENTION_BASE}/policies",
        headers=headers,
        json={
            "name": f"{entity_type} policy",
            "entity_type": entity_type,
            "retention_days": retention_days,
            "lock_days": 0,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_retention_enforcement_covers_all_five_entity_types(client, db_session):
    """G3 item 1: RetentionService.evaluate() supported all 5 ALLOWED_RETENTION_ENTITY_TYPES
    at the validation/save layer, but actual enforcement only ever queried ExportJob --
    compliance_report/evidence_item/score_snapshot/audit_log retention policies were
    saveable but never enforced by anything. This proves all 5 are now genuinely
    enforced: an old row of each type is created, a short-retention policy is set for
    that entity_type, and evaluate() must report it as retention_elapsed/eligible_for_archive.
    """
    org = bootstrap_org_user(client, email_prefix="g3-retention-all5")
    headers = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    old_created_at = datetime.now(UTC) - timedelta(days=30)

    report = ComplianceReport(
        organization_id=org_id,
        report_type="soc2",
        title="Old Report",
        status="generated",
        generated_at=old_created_at,
    )
    evidence = EvidenceItem(
        organization_id=org_id,
        title="Old Evidence",
        evidence_type="document",
        source="manual",
        status="active",
    )
    snapshot = ScoreSnapshot(
        organization_id=org_id,
        snapshot_type="compliance_readiness",
        score=80,
        grade="B",
        calculated_at=old_created_at,
    )
    audit_row = AuditLog(
        organization_id=org_id,
        actor_user_id=owner_id,
        action="test.action",
        entity_type="test_entity",
    )
    db_session.add_all([report, evidence, snapshot, audit_row])
    db_session.commit()

    # Backdate created_at directly (TimestampMixin server_default fires on insert).
    for model, row_id in (
        (ComplianceReport, report.id),
        (EvidenceItem, evidence.id),
        (ScoreSnapshot, snapshot.id),
        (AuditLog, audit_row.id),
    ):
        db_session.query(model).filter(model.id == row_id).update({"created_at": old_created_at})
    db_session.commit()

    for entity_type in ("compliance_report", "evidence_item", "score_snapshot", "audit_log"):
        _create_policy(client, headers, entity_type=entity_type, retention_days=1)

        evaluate_resp = client.post(
            f"{RETENTION_BASE}/evaluate",
            headers=headers,
            json={"entity_type": entity_type, "dry_run": True},
        )
        assert evaluate_resp.status_code == 200, evaluate_resp.text
        body = evaluate_resp.json()
        print(f"ENTITY_TYPE={entity_type} BODY={body}")
        assert body["retention_elapsed"], (
            f"entity_type={entity_type}: expected the 30-day-old row to be reported as "
            f"retention_elapsed under a 1-day retention policy, got: {body}"
        )
        assert body["eligible_for_archive"], (
            f"entity_type={entity_type}: expected the 30-day-old row to be eligible_for_archive, "
            f"got: {body}"
        )
