import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.user import User
from app.services.audit_service import AuditService


class RiskAppetiteService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def derive_severity(new_score: int, max_acceptable_score: int) -> str:
        breach_ratio = new_score / max_acceptable_score
        if breach_ratio >= 1.5:
            return "critical"
        if breach_ratio >= 1.2:
            return "high"
        if breach_ratio >= 1.0:
            return "medium"
        return "low"

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str) -> None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )

    def require_threshold_in_org(self, organization_id: uuid.UUID, threshold_id: uuid.UUID) -> RiskAppetiteThreshold:
        threshold = self.db.execute(
            select(RiskAppetiteThreshold).where(
                RiskAppetiteThreshold.id == threshold_id,
                RiskAppetiteThreshold.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if threshold is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk appetite threshold not found")
        return threshold

    def ensure_no_active_duplicate(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        risk_category: str,
        exclude_threshold_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(RiskAppetiteThreshold).where(
            RiskAppetiteThreshold.organization_id == organization_id,
            RiskAppetiteThreshold.scope_type == scope_type,
            RiskAppetiteThreshold.risk_category == risk_category,
            RiskAppetiteThreshold.is_active.is_(True),
        )
        if scope_id is None:
            stmt = stmt.where(RiskAppetiteThreshold.scope_id.is_(None))
        else:
            stmt = stmt.where(RiskAppetiteThreshold.scope_id == scope_id)
        if exclude_threshold_id is not None:
            stmt = stmt.where(RiskAppetiteThreshold.id != exclude_threshold_id)

        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Active threshold already exists for this scope and category. "
                    "Deactivate existing threshold before creating a new one."
                ),
            )

    def ensure_scope_in_org(self, organization_id: uuid.UUID, scope_type: str, scope_id: uuid.UUID | None) -> None:
        if scope_type != "business_unit":
            return
        business_unit = self.db.execute(
            select(BusinessUnit.id).where(
                BusinessUnit.id == scope_id,
                BusinessUnit.organization_id == organization_id,
                BusinessUnit.is_active.is_(True),
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if business_unit is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scope_id must reference an active business unit in the organization",
            )

    def _resolve_most_specific_threshold(
        self,
        *,
        organization_id: uuid.UUID,
        risk_category: str,
        scope_id: uuid.UUID | None,
    ) -> RiskAppetiteThreshold | None:
        stmt = (
            select(RiskAppetiteThreshold)
            .where(
                RiskAppetiteThreshold.organization_id == organization_id,
                RiskAppetiteThreshold.risk_category == risk_category,
                RiskAppetiteThreshold.is_active.is_(True),
                RiskAppetiteThreshold.scope_type.in_(["org", "business_unit"]),
            )
            .order_by(
                case((RiskAppetiteThreshold.scope_type == "business_unit", 0), else_=1),
                RiskAppetiteThreshold.created_at.desc(),
            )
        )
        rows = self.db.execute(stmt).scalars().all()
        if not rows:
            return None

        if scope_id is not None:
            for row in rows:
                if row.scope_type == "business_unit" and row.scope_id == scope_id:
                    return row

        for row in rows:
            if row.scope_type == "org" and row.scope_id is None:
                return row

        return None

    def _find_open_breach_alert(self, *, org_id: uuid.UUID, risk_id: uuid.UUID) -> ControlMonitoringAlert | None:
        open_alerts = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
        ).scalars().all()
        for row in open_alerts:
            if not isinstance(row.alert_context_json, dict):
                continue
            if str(row.alert_context_json.get("risk_id")) == str(risk_id):
                return row
        return None

    def _auto_resolve_breach_alert(
        self,
        *,
        alert: ControlMonitoringAlert,
        org_id: uuid.UUID,
        new_score: int,
        reason: str,
    ) -> None:
        """Close a previously-open risk_threshold_breach alert once the condition that raised
        it no longer holds (score dropped back under the resolved threshold, or the threshold
        itself was relaxed) -- otherwise a "live breach" would keep being reported forever after
        it stopped being true."""
        alert.status = "resolved"
        alert.resolved_at = datetime.now(UTC)
        alert.resolved_by_user_id = None
        alert.resolution_notes = reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="risk_appetite.breach_auto_resolved",
            entity_type="control_monitoring_alert",
            entity_id=alert.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"status": alert.status, "resolved_at": alert.resolved_at.isoformat(), "reason": reason},
            metadata_json={
                "source": "system",
                "context_json": {"current_score": new_score, "reason": reason},
            },
        )

    def check_appetite_breach(
        self,
        *,
        org_id: uuid.UUID,
        risk_id: uuid.UUID,
        new_score: int,
        risk_category: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> ControlMonitoringAlert | None:
        risk = self.db.execute(
            select(Risk).where(
                Risk.id == risk_id,
                Risk.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if risk is None:
            return None

        scope_id = None
        if isinstance(risk.metadata_json, dict):
            raw_scope_id = risk.metadata_json.get("business_unit_id")
            if isinstance(raw_scope_id, str):
                try:
                    scope_id = uuid.UUID(raw_scope_id)
                except ValueError:
                    scope_id = None

        threshold = self._resolve_most_specific_threshold(
            organization_id=org_id,
            risk_category=risk_category,
            scope_id=scope_id,
        )

        existing_alert = self._find_open_breach_alert(org_id=org_id, risk_id=risk_id)

        if threshold is None:
            # No active threshold applies anymore (e.g. it was deactivated) -- any open breach
            # alert for this risk no longer has anything to be breaching.
            if existing_alert is not None:
                self._auto_resolve_breach_alert(
                    alert=existing_alert,
                    org_id=org_id,
                    new_score=new_score,
                    reason="No active risk appetite threshold applies to this risk anymore.",
                )
            return None

        if new_score <= threshold.max_acceptable_score:
            if existing_alert is not None:
                self._auto_resolve_breach_alert(
                    alert=existing_alert,
                    org_id=org_id,
                    new_score=new_score,
                    reason=(
                        f"Risk score {new_score} is now at or under threshold "
                        f"{threshold.max_acceptable_score}; breach no longer applies."
                    ),
                )
            return None

        if existing_alert is not None:
            # Already have an open alert for this risk -- keep its snapshot of new_score current
            # rather than silently leaving stale numbers in a "live" alert.
            ctx = dict(existing_alert.alert_context_json or {})
            if ctx.get("new_score") != new_score:
                ctx["new_score"] = new_score
                existing_alert.alert_context_json = ctx
                existing_alert.title = (
                    f"Risk appetite breach: {risk_category} score "
                    f"{new_score} exceeds threshold {threshold.max_acceptable_score}"
                )
                self.db.flush()
            return existing_alert

        severity = self.derive_severity(new_score, threshold.max_acceptable_score)
        title = (
            f"Risk appetite breach: {risk_category} score "
            f"{new_score} exceeds threshold {threshold.max_acceptable_score}"
        )
        description = (
            f"Risk {risk_id} exceeded threshold {threshold.id}. "
            f"Scope={threshold.scope_type}:{threshold.scope_id}."
        )

        alert = ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="risk_threshold_breach",
            severity=severity,
            status="open",
            title=title,
            description=description,
            alert_context_json={
                "risk_id": str(risk_id),
                "threshold_id": str(threshold.id),
                "risk_category": risk_category,
                "new_score": new_score,
                "max_acceptable_score": threshold.max_acceptable_score,
                "scope_type": threshold.scope_type,
                "scope_id": str(threshold.scope_id) if threshold.scope_id else None,
            },
            assigned_to_user_id=threshold.escalation_owner_id,
        )
        self.db.add(alert)
        self.db.flush()

        score_delta = new_score - threshold.max_acceptable_score
        AuditService(self.db).write_audit_log(
            action="risk_appetite.breach_detected",
            entity_type="risk_appetite_threshold",
            entity_id=threshold.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "risk_id": str(risk_id),
                "threshold_id": str(threshold.id),
                "score": new_score,
                "max_score": threshold.max_acceptable_score,
            },
            metadata_json={
                "source": "service",
                "context_json": {
                    "risk_id": str(risk_id),
                    "threshold_id": str(threshold.id),
                    "score": new_score,
                    "max_score": threshold.max_acceptable_score,
                    "score_delta": score_delta,
                },
            },
        )
        return alert

    def resync_alerts_for_threshold(
        self,
        *,
        org_id: uuid.UUID,
        threshold_id: uuid.UUID,
        threshold: RiskAppetiteThreshold | None,
    ) -> int:
        """Re-evaluate open risk_threshold_breach alerts raised against a specific threshold
        after that threshold was edited (raised) or deactivated. Without this, an alert created
        while max_acceptable_score was e.g. 10 keeps reporting a "live breach" forever even after
        an admin raises the threshold to 20 or turns it off -- nothing else re-triggers a check
        for that risk unless its own score happens to change again.

        `threshold` is None when the threshold was deactivated; otherwise it's the row with its
        already-updated max_acceptable_score.
        """
        open_alerts = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
        ).scalars().all()

        resolved_count = 0
        for alert in open_alerts:
            ctx = alert.alert_context_json if isinstance(alert.alert_context_json, dict) else {}
            if str(ctx.get("threshold_id")) != str(threshold_id):
                continue

            new_score = ctx.get("new_score")
            if threshold is None:
                reason = "Risk appetite threshold was deactivated; breach no longer applies."
            elif isinstance(new_score, int) and new_score <= threshold.max_acceptable_score:
                reason = (
                    f"Risk appetite threshold was raised to {threshold.max_acceptable_score}; "
                    f"recorded score {new_score} no longer breaches it."
                )
            else:
                continue

            self._auto_resolve_breach_alert(
                alert=alert,
                org_id=org_id,
                new_score=new_score if isinstance(new_score, int) else 0,
                reason=reason,
            )
            resolved_count += 1

        return resolved_count
