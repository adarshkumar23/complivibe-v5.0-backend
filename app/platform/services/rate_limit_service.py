from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.rate_limit_config import RateLimitConfig
from app.services.audit_service import AuditService


DEFAULT_CONFIGS: list[dict] = [
    # 300/minute (was 60): a single dashboard page fires 4-8 parallel queries, and
    # normal multi-page navigation within a minute is legitimate usage that
    # measurably tripped the old 60/minute ceiling in live verification -- see
    # app/core/rate_limiter.py's ENDPOINT_GROUP_DEFAULTS, which this platform-default
    # DB row takes priority over for any authenticated request (get_org_limit falls
    # back to that dict only when no DB row exists at all).
    {"endpoint_group": "api_general", "requests_per_minute": 300, "requests_per_hour": 5000, "requests_per_day": 50000},
    {"endpoint_group": "ingest", "requests_per_minute": 30, "requests_per_hour": 500, "requests_per_day": 5000},
    {"endpoint_group": "auth", "requests_per_minute": 10, "requests_per_hour": 100, "requests_per_day": 500},
    {"endpoint_group": "reports", "requests_per_minute": 20, "requests_per_hour": 200, "requests_per_day": 2000},
    {"endpoint_group": "public", "requests_per_minute": 120, "requests_per_hour": 2000, "requests_per_day": None},
    {"endpoint_group": "ai_governance", "requests_per_minute": 30, "requests_per_hour": 500, "requests_per_day": 5000},
    {"endpoint_group": "scim", "requests_per_minute": 60, "requests_per_hour": 1000, "requests_per_day": None},
]


class RateLimitService:
    def ensure_platform_defaults(self, db: Session) -> None:
        existing = (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id.is_(None),
                RateLimitConfig.is_active.is_(True),
            )
            .count()
        )
        if existing >= len(DEFAULT_CONFIGS):
            return

        for row in DEFAULT_CONFIGS:
            item = (
                db.query(RateLimitConfig)
                .filter(
                    RateLimitConfig.organization_id.is_(None),
                    RateLimitConfig.endpoint_group == row["endpoint_group"],
                )
                .first()
            )
            if item is None:
                db.add(
                    RateLimitConfig(
                        organization_id=None,
                        endpoint_group=row["endpoint_group"],
                        requests_per_minute=row["requests_per_minute"],
                        requests_per_hour=row["requests_per_hour"],
                        requests_per_day=row["requests_per_day"],
                        burst_allowance=10,
                        is_active=True,
                        created_by=None,
                    )
                )
            elif not item.is_active:
                item.is_active = True
                item.updated_at = datetime.now(UTC)
        db.flush()

    def get_platform_defaults(self, db: Session) -> list[RateLimitConfig]:
        self.ensure_platform_defaults(db)
        return (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id.is_(None),
                RateLimitConfig.is_active.is_(True),
            )
            .order_by(RateLimitConfig.endpoint_group.asc())
            .all()
        )

    def get_org_config(self, org_id: uuid.UUID, db: Session) -> list[RateLimitConfig]:
        return (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id == org_id,
                RateLimitConfig.is_active.is_(True),
            )
            .order_by(RateLimitConfig.endpoint_group.asc())
            .all()
        )

    def set_org_limit(
        self,
        org_id: uuid.UUID,
        endpoint_group: str,
        requests_per_minute: int,
        requests_per_hour: int,
        created_by: uuid.UUID,
        db: Session,
    ) -> RateLimitConfig:
        if requests_per_minute <= 0 or requests_per_hour <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rate limits must be positive integers")

        existing = (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id == org_id,
                RateLimitConfig.endpoint_group == endpoint_group,
            )
            .first()
        )

        if existing:
            existing.requests_per_minute = requests_per_minute
            existing.requests_per_hour = requests_per_hour
            existing.is_active = True
            existing.updated_at = datetime.now(UTC)
            db.flush()
            return existing

        config = RateLimitConfig(
            organization_id=org_id,
            endpoint_group=endpoint_group,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=None,
            burst_allowance=10,
            is_active=True,
            created_by=created_by,
        )
        db.add(config)
        db.flush()

        AuditService(db).write_audit_log(
            action="rate_limit.org_config_set",
            entity_type="rate_limit_configs",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=config.id,
            metadata_json={
                "endpoint_group": endpoint_group,
                "rpm": requests_per_minute,
                "rph": requests_per_hour,
            },
        )
        return config

    def reset_to_default(
        self,
        org_id: uuid.UUID,
        endpoint_group: str,
        user_id: uuid.UUID,
        db: Session,
    ) -> None:
        config = (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id == org_id,
                RateLimitConfig.endpoint_group == endpoint_group,
                RateLimitConfig.is_active.is_(True),
            )
            .first()
        )
        if config:
            config.is_active = False
            config.updated_at = datetime.now(UTC)
            db.flush()
            AuditService(db).write_audit_log(
                action="rate_limit.org_config_reset",
                entity_type="rate_limit_configs",
                organization_id=org_id,
                actor_user_id=user_id,
                entity_id=config.id,
                metadata_json={"endpoint_group": endpoint_group},
            )
