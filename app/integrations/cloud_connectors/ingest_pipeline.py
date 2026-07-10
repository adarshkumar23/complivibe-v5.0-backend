import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.finding_mapping_service import FindingControlMappingService
from app.integrations.cloud_connectors.monitoring_service import CloudFindingMonitoringService
from app.models.cloud_evidence_connector import CloudEvidenceConnector, CloudEvidenceConnectorEvent
from app.services.evidence_service import EvidenceService


@dataclass
class NormalizedFinding:
    provider_event_id: str
    category: str
    severity: str
    resource_id: str | None
    title: str
    description: str
    raw_payload: dict


def ingest_normalized_finding(db: Session, connector: CloudEvidenceConnector, finding: NormalizedFinding) -> CloudEvidenceConnectorEvent:
    """Shared pipeline for every provider: dedup -> EvidenceService (never insert into
    evidence_items directly) -> Feature 2 mapping -> Feature 3 monitoring. Called only
    after the caller has verified the provider-specific signature/auth."""
    org_id = connector.organization_id
    now = datetime.now(UTC)

    existing = db.execute(
        select(CloudEvidenceConnectorEvent).where(
            CloudEvidenceConnectorEvent.connector_id == connector.id,
            CloudEvidenceConnectorEvent.provider_event_id == finding.provider_event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    event = CloudEvidenceConnectorEvent(
        organization_id=org_id,
        connector_id=connector.id,
        provider_event_id=finding.provider_event_id,
        status="created",
        finding_summary_json={
            "category": finding.category,
            "severity": finding.severity,
            "resource_id": finding.resource_id,
            "title": finding.title,
        },
        received_at=now,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(CloudEvidenceConnectorEvent).where(
                CloudEvidenceConnectorEvent.connector_id == connector.id,
                CloudEvidenceConnectorEvent.provider_event_id == finding.provider_event_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise

    evidence = EvidenceService(db).create_imported_evidence(
        organization_id=org_id,
        title=finding.title,
        description=finding.description,
        evidence_type="cloud_finding",
        source_import_tool=f"cloud_connector_{connector.connector_type}",
        collected_at=now,
        original_created_at=now,
        actor_user_id=None,
    )
    event.evidence_item_id = evidence.id
    db.flush()

    suggestion = FindingControlMappingService(db).suggest_for_finding(
        org_id,
        event.id,
        evidence.id,
        finding.category,
        auto_apply_allowed=connector.auto_apply_deterministic_mappings,
        actor_user_id=None,
    )

    if suggestion is not None and suggestion.status == "applied":
        CloudFindingMonitoringService(db).record_finding_test_run(
            org_id,
            suggestion.suggested_control_id,
            evidence.id,
            finding.severity,
            finding.title,
        )

    CloudConnectorService(db).record_event_received(connector, success=True)
    return event
