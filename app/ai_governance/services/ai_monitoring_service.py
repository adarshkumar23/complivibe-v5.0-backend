import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.signal_service import SignalService
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.satellites.llm_observability.drift_adapters import DistributionDriftDetector
from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

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
        """Return True when `value` is within the healthy band (no breach).

        `comparison_direction` describes the *breach* direction:
        - "above": a breach occurs when the reading meets/exceeds the threshold
          (e.g. error_rate climbing too high). Healthy readings stay below it.
        - "below": a breach occurs when the reading meets/falls below the
          threshold (e.g. accuracy dropping too low). Healthy readings stay
          above it.
        """
        if config.comparison_direction == "above":
            return value < config.threshold_value
        return value > config.threshold_value

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
        ai_system = self._require_ai_system(org_id, system_id)

        now = self.utcnow()
        baseline_value = payload.get("baseline_value")
        row = AIMonitoringConfig(
            organization_id=org_id,
            ai_system_id=system_id,
            metric_type=payload["metric_type"],
            threshold_value=payload["threshold_value"],
            comparison_direction=payload["comparison_direction"],
            alert_on_breach=bool(payload.get("alert_on_breach", True)),
            check_frequency=payload.get("check_frequency"),
            baseline_value=baseline_value,
            # Snapshot the system's current model_version alongside the baseline so we
            # can later detect that the model changed and the baseline is now stale.
            baseline_model_version=ai_system.model_version if baseline_value is not None else None,
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
            metric_type = validate_choice(metric_type, ALLOWED_METRIC_TYPES, "metric_type")
            stmt = stmt.where(AIMonitoringConfig.metric_type == metric_type)
        return self.db.execute(stmt.order_by(AIMonitoringConfig.created_at.desc())).scalars().all()

    def update_config(self, org_id: uuid.UUID, config_id: uuid.UUID, data) -> AIMonitoringConfig:
        row = self._require_config(org_id, config_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload, is_update=True)

        api_key = payload.pop("api_key", None)
        for key, value in payload.items():
            setattr(row, key, value)

        if "baseline_value" in payload:
            # Re-baselining: re-snapshot the system's current model_version so a
            # later model change can still be detected against this new baseline.
            ai_system = self._require_ai_system(org_id, row.ai_system_id)
            row.baseline_model_version = ai_system.model_version if payload["baseline_value"] is not None else None

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

    def _compute_degradation_trend(self, config: AIMonitoringConfig, *, lookback: int = 5) -> dict:
        """Reason about degradation over time, not just the single latest value.

        Looks at the most recent `lookback` readings (including the one just
        recorded) to compute a consecutive-breach streak and, when a baseline
        is configured, how far the current value has drifted from it. This is
        what lets an alert say "3 consecutive breaches, 42% worse than
        baseline" instead of a single point-in-time threshold comparison.
        """
        recent = self.db.execute(
            select(AIMonitoringReading)
            .where(
                AIMonitoringReading.organization_id == config.organization_id,
                AIMonitoringReading.config_id == config.id,
            )
            .order_by(AIMonitoringReading.created_at.desc())
            .limit(lookback)
        ).scalars().all()

        breach_streak = 0
        for reading in recent:
            if reading.within_threshold is False:
                breach_streak += 1
            else:
                break

        pct_from_baseline = None
        if config.baseline_value is not None and config.baseline_value != 0 and recent:
            latest_value = recent[0].value
            pct_from_baseline = float((latest_value - config.baseline_value) / abs(config.baseline_value) * 100)

        return {
            "breach_streak": breach_streak,
            "sustained_degradation": breach_streak >= 3,
            "pct_from_baseline": pct_from_baseline,
        }

    def _create_breach_alert(self, config: AIMonitoringConfig, value: Decimal, trend: dict) -> ControlMonitoringAlert:
        direction_text = "above" if config.comparison_direction == "above" else "below"
        description = (
            f"AI monitoring breach: {config.metric_type} = {value} "
            f"({direction_text} threshold {config.threshold_value})"
        )
        breach_streak = trend["breach_streak"]
        if trend["sustained_degradation"]:
            description += f" — sustained degradation: {breach_streak} consecutive breaches"
        pct_from_baseline = trend["pct_from_baseline"]
        if pct_from_baseline is not None:
            description += f"; {pct_from_baseline:+.1f}% vs baseline {config.baseline_value}"

        severity = self._severity_for_metric(config.metric_type)
        if trend["sustained_degradation"]:
            # A single blip and a multi-reading sustained drift are not the same
            # risk: escalate severity so a trend doesn't get lost among one-offs.
            severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            escalated = "critical" if severity_rank.get(severity, 0) >= 2 else "high"
            severity = escalated

        alert = ControlMonitoringAlert(
            organization_id=config.organization_id,
            rule_id=None,
            definition_id=None,
            control_id=None,
            alert_type="ai_monitoring",
            severity=severity,
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
                "breach_streak": breach_streak,
                "sustained_degradation": trend["sustained_degradation"],
                "pct_from_baseline": pct_from_baseline,
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
        reading_source = validate_choice(reading_source, ALLOWED_READING_SOURCES, "reading_source")
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
            trend = self._compute_degradation_trend(config)
            alert = self._create_breach_alert(config, value, trend)
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

        breach_signal_type = {
            "bias_parity_gap": "bias_signal",
            "output_drift": "output_distribution_shift",
        }.get(config.metric_type)
        if not within_threshold and breach_signal_type is not None:
            SignalService(self.db).emit_signal(
                org_id,
                config.ai_system_id,
                signal_type=breach_signal_type,
                description=f"Monitoring metric {config.metric_type} breached threshold: {value}",
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

    def build_threshold_registry(self, org_id: uuid.UUID, *, ai_system_id: uuid.UUID | None = None) -> dict:
        """Every active threshold this organisation is enforcing.

        The machine-facing counterpart to the monitoring UI: an external collector needs
        to know what to measure and what core will compare it against, so it can compute
        the right metrics at the right cadence. It deliberately returns no credential --
        see ThresholdRegistryEntry, whose field set is asserted by test rather than left
        to reviewer diligence.

        `api_key_hash` is excluded structurally, by never selecting it into the response
        model. That it is only a hash is not a reason to relax: it is the exact value
        `receive_inbound_reading` compares against, so anyone holding it can replay it
        as the credential itself.
        """
        stmt = select(AIMonitoringConfig).where(
            AIMonitoringConfig.organization_id == org_id,
            AIMonitoringConfig.is_active.is_(True),
            AIMonitoringConfig.deleted_at.is_(None),
        )
        if ai_system_id is not None:
            stmt = stmt.where(AIMonitoringConfig.ai_system_id == ai_system_id)
        stmt = stmt.order_by(
            AIMonitoringConfig.ai_system_id.asc(),
            AIMonitoringConfig.metric_type.asc(),
            AIMonitoringConfig.escalation_order.asc(),
        )
        configs = self.db.execute(stmt).scalars().all()

        return {
            "organization_id": org_id,
            "generated_at": self.utcnow(),
            "total": len(configs),
            "thresholds": [
                {
                    "config_id": row.id,
                    "ai_system_id": row.ai_system_id,
                    "metric_type": row.metric_type,
                    "tier": row.tier,
                    "escalation_order": row.escalation_order,
                    "threshold_value": row.threshold_value,
                    "threshold_operator": row.threshold_operator,
                    "comparison_direction": row.comparison_direction,
                    "obligation_id": row.obligation_id,
                    "workflow_to_trigger": row.workflow_to_trigger,
                    "check_frequency": row.check_frequency,
                    "baseline_value": row.baseline_value,
                    "collection_hint": row.check_frequency,
                }
                for row in configs
            ],
        }

    def list_readings(
        self,
        org_id: uuid.UUID,
        config_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Time-series history for a single metric, plus a trend summary.

        This is the actual visualization/summary source for a metric such as
        `output_drift` or `bias_parity_gap`: callers can chart `readings` over
        time, and `trend` gives a computed direction/magnitude so the caller
        doesn't have to re-derive it client-side.
        """
        config = self._require_config(org_id, config_id)

        total = self.db.execute(
            select(func.count()).select_from(AIMonitoringReading).where(
                AIMonitoringReading.organization_id == org_id,
                AIMonitoringReading.config_id == config_id,
            )
        ).scalar_one()

        readings = self.db.execute(
            select(AIMonitoringReading)
            .where(
                AIMonitoringReading.organization_id == org_id,
                AIMonitoringReading.config_id == config_id,
            )
            .order_by(AIMonitoringReading.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()

        values = [r.value for r in readings]
        # `is False`, not `not ...`: within_threshold is NULLABLE since 0321 and NULL
        # means "no single-config verdict", not "breached". Counting NULLs here would
        # inflate the dashboard's breach count with readings nobody judged.
        breach_count = sum(1 for r in readings if r.within_threshold is False)
        trend_direction = None
        if len(values) >= 2:
            # values are newest-first; compare newest to oldest in this page.
            delta = values[0] - values[-1]
            if delta > 0:
                trend_direction = "increasing"
            elif delta < 0:
                trend_direction = "decreasing"
            else:
                trend_direction = "flat"

        trend = self._compute_degradation_trend(config)
        return {
            "config": config,
            "readings": readings,
            "total": int(total),
            "summary": {
                "count_in_page": len(readings),
                "min_value": min(values) if values else None,
                "max_value": max(values) if values else None,
                "avg_value": (sum(values) / len(values)) if values else None,
                "breach_count_in_page": breach_count,
                "trend_direction": trend_direction,
                "breach_streak": trend["breach_streak"],
                "sustained_degradation": trend["sustained_degradation"],
                "pct_from_baseline": trend["pct_from_baseline"],
            },
        }

    # A reading further than this percentage from the recorded baseline is
    # treated as drift worth surfacing on the dashboard, independent of
    # whether it also breaches the hard alert threshold. This scalar
    # percent-from-baseline check is used for every metric_type EXCEPT
    # "output_drift", where enough history exists -- see
    # _statistical_output_drift below for why that one metric gets a real
    # statistical drift test instead of a point-to-point percent diff.
    DRIFT_PCT_THRESHOLD = Decimal("20")

    # Minimum readings needed on each side (reference vs current) before a
    # real distributional drift test is statistically meaningful. Below
    # this, _statistical_output_drift falls back to the same
    # percent-from-baseline calculation used for every other metric type
    # rather than pretending a 1-2 sample "distribution" comparison means
    # anything.
    DRIFT_TEST_WINDOW_SIZE = 5

    def _statistical_output_drift(self, config: AIMonitoringConfig) -> tuple[Decimal, bool] | None:
        """Real statistical distribution-drift check for `output_drift` configs.

        `output_drift` is the one metric_type that actually means "has the
        distribution of model outputs shifted" -- a question a single
        latest-value-vs-baseline percent diff can't answer (two point values
        say nothing about distributional shape/spread). Instead this treats
        the reading history itself as two samples: the oldest
        DRIFT_TEST_WINDOW_SIZE readings ("reference", roughly the period the
        system was first monitored) vs the newest DRIFT_TEST_WINDOW_SIZE
        readings ("current"), and runs them through the same statistical
        drift detector already used by the LLM observability satellite
        (app/satellites/llm_observability/drift_adapters.py) rather than a
        second, different integration.

        Returns None (caller falls back to the percent-from-baseline
        calculation) when there isn't enough history for a meaningful test,
        or when the two windows overlap (too few total readings).
        """
        readings = self.db.execute(
            select(AIMonitoringReading.value, AIMonitoringReading.created_at)
            .where(
                AIMonitoringReading.organization_id == config.organization_id,
                AIMonitoringReading.config_id == config.id,
            )
            .order_by(AIMonitoringReading.created_at.asc(), AIMonitoringReading.id.asc())
        ).all()

        window = self.DRIFT_TEST_WINDOW_SIZE
        if len(readings) < 2 * window:
            return None

        reference_values = [float(value) for value, _ in readings[:window]]
        current_values = [float(value) for value, _ in readings[-window:]]

        reference_df = pd.DataFrame({"value": reference_values})
        current_df = pd.DataFrame({"value": current_values})

        # detect_data_drift always returns [drift_share_result, drifted_columns_result]
        # in that fixed order (see drift_adapters.py) -- indexed rather than
        # matched by metric_type string to avoid the vendor-specific name.
        drift_share_result = DistributionDriftDetector().detect_data_drift(
            reference_data=reference_df, current_data=current_df, numerical_columns=["value"]
        )[0]
        dataset_drift = bool(drift_share_result.details.get("dataset_drift"))
        drift_pct = decimal_from_float(float(drift_share_result.value) * 100.0)
        return drift_pct, dataset_drift

    def get_monitoring_dashboard(self, org_id: uuid.UUID, system_id: uuid.UUID) -> dict:
        ai_system = self._require_ai_system(org_id, system_id)
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

            drift_pct = None
            drift_detected = False
            statistical_result = self._statistical_output_drift(cfg) if cfg.metric_type == "output_drift" else None
            if statistical_result is not None:
                drift_pct, drift_detected = statistical_result
            elif cfg.baseline_value is not None and cfg.last_reading_value is not None and cfg.baseline_value != 0:
                drift_pct = abs(cfg.last_reading_value - cfg.baseline_value) / abs(cfg.baseline_value) * Decimal("100")
                drift_detected = drift_pct > self.DRIFT_PCT_THRESHOLD

            baseline_reassessment_required = bool(
                cfg.baseline_model_version is not None and cfg.baseline_model_version != ai_system.model_version
            )

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
                    "baseline_value": cfg.baseline_value,
                    "drift_pct": drift_pct,
                    "drift_detected": drift_detected,
                    "baseline_reassessment_required": baseline_reassessment_required,
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
