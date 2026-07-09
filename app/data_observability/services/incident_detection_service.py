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
from app.core.validation import validate_choice

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

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _severity_rank(value: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(value, 0)

    def incident_context(self, row: DataIncident, *, now: datetime | None = None) -> dict:
        evaluated_now = now or self.utcnow()
        detected_at = self._as_utc(row.detected_at) or evaluated_now
        age_hours = max(0, int((evaluated_now - detected_at).total_seconds() // 3600))
        evidence = dict(row.evidence_json or {})
        recurrence_count = int(evidence.get("recurrence_count", 1))
        context_flags: list[str] = []
        if row.detected_by in {"scheduler", "rule_engine", "api"}:
            context_flags.append("auto_detected")
        if recurrence_count > 1:
            context_flags.append("repeated_incident")
        if row.status == "new":
            context_flags.append("untriaged")
            if age_hours >= 24:
                context_flags.append("stale_new_incident")
        if row.severity in {"critical", "high"} and row.status in {"new", "investigating", "contained"}:
            context_flags.append("high_impact_open_incident")
        if row.linked_issue_id is not None:
            issue = self.db.get(Issue, row.linked_issue_id)
            if issue is None or issue.deleted_at is not None:
                context_flags.append("linked_issue_missing_or_closed")
        return {
            "age_hours": age_hours,
            "recurrence_count": recurrence_count,
            "escalated_to_issue": row.linked_issue_id is not None,
            "context_flags": context_flags,
        }

    def incident_response_payload(self, row: DataIncident) -> dict:
        context = self.incident_context(row)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "data_asset_id": row.data_asset_id,
            "detector_type": row.detector_type,
            "detector_ref_id": row.detector_ref_id,
            "title": row.title,
            "description": row.description,
            "severity": row.severity,
            "status": row.status,
            "rule_type": row.rule_type,
            "evidence_json": row.evidence_json,
            "linked_issue_id": row.linked_issue_id,
            "detected_by": row.detected_by,
            "detected_at": row.detected_at,
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at,
            "status_notes_json": row.status_notes_json or [],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "age_hours": context["age_hours"],
            "recurrence_count": context["recurrence_count"],
            "escalated_to_issue": context["escalated_to_issue"],
            "context_flags": context["context_flags"],
        }

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
        detector_type = validate_choice(detector_type, ALLOWED_DETECTOR_TYPES, "detector_type")
        severity = validate_choice(severity, ALLOWED_SEVERITIES, "severity")
        detected_by = validate_choice(detected_by, ALLOWED_DETECTED_BY, "detected_by")
        asset = self._require_asset(org_id, data_asset_id)

        existing = self._check_dedup(org_id, data_asset_id, detector_type, rule_type)
        if existing is not None:
            now = self.utcnow()
            evidence_json = dict(existing.evidence_json or {})
            recurrence_count = int(evidence_json.get("recurrence_count", 1)) + 1
            evidence_json["recurrence_count"] = recurrence_count
            evidence_json["last_seen_at"] = now.isoformat()
            if evidence_json.get("first_seen_at") is None:
                evidence_json["first_seen_at"] = (self._as_utc(existing.detected_at) or now).isoformat()

            severity_upgraded = self._severity_rank(severity) > self._severity_rank(existing.severity)
            previous_severity = existing.severity
            if severity_upgraded:
                existing.severity = severity
                evidence_json["previous_severity"] = previous_severity
                evidence_json["severity_upgraded_at"] = now.isoformat()
            if evidence:
                evidence_json["latest_evidence"] = evidence

            existing.evidence_json = evidence_json
            existing.updated_at = now
            self.db.flush()

            if existing.severity == "critical" and existing.linked_issue_id is None:
                issue = self._create_issue_for_incident(existing, asset, actor_user_id)
                existing.linked_issue_id = issue.id
                existing.updated_at = self.utcnow()
                self.db.flush()
                AuditService(self.db).write_audit_log(
                    action="data_incident.auto_escalated",
                    entity_type="issue",
                    entity_id=issue.id,
                    organization_id=org_id,
                    actor_user_id=actor_user_id,
                    after_json={"incident_id": str(existing.id), "source_type": "data_incident"},
                    metadata_json={"source": "dedup_escalation"},
                )

            AuditService(self.db).write_audit_log(
                action="data_incident.deduplicated",
                entity_type="data_incident",
                entity_id=existing.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={
                    "recurrence_count": recurrence_count,
                    "severity": existing.severity,
                    "severity_upgraded": severity_upgraded,
                },
                metadata_json={"source": detected_by, "rule_type": rule_type},
            )
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
            severity = validate_choice(severity, ALLOWED_SEVERITIES, "severity")
            stmt = stmt.where(DataIncident.severity == severity)
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_STATUS, "status")
            stmt = stmt.where(DataIncident.status == status_filter)
        if detector_type is not None:
            detector_type = validate_choice(detector_type, ALLOWED_DETECTOR_TYPES, "detector_type")
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
            # Append (never overwrite) so notes from earlier transitions (e.g. investigate,
            # contain) survive later transitions (e.g. resolve, dismiss) and remain queryable
            # via GET /data-observability/incidents/{id} (status_notes_json).
            history = list(row.status_notes_json or [])
            history.append(
                {
                    "status": new_status,
                    "note": notes,
                    "user_id": str(user_id),
                    "at": self.utcnow().isoformat(),
                }
            )
            row.status_notes_json = history
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_incident.status_changed",
            entity_type="data_incident",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "note": notes},
            metadata_json={"source": "api"},
        )
        return row

    def investigate_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> DataIncident:
        return self._set_status(org_id, incident_id, "investigating", user_id, notes=notes)

    def contain_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> DataIncident:
        return self._set_status(org_id, incident_id, "contained", user_id, notes=notes)

    def resolve_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, resolved_by: uuid.UUID, notes: str | None = None) -> DataIncident:
        return self._set_status(org_id, incident_id, "resolved", resolved_by, notes=notes)

    def dismiss_incident(self, org_id: uuid.UUID, incident_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> DataIncident:
        return self._set_status(org_id, incident_id, "dismissed", user_id, notes=notes)

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
        now = self.utcnow()
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
        open_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.status.in_(["new", "investigating", "contained"]),
                )
            ).scalar_one()
            or 0
        )
        critical_open_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.severity == "critical",
                    DataIncident.status.in_(["new", "investigating", "contained"]),
                )
            ).scalar_one()
            or 0
        )
        stale_new_threshold = now - timedelta(hours=24)
        stale_new_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.status == "new",
                    DataIncident.detected_at < stale_new_threshold,
                )
            ).scalar_one()
            or 0
        )

        resolved_rows = self.db.execute(
            select(DataIncident.detected_at, DataIncident.resolved_at).where(
                DataIncident.organization_id == org_id,
                DataIncident.status == "resolved",
                DataIncident.resolved_at.is_not(None),
            )
        ).all()
        resolution_hours: list[float] = []
        for detected_at, resolved_at in resolved_rows:
            d = self._as_utc(detected_at)
            r = self._as_utc(resolved_at)
            if d is None or r is None:
                continue
            delta_hours = (r - d).total_seconds() / 3600
            if delta_hours >= 0:
                resolution_hours.append(delta_hours)
        mean_time_to_resolve_hours = round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0.0

        context_flags: list[str] = []
        if critical_open_count > 0:
            context_flags.append("critical_open_incidents_present")
        if stale_new_count > 0:
            context_flags.append("stale_new_incidents_present")
        if total > 0 and (auto_escalated_count / total) >= 0.5:
            context_flags.append("high_auto_escalation_share")
        if mean_time_to_resolve_hours > 72:
            context_flags.append("high_mean_time_to_resolve")

        return {
            "total": total,
            "by_severity": by_severity,
            "by_status": by_status,
            "by_detector_type": by_detector_type,
            "new_count": new_count,
            "auto_escalated_count": auto_escalated_count,
            "assets_with_active_incidents": assets_with_active_incidents,
            "open_count": open_count,
            "critical_open_count": critical_open_count,
            "stale_new_count": stale_new_count,
            "mean_time_to_resolve_hours": mean_time_to_resolve_hours,
            "context_flags": context_flags,
        }
