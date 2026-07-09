import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.subprocessor_service import SubprocessorService
from app.core.geo import region_covers
from app.data_observability.services.incident_detection_service import DataIncidentService
from app.models.data_asset import DataAsset
from app.models.data_incident import DataIncident
from app.models.data_residency_policy import DataResidencyPolicy
from app.models.data_residency_violation import DataResidencyViolation
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

EEA_COUNTRIES = set(SubprocessorService.EEA_COUNTRIES)
ALLOWED_VIOLATION_STATUS = {"open", "acknowledged", "resolved", "waived"}


class ResidencyService:
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

    def _require_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> DataResidencyPolicy:
        row = self.db.execute(
            select(DataResidencyPolicy).where(
                DataResidencyPolicy.organization_id == org_id,
                DataResidencyPolicy.id == policy_id,
                DataResidencyPolicy.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residency policy not found")
        return row

    def _require_violation(self, org_id: uuid.UUID, violation_id: uuid.UUID) -> DataResidencyViolation:
        row = self.db.execute(
            select(DataResidencyViolation).where(
                DataResidencyViolation.organization_id == org_id,
                DataResidencyViolation.id == violation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residency violation not found")
        return row

    def create_policy(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DataResidencyPolicy:
        payload = data.model_dump()
        now = self.utcnow()
        row = DataResidencyPolicy(
            organization_id=org_id,
            name=payload["name"],
            description=payload.get("description"),
            required_countries=payload.get("required_countries") or [],
            prohibited_countries=payload.get("prohibited_countries") or [],
            require_eea_only=bool(payload.get("require_eea_only", False)),
            require_domestic_only=bool(payload.get("require_domestic_only", False)),
            legal_basis=payload.get("legal_basis"),
            applies_to_classification_types=payload.get("applies_to_classification_types") or [],
            applies_to_sensitivity_tiers=payload.get("applies_to_sensitivity_tiers") or [],
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="residency.policy_created",
            entity_type="data_residency_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": row.name, "require_eea_only": row.require_eea_only},
            metadata_json={"source": "api"},
        )
        return row

    def get_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> DataResidencyPolicy:
        return self._require_policy(org_id, policy_id)

    def list_policies(self, org_id: uuid.UUID, is_active: bool | None = None) -> list[DataResidencyPolicy]:
        stmt = select(DataResidencyPolicy).where(
            DataResidencyPolicy.organization_id == org_id,
            DataResidencyPolicy.deleted_at.is_(None),
        )
        if is_active is not None:
            stmt = stmt.where(DataResidencyPolicy.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(DataResidencyPolicy.created_at.desc())).scalars().all()

    def update_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, data) -> DataResidencyPolicy:
        row = self._require_policy(org_id, policy_id)
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="residency.policy_updated",
            entity_type="data_residency_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"name": row.name, "require_eea_only": row.require_eea_only, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> DataResidencyPolicy:
        row = self._require_policy(org_id, policy_id)
        row.is_active = False
        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="residency.policy_deactivated",
            entity_type="data_residency_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    # Hierarchical region matching lives in app.core.geo.region_covers (shared
    # across residency, subprocessor, access-monitoring, and obligation
    # jurisdiction logic) so a scope like "IN" correctly covers a more
    # specific location like "IN-Mumbai" instead of requiring exact equality.
    region_covers = staticmethod(region_covers)

    def check_residency_compliance(self, asset: DataAsset, policy: DataResidencyPolicy) -> dict:
        asset_locations = set(asset.geographic_locations or [])
        violations: list[dict] = []

        prohibited = set(policy.prohibited_countries or [])
        in_prohibited = sorted(
            {loc for loc in asset_locations if any(self.region_covers(country, loc) for country in prohibited)}
        )
        if in_prohibited:
            violations.append({"type": "data_in_prohibited_country", "countries": in_prohibited})

        required = set(policy.required_countries or [])
        if required:
            missing = sorted(
                {country for country in required if not any(self.region_covers(country, loc) for loc in asset_locations)}
            )
            if missing:
                violations.append({"type": "data_outside_required_country", "countries": missing})

        if policy.require_eea_only:
            outside_eea = sorted(
                {loc for loc in asset_locations if not any(self.region_covers(country, loc) for country in EEA_COUNTRIES)}
            )
            if outside_eea:
                violations.append({"type": "data_outside_eea", "countries": outside_eea})

        if policy.require_domestic_only and len(asset_locations) > 1:
            # No explicit home-country field on organization; treat multiple locations as outside-domestic.
            violations.append({"type": "data_outside_domestic", "countries": sorted(asset_locations)})

        return {"compliant": len(violations) == 0, "violations": violations}

    def _policy_applies(self, asset: DataAsset, policy: DataResidencyPolicy) -> bool:
        class_filters = set(policy.applies_to_classification_types or [])
        tier_filters = set(policy.applies_to_sensitivity_tiers or [])
        class_match = (not class_filters) or (asset.classification_type in class_filters)
        tier_match = (not tier_filters) or (asset.sensitivity_tier in tier_filters)
        return class_match and tier_match

    def _existing_open_violation(self, org_id: uuid.UUID, asset_id: uuid.UUID, policy_id: uuid.UUID, violation_type: str) -> DataResidencyViolation | None:
        return self.db.execute(
            select(DataResidencyViolation).where(
                DataResidencyViolation.organization_id == org_id,
                DataResidencyViolation.data_asset_id == asset_id,
                DataResidencyViolation.policy_id == policy_id,
                DataResidencyViolation.violation_type == violation_type,
                DataResidencyViolation.status.in_(["open", "acknowledged"]),
            )
        ).scalar_one_or_none()

    def check_asset_residency(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> dict:
        asset = self._require_asset(org_id, data_asset_id)
        policies = self.db.execute(
            select(DataResidencyPolicy).where(
                DataResidencyPolicy.organization_id == org_id,
                DataResidencyPolicy.is_active.is_(True),
                DataResidencyPolicy.deleted_at.is_(None),
            )
        ).scalars().all()

        results: list[dict] = []
        for policy in policies:
            if not self._policy_applies(asset, policy):
                continue
            evaluated = self.check_residency_compliance(asset, policy)
            results.append(
                {
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "compliant": evaluated["compliant"],
                    "violations": evaluated["violations"],
                }
            )
        return {
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "compliant": all(item["compliant"] for item in results) if results else True,
            "policy_results": results,
        }

    def run_residency_sweep(self, org_id: uuid.UUID | None = None) -> dict:
        assets_stmt = select(DataAsset).where(
            DataAsset.deleted_at.is_(None),
            DataAsset.status == "active",
        )
        if org_id is not None:
            assets_stmt = assets_stmt.where(DataAsset.organization_id == org_id)
        assets = self.db.execute(assets_stmt).scalars().all()

        assets_checked = 0
        violations_found = 0
        incidents_created = 0

        for asset in assets:
            if not (asset.geographic_locations or []):
                continue
            assets_checked += 1

            policies = self.db.execute(
                select(DataResidencyPolicy).where(
                    DataResidencyPolicy.organization_id == asset.organization_id,
                    DataResidencyPolicy.is_active.is_(True),
                    DataResidencyPolicy.deleted_at.is_(None),
                )
            ).scalars().all()

            for policy in policies:
                if not self._policy_applies(asset, policy):
                    continue
                evaluated = self.check_residency_compliance(asset, policy)
                if evaluated["compliant"]:
                    continue

                for violation in evaluated["violations"]:
                    violation_type = str(violation["type"])
                    existing = self._existing_open_violation(asset.organization_id, asset.id, policy.id, violation_type)
                    if existing is not None:
                        continue

                    now = self.utcnow()
                    row = DataResidencyViolation(
                        organization_id=asset.organization_id,
                        data_asset_id=asset.id,
                        policy_id=policy.id,
                        violation_type=violation_type,
                        detected_at=now,
                        violating_locations=violation.get("countries") or [],
                        status="open",
                        acknowledged_by=None,
                        resolved_by=None,
                        resolved_at=None,
                        linked_incident_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                    self.db.add(row)
                    self.db.flush()
                    violations_found += 1

                    severity = "high"
                    if violation_type == "data_in_prohibited_country":
                        severity = "critical"
                    elif violation_type == "data_outside_eea":
                        severity = "high"

                    incident = DataIncidentService(self.db).create_incident(
                        org_id=asset.organization_id,
                        data_asset_id=asset.id,
                        detector_type="residency_violation",
                        title=f"Residency violation: {asset.name}",
                        description=(
                            f"Residency policy '{policy.name}' violated for asset '{asset.name}': "
                            f"{violation_type} {violation.get('countries') or []}"
                        ),
                        severity=severity,
                        rule_type=violation_type,
                        detector_ref_id=row.id,
                        evidence={
                            "policy_id": str(policy.id),
                            "violation_type": violation_type,
                            "violating_locations": violation.get("countries") or [],
                        },
                        detected_by="scheduler",
                        actor_user_id=None,
                    )
                    if incident is not None:
                        incidents_created += 1
                        row.linked_incident_id = incident.id
                        row.updated_at = self.utcnow()
                        self.db.flush()

                    AuditService(self.db).write_audit_log(
                        action="residency.violation_detected",
                        entity_type="data_residency_violation",
                        entity_id=row.id,
                        organization_id=asset.organization_id,
                        actor_user_id=None,
                        after_json={"asset_id": str(asset.id), "policy_id": str(policy.id), "violation_type": violation_type},
                        metadata_json={"source": "sweep"},
                    )

        return {
            "assets_checked": assets_checked,
            "violations_found": violations_found,
            "incidents_created": incidents_created,
        }

    def list_violations(self, org_id: uuid.UUID, status_filter: str | None = None, data_asset_id: uuid.UUID | None = None) -> list[DataResidencyViolation]:
        stmt = select(DataResidencyViolation).where(DataResidencyViolation.organization_id == org_id)
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_VIOLATION_STATUS, "status")
            stmt = stmt.where(DataResidencyViolation.status == status_filter)
        if data_asset_id is not None:
            stmt = stmt.where(DataResidencyViolation.data_asset_id == data_asset_id)
        return self.db.execute(stmt.order_by(DataResidencyViolation.detected_at.desc())).scalars().all()

    def acknowledge_violation(self, org_id: uuid.UUID, violation_id: uuid.UUID, user_id: uuid.UUID) -> DataResidencyViolation:
        row = self._require_violation(org_id, violation_id)
        row.status = "acknowledged"
        row.acknowledged_by = user_id
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="residency.violation_acknowledged",
            entity_type="data_residency_violation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def resolve_violation(self, org_id: uuid.UUID, violation_id: uuid.UUID, user_id: uuid.UUID) -> DataResidencyViolation:
        row = self._require_violation(org_id, violation_id)
        row.status = "resolved"
        row.resolved_by = user_id
        row.resolved_at = self.utcnow()
        row.updated_at = row.resolved_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="residency.violation_resolved",
            entity_type="data_residency_violation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def waive_violation(self, org_id: uuid.UUID, violation_id: uuid.UUID, user_id: uuid.UUID) -> DataResidencyViolation:
        row = self._require_violation(org_id, violation_id)
        row.status = "waived"
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def get_residency_summary(self, org_id: uuid.UUID) -> dict:
        total_assets_checked = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                    DataAsset.status == "active",
                )
            ).scalar_one()
            or 0
        )

        violation_count = int(
            self.db.execute(select(func.count(DataResidencyViolation.id)).where(DataResidencyViolation.organization_id == org_id)).scalar_one()
            or 0
        )
        open_violations = int(
            self.db.execute(
                select(func.count(DataResidencyViolation.id)).where(
                    DataResidencyViolation.organization_id == org_id,
                    DataResidencyViolation.status.in_(["open", "acknowledged"]),
                )
            ).scalar_one()
            or 0
        )

        by_type_rows = self.db.execute(
            select(DataResidencyViolation.violation_type, func.count(DataResidencyViolation.id))
            .where(DataResidencyViolation.organization_id == org_id)
            .group_by(DataResidencyViolation.violation_type)
        ).all()
        by_violation_type = {str(v_type): int(count) for v_type, count in by_type_rows}

        asset_rows = self.db.execute(
            select(DataResidencyViolation.data_asset_id, DataAsset.name, DataResidencyViolation.violation_type)
            .join(DataAsset, DataAsset.id == DataResidencyViolation.data_asset_id)
            .where(
                DataResidencyViolation.organization_id == org_id,
                DataResidencyViolation.status.in_(["open", "acknowledged"]),
            )
        ).all()
        asset_map: dict[str, dict] = {}
        for asset_id, asset_name, v_type in asset_rows:
            key = str(asset_id)
            if key not in asset_map:
                asset_map[key] = {"asset_id": key, "asset_name": asset_name, "violation_types": set()}
            asset_map[key]["violation_types"].add(str(v_type))
        assets_with_open_violations = [
            {
                "asset_id": value["asset_id"],
                "asset_name": value["asset_name"],
                "violation_types": sorted(value["violation_types"]),
            }
            for value in asset_map.values()
        ][:10]

        eea_compliant_assets = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                    DataAsset.status == "active",
                    ~DataAsset.id.in_(
                        select(DataResidencyViolation.data_asset_id).where(
                            DataResidencyViolation.organization_id == org_id,
                            DataResidencyViolation.violation_type == "data_outside_eea",
                            DataResidencyViolation.status.in_(["open", "acknowledged"]),
                        )
                    ),
                )
            ).scalar_one()
            or 0
        )
        eea_compliant_pct = (eea_compliant_assets / total_assets_checked * 100.0) if total_assets_checked > 0 else 100.0

        # Same distinct-asset methodology as eea_compliant_assets above, but across all
        # violation types rather than just data_outside_eea. total_assets_checked - open_violations
        # is wrong whenever a single asset carries more than one open violation (double-subtracts it).
        compliant_assets = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                    DataAsset.status == "active",
                    ~DataAsset.id.in_(
                        select(DataResidencyViolation.data_asset_id).where(
                            DataResidencyViolation.organization_id == org_id,
                            DataResidencyViolation.status.in_(["open", "acknowledged"]),
                        )
                    ),
                )
            ).scalar_one()
            or 0
        )

        return {
            "total_assets_checked": total_assets_checked,
            "compliant_count": compliant_assets,
            "violation_count": violation_count,
            "open_violations": open_violations,
            "by_violation_type": by_violation_type,
            "assets_with_open_violations": assets_with_open_violations,
            "eea_compliant_pct": round(eea_compliant_pct, 2),
        }


def run_daily_data_residency_sweep(db: Session) -> dict:
    return ResidencyService(db).run_residency_sweep(org_id=None)
