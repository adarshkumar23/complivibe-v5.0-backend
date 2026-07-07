from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.competitor_pricing_entry import CompetitorPricingEntry
from app.models.competitor_pricing_version import CompetitorPricingVersion
from app.schemas.pricing import CompetitorPricingEntryRefresh
from app.services.audit_service import AuditService

DEFAULT_COMPETITOR_PRICING: list[dict[str, Any]] = [
    {
        "competitor_key": "vanta",
        "competitor_name": "Vanta",
        "pricing_model": "contact_sales",
        "public_pricing_available": False,
        "pricing_summary": "Vanta markets plan selection with personalized pricing and demo-led sales motions; no public list price is published.",
        "source_url": "https://www.vanta.com/",
        "source_excerpt": "Request a free demo today to discuss your business needs and get personalized pricing.",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_marketing_page"},
    },
    {
        "competitor_key": "drata",
        "competitor_name": "Drata",
        "pricing_model": "tiered_quote",
        "public_pricing_available": False,
        "pricing_summary": "Drata presents multiple plans but requires sales engagement for final pricing details.",
        "source_url": "https://drata.com/plans",
        "source_excerpt": "Explore Drata’s plans and pricing to build a scalable GRC program.",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_pricing_page"},
    },
    {
        "competitor_key": "sprinto",
        "competitor_name": "Sprinto",
        "pricing_model": "tiered_quote",
        "public_pricing_available": False,
        "pricing_summary": "Sprinto exposes plan packaging by growth stage, while commercial pricing is sales-led.",
        "source_url": "https://sprinto.com/pricing/",
        "source_excerpt": "From your first certification journey to enterprise-scale GRC, Sprinto adapts to your compliance journey.",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_pricing_page"},
    },
    {
        "competitor_key": "scrut",
        "competitor_name": "Scrut",
        "pricing_model": "contact_sales",
        "public_pricing_available": False,
        "pricing_summary": "Scrut positions platform capabilities publicly and routes commercial details through demo/contact workflows.",
        "source_url": "https://www.scrut.io/",
        "source_excerpt": "Build risk-aligned security programs that scale with you.",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_home_page"},
    },
    {
        "competitor_key": "onetrust",
        "competitor_name": "OneTrust",
        "pricing_model": "custom_package",
        "public_pricing_available": False,
        "pricing_summary": "OneTrust presents package-based pricing guidance and package scoping, with quote-based commercial terms.",
        "source_url": "https://www.onetrust.com/pricing/",
        "source_excerpt": "Explore our simple, scalable packages designed to help you collect, govern, and use your data.",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_pricing_page"},
    },
    {
        "competitor_key": "credo_ai",
        "competitor_name": "Credo AI",
        "pricing_model": "contact_sales",
        "public_pricing_available": False,
        "pricing_summary": "Credo AI communicates product positioning publicly and directs pricing discovery to demo/contact channels.",
        "source_url": "https://www.credo.ai/",
        "source_excerpt": "Get a Demo",
        "currency": None,
        "starting_price_amount": None,
        "starting_price_unit": None,
        "last_verified_at": datetime(2026, 7, 6, tzinfo=UTC),
        "metadata_json": {"source_type": "official_home_page"},
    },
]


class CompetitorPricingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _latest_version(self) -> CompetitorPricingVersion | None:
        return self.db.execute(
            select(CompetitorPricingVersion).order_by(
                CompetitorPricingVersion.published_at.desc(),
                CompetitorPricingVersion.last_updated.desc(),
            )
        ).scalars().first()

    def _entries_for_version(self, version_id: uuid.UUID) -> list[CompetitorPricingEntry]:
        return self.db.execute(
            select(CompetitorPricingEntry)
            .where(CompetitorPricingEntry.version_id == version_id)
            .order_by(CompetitorPricingEntry.competitor_name.asc())
        ).scalars().all()

    @staticmethod
    def _as_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _validate_entries(self, entries: list[CompetitorPricingEntryRefresh]) -> None:
        seen_competitor_keys: set[str] = set()
        for payload in entries:
            if payload.competitor_key in seen_competitor_keys:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate competitor_key in snapshot: {payload.competitor_key}",
                )
            seen_competitor_keys.add(payload.competitor_key)

            has_amount = payload.starting_price_amount is not None
            has_currency = payload.currency is not None
            if has_amount != has_currency:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="currency and starting_price_amount must be provided together",
                )
            if has_amount and not payload.public_pricing_available:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="public_pricing_available must be true when starting_price_amount is provided",
                )

    def ensure_seed_snapshot(self) -> CompetitorPricingVersion:
        version = self._latest_version()
        if version is not None:
            return version
        return self.create_snapshot(
            entries=[CompetitorPricingEntryRefresh(**item) for item in DEFAULT_COMPETITOR_PRICING],
            actor_user_id=None,
            actor_organization_id=None,
            source_note="Auto-seeded baseline from official vendor pricing pages and landing pages.",
            published_at=datetime(2026, 7, 6, tzinfo=UTC),
        )

    def create_snapshot(
        self,
        *,
        entries: list[CompetitorPricingEntryRefresh],
        actor_user_id: uuid.UUID | None,
        actor_organization_id: uuid.UUID | None,
        source_note: str | None,
        published_at: datetime | None = None,
        actor_is_superuser: bool | None = None,
    ) -> CompetitorPricingVersion:
        if not entries:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one pricing entry is required")
        self._validate_entries(entries)

        version = CompetitorPricingVersion(
            created_by_user_id=actor_user_id,
            source_note=source_note,
            published_at=published_at or self._utcnow(),
            last_updated=self._utcnow(),
        )
        self.db.add(version)
        self.db.flush()

        if actor_organization_id is not None:
            self.audit.write_audit_log(
                action="pricing.snapshot_created",
                entity_type="competitor_pricing_versions",
                entity_id=version.id,
                organization_id=actor_organization_id,
                actor_user_id=actor_user_id,
                after_json={"published_at": version.published_at.isoformat(), "entry_count": len(entries)},
                metadata_json={
                    "source_note": source_note or "",
                    "actor_is_superuser": bool(actor_is_superuser),
                },
            )

        for payload in entries:
            entry = CompetitorPricingEntry(
                version_id=version.id,
                competitor_key=payload.competitor_key,
                competitor_name=payload.competitor_name,
                pricing_model=payload.pricing_model,
                public_pricing_available=payload.public_pricing_available,
                pricing_summary=payload.pricing_summary,
                source_url=payload.source_url,
                source_excerpt=payload.source_excerpt,
                currency=payload.currency,
                starting_price_amount=Decimal(str(payload.starting_price_amount)) if payload.starting_price_amount is not None else None,
                starting_price_unit=payload.starting_price_unit,
                last_verified_at=payload.last_verified_at,
                metadata_json=payload.metadata_json,
            )
            self.db.add(entry)
            self.db.flush()
            if actor_organization_id is not None:
                self.audit.write_audit_log(
                    action="pricing.entry_created",
                    entity_type="competitor_pricing_entries",
                    entity_id=entry.id,
                    organization_id=actor_organization_id,
                    actor_user_id=actor_user_id,
                    after_json={
                        "competitor_key": entry.competitor_key,
                        "pricing_model": entry.pricing_model,
                        "public_pricing_available": entry.public_pricing_available,
                    },
                    metadata_json={"version_id": str(version.id)},
                )
        return version

    def latest_snapshot_payload(self) -> dict[str, Any]:
        version = self.ensure_seed_snapshot()
        entries = self._entries_for_version(version.id)
        latest_verified_at = max((self._as_aware_utc(row.last_verified_at) for row in entries), default=None)
        data_age_days: int | None = None
        if latest_verified_at is not None:
            data_age_days = max(0, (self._utcnow() - latest_verified_at).days)
        is_stale = bool(data_age_days is not None and data_age_days > 30)
        total_competitors = len(entries)
        public_pricing_available_count = sum(1 for row in entries if row.public_pricing_available)
        starting_price_available_count = sum(1 for row in entries if row.starting_price_amount is not None)
        public_pricing_coverage_pct = round((public_pricing_available_count / total_competitors) * 100, 2) if total_competitors else 0
        context_flags: list[str] = []
        if is_stale:
            context_flags.append("pricing_data_stale")
        if total_competitors < len(DEFAULT_COMPETITOR_PRICING):
            context_flags.append("competitor_coverage_partial")
        if total_competitors == 0:
            context_flags.append("pricing_snapshot_empty")
        if starting_price_available_count == 0:
            context_flags.append("no_public_starting_prices")
        if public_pricing_available_count == 0:
            context_flags.append("quote_led_market")
        return {
            "version_id": version.id,
            "source_note": version.source_note,
            "published_at": version.published_at,
            "last_updated": version.last_updated,
            "latest_verified_at": latest_verified_at,
            "data_age_days": data_age_days,
            "is_stale": is_stale,
            "total_competitors": total_competitors,
            "public_pricing_available_count": public_pricing_available_count,
            "starting_price_available_count": starting_price_available_count,
            "public_pricing_coverage_pct": public_pricing_coverage_pct,
            "context_flags": context_flags,
            "entries": [
                {
                    "id": row.id,
                    "competitor_key": row.competitor_key,
                    "competitor_name": row.competitor_name,
                    "pricing_model": row.pricing_model,
                    "public_pricing_available": row.public_pricing_available,
                    "pricing_summary": row.pricing_summary,
                    "source_url": row.source_url,
                    "source_excerpt": row.source_excerpt,
                    "currency": row.currency,
                    "starting_price_amount": float(row.starting_price_amount) if row.starting_price_amount is not None else None,
                    "starting_price_unit": row.starting_price_unit,
                    "last_verified_at": row.last_verified_at,
                    "metadata_json": row.metadata_json or {},
                }
                for row in entries
            ],
        }
