from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.security.parsers.fides_parser import FidesParser
from app.models.data_asset import DataAsset
from app.services.audit_service import AuditService


class FidesImportService:
    def import_manifest(self, org_id: uuid.UUID, payload: dict | list, imported_by: uuid.UUID, db: Session) -> dict:
        parser = FidesParser()
        parsed_assets = parser.parse(payload)

        created = 0
        updated = 0
        skipped = 0

        for asset_data in parsed_assets:
            fides_key = asset_data.get("fides_key") or None
            existing = None
            if fides_key:
                existing = db.execute(
                    select(DataAsset).where(
                        DataAsset.organization_id == org_id,
                        DataAsset.import_source == "fides",
                        DataAsset.import_key == fides_key,
                        DataAsset.deleted_at.is_(None),
                    )
                ).scalar_one_or_none()

            if existing is not None:
                existing.name = asset_data["name"]
                existing.description = asset_data.get("description")
                if not existing.classification_confirmed:
                    existing.classification_type = asset_data.get("classification_type")
                    existing.sensitivity_tier = asset_data.get("sensitivity_tier")
                    existing.classification_source = "fides"
                updated += 1
                db.flush()
                continue

            row = DataAsset(
                organization_id=org_id,
                name=asset_data["name"],
                asset_type="database",
                description=asset_data.get("description"),
                owner_id=imported_by,
                custodian_id=None,
                sensitivity_tier=asset_data.get("sensitivity_tier"),
                classification_type=asset_data.get("classification_type"),
                classification_confidence=None,
                classification_source="fides",
                classification_confirmed=False,
                geographic_locations=[],
                permitted_regions=[],
                schema_column_names=None,
                retention_policy_days=None,
                retention_review_date=None,
                data_volume_estimate=None,
                source_system="fides",
                import_source="fides",
                import_key=fides_key,
                tags=["fides_import"],
                is_phi=False,
                hipaa_safeguard_required=None,
                status="active",
                created_by=imported_by,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
            )
            db.add(row)
            db.flush()
            created += 1

        AuditService(db).write_audit_log(
            action="data.fides_import_completed",
            entity_type="data_assets",
            organization_id=org_id,
            actor_user_id=imported_by,
            metadata_json={
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "total": len(parsed_assets),
            },
        )

        return {
            "total_datasets": len(parsed_assets),
            "assets_created": created,
            "assets_updated": updated,
            "assets_skipped": skipped,
        }

    def get_import_status(self, org_id: uuid.UUID, db: Session) -> dict:
        count = db.execute(
            select(func.count(DataAsset.id)).where(
                DataAsset.organization_id == org_id,
                DataAsset.import_source == "fides",
                DataAsset.deleted_at.is_(None),
            )
        ).scalar_one()
        return {"import_source": "fides", "asset_count": int(count)}
