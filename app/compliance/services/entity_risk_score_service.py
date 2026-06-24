import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.models.entity_risk_score import EntityRiskScore
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.vendor import Vendor
from app.models.vendor_control_link import VendorControlLink
from app.services.audit_service import AuditService


class EntityRiskScoreService:
    ENTITY_TYPES = ("vendor", "asset", "business_unit", "framework")
    SCORE_METHODS = ("equal_weight", "max_score", "weighted_avg")

    @staticmethod
    def _score_band(score: float) -> str:
        if score >= 75.0:
            return "critical"
        if score >= 50.0:
            return "high"
        if score >= 25.0:
            return "medium"
        if score > 0.0:
            return "low"
        return "none"

    @staticmethod
    def _to_float(value: Decimal | float | int | None) -> float:
        if value is None:
            return 0.0
        return float(value)

    @staticmethod
    def _table_exists(db: Session, table_name: str) -> bool:
        bind = db.get_bind()
        if bind is None:
            return False
        return inspect(bind).has_table(table_name)

    @classmethod
    def _resolve_entity_label(
        cls,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
    ) -> tuple[str, str | None]:
        if entity_type == "vendor":
            row = db.execute(
                select(Vendor).where(Vendor.organization_id == org_id, Vendor.id == entity_id)
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
            return row.name, None

        if entity_type == "framework":
            framework = db.execute(select(Framework).where(Framework.id == entity_id)).scalar_one_or_none()
            if framework is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
            in_org = db.execute(
                select(OrganizationFramework).where(
                    OrganizationFramework.organization_id == org_id,
                    OrganizationFramework.framework_id == entity_id,
                )
            ).scalar_one_or_none()
            if in_org is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
            return framework.name or framework.code, None

        if entity_type == "asset":
            if not cls._table_exists(db, "assets"):
                return str(entity_id), "Asset model not yet implemented. Entity label uses raw UUID."

            row = db.execute(
                text(
                    """
                    SELECT name
                    FROM assets
                    WHERE id = :entity_id AND organization_id = :org_id
                    LIMIT 1
                    """
                ),
                {"entity_id": str(entity_id), "org_id": str(org_id)},
            ).first()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
            return str(row[0]), None

        if entity_type == "business_unit":
            return str(entity_id), "Business unit model not yet implemented. Entity label uses raw UUID."

        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid entity_type")

    @classmethod
    def get_linked_risks(
        cls,
        entity_type: str,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
    ) -> list[Risk]:
        risks, _ = cls._get_linked_risks_with_notes(entity_type, entity_id, org_id, db)
        return risks

    @classmethod
    def _get_linked_risks_with_notes(
        cls,
        entity_type: str,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
    ) -> tuple[list[Risk], str | None]:
        if entity_type == "vendor":
            rows = db.execute(
                select(Risk)
                .join(RiskControlLink, RiskControlLink.risk_id == Risk.id)
                .join(VendorControlLink, VendorControlLink.control_id == RiskControlLink.control_id)
                .where(
                    Risk.organization_id == org_id,
                    Risk.status.not_in(["closed", "archived"]),
                    RiskControlLink.organization_id == org_id,
                    RiskControlLink.status == "active",
                    VendorControlLink.organization_id == org_id,
                    VendorControlLink.vendor_id == entity_id,
                    VendorControlLink.status == "active",
                )
                .distinct()
            ).scalars().all()
            return rows, None

        if entity_type == "framework":
            rows = db.execute(
                select(Risk)
                .join(RiskControlLink, RiskControlLink.risk_id == Risk.id)
                .join(ControlObligationMapping, ControlObligationMapping.control_id == RiskControlLink.control_id)
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .where(
                    Risk.organization_id == org_id,
                    Risk.status.not_in(["closed", "archived"]),
                    RiskControlLink.organization_id == org_id,
                    RiskControlLink.status == "active",
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id == entity_id,
                )
                .distinct()
            ).scalars().all()
            return rows, None

        if entity_type == "asset":
            if not cls._table_exists(db, "risk_asset_links"):
                return [], "Asset risk links not yet implemented. Score based on 0 linked risks."

            rows = db.execute(
                text(
                    """
                    SELECT r.*
                    FROM risks r
                    WHERE r.id IN (
                        SELECT DISTINCT ral.risk_id
                        FROM risk_asset_links ral
                        WHERE ral.asset_id = :entity_id
                          AND ral.organization_id = :org_id
                          AND ral.status = 'active'
                    )
                    AND r.organization_id = :org_id
                    AND r.status NOT IN ('closed', 'archived')
                    """
                ),
                {"entity_id": str(entity_id), "org_id": str(org_id)},
            )
            risk_ids = [uuid.UUID(str(row.id)) for row in rows]
            if not risk_ids:
                return [], None
            risks = db.execute(
                select(Risk).where(Risk.organization_id == org_id, Risk.id.in_(risk_ids))
            ).scalars().all()
            return risks, None

        if entity_type == "business_unit":
            if not hasattr(Risk, "business_unit_id"):
                return [], "Business unit links not yet implemented. Score based on 0 linked risks."

            rows = db.execute(
                select(Risk).where(
                    Risk.organization_id == org_id,
                    getattr(Risk, "business_unit_id") == entity_id,
                    Risk.status.not_in(["closed", "archived"]),
                )
            ).scalars().all()
            return rows, None

        return [], None

    @classmethod
    def compute(
        cls,
        entity_type: str,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        score_method: str,
        db: Session,
        computed_by_user_id: uuid.UUID | None = None,
    ) -> EntityRiskScore:
        if entity_type not in cls.ENTITY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid entity_type")
        if score_method not in cls.SCORE_METHODS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid score_method")

        entity_label, label_note = cls._resolve_entity_label(
            entity_type=entity_type,
            entity_id=entity_id,
            org_id=org_id,
            db=db,
        )

        risks, link_note = cls._get_linked_risks_with_notes(entity_type, entity_id, org_id, db)
        notes: list[str] = [n for n in [label_note, link_note] if n]

        component_risks_json: list[dict] = []
        risk_count = len(risks)

        if risk_count == 0:
            composite_score = 0.0
            score_band = "none"
        elif score_method == "max_score":
            max_score = max([int(r.inherent_score) for r in risks if r.inherent_score is not None] or [0])
            composite_score = (float(max_score) / 25.0) * 100.0
            for r in risks:
                component_risks_json.append(
                    {
                        "risk_id": str(r.id),
                        "risk_name": r.title,
                        "score": int(r.inherent_score) if r.inherent_score is not None else None,
                        "weight": None,
                        "weighted_contribution": float(r.inherent_score) if r.inherent_score is not None else None,
                    }
                )
            score_band = cls._score_band(composite_score)
        else:
            effective_method = score_method
            if score_method == "weighted_avg":
                notes.append(
                    "weighted_avg requested; equal weights applied (custom weights not yet configured)"
                )
                effective_method = "equal_weight"

            weight = 1.0 / float(risk_count)
            weighted_sum = 0.0
            for r in risks:
                raw_score = cls._to_float(r.inherent_score)
                contribution = raw_score * weight
                weighted_sum += contribution
                component_risks_json.append(
                    {
                        "risk_id": str(r.id),
                        "risk_name": r.title,
                        "score": int(r.inherent_score) if r.inherent_score is not None else None,
                        "weight": round(weight, 6),
                        "weighted_contribution": round(contribution, 4),
                    }
                )

            composite_score = (weighted_sum / 25.0) * 100.0
            score_band = cls._score_band(composite_score)
            score_method = "weighted_avg" if score_method == "weighted_avg" else effective_method

        composite_score = round(max(0.0, min(100.0, composite_score)), 2)
        score_band = cls._score_band(composite_score)

        row = EntityRiskScore(
            organization_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            composite_score=composite_score,
            score_band=score_band,
            risk_count=risk_count,
            score_method=score_method,
            component_risks_json=component_risks_json,
            computation_notes=" ".join(notes) if notes else None,
            computed_by_user_id=computed_by_user_id,
            computed_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()

        AuditService(db).write_audit_log(
            action="entity_risk_score.computed",
            entity_type="entity_risk_score",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=computed_by_user_id,
            after_json={
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "entity_label": entity_label,
                "composite_score": composite_score,
                "score_band": score_band,
                "risk_count": risk_count,
                "score_method": score_method,
            },
            metadata_json={
                "context_json": {
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                    "entity_label": entity_label,
                    "composite_score": composite_score,
                    "score_band": score_band,
                    "risk_count": risk_count,
                    "score_method": score_method,
                    "triggered_by": "user" if computed_by_user_id else "system",
                }
            },
        )
        return row

    @staticmethod
    def get_latest(entity_type: str, entity_id: uuid.UUID, org_id: uuid.UUID, db: Session) -> EntityRiskScore | None:
        return db.execute(
            select(EntityRiskScore)
            .where(
                EntityRiskScore.organization_id == org_id,
                EntityRiskScore.entity_type == entity_type,
                EntityRiskScore.entity_id == entity_id,
            )
            .order_by(EntityRiskScore.computed_at.desc(), EntityRiskScore.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def get_history(
        entity_type: str,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
        limit: int = 10,
    ) -> list[EntityRiskScore]:
        return db.execute(
            select(EntityRiskScore)
            .where(
                EntityRiskScore.organization_id == org_id,
                EntityRiskScore.entity_type == entity_type,
                EntityRiskScore.entity_id == entity_id,
            )
            .order_by(EntityRiskScore.computed_at.desc(), EntityRiskScore.created_at.desc())
            .limit(limit)
        ).scalars().all()

    @staticmethod
    def get_all_latest(entity_type: str, org_id: uuid.UUID, db: Session) -> list[EntityRiskScore]:
        rows = db.execute(
            select(EntityRiskScore)
            .where(
                EntityRiskScore.organization_id == org_id,
                EntityRiskScore.entity_type == entity_type,
            )
            .order_by(EntityRiskScore.entity_id, EntityRiskScore.computed_at.desc(), EntityRiskScore.created_at.desc())
        ).scalars().all()

        latest: dict[uuid.UUID, EntityRiskScore] = {}
        for row in rows:
            if row.entity_id not in latest:
                latest[row.entity_id] = row
        return list(latest.values())
