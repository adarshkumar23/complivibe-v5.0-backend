import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.data_observability.services.classification_service import classify_metadata, classify_sample
from app.models.data_asset import DataAsset
from app.models.organization import Organization
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_ASSET_TYPES = {
    "database",
    "file_store",
    "data_stream",
    "api",
    "data_lake",
    "table",
    "schema",
    "bucket",
    "other",
}
ALLOWED_SENSITIVITY_TIERS = {"public", "internal", "confidential", "restricted", "secret"}
ALLOWED_CLASSIFICATION_TYPES = {
    "personal_data",
    "sensitive_personal_data",
    "financial_data",
    "health_data",
    "intellectual_property",
    "operational_data",
    "public_data",
    "unclassified",
}
ALLOWED_CLASSIFICATION_SOURCES = {"metadata_rules", "presidio_sample", "manual", "fides", "openmetadata", "mlflow"}
ALLOWED_STATUS = {"active", "archived", "under_review", "decommissioned"}
ALLOWED_HIPAA_SAFEGUARDS = {"administrative", "physical", "technical", "all"}
DPDP_LOCALIZATION_CLASSIFICATIONS = {"health_data", "financial_data", "sensitive_personal_data"}

try:
    from prometheus_client import Counter

    data_classification_confirmed = Counter(
        "complivibe_data_classification_confirmed_total",
        "Data assets with confirmed classification",
        ["org_id", "classification_type", "sensitivity_tier"],
    )
except Exception:  # pragma: no cover - metrics optional in tests/environments
    data_classification_confirmed = None


class DataAssetService:
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

    @staticmethod
    def _normalize_json_list(value: list | None) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Expected list value")

    def _validate_payload(self, payload: dict, *, is_update: bool = False) -> None:
        if payload.get("asset_type") is not None and payload["asset_type"] not in ALLOWED_ASSET_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid asset_type")
        if payload.get("sensitivity_tier") is not None and payload["sensitivity_tier"] not in ALLOWED_SENSITIVITY_TIERS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid sensitivity_tier")
        if payload.get("classification_type") is not None and payload["classification_type"] not in ALLOWED_CLASSIFICATION_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid classification_type")
        if payload.get("classification_source") is not None and payload["classification_source"] not in ALLOWED_CLASSIFICATION_SOURCES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid classification_source")
        if payload.get("status") is not None and payload["status"] not in ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if payload.get("hipaa_safeguard_required") is not None and payload["hipaa_safeguard_required"] not in ALLOWED_HIPAA_SAFEGUARDS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid hipaa_safeguard_required")
        confidence = payload.get("classification_confidence")
        if confidence is not None and not (Decimal("0") <= Decimal(confidence) <= Decimal("1")):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="classification_confidence must be between 0 and 1")

        for field in ["geographic_locations", "permitted_regions", "schema_column_names", "tags"]:
            if field in payload and payload[field] is not None and not isinstance(payload[field], list):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field} must be a list")

        if not is_update:
            for required in ["name", "asset_type", "owner_id"]:
                if not payload.get(required):
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{required} is required")

    def _run_tier1_classification(self, row: DataAsset) -> None:
        result = classify_metadata(row.name, row.description, row.schema_column_names)
        row.classification_type = result.get("classification_type")
        row.sensitivity_tier = result.get("sensitivity_tier")
        row.classification_confidence = result.get("confidence")
        row.classification_source = "metadata_rules"
        row.classification_confirmed = False

    def suggest_residency_policy(self, org_id: uuid.UUID, classification_type: str | None, permitted_regions: list | None) -> list:
        org = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        regions = list(permitted_regions or [])
        if (
            org is not None
            and bool(org.is_significant_data_fiduciary)
            and classification_type in DPDP_LOCALIZATION_CLASSIFICATIONS
            and "IN" not in regions
        ):
            regions.append("IN")
        return regions

    def create_asset(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DataAsset:
        payload = data.model_dump()
        self._validate_payload(payload)

        now = self.utcnow()
        row = DataAsset(
            organization_id=org_id,
            name=payload["name"],
            asset_type=payload["asset_type"],
            description=payload.get("description"),
            owner_id=payload["owner_id"],
            custodian_id=payload.get("custodian_id"),
            sensitivity_tier=payload.get("sensitivity_tier"),
            classification_type=payload.get("classification_type"),
            classification_confidence=payload.get("classification_confidence"),
            classification_source=payload.get("classification_source"),
            classification_confirmed=bool(payload.get("classification_confirmed", False)),
            geographic_locations=self._normalize_json_list(payload.get("geographic_locations")),
            permitted_regions=self._normalize_json_list(payload.get("permitted_regions")),
            schema_column_names=payload.get("schema_column_names"),
            retention_policy_days=payload.get("retention_policy_days"),
            retention_review_date=payload.get("retention_review_date"),
            data_volume_estimate=payload.get("data_volume_estimate"),
            source_system=payload.get("source_system"),
            tags=self._normalize_json_list(payload.get("tags")),
            is_phi=bool(payload.get("is_phi", False)),
            hipaa_safeguard_required=payload.get("hipaa_safeguard_required"),
            status=payload.get("status") or "active",
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        try:
            self._run_tier1_classification(row)
        except Exception:
            # Classification is best-effort and must not block asset creation.
            pass
        row.permitted_regions = self.suggest_residency_policy(org_id, row.classification_type, row.permitted_regions)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="data_asset.created",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "name": row.name,
                "asset_type": row.asset_type,
                "classification_type": row.classification_type,
                "sensitivity_tier": row.sensitivity_tier,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> DataAsset:
        return self._require_asset(org_id, asset_id)

    def list_assets(
        self,
        org_id: uuid.UUID,
        asset_type: str | None = None,
        sensitivity_tier: str | None = None,
        classification_type: str | None = None,
        classification_confirmed: bool | None = None,
        status_filter: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[DataAsset]:
        stmt = select(DataAsset).where(
            DataAsset.organization_id == org_id,
            DataAsset.deleted_at.is_(None),
        )
        if asset_type is not None:
            asset_type = validate_choice(asset_type, ALLOWED_ASSET_TYPES, "asset_type")
            stmt = stmt.where(DataAsset.asset_type == asset_type)
        if sensitivity_tier is not None:
            sensitivity_tier = validate_choice(sensitivity_tier, ALLOWED_SENSITIVITY_TIERS, "sensitivity_tier")
            stmt = stmt.where(DataAsset.sensitivity_tier == sensitivity_tier)
        if classification_type is not None:
            classification_type = validate_choice(classification_type, ALLOWED_CLASSIFICATION_TYPES, "classification_type")
            stmt = stmt.where(DataAsset.classification_type == classification_type)
        if classification_confirmed is not None:
            stmt = stmt.where(DataAsset.classification_confirmed.is_(classification_confirmed))
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_STATUS, "status")
            stmt = stmt.where(DataAsset.status == status_filter)
        return self.db.execute(
            stmt.order_by(DataAsset.created_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def update_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID, data, user_id: uuid.UUID) -> DataAsset:
        row = self._require_asset(org_id, asset_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload, is_update=True)

        should_reclassify = any(field in payload for field in ["name", "description", "schema_column_names"])

        for key, value in payload.items():
            if key in {"geographic_locations", "permitted_regions", "tags"} and value is None:
                value = []
            setattr(row, key, value)

        if should_reclassify:
            try:
                self._run_tier1_classification(row)
            except Exception:
                pass
        row.permitted_regions = self.suggest_residency_policy(org_id, row.classification_type, row.permitted_regions)

        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_asset.updated",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "name": row.name,
                "classification_type": row.classification_type,
                "sensitivity_tier": row.sensitivity_tier,
                "classification_confirmed": row.classification_confirmed,
            },
            metadata_json={"source": "api"},
        )
        return row

    def confirm_classification(
        self,
        org_id: uuid.UUID,
        asset_id: uuid.UUID,
        classification_type: str,
        sensitivity_tier: str,
        user_id: uuid.UUID,
    ) -> DataAsset:
        classification_type = validate_choice(classification_type, ALLOWED_CLASSIFICATION_TYPES, "classification_type")
        sensitivity_tier = validate_choice(sensitivity_tier, ALLOWED_SENSITIVITY_TIERS, "sensitivity_tier")
        row = self._require_asset(org_id, asset_id)
        overriding = row.classification_type != classification_type or row.sensitivity_tier != sensitivity_tier

        row.classification_type = classification_type
        row.sensitivity_tier = sensitivity_tier
        row.classification_confirmed = True
        if overriding:
            row.classification_source = "manual"
        elif row.classification_source is None:
            row.classification_source = "manual"
        row.permitted_regions = self.suggest_residency_policy(org_id, row.classification_type, row.permitted_regions)
        row.updated_at = self.utcnow()
        self.db.flush()

        if sensitivity_tier is not None and data_classification_confirmed is not None:
            try:
                data_classification_confirmed.labels(
                    org_id=str(org_id),
                    classification_type=classification_type,
                    sensitivity_tier=sensitivity_tier,
                ).inc()
            except Exception:
                pass

        AuditService(self.db).write_audit_log(
            action="data_asset.classification_confirmed",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "classification_type": row.classification_type,
                "sensitivity_tier": row.sensitivity_tier,
                "classification_source": row.classification_source,
                "classification_confirmed": row.classification_confirmed,
            },
            metadata_json={"source": "api"},
        )
        return row

    def classify_sample(self, org_id: uuid.UUID, asset_id: uuid.UUID, sample_text: str, user_id: uuid.UUID, language: str = "en") -> dict:
        row = self._require_asset(org_id, asset_id)
        result = classify_sample(sample_text=sample_text, language=language)

        AuditService(self.db).write_audit_log(
            action="data_asset.classified_by_sample",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": result.get("status"),
                "suggested_classification": result.get("suggested_classification"),
                "suggested_sensitivity_tier": result.get("suggested_sensitivity_tier"),
            },
            metadata_json={"source": "api", "language": language},
        )
        return result

    def get_summary(self, org_id: uuid.UUID) -> dict:
        base_filters = [
            DataAsset.organization_id == org_id,
            DataAsset.deleted_at.is_(None),
        ]

        total_assets = int(self.db.execute(select(func.count(DataAsset.id)).where(*base_filters)).scalar_one() or 0)

        by_asset_type_rows = self.db.execute(
            select(DataAsset.asset_type, func.count(DataAsset.id)).where(*base_filters).group_by(DataAsset.asset_type)
        ).all()
        by_asset_type = {str(asset_type): int(count) for asset_type, count in by_asset_type_rows}

        by_sensitivity_rows = self.db.execute(
            select(DataAsset.sensitivity_tier, func.count(DataAsset.id))
            .where(*base_filters)
            .group_by(DataAsset.sensitivity_tier)
        ).all()
        by_sensitivity_tier = {str(tier): int(count) for tier, count in by_sensitivity_rows if tier is not None}

        by_classification_rows = self.db.execute(
            select(DataAsset.classification_type, func.count(DataAsset.id))
            .where(*base_filters)
            .group_by(DataAsset.classification_type)
        ).all()
        by_classification_type = {str(class_type): int(count) for class_type, count in by_classification_rows if class_type is not None}

        confirmed_count = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(*base_filters, DataAsset.classification_confirmed.is_(True))
            ).scalar_one()
            or 0
        )
        unconfirmed_count = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(*base_filters, DataAsset.classification_confirmed.is_(False))
            ).scalar_one()
            or 0
        )
        needs_review_count = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    *base_filters,
                    or_(
                        DataAsset.classification_type.is_(None),
                        DataAsset.classification_confidence.is_(None),
                        DataAsset.classification_confidence < Decimal("0.5"),
                    ),
                )
            ).scalar_one()
            or 0
        )

        return {
            "total_assets": total_assets,
            "by_asset_type": by_asset_type,
            "by_sensitivity_tier": by_sensitivity_tier,
            "by_classification_type": by_classification_type,
            "confirmed_count": confirmed_count,
            "unconfirmed_count": unconfirmed_count,
            "needs_review_count": needs_review_count,
        }

    def archive_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID, user_id: uuid.UUID) -> DataAsset:
        row = self._require_asset(org_id, asset_id)
        row.status = "archived"
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_asset.archived",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID, user_id: uuid.UUID) -> DataAsset:
        row = self._require_asset(org_id, asset_id)
        if row.status != "decommissioned":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only decommissioned assets can be deleted")

        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_asset.deleted",
            entity_type="data_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row
