import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.data_asset import DataAsset
from app.models.data_incident import DataIncident
from app.models.issue import Issue
from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.services.audit_service import AuditService

ALLOWED_DETECTOR_TYPES = {"anomaly_rule", "quality_breach", "retention_violation", "residency_violation", "manual"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
ALLOWED_STATUS = {"new", "investigating", "contained", "resolved", "dismissed"}
TERMINAL_STATES = {"resolved", "dismissed"}
ALLOWED_DETECTED_BY = {"scheduler", "rule_engine", "manual", "api"}

DETECTOR_TO_ISSUE_TYPE = {
    "anomaly_rule": "unauthorized_access",
    "quality_breach": "operational_failure",
    "retention_violation": "compliance_violation",
    "residency_violation": "compliance_violation",
    "manual": "custom",
}


class DataIncidentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> DataAsset:
        row = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.id == asset_id,
                DataAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
        return row

    def _require_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID) -> DataIncident:
        row = self.db.execute(
            select(DataIncident).where(
                DataIncident.organization_id == org_id,
                DataIncident.id == incident_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data incident not found")
        return row

    def _check_dedup(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID,
        detector_type: str,
        rule_type: str | None,
    ) -> DataIncident | None:
        since = self.utcnow() - timedelta(hours=1)
        return self.db.execute(
            select(DataIncident)
            .where(
                DataIncident.organization_id == org_id,
                DataIncident.data_asset_id == data_asset_id,
                DataIncident.detector_type == detector_type,
                DataIncident.detected_at >= since,
                DataIncident.status.not_in(["resolved", "dismissed"]),
                DataIncident.rule_type == rule_type,
            )
            .order_by(DataIncident.detected_at.desc())
        ).scalars().first()

    def _create_noncritical_alert(self, incident: DataIncident) -> None:
        # Medium/low (and high) incidents generate alert-only handling by default.
        self.db.add(
            ControlMonitoringAlert(
                organization_id=incident.organization_id,
                rule_id=None,
                definition_id=None,
                control_id=None,
                alert_type="data_incident",
                severity=incident.severity,
                status="open",
                title=f"Data incident: {incident.title}",
                description=incident.description,
                alert_context_json={
                    "incident_id": str(incident.id),
                    "detector_type": incident.detector_type,
                    "data_asset_id": str(incident.data_asset_id),
                },
            )
        )
        self.db.flush()

    def _create_issue_for_incident(self, incident: DataIncident, asset: DataAsset, actor_user_id: uuid.UUID | None) -> Issue:
        issue = Issue(
            organization_id=incident.organization_id,
            title=f"[DATA INCIDENT] {incident.title}",
            description=incident.description,
            issue_type=DETECTOR_TO_ISSUE_TYPE.get(incident.detector_type, "custom"),
            severity="critical",
            source_type="data_incident",
            source_id=incident.id,
            status="open",
            owner_id=asset.owner_id,
            assigned_to=asset.custodian_id,
            created_by=actor_user_id or asset.owner_id,
            resolution_note=None,
            resolved_at=None,
            closed_at=None,
            deleted_at=None,
        )
        self.db.add(issue)
        self.db.flush()
        return issue

    def create_incident(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID,
        detector_type: str,
        title: str,
        description: str,
        severity: str,
        *,
        rule_type: str | None = None,
        detector_ref_id: uuid.UUID | None = None,
        evidence: dict | None = None,
        detected_by: str = "rule_engine",
        actor_user_id: uuid.UUID | None = None,
    ) -> DataIncident | None:
        if detector_type not in ALLOWED_DETECTOR_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid detector_type")
        if severity not in ALLOWED_SEVERITIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid severity")
        if detected_by not in ALLOWED_DETECTED_BY:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid detected_by")

        asset = self._require_asset(org_id, data_asset_id)

        existing = self._check_dedup(org_id, data_asset_id, detector_type, rule_type)
        if existing is not None:
            return existing

        now = self.utcnow()
        incident = DataIncident(
            organization_id=org_id,
            data_asset_id=data_asset_id,
            detector_type=detector_type,
            detector_ref_id=detector_ref_id,
            title=title,
            description=description,
            severity=severity,
            status="new",
            rule_type=rule_type,
            evidence_json=evidence or {},
            linked_issue_id=None,
            detected_by=detected_by,
            detected_at=now,
            resolved_by=None,
            resolved_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(incident)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_incident.created",
            entity_type="data_incident",
            entity_id=incident.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "data_asset_id": str(data_asset_id),
                "detector_type": detector_type,
                "severity": severity,
                "status": incident.status,
            },
            metadata_json={"source": detected_by, "rule_type": rule_type},
        )

        if severity == "critical":
            issue = self._create_issue_for_incident(incident, asset, actor_user_id)
            incident.linked_issue_id = issue.id
            incident.updated_at = self.utcnow()
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="data_incident.auto_escalated",
                entity_type="issue",
                entity_id=issue.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={"incident_id": str(incident.id), "source_type": "data_incident"},
                metadata_json={"source": "auto"},
            )
        else:
            self._create_noncritical_alert(incident)

        CustomerCommitmentService(self.db).trigger_commitments_for_incident(
            org_id,
            incident.detector_type,
            incident_id=incident.id,
            actor_user_id=actor_user_id,
        )

        return incident

    def get_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID) -> DataIncident:
        return self._require_incident(org_id, incident_id)

    def list_incidents(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID | None = None,
        severity: str | None = None,
        status_filter: str | None = None,
        detector_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[DataIncident]:
        stmt = select(DataIncident).where(DataIncident.organization_id == org_id)
        if data_asset_id is not None:
            stmt = stmt.where(DataIncident.data_asset_id == data_asset_id)
        if severity is not None:
            if severity not in ALLOWED_SEVERITIES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid severity filter")
            stmt = stmt.where(DataIncident.severity == severity)
        if status_filter is not None:
            if status_filter not in ALLOWED_STATUS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status filter")
            stmt = stmt.where(DataIncident.status == status_filter)
        if detector_type is not None:
            if detector_type not in ALLOWED_DETECTOR_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid detector_type filter")
            stmt = stmt.where(DataIncident.detector_type == detector_type)

        return self.db.execute(
            stmt.order_by(DataIncident.detected_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def _set_status(self, org_id: uuid.UUID, incident_id: uuid.UUID, new_status: str, user_id: uuid.UUID, notes: str | None = None) -> DataIncident:
        row = self._require_incident(org_id, incident_id)
        if row.status in TERMINAL_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Cannot transition from terminal status '{row.status}'. "
                    "Resolved and dismissed incidents are immutable."
                ),
            )
        row.status = new_status
        if new_status == "resolved":
            row.resolved_by = user_id
            row.resolved_at = self.utcnow()
        row.updated_at = self.utcnow()
        if notes:
            evidence = dict(row.evidence_json or {})
            evidence["status_note"] = notes
            row.evidence_json = evidence
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_incident.status_changed",
            entity_type="data_incident",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def investigate_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID) -> DataIncident:
        return self._set_status(org_id, incident_id, "investigating", user_id)

    def contain_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID) -> DataIncident:
        return self._set_status(org_id, incident_id, "contained", user_id)

    def resolve_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, resolved_by: uuid.UUID, notes: str | None = None) -> DataIncident:
        return self._set_status(org_id, incident_id, "resolved", resolved_by, notes=notes)

    def dismiss_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID) -> DataIncident:
        return self._set_status(org_id, incident_id, "dismissed", user_id)

    def escalate_to_issue(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID) -> Issue:
        incident = self._require_incident(org_id, incident_id)
        if incident.linked_issue_id is not None:
            issue = self.db.get(Issue, incident.linked_issue_id)
            if issue is not None:
                return issue

        asset = self._require_asset(org_id, incident.data_asset_id)
        issue = Issue(
            organization_id=org_id,
            title=f"[DATA INCIDENT] {incident.title}",
            description=incident.description,
            issue_type=DETECTOR_TO_ISSUE_TYPE.get(incident.detector_type, "custom"),
            severity=incident.severity,
            source_type="data_incident",
            source_id=incident.id,
            status="open",
            owner_id=asset.owner_id,
            assigned_to=asset.custodian_id,
            created_by=user_id,
            resolution_note=None,
            resolved_at=None,
            closed_at=None,
            deleted_at=None,
        )
        self.db.add(issue)
        self.db.flush()

        incident.linked_issue_id = issue.id
        incident.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_incident.manually_escalated",
            entity_type="issue",
            entity_id=issue.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"incident_id": str(incident.id), "source_type": "data_incident"},
            metadata_json={"source": "manual"},
        )
        return issue

    def get_incident_summary(self, org_id: uuid.UUID) -> dict:
        total = int(self.db.execute(select(func.count(DataIncident.id)).where(DataIncident.organization_id == org_id)).scalar_one() or 0)

        by_severity_rows = self.db.execute(
            select(DataIncident.severity, func.count(DataIncident.id)).where(DataIncident.organization_id == org_id).group_by(DataIncident.severity)
        ).all()
        by_severity = {str(sev): int(count) for sev, count in by_severity_rows}

        by_status_rows = self.db.execute(
            select(DataIncident.status, func.count(DataIncident.id)).where(DataIncident.organization_id == org_id).group_by(DataIncident.status)
        ).all()
        by_status = {str(st): int(count) for st, count in by_status_rows}

        by_detector_rows = self.db.execute(
            select(DataIncident.detector_type, func.count(DataIncident.id))
            .where(DataIncident.organization_id == org_id)
            .group_by(DataIncident.detector_type)
        ).all()
        by_detector_type = {str(dt): int(count) for dt, count in by_detector_rows}

        new_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(DataIncident.organization_id == org_id, DataIncident.status == "new")
            ).scalar_one()
            or 0
        )

        auto_escalated_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.linked_issue_id.is_not(None),
                )
            ).scalar_one()
            or 0
        )

        assets_with_active_incidents = int(
            self.db.execute(
                select(func.count(func.distinct(DataIncident.data_asset_id))).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.status.in_(["new", "investigating", "contained"]),
                )
            ).scalar_one()
            or 0
        )

        return {
            "total": total,
            "by_severity": by_severity,
            "by_status": by_status,
            "by_detector_type": by_detector_type,
            "new_count": new_count,
            "auto_escalated_count": auto_escalated_count,
            "assets_with_active_incidents": assets_with_active_incidents,
        }
