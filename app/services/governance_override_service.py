import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.export_attestation import ExportAttestation
from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent
from app.models.governance_override_approval import GovernanceOverrideApproval
from app.models.governance_override_event import GovernanceOverrideEvent
from app.models.governance_override_request import GovernanceOverrideRequest
from app.models.governance_override_template import GovernanceOverrideTemplate
from app.models.governance_override_template_version import GovernanceOverrideTemplateVersion
from app.models.membership import Membership
from app.models.retention_policy import RetentionPolicy
from app.models.role import Role
from app.repositories.governance_override_repository import GovernanceOverrideRepository
from app.services.attestation_service import AttestationService
from app.services.export_service import ExportService
from app.core.validation import validate_choice

ALLOWED_OVERRIDE_TYPES = {
    "export_lock_exception",
    "legal_hold_exception",
    "retention_window_exception",
    "attestation_governance_exception",
}

ALLOWED_TARGET_ENTITY_TYPES = {
    "export_job",
    "export_attestation",
    "retention_policy",
}

ALLOWED_REQUESTED_ACTIONS = {
    "archive_locked_export",
    "remove_legal_hold",
    "adjust_retention_window",
    "revoke_attestation_after_lock",
}

ALLOWED_OVERRIDE_REQUEST_STATUS = {
    "pending",
    "approved",
    "rejected",
    "executed",
    "cancelled",
    "expired",
}

ACTION_TARGET_MAP: dict[str, set[str]] = {
    "archive_locked_export": {"export_job"},
    "remove_legal_hold": {"export_job"},
    "adjust_retention_window": {"export_job"},
    "revoke_attestation_after_lock": {"export_attestation"},
}

ALLOWED_CONDITION_KEYS: dict[str, set[str]] = {
    "export_job": {
        "export_type",
        "status",
        "legal_hold",
        "lock_active",
        "retention_active",
        "retention_elapsed",
        "attestation_status",
        "has_active_attestation",
        "has_revoked_attestation",
        "verification_valid",
    },
    "export_attestation": {
        "status",
        "attestation_type",
        "export_legal_hold",
        "export_lock_active",
    },
    "retention_policy": {
        "entity_type",
        "status",
        "legal_hold_default",
    },
}

ALLOWED_CONDITION_OPERATORS = {"equals", "not_equals", "is_true", "is_false", "in", "not_in"}
ALLOWED_RULE_EFFECTS = {"set_required_approvals", "add_required_approvals", "restrict_approver_roles"}
OVERRIDE_PENDING_STALE_HOURS = 24
OVERRIDE_EXPIRY_WARNING_HOURS = 24


class GovernanceOverrideService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = GovernanceOverrideRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def validate_allowlist(override_type: str, target_entity_type: str, requested_action: str) -> None:
        override_type = validate_choice(override_type, ALLOWED_OVERRIDE_TYPES, "override_type", status_code=status.HTTP_400_BAD_REQUEST)
        target_entity_type = validate_choice(target_entity_type, ALLOWED_TARGET_ENTITY_TYPES, "target_entity_type", status_code=status.HTTP_400_BAD_REQUEST)
        requested_action = validate_choice(requested_action, ALLOWED_REQUESTED_ACTIONS, "requested_action", status_code=status.HTTP_400_BAD_REQUEST)
        allowed_targets = ACTION_TARGET_MAP.get(requested_action, set())
        if target_entity_type not in allowed_targets:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="requested_action is not valid for target_entity_type")

    def validate_target(self, *, organization_id: uuid.UUID, target_entity_type: str, target_entity_id: uuid.UUID) -> None:
        if target_entity_type == "export_job":
            row = self.db.execute(select(ExportJob).where(ExportJob.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")
            return
        if target_entity_type == "export_attestation":
            row = self.db.execute(select(ExportAttestation).where(ExportAttestation.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")
            return
        if target_entity_type == "retention_policy":
            row = self.db.execute(select(RetentionPolicy).where(RetentionPolicy.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")
            return
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_entity_type")

    def _add_event(
        self,
        *,
        request_row: GovernanceOverrideRequest,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor_user_id: uuid.UUID | None,
        details_json: dict | None,
    ) -> GovernanceOverrideEvent:
        row = GovernanceOverrideEvent(
            organization_id=request_row.organization_id,
            override_request_id=request_row.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            details_json=details_json,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _event_latest_timestamp_map(self, *, organization_id: uuid.UUID, request_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        if not request_ids:
            return {}
        rows = self.db.execute(
            select(
                GovernanceOverrideEvent.override_request_id,
                func.max(GovernanceOverrideEvent.created_at),
            )
            .where(
                GovernanceOverrideEvent.organization_id == organization_id,
                GovernanceOverrideEvent.override_request_id.in_(request_ids),
            )
            .group_by(GovernanceOverrideEvent.override_request_id)
        ).all()
        return {
            request_id: latest_ts
            for request_id, latest_ts in rows
            if request_id is not None and latest_ts is not None
        }

    def override_request_payload(
        self,
        *,
        row: GovernanceOverrideRequest,
        latest_event_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = self.now()
        created_at = self.as_utc(row.created_at) or now
        expires_at = self.as_utc(row.expires_at)
        request_age_hours = round(max(0.0, (now - created_at).total_seconds() / 3600.0), 3)
        expires_in_hours = None
        if expires_at is not None:
            expires_in_hours = round((expires_at - now).total_seconds() / 3600.0, 3)
        approvals_remaining = max(int(row.required_approvals) - int(row.approval_count), 0)
        decision_count = int(row.approval_count or 0) + int(row.rejection_count or 0)
        approval_progress_pct = round((int(row.approval_count or 0) / int(row.required_approvals)) * 100.0, 2) if int(row.required_approvals) > 0 else 0.0
        is_expired = bool(expires_at is not None and expires_at < now)
        target_facts_snapshot = ((row.routing_context_json or {}).get("target_facts") if isinstance(row.routing_context_json, dict) else None)
        target_facts_current: dict[str, Any] | None = None
        target_entity_missing = False
        target_state_changed_since_request = False
        if row.status in {"pending", "approved"}:
            try:
                target_facts_current = self.collect_target_facts(
                    organization_id=row.organization_id,
                    target_entity_type=row.target_entity_type,
                    target_entity_id=row.target_entity_id,
                )
            except HTTPException:
                target_entity_missing = True
            else:
                if isinstance(target_facts_snapshot, dict):
                    target_state_changed_since_request = bool(target_facts_current != target_facts_snapshot)
        stale_pending = bool(row.status == "pending" and request_age_hours >= OVERRIDE_PENDING_STALE_HOURS)
        context_flags: list[str] = []
        if row.status == "pending":
            context_flags.append("pending_request")
            if approvals_remaining > 0:
                context_flags.append("approvals_outstanding")
        if stale_pending:
            context_flags.append("pending_over_24h")
        if row.status in {"pending", "approved"} and expires_in_hours is not None and expires_in_hours <= OVERRIDE_EXPIRY_WARNING_HOURS:
            context_flags.append("expires_within_24h")
        if row.status == "approved" and row.executed_at is None:
            context_flags.append("awaiting_execution")
        if row.status == "expired":
            context_flags.append("expired_unexecuted")
        if target_entity_missing:
            context_flags.append("target_entity_missing")
        if target_state_changed_since_request:
            context_flags.append("target_state_changed")
        if row.status == "executed" and not bool(row.execution_result_json):
            context_flags.append("execution_result_missing")
        if row.template_id is None:
            context_flags.append("ad_hoc_override")
        if int(row.rejection_count or 0) > 0:
            context_flags.append("contains_rejections")
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "override_type": row.override_type,
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "requested_action": row.requested_action,
            "reason": row.reason,
            "status": row.status,
            "requested_by_user_id": row.requested_by_user_id,
            "template_id": row.template_id,
            "template_version": row.template_version,
            "required_approvals": int(row.required_approvals),
            "approval_count": int(row.approval_count),
            "rejection_count": int(row.rejection_count),
            "expires_at": row.expires_at,
            "executed_by_user_id": row.executed_by_user_id,
            "executed_at": row.executed_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "cancelled_at": row.cancelled_at,
            "cancellation_reason": row.cancellation_reason,
            "execution_result_json": row.execution_result_json,
            "routing_context_json": row.routing_context_json,
            "approver_role_names_json": row.approver_role_names_json,
            "metadata_json": row.metadata_json,
            "approvals_remaining": approvals_remaining,
            "decision_count": decision_count,
            "approval_progress_pct": approval_progress_pct,
            "request_age_hours": request_age_hours,
            "expires_in_hours": expires_in_hours,
            "is_expired": is_expired,
            "stale_pending": stale_pending,
            "last_event_at": latest_event_at,
            "target_state_changed_since_request": target_state_changed_since_request,
            "target_entity_missing": target_entity_missing,
            "context_flags": context_flags,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def validate_request_filters(
        *,
        status_filter: str | None,
        override_type: str | None,
        target_entity_type: str | None,
        requested_action: str | None,
    ) -> None:
        if status_filter is not None:
            validate_choice(
                status_filter,
                ALLOWED_OVERRIDE_REQUEST_STATUS,
                "status",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if override_type is not None:
            validate_choice(
                override_type,
                ALLOWED_OVERRIDE_TYPES,
                "override_type",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if target_entity_type is not None:
            validate_choice(
                target_entity_type,
                ALLOWED_TARGET_ENTITY_TYPES,
                "target_entity_type",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if requested_action is not None:
            validate_choice(
                requested_action,
                ALLOWED_REQUESTED_ACTIONS,
                "requested_action",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    def override_request_payloads(self, *, rows: list[GovernanceOverrideRequest]) -> list[dict[str, Any]]:
        if not rows:
            return []
        latest_map = self._event_latest_timestamp_map(
            organization_id=rows[0].organization_id,
            request_ids=[row.id for row in rows],
        )
        return [
            self.override_request_payload(
                row=row,
                latest_event_at=latest_map.get(row.id),
            )
            for row in rows
        ]

    def require_request(self, *, organization_id: uuid.UUID, override_id: uuid.UUID) -> GovernanceOverrideRequest:
        row = self.repo.get_request(override_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override request not found")
        return row

    def require_request_for_update(self, *, organization_id: uuid.UUID, override_id: uuid.UUID) -> GovernanceOverrideRequest:
        """Same lookup as require_request(), but takes a row lock (see
        GovernanceOverrideRepository.get_request_for_update) so concurrent approve/reject
        calls against the same override request serialize instead of racing. Use this for
        any mutating decision path (approve/reject) rather than require_request()."""
        row = self.repo.get_request_for_update(override_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override request not found")
        return row

    def require_template(self, *, organization_id: uuid.UUID, template_id: uuid.UUID) -> GovernanceOverrideTemplate:
        row = self.repo.get_template(template_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override template not found")
        return row

    def validate_role_names_for_org(self, *, organization_id: uuid.UUID, role_names: list[str] | None) -> None:
        if role_names is None:
            return
        normalized = [r.strip() for r in role_names if r and r.strip()]
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approver_role_names_json cannot be empty")
        rows = self.db.execute(select(Role.name).where(Role.organization_id == organization_id)).scalars().all()
        existing = set(rows)
        for role_name in normalized:
            if role_name not in existing:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown approver role: {role_name}")

    def validate_condition_rules(self, *, target_entity_type: str, condition_rules_json: list[dict] | None) -> None:
        if condition_rules_json is None:
            return
        if not isinstance(condition_rules_json, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="condition_rules_json must be a list")

        allowed_keys = ALLOWED_CONDITION_KEYS.get(target_entity_type)
        if allowed_keys is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_entity_type")

        for rule in condition_rules_json:
            if not isinstance(rule, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each rule must be an object")
            conditions = rule.get("conditions")
            effect = rule.get("effect")
            if not isinstance(conditions, list) or not conditions:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule conditions must be a non-empty list")
            if not isinstance(effect, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule effect must be an object")

            for condition in conditions:
                if not isinstance(condition, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Condition must be an object")
                key = condition.get("key")
                operator = condition.get("operator")
                value = condition.get("value")
                if key not in allowed_keys:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid condition key: {key}")
                if operator not in ALLOWED_CONDITION_OPERATORS:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid operator: {operator}")
                if operator in {"equals", "not_equals"} and value is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Condition value is required")
                if operator in {"in", "not_in"} and not isinstance(value, list):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Condition value must be a list")

            effect_type = effect.get("type")
            effect_value = effect.get("value")
            if effect_type not in ALLOWED_RULE_EFFECTS:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid effect type: {effect_type}")
            if effect_type == "set_required_approvals":
                if not isinstance(effect_value, int) or effect_value < 2:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="set_required_approvals requires integer value >= 2")
            elif effect_type == "add_required_approvals":
                if not isinstance(effect_value, int) or effect_value < 1:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="add_required_approvals requires integer value >= 1")
            elif effect_type == "restrict_approver_roles":
                if not isinstance(effect_value, list) or not effect_value:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="restrict_approver_roles requires non-empty list")

    def create_template_version_snapshot(
        self,
        *,
        template: GovernanceOverrideTemplate,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceOverrideTemplateVersion:
        row = GovernanceOverrideTemplateVersion(
            organization_id=template.organization_id,
            template_id=template.id,
            version=template.version,
            name=template.name,
            description=template.description,
            override_type=template.override_type,
            target_entity_type=template.target_entity_type,
            requested_action=template.requested_action,
            default_required_approvals=template.default_required_approvals,
            approver_role_names_json=template.approver_role_names_json,
            condition_rules_json=template.condition_rules_json,
            status=template.status,
            created_by_user_id=actor_user_id,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def create_template(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        override_type: str,
        target_entity_type: str,
        requested_action: str,
        default_required_approvals: int,
        approver_role_names_json: list[str] | None,
        condition_rules_json: list[dict] | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> GovernanceOverrideTemplate:
        if default_required_approvals < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="default_required_approvals must be at least 2")
        self.validate_allowlist(override_type, target_entity_type, requested_action)
        self.validate_role_names_for_org(organization_id=organization_id, role_names=approver_role_names_json)
        self.validate_condition_rules(target_entity_type=target_entity_type, condition_rules_json=condition_rules_json)

        row = GovernanceOverrideTemplate(
            organization_id=organization_id,
            name=name,
            description=description,
            override_type=override_type,
            target_entity_type=target_entity_type,
            requested_action=requested_action,
            status=status_value,
            default_required_approvals=default_required_approvals,
            approver_role_names_json=approver_role_names_json,
            condition_rules_json=condition_rules_json,
            version=1,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self.create_template_version_snapshot(template=row, actor_user_id=actor_user_id)
        return row

    def update_template(
        self,
        *,
        template: GovernanceOverrideTemplate,
        actor_user_id: uuid.UUID,
        name: str | None,
        description: str | None,
        override_type: str | None,
        target_entity_type: str | None,
        requested_action: str | None,
        default_required_approvals: int | None,
        approver_role_names_json: list[str] | None,
        condition_rules_json: list[dict] | None,
        status_value: str | None,
    ) -> GovernanceOverrideTemplate:
        next_override_type = override_type or template.override_type
        next_target_entity_type = target_entity_type or template.target_entity_type
        next_requested_action = requested_action or template.requested_action
        next_required_approvals = default_required_approvals if default_required_approvals is not None else template.default_required_approvals
        next_roles = approver_role_names_json if approver_role_names_json is not None else template.approver_role_names_json
        next_rules = condition_rules_json if condition_rules_json is not None else template.condition_rules_json

        if next_required_approvals < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="default_required_approvals must be at least 2")
        self.validate_allowlist(next_override_type, next_target_entity_type, next_requested_action)
        self.validate_role_names_for_org(organization_id=template.organization_id, role_names=next_roles)
        self.validate_condition_rules(target_entity_type=next_target_entity_type, condition_rules_json=next_rules)

        important_changed = False
        if name is not None and name != template.name:
            template.name = name
            important_changed = True
        if description is not None and description != template.description:
            template.description = description
            important_changed = True
        if override_type is not None and override_type != template.override_type:
            template.override_type = override_type
            important_changed = True
        if target_entity_type is not None and target_entity_type != template.target_entity_type:
            template.target_entity_type = target_entity_type
            important_changed = True
        if requested_action is not None and requested_action != template.requested_action:
            template.requested_action = requested_action
            important_changed = True
        if default_required_approvals is not None and default_required_approvals != template.default_required_approvals:
            template.default_required_approvals = default_required_approvals
            important_changed = True
        if approver_role_names_json is not None and approver_role_names_json != template.approver_role_names_json:
            template.approver_role_names_json = approver_role_names_json
            important_changed = True
        if condition_rules_json is not None and condition_rules_json != template.condition_rules_json:
            template.condition_rules_json = condition_rules_json
            important_changed = True
        if status_value is not None and status_value != template.status:
            template.status = status_value
            important_changed = True

        if important_changed:
            template.version += 1
            self.db.flush()
            self.create_template_version_snapshot(template=template, actor_user_id=actor_user_id)
        else:
            self.db.flush()
        return template

    def collect_target_facts(self, *, organization_id: uuid.UUID, target_entity_type: str, target_entity_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        if target_entity_type == "export_job":
            row = self.db.execute(select(ExportJob).where(ExportJob.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")

            has_active_attestation = int(
                self.db.execute(
                    select(func.count(ExportAttestation.id)).where(
                        ExportAttestation.organization_id == organization_id,
                        ExportAttestation.export_job_id == row.id,
                        ExportAttestation.status == "active",
                    )
                ).scalar_one()
            ) > 0
            has_revoked_attestation = int(
                self.db.execute(
                    select(func.count(ExportAttestation.id)).where(
                        ExportAttestation.organization_id == organization_id,
                        ExportAttestation.export_job_id == row.id,
                        ExportAttestation.status == "revoked",
                    )
                ).scalar_one()
            ) > 0
            latest_verification = self.db.execute(
                select(ExportJobEvent)
                .where(
                    ExportJobEvent.organization_id == organization_id,
                    ExportJobEvent.export_job_id == row.id,
                    ExportJobEvent.event_type == "export.verified",
                )
                .order_by(ExportJobEvent.created_at.desc())
            ).scalars().first()
            verification_valid = bool((latest_verification.details_json or {}).get("valid")) if latest_verification else False

            locked_until = self.as_utc(row.locked_until)
            retention_until = self.as_utc(row.retention_until)
            return {
                "export_type": row.export_type,
                "status": row.status,
                "legal_hold": bool(row.legal_hold),
                "lock_active": bool(locked_until and locked_until > now),
                "retention_active": bool(retention_until and retention_until > now),
                "retention_elapsed": bool(retention_until and retention_until <= now),
                "attestation_status": row.attestation_status,
                "has_active_attestation": has_active_attestation,
                "has_revoked_attestation": has_revoked_attestation,
                "verification_valid": verification_valid,
            }

        if target_entity_type == "export_attestation":
            row = self.db.execute(select(ExportAttestation).where(ExportAttestation.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")
            export = self.db.execute(select(ExportJob).where(ExportJob.id == row.export_job_id)).scalar_one_or_none()
            if export is None or export.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")

            locked_until = self.as_utc(export.locked_until)
            return {
                "status": row.status,
                "attestation_type": row.attestation_type,
                "export_legal_hold": bool(export.legal_hold),
                "export_lock_active": bool(locked_until and locked_until > now),
            }

        if target_entity_type == "retention_policy":
            row = self.db.execute(select(RetentionPolicy).where(RetentionPolicy.id == target_entity_id)).scalar_one_or_none()
            if row is None or row.organization_id != organization_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target entity not found for organization")
            return {
                "entity_type": row.entity_type,
                "status": row.status,
                "legal_hold_default": bool(row.legal_hold_default),
            }

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_entity_type")

    @staticmethod
    def evaluate_condition(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
        key = condition.get("key")
        operator = condition.get("operator")
        value = condition.get("value")
        fact_value = facts.get(key)

        if operator == "equals":
            return fact_value == value
        if operator == "not_equals":
            return fact_value != value
        if operator == "is_true":
            return bool(fact_value) is True
        if operator == "is_false":
            return bool(fact_value) is False
        if operator == "in":
            return fact_value in value
        if operator == "not_in":
            return fact_value not in value
        return False

    def evaluate_template_routing(
        self,
        *,
        template: GovernanceOverrideTemplate,
        target_entity_id: uuid.UUID,
    ) -> dict[str, Any]:
        facts = self.collect_target_facts(
            organization_id=template.organization_id,
            target_entity_type=template.target_entity_type,
            target_entity_id=target_entity_id,
        )
        base_required_approvals = template.default_required_approvals
        final_required_approvals = base_required_approvals
        base_approver_roles = list(template.approver_role_names_json) if template.approver_role_names_json else None
        final_approver_roles = list(base_approver_roles) if base_approver_roles else None
        matched_rules: list[dict[str, Any]] = []

        for rule in template.condition_rules_json or []:
            conditions = rule.get("conditions", [])
            if not all(self.evaluate_condition(condition, facts) for condition in conditions):
                continue

            effect = rule.get("effect") or {}
            effect_type = effect.get("type")
            effect_value = effect.get("value")
            if effect_type == "set_required_approvals":
                final_required_approvals = int(effect_value)
            elif effect_type == "add_required_approvals":
                final_required_approvals += int(effect_value)
            elif effect_type == "restrict_approver_roles":
                next_roles = [str(role_name) for role_name in effect_value]
                if final_approver_roles is None:
                    final_approver_roles = next_roles
                else:
                    final_approver_roles = [role_name for role_name in final_approver_roles if role_name in set(next_roles)]
            matched_rules.append(
                {
                    "name": rule.get("name"),
                    "effect": effect,
                }
            )

        if final_required_approvals < 2:
            final_required_approvals = 2

        routing_context = {
            "base_required_approvals": base_required_approvals,
            "final_required_approvals": final_required_approvals,
            "base_approver_roles": base_approver_roles,
            "final_approver_roles": final_approver_roles,
            "matched_rules": matched_rules,
            "target_facts": facts,
        }
        return {
            "required_approvals": final_required_approvals,
            "approver_role_names_json": final_approver_roles,
            "routing_context_json": routing_context,
        }

    def create_request(
        self,
        *,
        organization_id: uuid.UUID,
        override_type: str,
        target_entity_type: str,
        target_entity_id: uuid.UUID,
        requested_action: str,
        reason: str,
        required_approvals: int,
        requested_by_user_id: uuid.UUID,
        expires_at: datetime | None,
        metadata_json: dict | None,
        template_id: uuid.UUID | None = None,
        template_version: int | None = None,
        routing_context_json: dict | None = None,
        approver_role_names_json: list[str] | None = None,
    ) -> GovernanceOverrideRequest:
        reason = str(reason).strip()
        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        if required_approvals < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="required_approvals must be at least 2")
        self.validate_allowlist(override_type, target_entity_type, requested_action)
        self.validate_target(organization_id=organization_id, target_entity_type=target_entity_type, target_entity_id=target_entity_id)
        self.validate_role_names_for_org(organization_id=organization_id, role_names=approver_role_names_json)

        row = GovernanceOverrideRequest(
            organization_id=organization_id,
            override_type=override_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            requested_action=requested_action,
            reason=reason,
            status="pending",
            requested_by_user_id=requested_by_user_id,
            template_id=template_id,
            template_version=template_version,
            required_approvals=required_approvals,
            approval_count=0,
            rejection_count=0,
            expires_at=expires_at,
            routing_context_json=routing_context_json,
            approver_role_names_json=approver_role_names_json,
            metadata_json=metadata_json,
        )
        self.db.add(row)
        self.db.flush()
        self._add_event(
            request_row=row,
            event_type="override.created",
            from_status=None,
            to_status=row.status,
            actor_user_id=requested_by_user_id,
            details_json={"requested_action": row.requested_action},
        )
        return row

    def create_request_from_template(
        self,
        *,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        reason: str,
        expires_at: datetime | None,
        metadata_json: dict | None,
        requested_by_user_id: uuid.UUID,
    ) -> GovernanceOverrideRequest:
        template = self.require_template(organization_id=organization_id, template_id=template_id)
        if template.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template must be active")

        routing = self.evaluate_template_routing(template=template, target_entity_id=target_entity_id)
        row = self.create_request(
            organization_id=organization_id,
            override_type=template.override_type,
            target_entity_type=template.target_entity_type,
            target_entity_id=target_entity_id,
            requested_action=template.requested_action,
            reason=reason,
            required_approvals=routing["required_approvals"],
            requested_by_user_id=requested_by_user_id,
            expires_at=expires_at,
            metadata_json=metadata_json,
            template_id=template.id,
            template_version=template.version,
            routing_context_json=routing["routing_context_json"],
            approver_role_names_json=routing["approver_role_names_json"],
        )
        return row

    def _ensure_pending_and_not_expired(self, row: GovernanceOverrideRequest) -> None:
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override request is not pending")
        expires_at = self.as_utc(row.expires_at)
        if expires_at is not None and expires_at < self.now():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override request is expired")

    def _approver_role_name(self, *, organization_id: uuid.UUID, approver_user_id: uuid.UUID) -> str:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == approver_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver is not an active organization member")
        role = self.db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver role not found")
        return role.name

    def approve(
        self,
        *,
        row: GovernanceOverrideRequest,
        approver_user_id: uuid.UUID,
        reason: str | None,
    ) -> GovernanceOverrideRequest:
        self._ensure_pending_and_not_expired(row)
        if row.requested_by_user_id == approver_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requester cannot approve their own override request")
        reason = reason.strip() if isinstance(reason, str) else None
        if reason == "":
            reason = None
        existing = self.repo.get_approval_by_user(
            organization_id=row.organization_id,
            override_request_id=row.id,
            approver_user_id=approver_user_id,
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approver has already reviewed this override request")

        if row.approver_role_names_json:
            approver_role_name = self._approver_role_name(organization_id=row.organization_id, approver_user_id=approver_user_id)
            if approver_role_name not in set(row.approver_role_names_json):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver role is not allowed for this override request")

        approval = GovernanceOverrideApproval(
            organization_id=row.organization_id,
            override_request_id=row.id,
            approver_user_id=approver_user_id,
            decision="approved",
            reason=reason,
            created_at=self.now(),
        )
        self.db.add(approval)
        row.approval_count += 1
        if row.approval_count >= row.required_approvals:
            before = row.status
            row.status = "approved"
            self._add_event(
                request_row=row,
                event_type="override.approved",
                from_status=before,
                to_status=row.status,
                actor_user_id=approver_user_id,
                details_json={"approval_count": row.approval_count, "required_approvals": row.required_approvals},
            )
        else:
            self._add_event(
                request_row=row,
                event_type="override.approved",
                from_status=row.status,
                to_status=row.status,
                actor_user_id=approver_user_id,
                details_json={"approval_count": row.approval_count, "required_approvals": row.required_approvals},
            )
        try:
            self.db.flush()
        except IntegrityError as exc:
            # Defense in depth alongside the row lock taken by
            # require_request_for_update()/get_request_for_update(): if a duplicate
            # approval from the same approver ever reaches this point anyway (e.g. a
            # caller that bypassed the locked lookup), surface it as a clean 409 instead
            # of an unhandled IntegrityError (-> raw 500).
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approver has already reviewed this override request",
            ) from exc
        return row

    def reject(
        self,
        *,
        row: GovernanceOverrideRequest,
        approver_user_id: uuid.UUID,
        reason: str,
    ) -> GovernanceOverrideRequest:
        self._ensure_pending_and_not_expired(row)
        if row.requested_by_user_id == approver_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requester cannot reject their own override request")
        reason = str(reason).strip()
        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        existing = self.repo.get_approval_by_user(
            organization_id=row.organization_id,
            override_request_id=row.id,
            approver_user_id=approver_user_id,
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approver has already reviewed this override request")

        if row.approver_role_names_json:
            approver_role_name = self._approver_role_name(organization_id=row.organization_id, approver_user_id=approver_user_id)
            if approver_role_name not in set(row.approver_role_names_json):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver role is not allowed for this override request")

        rejection = GovernanceOverrideApproval(
            organization_id=row.organization_id,
            override_request_id=row.id,
            approver_user_id=approver_user_id,
            decision="rejected",
            reason=reason,
            created_at=self.now(),
        )
        self.db.add(rejection)
        row.rejection_count += 1
        before = row.status
        row.status = "rejected"
        self._add_event(
            request_row=row,
            event_type="override.rejected",
            from_status=before,
            to_status=row.status,
            actor_user_id=approver_user_id,
            details_json={"reason": reason},
        )
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approver has already reviewed this override request",
            ) from exc
        return row

    def cancel(
        self,
        *,
        row: GovernanceOverrideRequest,
        actor_user_id: uuid.UUID,
        reason: str,
    ) -> GovernanceOverrideRequest:
        reason = str(reason).strip()
        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        if row.status not in {"pending", "approved"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override request cannot be cancelled")
        if row.status == "executed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Executed override request cannot be cancelled")
        before = row.status
        row.status = "cancelled"
        row.cancelled_by_user_id = actor_user_id
        row.cancelled_at = self.now()
        row.cancellation_reason = reason
        self._add_event(
            request_row=row,
            event_type="override.cancelled",
            from_status=before,
            to_status=row.status,
            actor_user_id=actor_user_id,
            details_json={"reason": reason},
        )
        self.db.flush()
        return row

    def _execute_archive_locked_export(self, row: GovernanceOverrideRequest, actor_user_id: uuid.UUID) -> dict[str, Any]:
        export = self.db.execute(select(ExportJob).where(ExportJob.id == row.target_entity_id)).scalar_one_or_none()
        if export is None or export.organization_id != row.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target export job not found")
        if export.legal_hold:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export is under legal hold; remove legal hold via separate approved override first")

        before = export.status
        export.status = "archived"
        export.archived_at = self.now()
        ExportService(self.db).add_event(
            job=export,
            event_type="export.archived_override",
            from_status=before,
            to_status=export.status,
            details_json={"override_request_id": str(row.id)},
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return {"export_job_id": str(export.id), "status": export.status}

    def _execute_remove_legal_hold(self, row: GovernanceOverrideRequest, actor_user_id: uuid.UUID) -> dict[str, Any]:
        export = self.db.execute(select(ExportJob).where(ExportJob.id == row.target_entity_id)).scalar_one_or_none()
        if export is None or export.organization_id != row.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target export job not found")

        export.legal_hold = False
        export.legal_hold_reason = f"Removed via override {row.id}: {row.reason}"
        export.legal_hold_set_by_user_id = actor_user_id
        export.legal_hold_set_at = self.now()
        ExportService(self.db).add_event(
            job=export,
            event_type="export.legal_hold_updated",
            from_status=export.status,
            to_status=export.status,
            details_json={"override_request_id": str(row.id), "legal_hold": False},
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return {"export_job_id": str(export.id), "legal_hold": export.legal_hold}

    def _execute_adjust_retention_window(self, row: GovernanceOverrideRequest, actor_user_id: uuid.UUID) -> dict[str, Any]:
        export = self.db.execute(select(ExportJob).where(ExportJob.id == row.target_entity_id)).scalar_one_or_none()
        if export is None or export.organization_id != row.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target export job not found")
        if not row.metadata_json:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadata_json is required for adjust_retention_window")
        locked_val = row.metadata_json.get("locked_until")
        retention_val = row.metadata_json.get("retention_until")
        if locked_val is None and retention_val is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadata_json must include locked_until and/or retention_until")

        def parse_dt(value: str | None) -> datetime | None:
            if value is None:
                return None
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime in metadata_json") from exc
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

        if "locked_until" in row.metadata_json:
            export.locked_until = parse_dt(locked_val)
        if "retention_until" in row.metadata_json:
            export.retention_until = parse_dt(retention_val)

        ExportService(self.db).add_event(
            job=export,
            event_type="export.retention_adjusted_override",
            from_status=export.status,
            to_status=export.status,
            details_json={
                "override_request_id": str(row.id),
                "locked_until": export.locked_until.isoformat() if export.locked_until else None,
                "retention_until": export.retention_until.isoformat() if export.retention_until else None,
            },
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return {
            "export_job_id": str(export.id),
            "locked_until": export.locked_until.isoformat() if export.locked_until else None,
            "retention_until": export.retention_until.isoformat() if export.retention_until else None,
        }

    def _execute_revoke_attestation_after_lock(self, row: GovernanceOverrideRequest, actor_user_id: uuid.UUID) -> dict[str, Any]:
        attestation = self.db.execute(select(ExportAttestation).where(ExportAttestation.id == row.target_entity_id)).scalar_one_or_none()
        if attestation is None or attestation.organization_id != row.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target attestation not found")
        job = self.db.execute(select(ExportJob).where(ExportJob.id == attestation.export_job_id)).scalar_one_or_none()
        if job is None or job.organization_id != row.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target export job not found for attestation")

        AttestationService(self.db).revoke_attestation(
            row=attestation,
            job=job,
            actor_user_id=actor_user_id,
            revocation_reason=f"Revoked via override {row.id}: {row.reason}",
        )
        ExportService(self.db).add_event(
            job=job,
            event_type="export.attestation_revoked",
            from_status=job.status,
            to_status=job.status,
            details_json={"override_request_id": str(row.id), "attestation_id": str(attestation.id)},
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return {"attestation_id": str(attestation.id), "status": attestation.status}

    def execute(self, *, row: GovernanceOverrideRequest, actor_user_id: uuid.UUID) -> GovernanceOverrideRequest:
        if row.status != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override request is not approved")
        expires_at = self.as_utc(row.expires_at)
        if expires_at is not None and expires_at < self.now():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override request is expired")

        try:
            if row.requested_action == "archive_locked_export":
                result = self._execute_archive_locked_export(row, actor_user_id)
            elif row.requested_action == "remove_legal_hold":
                result = self._execute_remove_legal_hold(row, actor_user_id)
            elif row.requested_action == "adjust_retention_window":
                result = self._execute_adjust_retention_window(row, actor_user_id)
            elif row.requested_action == "revoke_attestation_after_lock":
                result = self._execute_revoke_attestation_after_lock(row, actor_user_id)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported requested_action")
        except Exception as exc:  # noqa: BLE001
            self._add_event(
                request_row=row,
                event_type="override.execution_failed",
                from_status=row.status,
                to_status=row.status,
                actor_user_id=actor_user_id,
                details_json={"error_message": str(exc)},
            )
            self.db.flush()
            raise

        before = row.status
        row.status = "executed"
        row.executed_by_user_id = actor_user_id
        row.executed_at = self.now()
        row.execution_result_json = result
        self._add_event(
            request_row=row,
            event_type="override.executed",
            from_status=before,
            to_status=row.status,
            actor_user_id=actor_user_id,
            details_json=result,
        )
        self.db.flush()
        return row

    def expire_pending(self, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID) -> int:
        now = self.now()
        rows = self.db.execute(
            select(GovernanceOverrideRequest).where(
                GovernanceOverrideRequest.organization_id == organization_id,
                GovernanceOverrideRequest.status == "pending",
                GovernanceOverrideRequest.expires_at.is_not(None),
                GovernanceOverrideRequest.expires_at < now,
            )
        ).scalars().all()
        for row in rows:
            before = row.status
            row.status = "expired"
            self._add_event(
                request_row=row,
                event_type="override.expired",
                from_status=before,
                to_status=row.status,
                actor_user_id=actor_user_id,
                details_json=None,
            )
        self.db.flush()
        return len(rows)

    def summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        since_30d = now - timedelta(days=30)
        older_24h = now - timedelta(hours=24)

        total_requests = int(
            self.db.execute(select(func.count(GovernanceOverrideRequest.id)).where(GovernanceOverrideRequest.organization_id == organization_id)).scalar_one()
        )

        def count_by_status(s: str) -> int:
            return int(
                self.db.execute(
                    select(func.count(GovernanceOverrideRequest.id)).where(
                        GovernanceOverrideRequest.organization_id == organization_id,
                        GovernanceOverrideRequest.status == s,
                    )
                ).scalar_one()
            )

        pending_requests = count_by_status("pending")
        approved_requests = count_by_status("approved")
        rejected_requests = count_by_status("rejected")
        executed_requests = count_by_status("executed")
        cancelled_requests = count_by_status("cancelled")
        expired_requests = count_by_status("expired")

        pending_approval_over_24h = int(
            self.db.execute(
                select(func.count(GovernanceOverrideRequest.id)).where(
                    GovernanceOverrideRequest.organization_id == organization_id,
                    GovernanceOverrideRequest.status == "pending",
                    GovernanceOverrideRequest.created_at < older_24h,
                )
            ).scalar_one()
        )
        overrides_executed_last_30d = int(
            self.db.execute(
                select(func.count(GovernanceOverrideRequest.id)).where(
                    GovernanceOverrideRequest.organization_id == organization_id,
                    GovernanceOverrideRequest.status == "executed",
                    GovernanceOverrideRequest.executed_at.is_not(None),
                    GovernanceOverrideRequest.executed_at >= since_30d,
                )
            ).scalar_one()
        )
        pending_expiring_within_24h = int(
            self.db.execute(
                select(func.count(GovernanceOverrideRequest.id)).where(
                    GovernanceOverrideRequest.organization_id == organization_id,
                    GovernanceOverrideRequest.status == "pending",
                    GovernanceOverrideRequest.expires_at.is_not(None),
                    GovernanceOverrideRequest.expires_at >= now,
                    GovernanceOverrideRequest.expires_at <= now + timedelta(hours=OVERRIDE_EXPIRY_WARNING_HOURS),
                )
            ).scalar_one()
        )
        approved_awaiting_execution = int(
            self.db.execute(
                select(func.count(GovernanceOverrideRequest.id)).where(
                    GovernanceOverrideRequest.organization_id == organization_id,
                    GovernanceOverrideRequest.status == "approved",
                    GovernanceOverrideRequest.executed_at.is_(None),
                )
            ).scalar_one()
        )
        execution_failed_last_30d = int(
            self.db.execute(
                select(func.count(GovernanceOverrideEvent.id)).where(
                    GovernanceOverrideEvent.organization_id == organization_id,
                    GovernanceOverrideEvent.event_type == "override.execution_failed",
                    GovernanceOverrideEvent.created_at >= since_30d,
                )
            ).scalar_one()
        )
        oldest_pending_created_at = self.db.execute(
            select(func.min(GovernanceOverrideRequest.created_at)).where(
                GovernanceOverrideRequest.organization_id == organization_id,
                GovernanceOverrideRequest.status == "pending",
            )
        ).scalar_one_or_none()
        oldest_pending_request_age_hours = None
        if oldest_pending_created_at is not None:
            oldest_pending_request_age_hours = round(
                max(0.0, (now - (self.as_utc(oldest_pending_created_at) or now)).total_seconds() / 3600.0),
                3,
            )
        context_flags: list[str] = []
        if pending_requests == 0:
            context_flags.append("no_pending_requests")
        if pending_approval_over_24h > 0:
            context_flags.append("stale_pending_requests")
        if pending_expiring_within_24h > 0:
            context_flags.append("pending_expiring_within_24h")
        if approved_awaiting_execution > 0:
            context_flags.append("approved_waiting_execution")
        if execution_failed_last_30d > 0:
            context_flags.append("recent_execution_failures")

        return {
            "total_requests": total_requests,
            "pending_requests": pending_requests,
            "approved_requests": approved_requests,
            "rejected_requests": rejected_requests,
            "executed_requests": executed_requests,
            "cancelled_requests": cancelled_requests,
            "expired_requests": expired_requests,
            "pending_approval_over_24h": pending_approval_over_24h,
            "overrides_executed_last_30d": overrides_executed_last_30d,
            "pending_expiring_within_24h": pending_expiring_within_24h,
            "approved_awaiting_execution": approved_awaiting_execution,
            "execution_failed_last_30d": execution_failed_last_30d,
            "oldest_pending_request_age_hours": oldest_pending_request_age_hours,
            "context_flags": context_flags,
        }

    def eligible_approvers(self, *, row: GovernanceOverrideRequest) -> list[dict[str, Any]]:
        already_reviewed = {
            approval.approver_user_id
            for approval in self.repo.list_approvals(organization_id=row.organization_id, override_request_id=row.id)
        }

        query = (
            select(Membership.user_id, Role.name)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == row.organization_id,
                Membership.status == "active",
                Membership.user_id != row.requested_by_user_id,
            )
        )
        if row.approver_role_names_json:
            query = query.where(Role.name.in_(row.approver_role_names_json))

        rows = self.db.execute(query).all()
        return [
            {"user_id": user_id, "role_name": role_name}
            for user_id, role_name in rows
            if user_id not in already_reviewed
        ]

    def template_summary(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        since_30d = self.now() - timedelta(days=30)

        def count_templates(where_clause) -> int:
            return int(self.db.execute(select(func.count(GovernanceOverrideTemplate.id)).where(*where_clause)).scalar_one())

        total_templates = count_templates([GovernanceOverrideTemplate.organization_id == organization_id])
        active_templates = count_templates([GovernanceOverrideTemplate.organization_id == organization_id, GovernanceOverrideTemplate.status == "active"])
        inactive_templates = count_templates([GovernanceOverrideTemplate.organization_id == organization_id, GovernanceOverrideTemplate.status == "inactive"])
        archived_templates = count_templates([GovernanceOverrideTemplate.organization_id == organization_id, GovernanceOverrideTemplate.status == "archived"])
        templates_with_conditional_rules = int(
            self.db.execute(
                select(func.count(GovernanceOverrideTemplate.id)).where(
                    GovernanceOverrideTemplate.organization_id == organization_id,
                    GovernanceOverrideTemplate.condition_rules_json.is_not(None),
                )
            ).scalar_one()
        )

        return {
            "total_templates": total_templates,
            "active_templates": active_templates,
            "inactive_templates": inactive_templates,
            "archived_templates": archived_templates,
            "templates_with_conditional_rules": templates_with_conditional_rules,
            "template_bound_requests_last_30d": self.repo.count_template_bound_requests_since(
                organization_id=organization_id,
                since=since_30d,
            ),
        }
