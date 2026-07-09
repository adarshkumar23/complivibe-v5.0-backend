import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.geo import region_covers
from app.data_observability.services.anomaly_detection_service import AnomalyDetectionService
from app.data_observability.services.incident_detection_service import DataIncidentService
from app.data_observability.services.lineage_service import LineageService
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.data_access_anomaly_rule import DataAccessAnomalyRule
from app.models.data_access_log import DataAccessLog
from app.models.data_asset import DataAsset
from app.models.membership import Membership
from app.models.user import User
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

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _parse_asset_regions(asset: DataAsset | None) -> set[str]:
        if asset is None:
            return set()
        raw = asset.permitted_regions
        if not isinstance(raw, list):
            return set()
        return {str(region).upper() for region in raw if str(region).strip()}

    def log_context(self, row: DataAccessLog, *, asset: DataAsset | None = None) -> dict:
        access_time = self._as_utc(row.access_time) or self.utcnow()
        context_flags: list[str] = []
        risk_score = 0

        if access_time.hour >= 22 or access_time.hour < 6:
            context_flags.append("after_hours_access")
            risk_score += 20
        if row.access_result == "failed":
            context_flags.append("failed_access")
            risk_score += 30
        if row.bytes_transferred is not None and row.bytes_transferred >= 1_000_000_000:
            context_flags.append("large_data_transfer")
            risk_score += 25

        permitted_regions = self._parse_asset_regions(asset)
        source_country = (row.source_country or "").upper()
        # source_country is always a plain 2-letter ISO country code, while
        # permitted_regions may contain more specific hierarchical entries
        # (e.g. "IN-Mumbai"). A source country covers a permitted region when
        # it's the broader country the region belongs to, so compare
        # hierarchically instead of requiring an exact string match.
        if (
            source_country
            and permitted_regions
            and not any(region_covers(source_country, region) for region in permitted_regions)
        ):
            context_flags.append("cross_border_region_mismatch")
            risk_score += 35

        if row.actor_id is None and row.actor_external is None:
            context_flags.append("missing_actor_identity")
            risk_score += 10

        risk_score = min(100, risk_score)
        if risk_score >= 70:
            risk_level = "high"
        elif risk_score >= 35:
            risk_level = "medium"
        else:
            risk_level = "low"
        return {"risk_score": risk_score, "risk_level": risk_level, "context_flags": context_flags}

    def access_log_response_payload(self, row: DataAccessLog) -> dict:
        asset = self.db.get(DataAsset, row.data_asset_id)
        context = self.log_context(row, asset=asset)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "data_asset_id": row.data_asset_id,
            "actor_id": row.actor_id,
            "actor_external": row.actor_external,
            "access_type": row.access_type,
            "access_result": row.access_result,
            "source_ip": row.source_ip,
            "source_country": row.source_country,
            "bytes_transferred": row.bytes_transferred,
            "row_count": row.row_count,
            "session_id": row.session_id,
            "access_time": row.access_time,
            "created_at": row.created_at,
            "metadata_json": row.metadata_json,
            "risk_score": context["risk_score"],
            "risk_level": context["risk_level"],
            "context_flags": context["context_flags"],
        }

    def anomaly_rule_response_payload(
        self, row: DataAccessAnomalyRule, *, hit_count_7d: int = 0, last_triggered_at: datetime | None = None
    ) -> dict:
        context_flags: list[str] = []
        if not row.is_active:
            context_flags.append("inactive_rule")
        if hit_count_7d == 0:
            context_flags.append("no_recent_triggers")
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "data_asset_id": row.data_asset_id,
            "rule_type": row.rule_type,
            "rule_config": row.rule_config,
            "is_active": row.is_active,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
            "hit_count_7d": hit_count_7d,
            "last_triggered_at": last_triggered_at,
            "context_flags": context_flags,
        }

    def summarize_rule_hits(self, org_id: uuid.UUID, *, days: int = 7) -> tuple[dict[str, int], dict[str, datetime | None]]:
        since = self.utcnow() - timedelta(days=max(1, int(days)))
        alerts = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "data_access_anomaly",
                ControlMonitoringAlert.created_at >= since,
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        latest: dict[str, datetime | None] = {}
        for alert in alerts:
            rule_id = str((alert.alert_context_json or {}).get("rule_id") or "")
            if not rule_id:
                continue
            counts[rule_id] = counts.get(rule_id, 0) + 1
            alert_created_at = self._as_utc(alert.created_at)
            latest_created_at = self._as_utc(latest.get(rule_id))
            if latest_created_at is None or (alert_created_at is not None and alert_created_at > latest_created_at):
                latest[rule_id] = alert_created_at
        return counts, latest

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

    def _require_active_org_actor(self, org_id: uuid.UUID, actor_id: uuid.UUID | None) -> None:
        if actor_id is None:
            return
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == actor_id,
                User.is_active.is_(True),
                User.status == "active",
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="actor_id must reference an active organization user",
            )

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
        if payload.get("actor_id") is not None and payload.get("actor_external"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either actor_id or actor_external, not both",
            )
        if payload.get("bytes_transferred") is not None and int(payload["bytes_transferred"]) < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bytes_transferred must be non-negative")
        if payload.get("row_count") is not None and int(payload["row_count"]) < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="row_count must be non-negative")

        self._require_asset(org_id, data_asset_id)
        self._require_active_org_actor(org_id, payload.get("actor_id"))
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
        if from_time is not None and to_time is not None and self._as_utc(from_time) > self._as_utc(to_time):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from_time must be less than or equal to to_time",
            )
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
        window_days = max(1, int(days))
        since = self.utcnow() - timedelta(days=window_days)
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

        # actor_id (internal users) and actor_external (machine/external identifiers) are
        # disjoint identifier spaces on the same row set -- a machine-ingest access log row
        # has actor_id NULL and only actor_external populated, so both must be counted for
        # unique_actors to reflect real distinct actors instead of only human users.
        unique_internal_actors = int(
            self.db.execute(
                select(func.count(func.distinct(DataAccessLog.actor_id))).where(*base_filters, DataAccessLog.actor_id.is_not(None))
            ).scalar_one()
            or 0
        )
        unique_external_actors = int(
            self.db.execute(
                select(func.count(func.distinct(DataAccessLog.actor_external))).where(
                    *base_filters, DataAccessLog.actor_external.is_not(None)
                )
            ).scalar_one()
            or 0
        )
        unique_actors = unique_internal_actors + unique_external_actors

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

        access_rows = self.db.execute(select(DataAccessLog).where(*base_filters)).scalars().all()
        failed_accesses = sum(1 for row in access_rows if row.access_result == "failed")
        after_hours_accesses = sum(
            1
            for row in access_rows
            if ((self._as_utc(row.access_time) or self.utcnow()).hour >= 22 or (self._as_utc(row.access_time) or self.utcnow()).hour < 6)
        )
        cross_border_accesses = 0
        for row in access_rows:
            asset = self.db.get(DataAsset, row.data_asset_id)
            context = self.log_context(row, asset=asset)
            if "cross_border_region_mismatch" in context["context_flags"]:
                cross_border_accesses += 1

        failed_access_rate = round((failed_accesses / total), 4) if total > 0 else 0.0
        anomalous_access_rate = round((anomalies_detected / total), 4) if total > 0 else 0.0
        context_flags: list[str] = []
        if failed_access_rate >= 0.2:
            context_flags.append("failed_access_rate_elevated")
        if anomalous_access_rate >= 0.1:
            context_flags.append("anomaly_rate_elevated")
        if cross_border_accesses > 0:
            context_flags.append("cross_border_access_detected")
        if after_hours_accesses > 0:
            context_flags.append("after_hours_access_detected")

        return {
            "window_days": window_days,
            "total_accesses_7d": total,
            "by_access_type": by_access_type,
            "by_access_result": by_access_result,
            "unique_actors": unique_actors,
            "anomalies_detected": anomalies_detected,
            "failed_access_rate": failed_access_rate,
            "anomalous_access_rate": anomalous_access_rate,
            "after_hours_accesses": after_hours_accesses,
            "cross_border_accesses": cross_border_accesses,
            "context_flags": context_flags,
        }

    def create_anomaly_rule(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DataAccessAnomalyRule:
        payload = data.model_dump()
        payload["rule_type"] = validate_choice(payload["rule_type"], ALLOWED_RULE_TYPES, "rule_type")
        if payload.get("data_asset_id") is not None:
            self._require_asset(org_id, payload["data_asset_id"])
        duplicate = self.db.execute(
            select(DataAccessAnomalyRule).where(
                DataAccessAnomalyRule.organization_id == org_id,
                DataAccessAnomalyRule.data_asset_id == payload.get("data_asset_id"),
                DataAccessAnomalyRule.rule_type == payload["rule_type"],
                DataAccessAnomalyRule.is_active.is_(True),
                DataAccessAnomalyRule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active anomaly rule with the same rule_type already exists for this scope",
            )

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

    def update_anomaly_rule(
        self, org_id: uuid.UUID, rule_id: uuid.UUID, data, actor_user_id: uuid.UUID
    ) -> DataAccessAnomalyRule:
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
            actor_user_id=actor_user_id,
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
