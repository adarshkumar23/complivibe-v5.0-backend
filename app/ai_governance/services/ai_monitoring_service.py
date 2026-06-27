import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.signal_service import SignalService
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.services.audit_service import AuditService

ALLOWED_METRIC_TYPES = {
    "accuracy",
    "bias_parity_gap",
    "output_drift",
    "confidence_distribution",
    "response_time",
    "error_rate",
}
ALLOWED_DIRECTIONS = {"above", "below"}
ALLOWED_FREQUENCIES = {"realtime", "hourly", "daily", "weekly"}
ALLOWED_READING_SOURCES = {"manual", "api_report"}


class AIMonitoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_api_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _require_ai_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _require_config(self, org_id: uuid.UUID, config_id: uuid.UUID) -> AIMonitoringConfig:
        row = self.db.execute(
            select(AIMonitoringConfig).where(
                AIMonitoringConfig.organization_id == org_id,
                AIMonitoringConfig.id == config_id,
                AIMonitoringConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring config not found")
        return row

    def _validate_payload(self, payload: dict, *, is_update: bool = False) -> None:
        if payload.get("metric_type") is not None and payload["metric_type"] not in ALLOWED_METRIC_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid metric_type")
        if payload.get("comparison_direction") is not None and payload["comparison_direction"] not in ALLOWED_DIRECTIONS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid comparison_direction")
        if payload.get("check_frequency") is not None and payload["check_frequency"] not in ALLOWED_FREQUENCIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid check_frequency")

        if not is_update and not payload.get("api_key"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="api_key is required")

    @staticmethod
    def check_threshold(config: AIMonitoringConfig, value: Decimal) -> bool:
        if config.comparison_direction == "above":
            return value <= config.threshold_value
        return value >= config.threshold_value

    @staticmethod
    def _severity_for_metric(metric_type: str) -> str:
        if metric_type in {"accuracy", "bias_parity_gap"}:
            return "high"
        if metric_type == "output_drift":
            return "medium"
        return "low"

    def create_config(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> AIMonitoringConfig:
        payload = data.model_dump()
        self._validate_payload(payload)
        self._require_ai_system(org_id, system_id)

        now = self.utcnow()
        row = AIMonitoringConfig(
            organization_id=org_id,
            ai_system_id=system_id,
            metric_type=payload["metric_type"],
            threshold_value=payload["threshold_value"],
            comparison_direction=payload["comparison_direction"],
            alert_on_breach=bool(payload.get("alert_on_breach", True)),
            check_frequency=payload.get("check_frequency"),
            baseline_value=payload.get("baseline_value"),
            last_checked_at=None,
            last_reading_value=None,
            api_key_hash=self.hash_api_key(payload["api_key"]),
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "monitoring.config_created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"config_id": str(row.id), "metric_type": row.metric_type},
        )
        AuditService(self.db).write_audit_log(
            action="monitoring.config_created",
            entity_type="ai_monitoring_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "ai_system_id": str(row.ai_system_id),
                "metric_type": row.metric_type,
                "threshold_value": str(row.threshold_value),
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_config(self, org_id: uuid.UUID, config_id: uuid.UUID) -> AIMonitoringConfig:
        return self._require_config(org_id, config_id)

    def list_configs(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        metric_type: str | None = None,
    ) -> list[AIMonitoringConfig]:
        stmt = select(AIMonitoringConfig).where(
            AIMonitoringConfig.organization_id == org_id,
            AIMonitoringConfig.deleted_at.is_(None),
        )
        if system_id is not None:
            stmt = stmt.where(AIMonitoringConfig.ai_system_id == system_id)
        if is_active is not None:
            stmt = stmt.where(AIMonitoringConfig.is_active.is_(is_active))
        if metric_type is not None:
            if metric_type not in ALLOWED_METRIC_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid metric_type filter")
            stmt = stmt.where(AIMonitoringConfig.metric_type == metric_type)
        return self.db.execute(stmt.order_by(AIMonitoringConfig.created_at.desc())).scalars().all()

    def update_config(self, org_id: uuid.UUID, config_id: uuid.UUID, data) -> AIMonitoringConfig:
        row = self._require_config(org_id, config_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload, is_update=True)

        api_key = payload.pop("api_key", None)
        for key, value in payload.items():
            setattr(row, key, value)

        if api_key is not None:
            row.api_key_hash = self.hash_api_key(api_key)

        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def deactivate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID) -> AIMonitoringConfig:
        row = self._require_config(org_id, config_id)
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="monitoring.config_deactivated",
            entity_type="ai_monitoring_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def _create_breach_alert(self, config: AIMonitoringConfig, value: Decimal) -> ControlMonitoringAlert:
        direction_text = "above" if config.comparison_direction == "above" else "below"
        description = (
            f"AI monitoring breach: {config.metric_type} = {value} "
            f"({direction_text} threshold {config.threshold_value})"
        )
        alert = ControlMonitoringAlert(
            organization_id=config.organization_id,
            rule_id=None,
            definition_id=None,
            control_id=None,
            alert_type="ai_monitoring",
            severity=self._severity_for_metric(config.metric_type),
            status="open",
            title=f"AI monitoring breach: {config.metric_type}",
            description=description,
            alert_context_json={
                "config_id": str(config.id),
                "ai_system_id": str(config.ai_system_id),
                "metric_type": config.metric_type,
                "value": str(value),
                "threshold_value": str(config.threshold_value),
                "comparison_direction": config.comparison_direction,
            },
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def submit_reading(
        self,
        org_id: uuid.UUID,
        config_id: uuid.UUID,
        value: Decimal,
        reading_source: str,
        source_tool: str | None,
    ) -> AIMonitoringReading:
        if reading_source not in ALLOWED_READING_SOURCES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid reading_source")

        config = self._require_config(org_id, config_id)
        if not config.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Monitoring config is inactive")

        within_threshold = self.check_threshold(config, value)
        now = self.utcnow()
        row = AIMonitoringReading(
            organization_id=org_id,
            config_id=config.id,
            value=value,
            reading_source=reading_source,
            source_tool=source_tool,
            within_threshold=within_threshold,
            created_at=now,
        )
        self.db.add(row)

        config.last_checked_at = now
        config.last_reading_value = value
        config.updated_at = now
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "monitoring.reading_submitted",
            actor_id=None,
            actor_type="system",
            ai_system_id=config.ai_system_id,
            event_data={
                "config_id": str(config.id),
                "reading_id": str(row.id),
                "metric_type": config.metric_type,
                "within_threshold": within_threshold,
            },
        )
        AuditService(self.db).write_audit_log(
            action="monitoring.reading_submitted",
            entity_type="ai_monitoring_reading",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={
                "config_id": str(config.id),
                "value": str(value),
                "reading_source": reading_source,
                "within_threshold": within_threshold,
            },
            metadata_json={"source": "api", "source_tool": source_tool},
        )

        if not within_threshold and config.alert_on_breach:
            alert = self._create_breach_alert(config, value)
            AIGovernanceEventService.log(
                self.db,
                org_id,
                "monitoring.breach",
                actor_id=None,
                actor_type="system",
                ai_system_id=config.ai_system_id,
                event_data={
                    "config_id": str(config.id),
                    "reading_id": str(row.id),
                    "alert_id": str(alert.id),
                    "metric_type": config.metric_type,
                },
            )
            AuditService(self.db).write_audit_log(
                action="monitoring.breach",
                entity_type="control_monitoring_alert",
                entity_id=alert.id,
                organization_id=org_id,
                actor_user_id=None,
                after_json={
                    "config_id": str(config.id),
                    "reading_id": str(row.id),
                    "severity": alert.severity,
                    "description": alert.description,
                },
                metadata_json={"source": "service"},
            )

        if not within_threshold and config.metric_type == "bias_parity_gap":
            SignalService(self.db).emit_signal(
                org_id,
                config.ai_system_id,
                signal_type="bias_signal",
                description=f"Bias metric {config.metric_type} breached threshold: {value}",
            )

        return row

    def receive_inbound_reading(
        self,
        raw_key: str,
        config_id: uuid.UUID,
        value: Decimal,
        source_tool: str | None,
        metric_type: str | None = None,
    ) -> AIMonitoringReading:
        if not raw_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        key_hash = self.hash_api_key(raw_key)
        config = self.db.execute(
            select(AIMonitoringConfig).where(
                AIMonitoringConfig.id == config_id,
                AIMonitoringConfig.api_key_hash == key_hash,
                AIMonitoringConfig.is_active.is_(True),
                AIMonitoringConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        if metric_type is not None and metric_type != config.metric_type:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="metric_type does not match config")

        return self.submit_reading(
            config.organization_id,
            config.id,
            value,
            reading_source="api_report",
            source_tool=source_tool,
        )

    def get_monitoring_dashboard(self, org_id: uuid.UUID, system_id: uuid.UUID) -> dict:
        self._require_ai_system(org_id, system_id)
        configs = self.list_configs(org_id, system_id=system_id, is_active=None)
        config_ids = [row.id for row in configs]

        latest_by_config: dict[uuid.UUID, AIMonitoringReading] = {}
        if config_ids:
            ranked = (
                select(
                    AIMonitoringReading,
                    func.row_number()
                    .over(
                        partition_by=AIMonitoringReading.config_id,
                        order_by=AIMonitoringReading.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    AIMonitoringReading.organization_id == org_id,
                    AIMonitoringReading.config_id.in_(config_ids),
                )
                .subquery()
            )
            rows = self.db.execute(
                select(AIMonitoringReading)
                .select_from(ranked)
                .join(AIMonitoringReading, AIMonitoringReading.id == ranked.c.id)
                .where(ranked.c.rn == 1)
            ).scalars().all()
            latest_by_config = {row.config_id: row for row in rows}

        config_payload: list[dict] = []
        for cfg in configs:
            latest = latest_by_config.get(cfg.id)
            config_payload.append(
                {
                    "config_id": cfg.id,
                    "metric_type": cfg.metric_type,
                    "is_active": cfg.is_active,
                    "threshold_value": cfg.threshold_value,
                    "comparison_direction": cfg.comparison_direction,
                    "last_reading_value": cfg.last_reading_value,
                    "within_threshold": None if latest is None else latest.within_threshold,
                    "last_checked_at": cfg.last_checked_at,
                }
            )

        recent_breaches: list[AIMonitoringReading] = []
        if config_ids:
            recent_breaches = self.db.execute(
                select(AIMonitoringReading)
                .where(
                    AIMonitoringReading.organization_id == org_id,
                    AIMonitoringReading.config_id.in_(config_ids),
                    AIMonitoringReading.within_threshold.is_(False),
                )
                .order_by(AIMonitoringReading.created_at.desc())
                .limit(10)
            ).scalars().all()

        return {
            "configs": config_payload,
            "recent_breaches": recent_breaches,
        }

    def get_monitoring_alerts_by_system(self, org_id: uuid.UUID) -> list[dict]:
        since = self.utcnow() - timedelta(days=30)
        breach_count_expr = func.sum(
            case(
                (
                    and_(
                        AIMonitoringReading.within_threshold.is_(False),
                        AIMonitoringReading.created_at >= since,
                    ),
                    1,
                ),
                else_=0,
            )
        )

        rows = self.db.execute(
            select(
                AISystem.id,
                AISystem.name,
                breach_count_expr.label("breach_count"),
            )
            .join(
                AIMonitoringConfig,
                and_(
                    AIMonitoringConfig.organization_id == AISystem.organization_id,
                    AIMonitoringConfig.ai_system_id == AISystem.id,
                    AIMonitoringConfig.deleted_at.is_(None),
                ),
            )
            .outerjoin(AIMonitoringReading, AIMonitoringReading.config_id == AIMonitoringConfig.id)
            .where(
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
            .group_by(AISystem.id, AISystem.name)
            .order_by(func.sum(
                case(
                    (
                        and_(
                            AIMonitoringReading.within_threshold.is_(False),
                            AIMonitoringReading.created_at >= since,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).desc(), AISystem.name.asc())
            .limit(5)
        ).all()

        payload: list[dict] = []
        for system_id, system_name, breach_count in rows:
            payload.append(
                {
                    "system_id": str(system_id),
                    "system_name": system_name,
                    "breach_count": int(breach_count or 0),
                }
            )
        return payload
