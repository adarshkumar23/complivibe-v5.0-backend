import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.compliance.services.subprocessor_service import SubprocessorService
from app.core.geo import region_overlaps
from app.models.data_asset import DataAsset
from app.models.data_asset_obligation_link import DataAssetObligationLink
from app.models.data_obligation_suggestion import DataObligationSuggestion
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_LINK_TYPES = {"governed_by", "subject_to", "exempted_from"}

EEA_COUNTRIES = set(SubprocessorService.EEA_COUNTRIES)
GLOBAL_JURISDICTIONS = {"global", "international", "worldwide"}
# Matches concise jurisdiction codes like "IN", "US", "US-CA", "EU" -- as
# opposed to free-text jurisdiction labels like "European Union" that some
# frameworks (e.g. hand-authored/test fixtures) may still carry. Only
# code-shaped jurisdictions are strict-filtered by org footprint; free-text
# ones are treated as unrestricted since we can't parse a region out of them.
_JURISDICTION_CODE_RE = re.compile(r"^[A-Z]{2}(-[A-Z]{2,3})?$")


class DataObligationService:
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

    def _require_obligation(self, obligation_id: uuid.UUID) -> Obligation:
        row = self.db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
        return row

    def _require_suggestion_in_org(self, org_id: uuid.UUID, suggestion_id: uuid.UUID) -> DataObligationSuggestion:
        row = self.db.execute(
            select(DataObligationSuggestion).where(
                DataObligationSuggestion.organization_id == org_id,
                DataObligationSuggestion.id == suggestion_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data obligation suggestion not found")
        return row

    def link_asset_to_obligation(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID,
        obligation_id: uuid.UUID,
        link_type: str,
        linked_by: uuid.UUID,
        justification: str | None = None,
    ) -> DataAssetObligationLink:
        link_type = validate_choice(link_type, ALLOWED_LINK_TYPES, "link_type")
        self._require_asset(org_id, data_asset_id)
        self._require_obligation(obligation_id)

        existing = self.db.execute(
            select(DataAssetObligationLink).where(
                DataAssetObligationLink.organization_id == org_id,
                DataAssetObligationLink.data_asset_id == data_asset_id,
                DataAssetObligationLink.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset already linked to obligation")

        row = DataAssetObligationLink(
            organization_id=org_id,
            data_asset_id=data_asset_id,
            obligation_id=obligation_id,
            link_type=link_type,
            justification=justification,
            linked_by=linked_by,
            linked_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_obligation.linked",
            entity_type="data_asset_obligation_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=linked_by,
            after_json={
                "data_asset_id": str(data_asset_id),
                "obligation_id": str(obligation_id),
                "link_type": link_type,
            },
            metadata_json={"source": "api"},
        )
        return row

    def unlink_asset_from_obligation(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, obligation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(DataAssetObligationLink).where(
                DataAssetObligationLink.organization_id == org_id,
                DataAssetObligationLink.data_asset_id == data_asset_id,
                DataAssetObligationLink.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        link_id = row.id
        self.db.delete(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_obligation.unlinked",
            entity_type="data_asset_obligation_link",
            entity_id=link_id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"data_asset_id": str(data_asset_id), "obligation_id": str(obligation_id)},
            metadata_json={"source": "api"},
        )

    def get_asset_obligations(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, link_type: str | None = None) -> list[dict]:
        self._require_asset(org_id, data_asset_id)
        stmt = (
            select(DataAssetObligationLink, Obligation, Framework)
            .join(Obligation, Obligation.id == DataAssetObligationLink.obligation_id)
            .join(Framework, Framework.id == Obligation.framework_id)
            .where(
                DataAssetObligationLink.organization_id == org_id,
                DataAssetObligationLink.data_asset_id == data_asset_id,
            )
            .order_by(Framework.name.asc(), Obligation.reference_code.asc())
        )
        if link_type is not None:
            link_type = validate_choice(link_type, ALLOWED_LINK_TYPES, "link_type")
            stmt = stmt.where(DataAssetObligationLink.link_type == link_type)

        rows = self.db.execute(stmt).all()
        return [
            {
                "data_asset_id": str(link.data_asset_id),
                "obligation_id": str(obligation.id),
                "obligation_ref": obligation.reference_code,
                "obligation_title": obligation.title,
                "framework_code": framework.code,
                "framework_name": framework.name,
                "link_type": link.link_type,
                "justification": link.justification,
                "linked_at": link.linked_at,
            }
            for link, obligation, framework in rows
        ]

    def get_obligation_assets(self, org_id: uuid.UUID, obligation_id: uuid.UUID) -> list[dict]:
        self._require_obligation(obligation_id)
        rows = self.db.execute(
            select(DataAssetObligationLink, DataAsset)
            .join(DataAsset, DataAsset.id == DataAssetObligationLink.data_asset_id)
            .where(
                DataAssetObligationLink.organization_id == org_id,
                DataAssetObligationLink.obligation_id == obligation_id,
                DataAsset.deleted_at.is_(None),
            )
            .order_by(DataAsset.name.asc())
        ).all()
        return [
            {
                "asset_id": str(asset.id),
                "asset_name": asset.name,
                "asset_type": asset.asset_type,
                "classification_type": asset.classification_type,
                "sensitivity_tier": asset.sensitivity_tier,
                "link_type": link.link_type,
                "justification": link.justification,
            }
            for link, asset in rows
        ]

    def get_coverage_summary(self, org_id: uuid.UUID) -> dict:
        total_assets = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        linked_assets = int(
            self.db.execute(
                select(func.count(func.distinct(DataAssetObligationLink.data_asset_id))).where(
                    DataAssetObligationLink.organization_id == org_id,
                )
            ).scalar_one()
            or 0
        )

        by_link_type_rows = self.db.execute(
            select(DataAssetObligationLink.link_type, func.count(DataAssetObligationLink.id))
            .where(DataAssetObligationLink.organization_id == org_id)
            .group_by(DataAssetObligationLink.link_type)
        ).all()
        by_link_type = {str(link_type): int(count) for link_type, count in by_link_type_rows}

        by_framework_rows = self.db.execute(
            select(
                Framework.name,
                func.count(func.distinct(DataAssetObligationLink.data_asset_id)).label("asset_count"),
                func.count(func.distinct(DataAssetObligationLink.obligation_id)).label("obligation_count"),
            )
            .select_from(DataAssetObligationLink)
            .join(Obligation, Obligation.id == DataAssetObligationLink.obligation_id)
            .join(Framework, Framework.id == Obligation.framework_id)
            .where(DataAssetObligationLink.organization_id == org_id)
            .group_by(Framework.name)
        ).all()
        by_framework = {
            str(name): {
                "assets": int(asset_count or 0),
                "obligations": int(obligation_count or 0),
            }
            for name, asset_count, obligation_count in by_framework_rows
        }

        coverage_pct = (linked_assets / total_assets * 100.0) if total_assets > 0 else 0.0
        return {
            "total_assets": total_assets,
            "linked_assets": linked_assets,
            "unlinked_assets": max(total_assets - linked_assets, 0),
            "coverage_pct": round(coverage_pct, 2),
            "by_link_type": by_link_type,
            "by_framework": by_framework,
        }

    def _org_location_footprint(self, org_id: uuid.UUID) -> set[str]:
        """All distinct geographic_locations recorded across the org's active
        data assets -- used as a proxy for the org's actual data-residency
        footprint, so obligation suggestions can be filtered to frameworks
        whose jurisdiction is actually relevant (e.g. don't suggest CCPA for
        an org with no data anywhere in the US)."""
        rows = self.db.execute(
            select(DataAsset.geographic_locations).where(
                DataAsset.organization_id == org_id,
                DataAsset.deleted_at.is_(None),
            )
        ).scalars().all()
        footprint: set[str] = set()
        for locations in rows:
            for loc in locations or []:
                if loc:
                    footprint.add(str(loc).upper())
        return footprint

    @staticmethod
    def _framework_applies_to_footprint(framework: Framework, footprint: set[str]) -> bool:
        """True if `framework`'s jurisdiction is relevant to the org's data
        footprint. Frameworks with a "global"/blank jurisdiction, or a
        free-text (non-code) jurisdiction label we can't reliably parse into
        a region code, are always considered relevant. Code-shaped
        jurisdictions (e.g. "US", "US-CA", "EU", "IN") are only relevant if
        they hierarchically overlap a location in the org's footprint.
        """
        jurisdiction = (framework.jurisdiction or "").strip()
        if not jurisdiction or jurisdiction.lower() in GLOBAL_JURISDICTIONS:
            return True
        if not _JURISDICTION_CODE_RE.match(jurisdiction.upper()):
            # Free-text jurisdiction (e.g. "European Union") -- can't parse a
            # region code out of it, so don't filter it out.
            return True
        if not footprint:
            # No recorded data-location footprint at all: be conservative and
            # only surface jurisdiction-agnostic frameworks.
            return False

        code = jurisdiction.upper()
        if code == "EU":
            return any(loc.split("-", 1)[0] in EEA_COUNTRIES for loc in footprint)
        return any(region_overlaps(code, loc) for loc in footprint)

    def suggest_obligations(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> list[dict]:
        asset = self._require_asset(org_id, data_asset_id)
        classification = asset.classification_type

        framework_patterns: list[str]
        reason: str
        if classification == "personal_data":
            framework_patterns = ["GDPR", "DPDP", "CCPA"]
            reason = "Asset classified as personal_data"
        elif classification == "sensitive_personal_data":
            # Sensitive personal data is a strict superset of personal_data's
            # risk profile (special-category / high-harm data), so it must
            # get at least the same obligation coverage as personal_data --
            # never fewer suggestions.
            framework_patterns = ["GDPR", "DPDP", "CCPA"]
            reason = "Asset classified as sensitive_personal_data"
        elif classification == "health_data":
            framework_patterns = ["HIPAA"]
            reason = "Asset classified as health_data"
        elif classification == "financial_data":
            framework_patterns = ["PCI", "PCI DSS"]
            reason = "Asset classified as financial_data"
        else:
            return []

        conditions = []
        for p in framework_patterns:
            conditions.extend(
                [
                    Framework.code.ilike(f"%{p}%"),
                    Framework.name.ilike(f"%{p}%"),
                    Framework.jurisdiction.ilike(f"%{p}%"),
                ]
            )

        stmt = select(Obligation, Framework).join(Framework, Framework.id == Obligation.framework_id)
        if conditions:
            stmt = stmt.where(or_(*conditions))
        rows = self.db.execute(stmt).all()

        footprint = self._org_location_footprint(org_id)

        suggestions: list[dict] = []
        for obligation, framework in rows:
            match = False
            for p in framework_patterns:
                if p.lower() in (framework.code or "").lower() or p.lower() in (framework.name or "").lower() or p.lower() in (framework.jurisdiction or "").lower():
                    match = True
                    break
            if not match:
                continue
            if not self._framework_applies_to_footprint(framework, footprint):
                continue
            suggestions.append(
                {
                    "obligation_id": str(obligation.id),
                    "obligation_ref": obligation.reference_code,
                    "obligation_title": obligation.title,
                    "framework_code": framework.code,
                    "framework_name": framework.name,
                    "reason": reason,
                }
            )

        seen: set[str] = set()
        deduped: list[dict] = []
        for item in suggestions:
            key = item["obligation_id"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def generate_suggestions(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> list[DataObligationSuggestion]:
        self._require_asset(org_id, data_asset_id)
        computed = self.suggest_obligations(org_id, data_asset_id)
        now = self.utcnow()
        created_or_existing: list[DataObligationSuggestion] = []

        for item in computed:
            obligation_id = uuid.UUID(item["obligation_id"])
            framework = self.db.execute(
                select(Framework)
                .join(Obligation, Obligation.framework_id == Framework.id)
                .where(Obligation.id == obligation_id)
            ).scalar_one()

            existing = self.db.execute(
                select(DataObligationSuggestion).where(
                    DataObligationSuggestion.organization_id == org_id,
                    DataObligationSuggestion.data_asset_id == data_asset_id,
                    DataObligationSuggestion.obligation_id == obligation_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing.status != "dismissed":
                    created_or_existing.append(existing)
                    continue
                existing.status = "pending"
                existing.link_reason = item["reason"]
                existing.framework_id = framework.id
                existing.dismissed_by = None
                existing.updated_at = now
                self.db.flush()
                created_or_existing.append(existing)
                continue

            row = DataObligationSuggestion(
                organization_id=org_id,
                data_asset_id=data_asset_id,
                framework_id=framework.id,
                obligation_id=obligation_id,
                link_reason=item["reason"],
                status="pending",
                applied_by=None,
                dismissed_by=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
            created_or_existing.append(row)

        return created_or_existing

    def apply_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID, applied_by: uuid.UUID) -> DataObligationSuggestion:
        row = self._require_suggestion_in_org(org_id, suggestion_id)
        if row.status == "dismissed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dismissed suggestion cannot be applied")
        if row.status != "applied":
            self.link_asset_to_obligation(
                org_id=org_id,
                data_asset_id=row.data_asset_id,
                obligation_id=row.obligation_id,
                link_type="subject_to",
                linked_by=applied_by,
                justification=row.link_reason,
            )

        row.status = "applied"
        row.applied_by = applied_by
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_obligation.suggestion_applied",
            entity_type="data_obligation_suggestion",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=applied_by,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def dismiss_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID, dismissed_by: uuid.UUID) -> DataObligationSuggestion:
        row = self._require_suggestion_in_org(org_id, suggestion_id)
        row.status = "dismissed"
        row.dismissed_by = dismissed_by
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_obligation.suggestion_dismissed",
            entity_type="data_obligation_suggestion",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=dismissed_by,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def list_suggestions(
        self,
        org_id: uuid.UUID,
        *,
        data_asset_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[DataObligationSuggestion]:
        stmt = select(DataObligationSuggestion).where(DataObligationSuggestion.organization_id == org_id)
        if data_asset_id is not None:
            stmt = stmt.where(DataObligationSuggestion.data_asset_id == data_asset_id)
        if status is not None:
            stmt = stmt.where(DataObligationSuggestion.status == status)
        offset = max(page - 1, 0) * page_size
        stmt = stmt.order_by(DataObligationSuggestion.created_at.desc()).offset(offset).limit(page_size)
        return self.db.execute(stmt).scalars().all()

    def suggestion_payload(self, row: DataObligationSuggestion) -> dict:
        obligation, framework = self.db.execute(
            select(Obligation, Framework)
            .join(Framework, Framework.id == Obligation.framework_id)
            .where(Obligation.id == row.obligation_id)
        ).one()
        return {
            "id": str(row.id),
            "organization_id": str(row.organization_id),
            "data_asset_id": str(row.data_asset_id),
            "framework_id": str(row.framework_id),
            "obligation_id": str(row.obligation_id),
            "obligation_ref": obligation.reference_code,
            "obligation_title": obligation.title,
            "framework_code": framework.code,
            "framework_name": framework.name,
            "link_reason": row.link_reason,
            "status": row.status,
            "applied_by": str(row.applied_by) if row.applied_by else None,
            "dismissed_by": str(row.dismissed_by) if row.dismissed_by else None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
