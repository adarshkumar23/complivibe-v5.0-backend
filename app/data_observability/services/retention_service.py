import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_asset import DataAsset
from app.models.data_retention_policy import DataRetentionPolicy
from app.models.data_retention_review import DataRetentionReview
from app.models.email_outbox import EmailOutbox
from app.models.task import Task
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_ACTIONS = {"flag", "archive", "delete"}
ALLOWED_REVIEW_STATUS = {"pending", "in_review", "completed", "waived"}


class RetentionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _retention_due_at(cls, asset: DataAsset) -> datetime:
        # retention_review_date is the field actually exposed for editing via the asset API
        # (set explicitly by a user, or auto-set when a retention policy is applied -- see
        # apply_policy_to_asset). Editing it must have real effect on the sweep. Only fall
        # back to created_at + retention_policy_days for assets that predate having a review
        # date set at all.
        if asset.retention_review_date is not None:
            return cls._as_utc(datetime.combine(asset.retention_review_date, datetime.min.time()))
        return cls._as_utc(asset.created_at) + timedelta(days=int(asset.retention_policy_days or 0))

    def _require_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> DataRetentionPolicy:
        row = self.db.execute(
            select(DataRetentionPolicy).where(
                DataRetentionPolicy.organization_id == org_id,
                DataRetentionPolicy.id == policy_id,
                DataRetentionPolicy.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention policy not found")
        return row

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

    def _require_review(self, org_id: uuid.UUID, review_id: uuid.UUID) -> DataRetentionReview:
        row = self.db.execute(
            select(DataRetentionReview).where(
                DataRetentionReview.organization_id == org_id,
                DataRetentionReview.id == review_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention review not found")
        return row

    def create_policy(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DataRetentionPolicy:
        payload = data.model_dump()
        payload["action_on_expiry"] = validate_choice(payload["action_on_expiry"], ALLOWED_ACTIONS, "action_on_expiry")
        now = self.utcnow()
        row = DataRetentionPolicy(
            organization_id=org_id,
            name=payload["name"],
            description=payload.get("description"),
            retention_days=payload["retention_days"],
            max_retention_days=payload.get("max_retention_days"),
            applies_to_classification_types=payload.get("applies_to_classification_types") or [],
            applies_to_sensitivity_tiers=payload.get("applies_to_sensitivity_tiers") or [],
            legal_basis=payload.get("legal_basis"),
            action_on_expiry=payload["action_on_expiry"],
            legal_hold=bool(payload.get("legal_hold", False)),
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.policy_created",
            entity_type="data_retention_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "name": row.name,
                "retention_days": row.retention_days,
                "action_on_expiry": row.action_on_expiry,
                "legal_hold": row.legal_hold,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> DataRetentionPolicy:
        return self._require_policy(org_id, policy_id)

    def list_policies(self, org_id: uuid.UUID, is_active: bool | None = None) -> list[DataRetentionPolicy]:
        stmt = select(DataRetentionPolicy).where(
            DataRetentionPolicy.organization_id == org_id,
            DataRetentionPolicy.deleted_at.is_(None),
        )
        if is_active is not None:
            stmt = stmt.where(DataRetentionPolicy.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(DataRetentionPolicy.created_at.desc())).scalars().all()

    def update_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, data) -> DataRetentionPolicy:
        row = self._require_policy(org_id, policy_id)
        payload = data.model_dump(exclude_unset=True)
        if "action_on_expiry" in payload and payload["action_on_expiry"] not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid action_on_expiry")

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.policy_updated",
            entity_type="data_retention_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={
                "name": row.name,
                "retention_days": row.retention_days,
                "action_on_expiry": row.action_on_expiry,
                "legal_hold": row.legal_hold,
            },
            metadata_json={"source": "api"},
        )
        return row

    def set_legal_hold(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        legal_hold: bool,
        updated_by: uuid.UUID,
    ) -> DataRetentionPolicy:
        row = self._require_policy(org_id, policy_id)
        row.legal_hold = legal_hold
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="data_retention.legal_hold_updated",
            entity_type="data_retention_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=updated_by,
            after_json={"legal_hold": row.legal_hold},
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> DataRetentionPolicy:
        row = self._require_policy(org_id, policy_id)
        row.is_active = False
        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.policy_deactivated",
            entity_type="data_retention_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def apply_policy_to_asset(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> DataAsset:
        asset = self._require_asset(org_id, data_asset_id)
        policy = self._require_policy(org_id, policy_id)
        asset.retention_policy_days = policy.retention_days
        asset.retention_review_date = (self.utcnow() + timedelta(days=policy.retention_days)).date()
        asset.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.policy_applied",
            entity_type="data_asset",
            entity_id=asset.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"policy_id": str(policy.id), "retention_policy_days": asset.retention_policy_days},
            metadata_json={"source": "api"},
        )
        return asset

    def _find_applicable_policy(self, org_id: uuid.UUID, asset: DataAsset) -> DataRetentionPolicy | None:
        policies = self.db.execute(
            select(DataRetentionPolicy).where(
                DataRetentionPolicy.organization_id == org_id,
                DataRetentionPolicy.is_active.is_(True),
                DataRetentionPolicy.deleted_at.is_(None),
            )
        ).scalars().all()
        for policy in policies:
            class_types = list(policy.applies_to_classification_types or [])
            sensitivity = list(policy.applies_to_sensitivity_tiers or [])
            class_match = (not class_types) or (asset.classification_type in class_types)
            sensitivity_match = (not sensitivity) or (asset.sensitivity_tier in sensitivity)
            if class_match and sensitivity_match and asset.retention_policy_days == policy.retention_days:
                return policy
        return None

    def _queue_reminder(self, org_id: uuid.UUID, recipient_user_id: uuid.UUID | None, asset: DataAsset, created_by: uuid.UUID | None) -> int:
        if recipient_user_id is None:
            return 0
        user = self.db.execute(
            select(User).where(
                User.id == recipient_user_id,
                User.is_active.is_(True),
                User.status == "active",
                User.email.is_not(None),
            )
        ).scalar_one_or_none()
        if user is None or not user.email:
            return 0

        self.db.add(
            EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type="data_retention.review.required",
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=f"Retention review required: {asset.name}",
                body_text=f"Data asset '{asset.name}' requires retention review.",
                body_html=None,
                status="pending",
                priority="normal",
                scheduled_at=None,
                queued_at=self.utcnow(),
                attempt_count=0,
                max_attempts=3,
                metadata_json={"source": "data_retention_sweep", "data_asset_id": str(asset.id)},
                created_by_user_id=created_by,
            )
        )
        self.db.flush()
        return 1

    def run_retention_sweep(self, org_id: uuid.UUID | None = None) -> dict:
        now = self.utcnow()
        stmt = select(DataAsset).where(
            DataAsset.deleted_at.is_(None),
            DataAsset.status == "active",
            DataAsset.retention_policy_days.is_not(None),
        )
        if org_id is not None:
            stmt = stmt.where(DataAsset.organization_id == org_id)
        assets = self.db.execute(stmt).scalars().all()

        assets_flagged = 0
        tasks_created = 0
        reminders_queued = 0

        for asset in assets:
            if asset.retention_policy_days is None:
                continue
            due_at = self._retention_due_at(asset)
            if due_at > now:
                continue

            pending = self.db.execute(
                select(DataRetentionReview).where(
                    DataRetentionReview.organization_id == asset.organization_id,
                    DataRetentionReview.data_asset_id == asset.id,
                    DataRetentionReview.status == "pending",
                )
            ).scalar_one_or_none()
            if pending is not None:
                continue

            policy = self._find_applicable_policy(asset.organization_id, asset)
            if policy is not None and bool(policy.legal_hold):
                continue
            required_action = policy.action_on_expiry if policy else "flag"
            days_overdue = (now.date() - due_at.date()).days

            assignee = asset.custodian_id or asset.owner_id
            priority = "urgent" if required_action in {"archive", "delete"} else "normal"
            task = Task(
                organization_id=asset.organization_id,
                title=f"Retention review: {asset.name}",
                description=(
                    f"Data asset '{asset.name}' has exceeded its configured retention period of "
                    f"{asset.retention_policy_days} days. Required action: {required_action}. "
                    f"Data custodian: {str(assignee) if assignee else 'unassigned'}"
                ),
                status="open",
                priority=priority,
                task_type="data_retention_review",
                owner_user_id=assignee,
                created_by_user_id=policy.created_by if policy else asset.created_by,
                due_date=now,
                linked_entity_type="data_asset",
                linked_entity_id=asset.id,
                source="system",
                reminder_status="none",
                metadata_json={"required_action": required_action},
            )
            self.db.add(task)
            self.db.flush()
            tasks_created += 1

            review = DataRetentionReview(
                organization_id=asset.organization_id,
                data_asset_id=asset.id,
                policy_id=policy.id if policy else None,
                status="pending",
                review_type="retention_expired",
                days_overdue=days_overdue,
                required_action=required_action,
                linked_task_id=task.id,
                resolved_by=None,
                resolved_at=None,
                evidence_notes=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(review)
            self.db.flush()

            asset.retention_review_date = now.date()
            asset.updated_at = now
            reminders_queued += self._queue_reminder(asset.organization_id, assignee, asset, policy.created_by if policy else asset.created_by)
            assets_flagged += 1

            AuditService(self.db).write_audit_log(
                action="retention.asset_flagged",
                entity_type="data_retention_review",
                entity_id=review.id,
                organization_id=asset.organization_id,
                actor_user_id=None,
                after_json={"data_asset_id": str(asset.id), "required_action": required_action, "linked_task_id": str(task.id)},
                metadata_json={"source": "retention_sweep"},
            )

        return {
            "assets_flagged": assets_flagged,
            "tasks_created": tasks_created,
            "reminders_queued": reminders_queued,
        }

    def resolve_review(self, org_id: uuid.UUID, review_id: uuid.UUID, resolved_by: uuid.UUID, evidence_notes: str | None) -> DataRetentionReview:
        row = self._require_review(org_id, review_id)
        row.status = "completed"
        row.resolved_by = resolved_by
        row.resolved_at = self.utcnow()
        row.evidence_notes = evidence_notes
        row.updated_at = row.resolved_at

        # Push the asset's next review date out to today + retention_days
        # (not just "today"). run_retention_sweep() flags an asset whenever
        # retention_review_date <= now, so leaving it at today -- or never
        # advancing it at all -- means the very next sweep sees the asset as
        # still overdue and immediately creates a brand new review/task for
        # the one that was just resolved, i.e. an infinite reflagging loop.
        asset = self.db.execute(
            select(DataAsset).where(
                DataAsset.id == row.data_asset_id,
                DataAsset.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if asset is not None:
            retention_days = None
            if row.policy_id is not None:
                policy = self.db.execute(
                    select(DataRetentionPolicy).where(DataRetentionPolicy.id == row.policy_id)
                ).scalar_one_or_none()
                if policy is not None:
                    retention_days = policy.retention_days
            if retention_days is None:
                retention_days = asset.retention_policy_days
            if retention_days is not None:
                asset.retention_review_date = (self.utcnow() + timedelta(days=int(retention_days))).date()
                asset.updated_at = self.utcnow()

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.review_resolved",
            entity_type="data_retention_review",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=resolved_by,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def waive_review(self, org_id: uuid.UUID, review_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> DataRetentionReview:
        row = self._require_review(org_id, review_id)
        row.status = "waived"
        row.resolved_by = user_id
        row.resolved_at = self.utcnow()
        row.evidence_notes = reason
        row.updated_at = row.resolved_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="retention.review_waived",
            entity_type="data_retention_review",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def list_reviews(
        self,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        data_asset_id: uuid.UUID | None = None,
    ) -> list[DataRetentionReview]:
        stmt = select(DataRetentionReview).where(DataRetentionReview.organization_id == org_id)
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_REVIEW_STATUS, "status")
            stmt = stmt.where(DataRetentionReview.status == status_filter)
        if data_asset_id is not None:
            stmt = stmt.where(DataRetentionReview.data_asset_id == data_asset_id)
        return self.db.execute(stmt.order_by(DataRetentionReview.created_at.desc())).scalars().all()

    def get_retention_summary(self, org_id: uuid.UUID) -> dict:
        now = self.utcnow()
        assets = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.deleted_at.is_(None),
                DataAsset.retention_policy_days.is_not(None),
            )
        ).scalars().all()

        total_assets_with_policy = len(assets)
        expired_count = 0
        within_count = 0
        for asset in assets:
            due_at = self._retention_due_at(asset)
            if due_at <= now:
                expired_count += 1
            else:
                within_count += 1

        pending_reviews = int(
            self.db.execute(
                select(func.count(DataRetentionReview.id)).where(
                    DataRetentionReview.organization_id == org_id,
                    DataRetentionReview.status == "pending",
                )
            ).scalar_one()
            or 0
        )

        by_required_action_rows = self.db.execute(
            select(DataRetentionReview.required_action, func.count(DataRetentionReview.id))
            .where(DataRetentionReview.organization_id == org_id)
            .group_by(DataRetentionReview.required_action)
        ).all()
        by_required_action = {str(action): int(count) for action, count in by_required_action_rows}

        compliance_rate = 0.0
        if total_assets_with_policy > 0:
            compliance_rate = round((within_count / total_assets_with_policy) * 100.0, 2)

        return {
            "total_assets_with_policy": total_assets_with_policy,
            "expired_count": expired_count,
            "pending_reviews": pending_reviews,
            "by_required_action": by_required_action,
            "compliance_rate": compliance_rate,
        }


def run_daily_data_retention_sweep(db: Session) -> dict:
    return RetentionService(db).run_retention_sweep(org_id=None)
