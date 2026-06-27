import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.data_asset import DataAsset
from app.models.data_quality_config import DataQualityConfig
from app.models.data_quality_reading import DataQualityReading
from app.data_observability.services.incident_detection_service import DataIncidentService
from app.services.audit_service import AuditService

ALLOWED_METRIC_TYPES = {"completeness", "accuracy", "freshness", "consistency", "uniqueness"}
ALLOWED_DIRECTIONS = {"above", "below"}
ALLOWED_FREQUENCIES = {"realtime", "hourly", "daily", "weekly"}
ALLOWED_READING_SOURCES = {"manual", "api_report"}


class DataQualityService:
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

    def _require_config(self, org_id: uuid.UUID, config_id: uuid.UUID) -> DataQualityConfig:
        row = self.db.execute(
            select(DataQualityConfig).where(
                DataQualityConfig.organization_id == org_id,
                DataQualityConfig.id == config_id,
                DataQualityConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data quality config not found")
        return row

    def _validate_payload(self, payload: dict) -> None:
        if payload.get("metric_type") is not None and payload["metric_type"] not in ALLOWED_METRIC_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid metric_type")
        if payload.get("comparison_direction") is not None and payload["comparison_direction"] not in ALLOWED_DIRECTIONS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid comparison_direction")
        if payload.get("measurement_frequency") is not None and payload["measurement_frequency"] not in ALLOWED_FREQUENCIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid measurement_frequency")

    @staticmethod
    def check_threshold(config: DataQualityConfig, value: Decimal) -> bool:
        if config.comparison_direction == "above":
            return value <= config.threshold_value
        return value >= config.threshold_value

    def _derive_severity(self, config: DataQualityConfig, asset: DataAsset) -> str:
        if config.metric_type in {"completeness", "freshness"} and asset.classification_type == "personal_data":
            return "high"
        if config.metric_type in {"accuracy", "consistency"}:
            return "medium"
        return "low"

    def create_config(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, data, created_by: uuid.UUID) -> DataQualityConfig:
        payload = data.model_dump()
        self._validate_payload(payload)
        self._require_asset(org_id, data_asset_id)

        now = self.utcnow()
        row = DataQualityConfig(
            organization_id=org_id,
            data_asset_id=data_asset_id,
            metric_type=payload["metric_type"],
            threshold_value=payload["threshold_value"],
            comparison_direction=payload["comparison_direction"],
            alert_on_breach=bool(payload.get("alert_on_breach", True)),
            measurement_frequency=payload.get("measurement_frequency"),
            description=payload.get("description"),
            is_active=True,
            last_checked_at=None,
            last_value=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="quality.config_created",
            entity_type="data_quality_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "data_asset_id": str(data_asset_id),
                "metric_type": row.metric_type,
                "threshold_value": str(row.threshold_value),
                "comparison_direction": row.comparison_direction,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_config(self, org_id: uuid.UUID, config_id: uuid.UUID) -> DataQualityConfig:
        return self._require_config(org_id, config_id)

    def list_configs(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID | None = None,
        metric_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[DataQualityConfig]:
        stmt = select(DataQualityConfig).where(
            DataQualityConfig.organization_id == org_id,
            DataQualityConfig.deleted_at.is_(None),
        )
        if data_asset_id is not None:
            stmt = stmt.where(DataQualityConfig.data_asset_id == data_asset_id)
        if metric_type is not None:
            if metric_type not in ALLOWED_METRIC_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid metric_type filter")
            stmt = stmt.where(DataQualityConfig.metric_type == metric_type)
        if is_active is not None:
            stmt = stmt.where(DataQualityConfig.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(DataQualityConfig.created_at.desc())).scalars().all()

    def update_config(self, org_id: uuid.UUID, config_id: uuid.UUID, data) -> DataQualityConfig:
        row = self._require_config(org_id, config_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload)

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="quality.config_updated",
            entity_type="data_quality_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={
                "data_asset_id": str(row.data_asset_id),
                "metric_type": row.metric_type,
                "threshold_value": str(row.threshold_value),
                "comparison_direction": row.comparison_direction,
                "is_active": row.is_active,
            },
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID) -> DataQualityConfig:
        row = self._require_config(org_id, config_id)
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="quality.config_deactivated",
            entity_type="data_quality_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def _create_breach_alert(self, config: DataQualityConfig, asset: DataAsset, value: Decimal) -> ControlMonitoringAlert:
        direction_text = "above" if config.comparison_direction == "above" else "below"
        alert = ControlMonitoringAlert(
            organization_id=config.organization_id,
            rule_id=None,
            definition_id=None,
            control_id=None,
            alert_type="data_quality",
            severity=self._derive_severity(config, asset),
            status="open",
            title=f"Data quality breach: {config.metric_type}",
            description=(
                f"Data quality breach for asset '{asset.name}': {config.metric_type} = {value} "
                f"({direction_text} threshold {config.threshold_value})"
            ),
            alert_context_json={
                "config_id": str(config.id),
                "data_asset_id": str(config.data_asset_id),
                "metric_type": config.metric_type,
                "value": str(value),
                "threshold": str(config.threshold_value),
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
        notes: str | None,
    ) -> DataQualityReading:
        if reading_source not in ALLOWED_READING_SOURCES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid reading_source")

        config = self._require_config(org_id, config_id)
        if not config.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Data quality config is inactive")
        asset = self._require_asset(org_id, config.data_asset_id)

        within_threshold = self.check_threshold(config, value)
        now = self.utcnow()
        row = DataQualityReading(
            organization_id=org_id,
            config_id=config.id,
            value=value,
            reading_source=reading_source,
            source_tool=source_tool,
            within_threshold=within_threshold,
            notes=notes,
            created_at=now,
        )
        self.db.add(row)

        config.last_checked_at = now
        config.last_value = value
        config.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="quality.reading_submitted",
            entity_type="data_quality_reading",
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
            alert = self._create_breach_alert(config, asset, value)
            DataIncidentService(self.db).create_incident(
                org_id=org_id,
                data_asset_id=asset.id,
                detector_type="quality_breach",
                title=f"Quality breach: {config.metric_type}",
                description=(
                    f"Metric '{config.metric_type}' breached threshold for asset '{asset.name}'. "
                    f"Observed value {value} with threshold {config.threshold_value} "
                    f"({config.comparison_direction})."
                ),
                severity="medium",
                detector_ref_id=config.id,
                evidence={
                    "reading_id": str(row.id),
                    "config_id": str(config.id),
                    "metric_type": config.metric_type,
                    "value": str(value),
                    "threshold_value": str(config.threshold_value),
                    "comparison_direction": config.comparison_direction,
                },
                detected_by="rule_engine",
                actor_user_id=None,
            )
            AuditService(self.db).write_audit_log(
                action="quality.breach",
                entity_type="control_monitoring_alert",
                entity_id=alert.id,
                organization_id=org_id,
                actor_user_id=None,
                after_json={
                    "config_id": str(config.id),
                    "reading_id": str(row.id),
                    "severity": alert.severity,
                },
                metadata_json={"source": "service"},
            )

        return row

    def get_quality_dashboard(self, org_id: uuid.UUID, data_asset_id: uuid.UUID | None = None) -> dict:
        base_filters = [
            DataQualityConfig.organization_id == org_id,
            DataQualityConfig.deleted_at.is_(None),
        ]
        if data_asset_id is not None:
            base_filters.append(DataQualityConfig.data_asset_id == data_asset_id)

        total_configs = int(self.db.execute(select(func.count(DataQualityConfig.id)).where(*base_filters)).scalar_one() or 0)
        active_configs = int(
            self.db.execute(select(func.count(DataQualityConfig.id)).where(*base_filters, DataQualityConfig.is_active.is_(True))).scalar_one() or 0
        )

        config_ids = self.db.execute(select(DataQualityConfig.id).where(*base_filters)).scalars().all()
        recent_breaches_7d = 0
        if config_ids:
            since = self.utcnow() - timedelta(days=7)
            recent_breaches_7d = int(
                self.db.execute(
                    select(func.count(DataQualityReading.id)).where(
                        DataQualityReading.organization_id == org_id,
                        DataQualityReading.config_id.in_(config_ids),
                        DataQualityReading.within_threshold.is_(False),
                        DataQualityReading.created_at >= since,
                    )
                ).scalar_one()
                or 0
            )

        by_metric_type: dict[str, dict] = {}
        metric_rows = self.db.execute(
            select(
                DataQualityConfig.metric_type,
                func.count(DataQualityConfig.id).label("config_count"),
                func.sum(
                    case(
                        (DataQualityReading.within_threshold.is_(False), 1),
                        else_=0,
                    )
                ).label("breach_count"),
                func.count(DataQualityReading.id).label("reading_count"),
            )
            .select_from(DataQualityConfig)
            .outerjoin(DataQualityReading, DataQualityReading.config_id == DataQualityConfig.id)
            .where(*base_filters)
            .group_by(DataQualityConfig.metric_type)
        ).all()
        for metric_type, config_count, breach_count, reading_count in metric_rows:
            rate = float((breach_count or 0) / (reading_count or 1)) if (reading_count or 0) > 0 else 0.0
            by_metric_type[str(metric_type)] = {
                "configs": int(config_count or 0),
                "breach_rate": round(rate, 4),
            }

        assets_with_breaches = self.db.execute(
            select(
                DataAsset.id,
                DataAsset.name,
                func.count(DataQualityReading.id).label("breach_count"),
            )
            .select_from(DataAsset)
            .join(DataQualityConfig, DataQualityConfig.data_asset_id == DataAsset.id)
            .join(DataQualityReading, DataQualityReading.config_id == DataQualityConfig.id)
            .where(
                DataAsset.organization_id == org_id,
                DataAsset.deleted_at.is_(None),
                DataQualityConfig.deleted_at.is_(None),
                DataQualityReading.within_threshold.is_(False),
            )
            .group_by(DataAsset.id, DataAsset.name)
            .order_by(func.count(DataQualityReading.id).desc(), DataAsset.name.asc())
            .limit(5)
        ).all()

        return {
            "total_configs": total_configs,
            "active_configs": active_configs,
            "recent_breaches_7d": recent_breaches_7d,
            "by_metric_type": by_metric_type,
            "assets_with_breaches": [
                {"asset_id": str(asset_id), "asset_name": asset_name, "breach_count": int(breach_count or 0)}
                for asset_id, asset_name, breach_count in assets_with_breaches
            ],
        }
