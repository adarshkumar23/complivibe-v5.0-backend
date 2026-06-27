import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_observability.services.lineage_service import LineageService
from app.models.consent_banner_config import ConsentBannerConfig
from app.models.cookie_registry import CookieRegistry
from app.models.organization import Organization
from app.services.audit_service import AuditService

ALLOWED_COOKIE_CATEGORIES = {"strictly_necessary", "functional", "analytics", "marketing", "unknown"}


class CookieService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_cookie(self, org_id: uuid.UUID, cookie_id: uuid.UUID) -> CookieRegistry:
        row = self.db.execute(
            select(CookieRegistry).where(
                CookieRegistry.organization_id == org_id,
                CookieRegistry.id == cookie_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cookie not found")
        return row

    def _validate_category(self, category: str) -> None:
        if category not in ALLOWED_COOKIE_CATEGORIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid cookie category")

    def create_cookie(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> CookieRegistry:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        self._validate_category(payload["category"])

        existing = self.db.execute(
            select(CookieRegistry).where(
                CookieRegistry.organization_id == org_id,
                CookieRegistry.name == payload["name"],
                CookieRegistry.domain == payload["domain"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cookie already exists")

        now = self.utcnow()
        row = CookieRegistry(
            organization_id=org_id,
            name=payload["name"],
            domain=payload["domain"],
            category=payload["category"],
            purpose=payload.get("purpose"),
            provider=payload.get("provider"),
            duration=payload.get("duration"),
            is_third_party=bool(payload.get("is_third_party", False)),
            last_seen_at=None,
            first_seen_at=None,
            source="manual",
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="cookie.created",
            entity_type="cookie_registry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": row.name, "domain": row.domain, "category": row.category, "source": row.source},
            metadata_json={"source": "api"},
        )
        return row

    def list_cookies(self, org_id: uuid.UUID, category: str | None = None, is_active: bool | None = None) -> list[CookieRegistry]:
        stmt = select(CookieRegistry).where(CookieRegistry.organization_id == org_id)
        if category is not None:
            self._validate_category(category)
            stmt = stmt.where(CookieRegistry.category == category)
        if is_active is not None:
            stmt = stmt.where(CookieRegistry.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(CookieRegistry.updated_at.desc())).scalars().all()

    def update_cookie(self, org_id: uuid.UUID, cookie_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> CookieRegistry:
        row = self._require_cookie(org_id, cookie_id)
        payload = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)

        if "category" in payload and payload["category"] is not None:
            self._validate_category(payload["category"])

        for key, value in payload.items():
            setattr(row, key, value)

        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="cookie.updated",
            entity_type="cookie_registry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"category": row.category, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def process_scan_report(self, org_id: uuid.UUID, domain: str, cookies: list[dict], scanned_at: datetime) -> dict:
        now = self.utcnow()
        scanned_value = scanned_at.astimezone(UTC) if scanned_at.tzinfo else scanned_at.replace(tzinfo=UTC)

        new_count = 0
        updated = 0

        seen_keys: set[tuple[str, str]] = set()
        for cookie in cookies:
            key = (cookie.get("name", ""), domain)
            if not key[0] or key in seen_keys:
                continue
            seen_keys.add(key)

            category = cookie.get("category") or "unknown"
            if category not in ALLOWED_COOKIE_CATEGORIES:
                category = "unknown"

            row = self.db.execute(
                select(CookieRegistry).where(
                    CookieRegistry.organization_id == org_id,
                    CookieRegistry.name == key[0],
                    CookieRegistry.domain == key[1],
                )
            ).scalar_one_or_none()

            if row is None:
                creator = self.db.execute(
                    select(Organization.created_by).where(Organization.id == org_id)
                ).scalar_one_or_none()
                created_by = creator or uuid.uuid4()
                row = CookieRegistry(
                    organization_id=org_id,
                    name=key[0],
                    domain=key[1],
                    category=category,
                    purpose=cookie.get("purpose"),
                    provider=cookie.get("provider"),
                    duration=cookie.get("duration"),
                    is_third_party=bool(cookie.get("is_third_party", False)),
                    last_seen_at=scanned_value,
                    first_seen_at=scanned_value,
                    source="scan_report",
                    is_active=True,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(row)
                new_count += 1
            else:
                row.category = category
                row.purpose = cookie.get("purpose")
                row.provider = cookie.get("provider")
                row.duration = cookie.get("duration")
                row.is_third_party = bool(cookie.get("is_third_party", False))
                row.last_seen_at = scanned_value
                if row.first_seen_at is None:
                    row.first_seen_at = scanned_value
                row.source = "scan_report"
                row.updated_at = now
                updated += 1

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="cookie.scan_report_received",
            entity_type="cookie_registry",
            entity_id=None,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"domain": domain, "new_cookies": new_count, "updated": updated},
            metadata_json={"source": "inbound_scan"},
        )

        return {"new_cookies": new_count, "updated": updated}

    def get_banner_config(self, org_id: uuid.UUID) -> ConsentBannerConfig | None:
        return self.db.execute(
            select(ConsentBannerConfig).where(ConsentBannerConfig.organization_id == org_id)
        ).scalar_one_or_none()

    def create_or_update_banner(self, org_id: uuid.UUID, data, user_id: uuid.UUID) -> ConsentBannerConfig:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        categories = payload.get("enabled_categories") or ["strictly_necessary", "functional", "analytics", "marketing"]
        for category in categories:
            self._validate_category(category)

        now = self.utcnow()
        row = self.get_banner_config(org_id)
        if row is None:
            row = ConsentBannerConfig(
                organization_id=org_id,
                banner_title=payload.get("banner_title", "Cookie Preferences"),
                banner_body=payload["banner_body"],
                accept_all_text=payload.get("accept_all_text", "Accept All"),
                reject_all_text=payload.get("reject_all_text", "Reject All"),
                manage_text=payload.get("manage_text", "Manage Preferences"),
                enabled_categories=categories,
                is_active=bool(payload.get("is_active", True)),
                created_by=user_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.banner_title = payload.get("banner_title", row.banner_title)
            row.banner_body = payload.get("banner_body", row.banner_body)
            row.accept_all_text = payload.get("accept_all_text", row.accept_all_text)
            row.reject_all_text = payload.get("reject_all_text", row.reject_all_text)
            row.manage_text = payload.get("manage_text", row.manage_text)
            row.enabled_categories = categories
            row.is_active = bool(payload.get("is_active", row.is_active))
            row.updated_at = now

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="banner_config.updated",
            entity_type="consent_banner_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active, "enabled_categories": row.enabled_categories},
            metadata_json={"source": "api"},
        )
        return row

    def get_public_banner(self, slug: str) -> dict:
        org = self.db.execute(
            select(Organization).where(Organization.slug == slug, Organization.is_active.is_(True))
        ).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        config = self.db.execute(
            select(ConsentBannerConfig).where(
                ConsentBannerConfig.organization_id == org.id,
                ConsentBannerConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()

        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Banner config not found")

        categories = self.db.execute(
            select(CookieRegistry.category).where(
                CookieRegistry.organization_id == org.id,
                CookieRegistry.is_active.is_(True),
            )
        ).scalars().all()
        category_list = sorted(set(categories))

        return {
            "organization_slug": slug,
            "banner_config": {
                "banner_title": config.banner_title,
                "banner_body": config.banner_body,
                "accept_all_text": config.accept_all_text,
                "reject_all_text": config.reject_all_text,
                "manage_text": config.manage_text,
                "enabled_categories": config.enabled_categories,
                "is_active": config.is_active,
            },
            "cookie_categories": category_list,
        }

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return LineageService(self.db).resolve_org_by_api_key(raw_key)
