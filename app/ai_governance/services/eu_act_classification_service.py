import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_system import AISystem
from app.models.eu_act_annex_mapping import EUActAnnexMapping
from app.models.eu_ai_act_classification import EUAIActClassification
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService


ARTICLE_CATEGORIES = {
    "prohibited",
    "high_risk_annex1",
    "high_risk_annex3",
    "limited_risk",
    "minimal_risk",
}
CONFORMITY_ROUTES = {"self_assessment", "notified_body"}


class EUAIActClassificationService:
    TRANSPARENCY_MAP = {
        "prohibited": ["Deployment prohibited under EU AI Act Article 5"],
        "high_risk_annex1": [
            "Maintain technical documentation",
            "Implement risk management and human oversight",
        ],
        "high_risk_annex3": [
            "Maintain technical documentation",
            "Implement risk management and human oversight",
            "Register system in EU database where required",
        ],
        "limited_risk": [
            "Inform users they are interacting with AI",
            "Provide clear transparency disclosures",
        ],
        "minimal_risk": ["No mandatory transparency obligations"],
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def classify_system(self, org_id: uuid.UUID, system_id: uuid.UUID, data, user_id: uuid.UUID) -> EUAIActClassification:
        self._require_system(org_id, system_id)
        SeedService.ensure_eu_act_annex_mappings(self.db)

        article_category = data.article_category
        if article_category not in ARTICLE_CATEGORIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid article_category")

        annex_reference = data.annex_reference
        if annex_reference is not None:
            annex_row = self.db.execute(
                select(EUActAnnexMapping).where(EUActAnnexMapping.annex_ref == annex_reference)
            ).scalar_one_or_none()
            if annex_row is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown annex_reference")

        route = data.conformity_route
        if article_category in {"prohibited", "high_risk_annex1", "high_risk_annex3"}:
            if route is None:
                route = "self_assessment"
            elif route not in CONFORMITY_ROUTES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid conformity_route")
        else:
            route = None

        existing = self.db.execute(
            select(EUAIActClassification).where(
                EUAIActClassification.organization_id == org_id,
                EUAIActClassification.ai_system_id == system_id,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        registration_required = article_category == "high_risk_annex3"
        transparency_obligations = list(self.TRANSPARENCY_MAP.get(article_category, []))

        if existing is None:
            row = EUAIActClassification(
                organization_id=org_id,
                ai_system_id=system_id,
                article_category=article_category,
                annex_reference=annex_reference,
                conformity_route=route,
                registration_required=registration_required,
                transparency_obligations=transparency_obligations,
                classified_by=user_id,
                classified_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
        else:
            existing.article_category = article_category
            existing.annex_reference = annex_reference
            existing.conformity_route = route
            existing.registration_required = registration_required
            existing.transparency_obligations = transparency_obligations
            existing.classified_by = user_id
            existing.classified_at = now
            existing.updated_at = now
            row = existing

        # Align ai_system risk_tier with category where relevant.
        system = self._require_system(org_id, system_id)
        tier_map = {
            "prohibited": "prohibited",
            "high_risk_annex1": "high",
            "high_risk_annex3": "high",
            "limited_risk": "limited",
            "minimal_risk": "minimal",
        }
        system.risk_tier = tier_map.get(article_category)

        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.classified",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=system_id,
            event_data={
                "article_category": article_category,
                "annex_reference": annex_reference,
                "registration_required": registration_required,
            },
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.classified",
            entity_type="eu_ai_act_classification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "article_category": row.article_category,
                "annex_reference": row.annex_reference,
                "registration_required": row.registration_required,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_classification(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUAIActClassification:
        row = self.db.execute(
            select(EUAIActClassification).where(
                EUAIActClassification.organization_id == org_id,
                EUAIActClassification.ai_system_id == system_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EU AI Act classification not found")
        return row

    def get_applicable_obligations(self, org_id: uuid.UUID, system_id: uuid.UUID) -> list[Obligation]:
        classification = self.get_classification(org_id, system_id)

        framework = self.db.execute(
            select(Framework).where(
                or_(
                    Framework.code.ilike("%EU_AI_ACT%"),
                    Framework.name.ilike("%eu%ai%act%"),
                    Framework.name.ilike("%ai act%"),
                )
            )
        ).scalar_one_or_none()
        if framework is None:
            return []

        stmt = select(Obligation).where(
            Obligation.framework_id == framework.id,
            Obligation.status == "active",
        )

        if classification.annex_reference:
            annex = self.db.execute(
                select(EUActAnnexMapping).where(EUActAnnexMapping.annex_ref == classification.annex_reference)
            ).scalar_one_or_none()
            if annex and annex.article_refs:
                article_tokens = [str(v) for v in list(annex.article_refs or [])]
                predicates = [
                    or_(
                        Obligation.reference_code.ilike(f"%{token}%"),
                        Obligation.title.ilike(f"%{token}%"),
                        Obligation.description.ilike(f"%{token}%"),
                    )
                    for token in article_tokens
                ]
                if predicates:
                    stmt = stmt.where(or_(*predicates))

        return self.db.execute(stmt.order_by(Obligation.reference_code.asc())).scalars().all()

    def list_annex_sectors(self) -> list[EUActAnnexMapping]:
        SeedService.ensure_eu_act_annex_mappings(self.db)
        return self.db.execute(
            select(EUActAnnexMapping).where(EUActAnnexMapping.is_active.is_(True)).order_by(EUActAnnexMapping.annex_ref.asc())
        ).scalars().all()
