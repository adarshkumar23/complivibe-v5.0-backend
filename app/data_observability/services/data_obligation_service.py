import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.data_asset import DataAsset
from app.models.data_asset_obligation_link import DataAssetObligationLink
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.services.audit_service import AuditService

ALLOWED_LINK_TYPES = {"governed_by", "subject_to", "exempted_from"}


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

    def link_asset_to_obligation(
        self,
        org_id: uuid.UUID,
        data_asset_id: uuid.UUID,
        obligation_id: uuid.UUID,
        link_type: str,
        linked_by: uuid.UUID,
        justification: str | None = None,
    ) -> DataAssetObligationLink:
        if link_type not in ALLOWED_LINK_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid link_type")

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
            if link_type not in ALLOWED_LINK_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid link_type filter")
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

    def suggest_obligations(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> list[dict]:
        asset = self._require_asset(org_id, data_asset_id)
        classification = asset.classification_type

        framework_patterns: list[str]
        reason: str
        if classification == "personal_data":
            framework_patterns = ["GDPR", "DPDP", "CCPA"]
            reason = "Asset classified as personal_data"
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

        suggestions: list[dict] = []
        for obligation, framework in rows:
            match = False
            for p in framework_patterns:
                if p.lower() in (framework.code or "").lower() or p.lower() in (framework.name or "").lower() or p.lower() in (framework.jurisdiction or "").lower():
                    match = True
                    break
            if not match:
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
