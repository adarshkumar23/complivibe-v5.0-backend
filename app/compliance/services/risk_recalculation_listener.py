import uuid
from datetime import UTC, datetime

from sqlalchemy import distinct, select

from app.compliance.services.risk_scoring_service import RiskScoringService
from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.vendor_control_link import VendorControlLink
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService


class RiskRecalculationListener:
    def _linked_risk_ids_for_control(self, *, org_id: uuid.UUID, control_id: uuid.UUID, db) -> list[uuid.UUID]:
        rows = db.execute(
            select(distinct(RiskControlLink.risk_id)).where(
                RiskControlLink.organization_id == org_id,
                RiskControlLink.control_id == control_id,
                RiskControlLink.status == "active",
            )
        ).scalars().all()
        return list(rows)

    def _linked_risk_ids_for_evidence(self, *, org_id: uuid.UUID, evidence_id: uuid.UUID, db) -> list[uuid.UUID]:
        rows = db.execute(
            select(distinct(RiskControlLink.risk_id))
            .join(
                EvidenceControlLink,
                EvidenceControlLink.control_id == RiskControlLink.control_id,
            )
            .where(
                RiskControlLink.organization_id == org_id,
                RiskControlLink.status == "active",
                EvidenceControlLink.organization_id == org_id,
                EvidenceControlLink.evidence_item_id == evidence_id,
                EvidenceControlLink.link_status == "active",
            )
        ).scalars().all()
        return list(rows)

    def _linked_risk_ids_for_vendor(self, *, org_id: uuid.UUID, vendor_id: uuid.UUID, db) -> list[uuid.UUID]:
        rows = db.execute(
            select(distinct(RiskControlLink.risk_id))
            .join(
                VendorControlLink,
                VendorControlLink.control_id == RiskControlLink.control_id,
            )
            .where(
                RiskControlLink.organization_id == org_id,
                RiskControlLink.status == "active",
                VendorControlLink.organization_id == org_id,
                VendorControlLink.vendor_id == vendor_id,
                VendorControlLink.status == "active",
            )
        ).scalars().all()
        return list(rows)

    def _linked_active_controls(self, *, org_id: uuid.UUID, risk_id: uuid.UUID, db) -> list[Control]:
        return list(
            db.execute(
                select(Control)
                .join(RiskControlLink, RiskControlLink.control_id == Control.id)
                .where(
                    RiskControlLink.organization_id == org_id,
                    RiskControlLink.risk_id == risk_id,
                    RiskControlLink.status == "active",
                )
            ).scalars().all()
        )

    def handle(self, payload: EventPayload) -> None:
        db = payload.db
        if payload.entity_type == "control":
            linked_risk_ids = self._linked_risk_ids_for_control(org_id=payload.org_id, control_id=payload.entity_id, db=db)
        elif payload.entity_type == "evidence":
            linked_risk_ids = self._linked_risk_ids_for_evidence(org_id=payload.org_id, evidence_id=payload.entity_id, db=db)
        elif payload.entity_type == "vendor":
            linked_risk_ids = self._linked_risk_ids_for_vendor(org_id=payload.org_id, vendor_id=payload.entity_id, db=db)
        else:
            return

        if not linked_risk_ids:
            return

        changed = False
        for risk_id in linked_risk_ids:
            risk = db.execute(
                select(Risk).where(
                    Risk.id == risk_id,
                    Risk.organization_id == payload.org_id,
                )
            ).scalar_one_or_none()
            if risk is None:
                continue

            settings = RiskScoringService.get_or_create_org_settings(payload.org_id, db)
            previous_score = int(risk.inherent_score)
            new_score = int(RiskScoringService.compute_score(risk, settings))

            linked_controls = self._linked_active_controls(org_id=payload.org_id, risk_id=risk.id, db=db)
            previous_residual_score = risk.residual_score
            new_residual_likelihood, new_residual_impact, new_residual_score = RiskScoringService.compute_residual(
                risk, linked_controls
            )

            inherent_changed = new_score != previous_score
            residual_changed = new_residual_score != previous_residual_score
            if not inherent_changed and not residual_changed:
                continue

            if inherent_changed:
                risk.inherent_score = new_score
                risk.severity = RiskService.score_to_severity(new_score)
            risk.residual_likelihood = new_residual_likelihood
            risk.residual_impact = new_residual_impact
            risk.residual_score = new_residual_score
            risk.updated_at = datetime.now(UTC)
            db.flush()
            RiskService(db).check_appetite_breach(organization_id=payload.org_id, risk=risk, actor_user_id=None)
            changed = True

            AuditService(db).write_audit_log(
                action="risk.score_recalculated",
                entity_type="risk",
                entity_id=risk.id,
                organization_id=payload.org_id,
                metadata_json={
                    "context_json": {
                        "triggered_by_event": payload.event_type,
                        "triggered_by_entity_type": payload.entity_type,
                        "triggered_by_entity_id": str(payload.entity_id),
                        "previous_score": previous_score,
                        "new_score": new_score,
                        "previous_residual_score": previous_residual_score,
                        "new_residual_score": new_residual_score,
                        "linked_active_control_count": len(linked_controls),
                        "score_method": risk.composite_score_method,
                    }
                },
            )

            if inherent_changed:
                EventBus.get_instance().emit(
                    EventType.RISK_SCORE_UPDATED,
                    EventPayload(
                        org_id=payload.org_id,
                        entity_type="risk",
                        entity_id=risk.id,
                        event_type=EventType.RISK_SCORE_UPDATED,
                        previous_value=previous_score,
                        new_value=new_score,
                        triggered_by="system",
                        db=db,
                    ),
                )
        if changed:
            db.commit()

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.CONTROL_STATUS_CHANGED, self.handle)
        bus.subscribe(EventType.EVIDENCE_STATUS_CHANGED, self.handle)
        bus.subscribe(EventType.EVIDENCE_EXPIRED, self.handle)
        bus.subscribe(EventType.VENDOR_SCORE_UPDATED, self.handle)
