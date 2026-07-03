import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework


class ControlService:
    @staticmethod
    def emit_control_status_changed(
        db: Session,
        *,
        organization_id: uuid.UUID,
        control_id: uuid.UUID,
        previous_status: str,
        new_status: str,
        triggered_by: str = "user_action",
    ) -> None:
        if previous_status == new_status:
            return
        EventBus.get_instance().emit(
            EventType.CONTROL_STATUS_CHANGED,
            EventPayload(
                org_id=organization_id,
                entity_type="control",
                entity_id=control_id,
                event_type=EventType.CONTROL_STATUS_CHANGED,
                previous_value=previous_status,
                new_value=new_status,
                triggered_by=triggered_by,
                db=db,
            ),
        )

    @staticmethod
    def set_status(
        db: Session,
        *,
        organization_id: uuid.UUID,
        control_id: uuid.UUID,
        new_status: str,
        triggered_by: str = "service",
    ) -> Control:
        control = db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        previous_status = control.status
        control.status = new_status
        db.flush()
        ControlService.emit_control_status_changed(
            db,
            organization_id=organization_id,
            control_id=control.id,
            previous_status=previous_status,
            new_status=new_status,
            triggered_by=triggered_by,
        )
        return control

    @staticmethod
    def ensure_owner_is_active_member(db: Session, organization_id: uuid.UUID, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return

        membership = db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

    @staticmethod
    def ensure_obligation_framework_is_active(db: Session, organization_id: uuid.UUID, obligation_id: uuid.UUID) -> Obligation:
        obligation = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if obligation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

        org_framework = db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == obligation.framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if org_framework is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot map control to obligation from inactive framework",
            )

        return obligation

    @staticmethod
    def evidence_count_for_control(db: Session, organization_id: uuid.UUID, control_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(EvidenceControlLink.id))
            .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
            .where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.control_id == control_id,
                EvidenceControlLink.link_status == "active",
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status != "archived",
            )
        )
        return int(db.execute(stmt).scalar_one())

    @staticmethod
    def gap_summary(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
        total_active_obligations = int(
            db.execute(
                select(func.count(Obligation.id))
                .join(OrganizationFramework, OrganizationFramework.framework_id == Obligation.framework_id)
                .where(
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                    Obligation.status == "active",
                )
            ).scalar_one()
        )

        obligations_with_controls = int(
            db.execute(
                select(func.count(func.distinct(ControlObligationMapping.obligation_id))).where(
                    ControlObligationMapping.organization_id == organization_id,
                    ControlObligationMapping.status == "active",
                )
            ).scalar_one()
        )

        controls_not_started = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status == "not_started",
                )
            ).scalar_one()
        )
        controls_in_progress = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status == "in_progress",
                )
            ).scalar_one()
        )
        controls_implemented = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status == "implemented",
                )
            ).scalar_one()
        )
        high_criticality_open_controls = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.criticality.in_(["high", "critical"]),
                    Control.status.in_(["not_started", "in_progress", "needs_review", "failed"]),
                )
            ).scalar_one()
        )

        return {
            "total_active_obligations": total_active_obligations,
            "obligations_with_controls": obligations_with_controls,
            "obligations_without_controls": max(0, total_active_obligations - obligations_with_controls),
            "controls_not_started": controls_not_started,
            "controls_in_progress": controls_in_progress,
            "controls_implemented": controls_implemented,
            "high_criticality_open_controls": high_criticality_open_controls,
        }
