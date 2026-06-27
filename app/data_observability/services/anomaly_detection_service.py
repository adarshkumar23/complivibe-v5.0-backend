import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_access_anomaly_rule import DataAccessAnomalyRule
from app.models.data_access_log import DataAccessLog
from app.models.data_asset import DataAsset
from app.services.rbac_service import RBACService


class AnomalyDetectionService:
    """
    Pure threshold-rule evaluation.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_access_event(self, access_log: DataAccessLog) -> list[dict]:
        rules = self.db.execute(
            select(DataAccessAnomalyRule).where(
                DataAccessAnomalyRule.organization_id == access_log.organization_id,
                DataAccessAnomalyRule.is_active.is_(True),
                DataAccessAnomalyRule.deleted_at.is_(None),
                (
                    (DataAccessAnomalyRule.data_asset_id == access_log.data_asset_id)
                    | (DataAccessAnomalyRule.data_asset_id.is_(None))
                ),
            )
        ).scalars().all()

        breaches = []
        for rule in rules:
            result = self._evaluate(rule, access_log)
            if result["breached"]:
                breaches.append(
                    {
                        "rule_id": rule.id,
                        "rule_type": rule.rule_type,
                        "reason": result["reason"],
                    }
                )
        return breaches

    def _evaluate(self, rule: DataAccessAnomalyRule, access_log: DataAccessLog) -> dict:
        cfg = rule.rule_config or {}
        org_id = rule.organization_id
        asset_id = access_log.data_asset_id

        if rule.rule_type == "access_count_spike":
            window_minutes = int(cfg.get("window_minutes", 10))
            threshold = int(cfg.get("count", 100))
            count = int(
                self.db.execute(
                    select(func.count(DataAccessLog.id)).where(
                        DataAccessLog.organization_id == org_id,
                        DataAccessLog.data_asset_id == asset_id,
                        DataAccessLog.access_time >= access_log.access_time - timedelta(minutes=window_minutes),
                    )
                ).scalar_one()
                or 0
            )
            if count > threshold:
                return {
                    "breached": True,
                    "reason": f"{count} accesses in {window_minutes}min (threshold: {threshold})",
                }

        elif rule.rule_type == "after_hours_access":
            start = str(cfg.get("business_start", "09:00"))
            end = str(cfg.get("business_end", "18:00"))
            start_h, start_m = [int(x) for x in start.split(":")]
            end_h, end_m = [int(x) for x in end.split(":")]

            access_dt = access_log.access_time
            if access_dt.tzinfo is None:
                access_dt = access_dt.replace(tzinfo=UTC)
            access_dt = access_dt.astimezone(UTC)
            access_mins = access_dt.hour * 60 + access_dt.minute
            start_mins = start_h * 60 + start_m
            end_mins = end_h * 60 + end_m
            if not (start_mins <= access_mins <= end_mins):
                return {
                    "breached": True,
                    "reason": f"Access at {access_dt.isoformat()} outside business hours {start}-{end} UTC",
                }

        elif rule.rule_type == "new_actor_access":
            if access_log.actor_id:
                prior = self.db.execute(
                    select(DataAccessLog).where(
                        DataAccessLog.organization_id == org_id,
                        DataAccessLog.data_asset_id == asset_id,
                        DataAccessLog.actor_id == access_log.actor_id,
                        DataAccessLog.id != access_log.id,
                    )
                ).scalar_one_or_none()
                if prior is None:
                    return {
                        "breached": True,
                        "reason": f"First-ever access by actor {access_log.actor_id} to this asset",
                    }

        elif rule.rule_type == "mass_download":
            if access_log.bytes_transferred:
                threshold = int(cfg.get("bytes", 5368709120))
                if access_log.bytes_transferred > threshold:
                    gb = float(access_log.bytes_transferred) / 1e9
                    return {
                        "breached": True,
                        "reason": f"{gb:.2f}GB transferred (threshold: {threshold/1e9:.2f}GB)",
                    }

        elif rule.rule_type == "failed_access_spike":
            if access_log.access_result == "failed":
                window_minutes = int(cfg.get("window_minutes", 5))
                threshold = int(cfg.get("count", 20))
                count = int(
                    self.db.execute(
                        select(func.count(DataAccessLog.id)).where(
                            DataAccessLog.organization_id == org_id,
                            DataAccessLog.data_asset_id == asset_id,
                            DataAccessLog.access_result == "failed",
                            DataAccessLog.access_time >= access_log.access_time - timedelta(minutes=window_minutes),
                        )
                    ).scalar_one()
                    or 0
                )
                if count > threshold:
                    return {
                        "breached": True,
                        "reason": f"{count} failed attempts in {window_minutes}min",
                    }

        elif rule.rule_type == "cross_border_access":
            if access_log.source_country:
                asset = self.db.get(DataAsset, access_log.data_asset_id)
                permitted = list(asset.permitted_regions or []) if asset else []
                if permitted and access_log.source_country not in permitted:
                    return {
                        "breached": True,
                        "reason": f"Access from {access_log.source_country} not in permitted regions: {permitted}",
                    }

        elif rule.rule_type == "sensitivity_mismatch_access":
            asset = self.db.get(DataAsset, access_log.data_asset_id)
            restricted_tiers = list(cfg.get("restricted_tiers", ["restricted", "secret"]))
            if asset and asset.sensitivity_tier in restricted_tiers and access_log.actor_id:
                has_permission = RBACService.user_has_permission(
                    self.db,
                    access_log.actor_id,
                    access_log.organization_id,
                    "data:read",
                )
                if not has_permission:
                    return {
                        "breached": True,
                        "reason": f"Actor {access_log.actor_id} lacks data:read for {asset.sensitivity_tier} asset",
                    }

        return {"breached": False, "reason": ""}
