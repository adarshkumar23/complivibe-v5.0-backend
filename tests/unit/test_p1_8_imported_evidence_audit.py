"""P1.8 regression: create_imported_evidence (used by the cloud-connector
ingest path) must write an audit-log entry. Previously it added+flushed the
EvidenceItem with no AuditService call, so cloud-connector-ingested evidence
had no creation audit trail. Bulk-import writes its own import.* audit and
opts out (write_audit=False) to avoid a duplicate.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.evidence_service import EvidenceService
from tests.helpers.auth_org import bootstrap_org_user


def _count_audits(db, org_id, entity_id):
    return len(
        db.execute(
            select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.entity_id == entity_id)
        ).scalars().all()
    )


def test_create_imported_evidence_writes_audit_by_default(client, db_session):
    org = bootstrap_org_user(client, email_prefix="imp-ev-audit")
    org_id = uuid.UUID(org["organization_id"])

    row = EvidenceService(db_session).create_imported_evidence(
        organization_id=org_id,
        title="SOC2 from AWS connector",
        description=None,
        evidence_type="document",
        source_import_tool="aws_security_hub",
        collected_at=None,
        original_created_at=None,
        actor_user_id=None,
    )
    db_session.flush()
    assert _count_audits(db_session, org_id, row.id) >= 1, "imported evidence must have a creation audit log"


def test_create_imported_evidence_can_opt_out_for_bulk_import(client, db_session):
    org = bootstrap_org_user(client, email_prefix="imp-ev-optout")
    org_id = uuid.UUID(org["organization_id"])

    row = EvidenceService(db_session).create_imported_evidence(
        organization_id=org_id,
        title="bulk row",
        description=None,
        evidence_type="document",
        source_import_tool="csv",
        collected_at=None,
        original_created_at=None,
        actor_user_id=None,
        write_audit=False,
    )
    db_session.flush()
    assert _count_audits(db_session, org_id, row.id) == 0, "opt-out must not write a duplicate audit"
