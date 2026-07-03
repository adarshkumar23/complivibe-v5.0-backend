import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_observability.services.anomaly_detection_service import AnomalyDetectionService
from app.data_observability.services.incident_detection_service import DataIncidentService
from app.data_observability.services.lineage_service import LineageService
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.data_access_anomaly_rule import DataAccessAnomalyRule
from app.models.data_access_log import DataAccessLog
from app.models.data_asset import DataAsset
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_ACCESS_TYPES = {"read", "write", "delete", "export", "query"}
ALLOWED_ACCESS_RESULTS = {"success", "failed", "partial"}
ALLOWED_RULE_TYPES = {
    "access_count_spike",
    "after_hours_access",
    "new_actor_access",
    "mass_download",
    "failed_access_spike",
    "cross_border_access",
    "sensitivity_mismatch_access",
}


class AccessMonitoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_asset(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> DataAsset:
        row = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.id == data_asset_id,
                DataAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
        return row

    def _require_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID) -> DataAccessAnomalyRule:
        row = self.db.execute(
            select(DataAccessAnomalyRule).where(
                DataAccessAnomalyRule.organization_id == org_id,
                DataAccessAnomalyRule.id == rule_id,
                DataAccessAnomalyRule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly rule not found")
        return row

    def _create_anomaly_alert(self, access_log: DataAccessLog, breach: dict) -> ControlMonitoringAlert:
        alert = ControlMonitoringAlert(
            organization_id=access_log.organization_id,
            rule_id=None,
            definition_id=None,
            control_id=None,
            alert_type="data_access_anomaly",
            severity="high",
            status="open",
            title=f"Data access anomaly: {breach['rule_type']}",
            description=breach["reason"],
            alert_context_json={
                "data_asset_id": str(access_log.data_asset_id),
                "access_log_id": str(access_log.id),
                "rule_id": str(breach["rule_id"]),
                "rule_type": breach["rule_type"],
            },
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def _record_incident(self, access_log: DataAccessLog, breach: dict) -> None:
        DataIncidentService(self.db).create_incident(
            org_id=access_log.organization_id,
            data_asset_id=access_log.data_asset_id,
            detector_type="anomaly_rule",
            title=f"Access anomaly: {breach['rule_type']}",
            description=breach["reason"],
            severity="high",
            rule_type=breach["rule_type"],
            detector_ref_id=breach["rule_id"],
            evidence={
                "access_log_id": str(access_log.id),
                "rule_id": str(breach["rule_id"]),
                "rule_type": breach["rule_type"],
                "reason": breach["reason"],
            },
            detected_by="rule_engine",
            actor_user_id=access_log.actor_id,
        )

    def log_access_event(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, data) -> DataAccessLog:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        if payload.get("access_type") not in ALLOWED_ACCESS_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid access_type")
        if payload.get("access_result") not in ALLOWED_ACCESS_RESULTS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid access_result")

        self._require_asset(org_id, data_asset_id)
        row = DataAccessLog(
            organization_id=org_id,
            data_asset_id=data_asset_id,
            actor_id=payload.get("actor_id"),
            actor_external=payload.get("actor_external"),
            access_type=payload["access_type"],
            access_result=payload["access_result"],
            source_ip=payload.get("source_ip"),
            source_country=payload.get("source_country"),
            bytes_transferred=payload.get("bytes_transferred"),
            row_count=payload.get("row_count"),
            session_id=payload.get("session_id"),
            access_time=payload["access_time"],
            created_at=self.utcnow(),
            metadata_json=payload.get("metadata") or {},
        )
        self.db.add(row)
        self.db.flush()

        breaches = AnomalyDetectionService(self.db).evaluate_access_event(row)
        for breach in breaches:
            self._create_anomaly_alert(row, breach)
            self._record_incident(row, breach)

        AuditService(self.db).write_audit_log(
            action="access.logged",
            entity_type="data_access_log",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=row.actor_id,
            after_json={
                "data_asset_id": str(row.data_asset_id),
                "access_type": row.access_type,
                "access_result": row.access_result,
                "breaches": len(breaches),
            },
            metadata_json={"source": "ingest", "actor_external": row.actor_external},
        )
        return row

    def list_access_logs(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        access_type: str | None = None,
        access_result: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DataAccessLog]:
        stmt = select(DataAccessLog).where(DataAccessLog.organization_id == org_id)
        if data_asset_id is not None:
            stmt = stmt.where(DataAccessLog.data_asset_id == data_asset_id)
        if actor_id is not None:
            stmt = stmt.where(DataAccessLog.actor_id == actor_id)
        if access_type is not None:
            access_type = validate_choice(access_type, ALLOWED_ACCESS_TYPES, "access_type")
            stmt = stmt.where(DataAccessLog.access_type == access_type)
        if access_result is not None:
            access_result = validate_choice(access_result, ALLOWED_ACCESS_RESULTS, "access_result")
            stmt = stmt.where(DataAccessLog.access_result == access_result)
        if from_time is not None:
            stmt = stmt.where(DataAccessLog.access_time >= from_time)
        if to_time is not None:
            stmt = stmt.where(DataAccessLog.access_time <= to_time)

        return self.db.execute(
            stmt.order_by(DataAccessLog.access_time.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def get_access_summary(self, org_id: uuid.UUID, data_asset_id: uuid.UUID | None = None, days: int = 7) -> dict:
        since = self.utcnow() - timedelta(days=max(1, int(days)))
        base_filters = [
            DataAccessLog.organization_id == org_id,
            DataAccessLog.access_time >= since,
        ]
        if data_asset_id is not None:
            base_filters.append(DataAccessLog.data_asset_id == data_asset_id)

        total = int(self.db.execute(select(func.count(DataAccessLog.id)).where(*base_filters)).scalar_one() or 0)

        by_type_rows = self.db.execute(
            select(DataAccessLog.access_type, func.count(DataAccessLog.id)).where(*base_filters).group_by(DataAccessLog.access_type)
        ).all()
        by_access_type = {str(t): int(c) for t, c in by_type_rows}

        by_result_rows = self.db.execute(
            select(DataAccessLog.access_result, func.count(DataAccessLog.id)).where(*base_filters).group_by(DataAccessLog.access_result)
        ).all()
        by_access_result = {str(r): int(c) for r, c in by_result_rows}

        unique_actors = int(
            self.db.execute(
                select(func.count(func.distinct(DataAccessLog.actor_id))).where(*base_filters, DataAccessLog.actor_id.is_not(None))
            ).scalar_one()
            or 0
        )

        anomaly_alert_filters = [
            ControlMonitoringAlert.organization_id == org_id,
            ControlMonitoringAlert.alert_type == "data_access_anomaly",
            ControlMonitoringAlert.created_at >= since,
        ]
        if data_asset_id is None:
            anomalies_detected = int(
                self.db.execute(select(func.count(ControlMonitoringAlert.id)).where(*anomaly_alert_filters)).scalar_one() or 0
            )
        else:
            alerts = self.db.execute(select(ControlMonitoringAlert).where(*anomaly_alert_filters)).scalars().all()
            anomalies_detected = sum(
                1
                for alert in alerts
                if str((alert.alert_context_json or {}).get("data_asset_id")) == str(data_asset_id)
            )

        return {
            "total_accesses_7d": total,
            "by_access_type": by_access_type,
            "by_access_result": by_access_result,
            "unique_actors": unique_actors,
            "anomalies_detected": anomalies_detected,
        }

    def create_anomaly_rule(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DataAccessAnomalyRule:
        payload = data.model_dump()
        payload["rule_type"] = validate_choice(payload["rule_type"], ALLOWED_RULE_TYPES, "rule_type")
        if payload.get("data_asset_id") is not None:
            self._require_asset(org_id, payload["data_asset_id"])

        now = self.utcnow()
        row = DataAccessAnomalyRule(
            organization_id=org_id,
            data_asset_id=payload.get("data_asset_id"),
            rule_type=payload["rule_type"],
            rule_config=payload.get("rule_config") or {},
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="access.anomaly_rule_created",
            entity_type="data_access_anomaly_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"rule_type": row.rule_type, "data_asset_id": str(row.data_asset_id) if row.data_asset_id else None},
            metadata_json={"source": "api"},
        )
        return row

    def list_anomaly_rules(self, org_id: uuid.UUID, data_asset_id: uuid.UUID | None = None) -> list[DataAccessAnomalyRule]:
        stmt = select(DataAccessAnomalyRule).where(
            DataAccessAnomalyRule.organization_id == org_id,
            DataAccessAnomalyRule.deleted_at.is_(None),
        )
        if data_asset_id is not None:
            stmt = stmt.where(DataAccessAnomalyRule.data_asset_id == data_asset_id)
        return self.db.execute(stmt.order_by(DataAccessAnomalyRule.created_at.desc())).scalars().all()

    def update_anomaly_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID, data) -> DataAccessAnomalyRule:
        row = self._require_rule(org_id, rule_id)
        payload = data.model_dump(exclude_unset=True)
        if "rule_type" in payload and payload["rule_type"] not in ALLOWED_RULE_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid rule_type")
        if "data_asset_id" in payload and payload["data_asset_id"] is not None:
            self._require_asset(org_id, payload["data_asset_id"])

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="access.anomaly_rule_updated",
            entity_type="data_access_anomaly_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={
                "rule_type": row.rule_type,
                "data_asset_id": str(row.data_asset_id) if row.data_asset_id else None,
                "is_active": row.is_active,
            },
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID, user_id: uuid.UUID) -> DataAccessAnomalyRule:
        row = self._require_rule(org_id, rule_id)
        row.is_active = False
        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="access.anomaly_rule_deactivated",
            entity_type="data_access_anomaly_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return LineageService(self.db).resolve_org_by_api_key(raw_key)
