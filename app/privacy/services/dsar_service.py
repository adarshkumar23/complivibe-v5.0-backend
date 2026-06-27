import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.data_subject_request import DataSubjectRequest
from app.models.dsr_fulfillment_step import DSRFulfillmentStep
from app.models.dsr_sla_tracking import DSRSLATracking
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService

ALLOWED_REQUEST_TYPES = {"access", "erasure", "portability", "rectification", "restriction", "objection"}
ALLOWED_STATUS = {
    "received",
    "identity_verification",
    "in_progress",
    "on_hold",
    "fulfilled",
    "refused",
    "partially_fulfilled",
    "withdrawn",
}
ALLOWED_FRAMEWORKS = {"gdpr", "ccpa", "dpdp", "lgpd", "custom"}
ALLOWED_STEP_TYPES = {"identity_check", "locate_data", "review_data", "prepare_response", "legal_review", "send_response", "custom"}
ALLOWED_STEP_STATUS = {"pending", "in_progress", "completed", "skipped"}

TERMINAL_STATUSES = {"fulfilled", "refused", "partially_fulfilled", "withdrawn"}

STATUS_TRANSITIONS: dict[str, set[str]] = {
    "received": {"identity_verification", "in_progress", "withdrawn"},
    "identity_verification": {"in_progress", "refused", "withdrawn"},
    "in_progress": {"on_hold", "fulfilled", "partially_fulfilled", "refused"},
    "on_hold": {"in_progress", "withdrawn"},
    "fulfilled": set(),
    "refused": set(),
    "partially_fulfilled": set(),
    "withdrawn": set(),
}


class DSARService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_request(self, org_id: uuid.UUID, request_id: uuid.UUID) -> DataSubjectRequest:
        row = self.db.execute(
            select(DataSubjectRequest).where(
                DataSubjectRequest.organization_id == org_id,
                DataSubjectRequest.id == request_id,
                DataSubjectRequest.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data subject request not found")
        return row

    def _require_step(self, org_id: uuid.UUID, request_id: uuid.UUID, step_id: uuid.UUID) -> DSRFulfillmentStep:
        row = self.db.execute(
            select(DSRFulfillmentStep).where(
                DSRFulfillmentStep.organization_id == org_id,
                DSRFulfillmentStep.request_id == request_id,
                DSRFulfillmentStep.id == step_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fulfillment step not found")
        return row

    def _require_user_membership(self, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User is not an active organization member")
        return row

    def _compute_deadline_days(self, regulatory_framework: str, requested_days: int | None = None) -> int:
        if requested_days is not None:
            return int(requested_days)
        if regulatory_framework == "ccpa":
            return 45
        return 30

    def _next_request_ref(self, org_id: uuid.UUID, year: int, sequence: int | None = None) -> str:
        if sequence is None:
            like_prefix = f"DSR-{year}-%"
            count = int(
                self.db.execute(
                    select(func.count(DataSubjectRequest.id)).where(
                        DataSubjectRequest.organization_id == org_id,
                        DataSubjectRequest.request_ref.like(like_prefix),
                    )
                ).scalar_one()
                or 0
            )
            sequence = count + 1
        return f"DSR-{year}-{sequence:03d}"

    def _queue_outbox(self, org_id: uuid.UUID, to_user: User, subject: str, body: str, event_type: str, created_by: uuid.UUID | None) -> None:
        now = self.utcnow()
        outbox = EmailOutbox(
            organization_id=org_id,
            template_id=None,
            event_type=event_type,
            recipient_email=to_user.email,
            recipient_user_id=to_user.id,
            subject=subject,
            body_text=body,
            body_html=f"<p>{body}</p>",
            status="pending",
            priority="high",
            scheduled_at=None,
            queued_at=now,
            sent_at=None,
            failed_at=None,
            cancelled_at=None,
            locked_at=None,
            locked_by=None,
            lock_expires_at=None,
            last_attempt_at=None,
            next_attempt_at=None,
            dead_lettered_at=None,
            attempt_count=0,
            max_attempts=3,
            last_error=None,
            provider=None,
            provider_message_id=None,
            metadata_json={"source": "dsr"},
            worker_metadata_json=None,
            created_by_user_id=created_by,
        )
        self.db.add(outbox)
        self.db.flush()

    def _org_handlers(self, org_id: uuid.UUID) -> list[User]:
        rows = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
                Role.name.in_(["owner", "admin", "compliance_manager"]),
                User.email.is_not(None),
            )
        ).scalars().all()
        dedup: dict[uuid.UUID, User] = {row.id: row for row in rows}
        return list(dedup.values())

    def _create_sla_tracking(self, row: DataSubjectRequest) -> DSRSLATracking:
        now = self.utcnow()
        sla = DSRSLATracking(
            organization_id=row.organization_id,
            request_id=row.id,
            effective_deadline=row.extension_deadline or row.response_deadline,
            response_breached=False,
            breach_notified_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(sla)
        self.db.flush()
        return sla

    def _get_sla(self, org_id: uuid.UUID, request_id: uuid.UUID) -> DSRSLATracking:
        row = self.db.execute(
            select(DSRSLATracking).where(
                DSRSLATracking.organization_id == org_id,
                DSRSLATracking.request_id == request_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA tracking row not found")
        return row

    def create_request(self, org_id: uuid.UUID, data, created_by: uuid.UUID | None = None) -> DataSubjectRequest:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        if payload.get("request_type") not in ALLOWED_REQUEST_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid request_type")
        if payload.get("regulatory_framework", "gdpr") not in ALLOWED_FRAMEWORKS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid regulatory_framework")

        regulatory_framework = payload.get("regulatory_framework", "gdpr")
        deadline_days = self._compute_deadline_days(regulatory_framework, payload.get("deadline_days"))
        received_at = self.utcnow()
        response_deadline = received_at + timedelta(days=deadline_days)

        assigned_handler_id = payload.get("assigned_handler_id")
        assigned_handler: User | None = None
        if assigned_handler_id is not None:
            assigned_handler = self._require_user_membership(org_id, assigned_handler_id)

        year = received_at.year
        base_ref = self._next_request_ref(org_id, year)
        base_sequence = int(base_ref.rsplit("-", 1)[1])

        for attempt in range(2):
            request_ref = self._next_request_ref(org_id, year, base_sequence + attempt)
            row = DataSubjectRequest(
                organization_id=org_id,
                request_ref=request_ref,
                request_type=payload["request_type"],
                subject_name=payload["subject_name"],
                subject_email=str(payload["subject_email"]),
                subject_identifier=payload.get("subject_identifier"),
                description=payload.get("description"),
                status="received",
                regulatory_framework=regulatory_framework,
                response_deadline=response_deadline,
                deadline_days=deadline_days,
                extension_granted=False,
                extension_deadline=None,
                extension_reason=None,
                identity_verified=False,
                identity_verified_at=None,
                identity_verified_by=None,
                assigned_handler_id=assigned_handler_id,
                response_notes=None,
                refusal_reason=None,
                received_at=received_at,
                fulfilled_at=None,
                created_by=created_by,
                created_at=received_at,
                updated_at=received_at,
                deleted_at=None,
            )
            self.db.add(row)
            try:
                self.db.flush()
                self._create_sla_tracking(row)

                if assigned_handler is not None:
                    self._queue_outbox(
                        org_id,
                        assigned_handler,
                        subject=f"New DSR assigned: {row.request_ref}",
                        body=f"A new data subject request {row.request_ref} has been assigned to you.",
                        event_type="dsr.assigned_notification",
                        created_by=created_by,
                    )
                else:
                    for handler in self._org_handlers(org_id):
                        self._queue_outbox(
                            org_id,
                            handler,
                            subject=f"New DSR received: {row.request_ref}",
                            body=f"A new data subject request {row.request_ref} has been received.",
                            event_type="dsr.received_notification",
                            created_by=created_by,
                        )

                AuditService(self.db).write_audit_log(
                    action="dsr.created",
                    entity_type="data_subject_request",
                    entity_id=row.id,
                    organization_id=org_id,
                    actor_user_id=created_by,
                    after_json={
                        "request_ref": row.request_ref,
                        "request_type": row.request_type,
                        "status": row.status,
                        "framework": row.regulatory_framework,
                    },
                    metadata_json={"source": "public" if created_by is None else "api"},
                )
                return row
            except IntegrityError:
                self.db.rollback()
                if attempt == 1:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to generate unique request_ref")

        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to generate unique request_ref")

    def get_request(self, org_id: uuid.UUID, request_id: uuid.UUID) -> DataSubjectRequest:
        return self._require_request(org_id, request_id)

    def get_by_ref(self, org_id: uuid.UUID, request_ref: str) -> DataSubjectRequest:
        row = self.db.execute(
            select(DataSubjectRequest).where(
                DataSubjectRequest.organization_id == org_id,
                DataSubjectRequest.request_ref == request_ref,
                DataSubjectRequest.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data subject request not found")
        return row

    def list_requests(
        self,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        request_type: str | None = None,
        assigned_handler_id: uuid.UUID | None = None,
        overdue_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[DataSubjectRequest]:
        stmt = select(DataSubjectRequest).where(
            DataSubjectRequest.organization_id == org_id,
            DataSubjectRequest.deleted_at.is_(None),
        )

        if status_filter is not None:
            if status_filter not in ALLOWED_STATUS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status filter")
            stmt = stmt.where(DataSubjectRequest.status == status_filter)
        if request_type is not None:
            if request_type not in ALLOWED_REQUEST_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid request_type filter")
            stmt = stmt.where(DataSubjectRequest.request_type == request_type)
        if assigned_handler_id is not None:
            stmt = stmt.where(DataSubjectRequest.assigned_handler_id == assigned_handler_id)

        if overdue_only:
            now = self.utcnow()
            stmt = stmt.join(DSRSLATracking, DSRSLATracking.request_id == DataSubjectRequest.id).where(
                DSRSLATracking.effective_deadline < now,
                DataSubjectRequest.status.not_in(list(TERMINAL_STATUSES)),
            )

        return self.db.execute(
            stmt.order_by(DataSubjectRequest.received_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def transition_status(
        self,
        org_id: uuid.UUID,
        request_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
        notes: str | None = None,
        refusal_reason: str | None = None,
    ) -> DataSubjectRequest:
        row = self._require_request(org_id, request_id)
        if new_status not in ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid new_status")

        allowed = STATUS_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        row.status = new_status
        if notes:
            row.response_notes = notes
        if refusal_reason:
            row.refusal_reason = refusal_reason
        if new_status in {"fulfilled", "partially_fulfilled"}:
            row.fulfilled_at = self.utcnow()
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dsr.status_transitioned",
            entity_type="data_subject_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else None},
            metadata_json={"source": "api"},
        )
        return row

    def assign_handler(self, org_id: uuid.UUID, request_id: uuid.UUID, handler_id: uuid.UUID, user_id: uuid.UUID) -> DataSubjectRequest:
        row = self._require_request(org_id, request_id)
        handler = self._require_user_membership(org_id, handler_id)
        row.assigned_handler_id = handler_id
        row.updated_at = self.utcnow()
        self.db.flush()

        self._queue_outbox(
            org_id,
            handler,
            subject=f"DSR assigned: {row.request_ref}",
            body=f"You have been assigned data subject request {row.request_ref}.",
            event_type="dsr.assigned_notification",
            created_by=user_id,
        )

        AuditService(self.db).write_audit_log(
            action="dsr.assigned",
            entity_type="data_subject_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"assigned_handler_id": str(handler_id)},
            metadata_json={"source": "api"},
        )
        return row

    def verify_identity(self, org_id: uuid.UUID, request_id: uuid.UUID, user_id: uuid.UUID) -> DataSubjectRequest:
        row = self._require_request(org_id, request_id)
        if row.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot verify identity for terminal request")

        now = self.utcnow()
        row.identity_verified = True
        row.identity_verified_at = now
        row.identity_verified_by = user_id

        if row.status in {"received", "identity_verification"}:
            row.status = "in_progress"
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dsr.identity_verified",
            entity_type="data_subject_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"identity_verified": True, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def grant_extension(self, org_id: uuid.UUID, request_id: uuid.UUID, reason: str, user_id: uuid.UUID) -> DataSubjectRequest:
        row = self._require_request(org_id, request_id)
        extension_deadline = row.received_at + timedelta(days=60)
        row.extension_granted = True
        row.extension_reason = reason
        row.extension_deadline = extension_deadline
        row.updated_at = self.utcnow()

        sla = self._get_sla(org_id, request_id)
        sla.effective_deadline = extension_deadline
        sla.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dsr.extension_granted",
            entity_type="data_subject_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"extension_deadline": extension_deadline.isoformat(), "reason": reason},
            metadata_json={"source": "api"},
        )
        return row

    def add_fulfillment_step(self, org_id: uuid.UUID, request_id: uuid.UUID, data, user_id: uuid.UUID | None = None) -> DSRFulfillmentStep:
        self._require_request(org_id, request_id)
        payload = data.model_dump()
        if payload.get("step_type") not in ALLOWED_STEP_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid step_type")
        if payload.get("assigned_to") is not None:
            self._require_user_membership(org_id, payload["assigned_to"])

        now = self.utcnow()
        order_index = payload.get("order_index")
        if order_index is None:
            max_index = self.db.execute(
                select(func.max(DSRFulfillmentStep.order_index)).where(
                    DSRFulfillmentStep.organization_id == org_id,
                    DSRFulfillmentStep.request_id == request_id,
                )
            ).scalar_one_or_none()
            order_index = int(max_index or 0) + 1

        row = DSRFulfillmentStep(
            organization_id=org_id,
            request_id=request_id,
            step_type=payload["step_type"],
            description=payload["description"],
            status="pending",
            assigned_to=payload.get("assigned_to"),
            due_date=payload.get("due_date"),
            completed_at=None,
            notes=payload.get("notes"),
            order_index=int(order_index),
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dsr.step_added",
            entity_type="dsr_fulfillment_step",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"request_id": str(request_id), "step_type": row.step_type, "order_index": row.order_index},
            metadata_json={"source": "api"},
        )
        return row

    def update_fulfillment_step(self, org_id: uuid.UUID, request_id: uuid.UUID, step_id: uuid.UUID, data) -> DSRFulfillmentStep:
        row = self._require_step(org_id, request_id, step_id)
        payload = data.model_dump(exclude_unset=True)

        if "step_type" in payload and payload["step_type"] not in ALLOWED_STEP_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid step_type")
        if "status" in payload and payload["status"] not in ALLOWED_STEP_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid step status")
        if "assigned_to" in payload and payload["assigned_to"] is not None:
            self._require_user_membership(org_id, payload["assigned_to"])

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def complete_step(self, org_id: uuid.UUID, request_id: uuid.UUID, step_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> DSRFulfillmentStep:
        row = self._require_step(org_id, request_id, step_id)
        row.status = "completed"
        row.completed_at = self.utcnow()
        if notes:
            row.notes = notes
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dsr.step_completed",
            entity_type="dsr_fulfillment_step",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"request_id": str(request_id), "completed_at": row.completed_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def list_steps(self, org_id: uuid.UUID, request_id: uuid.UUID) -> list[DSRFulfillmentStep]:
        self._require_request(org_id, request_id)
        return self.db.execute(
            select(DSRFulfillmentStep)
            .where(
                DSRFulfillmentStep.organization_id == org_id,
                DSRFulfillmentStep.request_id == request_id,
            )
            .order_by(DSRFulfillmentStep.order_index.asc(), DSRFulfillmentStep.created_at.asc())
        ).scalars().all()

    def run_sla_sweep(self) -> dict:
        now = self.utcnow()
        rows = self.db.execute(
            select(DSRSLATracking, DataSubjectRequest)
            .join(DataSubjectRequest, DataSubjectRequest.id == DSRSLATracking.request_id)
            .where(
                DSRSLATracking.effective_deadline < now,
                DSRSLATracking.response_breached.is_(False),
                DataSubjectRequest.deleted_at.is_(None),
                DataSubjectRequest.status.not_in(list(TERMINAL_STATUSES)),
            )
        ).all()

        breached = 0
        reminders_queued = 0
        for sla, request in rows:
            sla.response_breached = True
            sla.breach_notified_at = now
            sla.updated_at = now
            breached += 1

            if request.assigned_handler_id is not None:
                handler = self.db.get(User, request.assigned_handler_id)
                if handler is not None and handler.email:
                    self._queue_outbox(
                        request.organization_id,
                        handler,
                        subject=f"DSR SLA breached: {request.request_ref}",
                        body=f"Data subject request {request.request_ref} is past its effective deadline.",
                        event_type="dsr.sla_breach_notification",
                        created_by=None,
                    )
                    reminders_queued += 1

            AuditService(self.db).write_audit_log(
                action="dsr.sla_breached",
                entity_type="data_subject_request",
                entity_id=request.id,
                organization_id=request.organization_id,
                actor_user_id=None,
                after_json={"request_ref": request.request_ref, "effective_deadline": sla.effective_deadline.isoformat()},
                metadata_json={"source": "scheduler"},
            )

        return {"requests_checked": len(rows), "breaches_marked": breached, "reminders_queued": reminders_queued}

    def get_dsr_summary(self, org_id: uuid.UUID) -> dict:
        base_filters = [
            DataSubjectRequest.organization_id == org_id,
            DataSubjectRequest.deleted_at.is_(None),
        ]
        total = int(self.db.execute(select(func.count(DataSubjectRequest.id)).where(*base_filters)).scalar_one() or 0)

        status_rows = self.db.execute(
            select(DataSubjectRequest.status, func.count(DataSubjectRequest.id)).where(*base_filters).group_by(DataSubjectRequest.status)
        ).all()
        by_status = {str(k): int(v) for k, v in status_rows}

        type_rows = self.db.execute(
            select(DataSubjectRequest.request_type, func.count(DataSubjectRequest.id)).where(*base_filters).group_by(DataSubjectRequest.request_type)
        ).all()
        by_type = {str(k): int(v) for k, v in type_rows}

        fw_rows = self.db.execute(
            select(DataSubjectRequest.regulatory_framework, func.count(DataSubjectRequest.id))
            .where(*base_filters)
            .group_by(DataSubjectRequest.regulatory_framework)
        ).all()
        by_framework = {str(k): int(v) for k, v in fw_rows}

        overdue_count = int(
            self.db.execute(
                select(func.count(DataSubjectRequest.id))
                .join(DSRSLATracking, DSRSLATracking.request_id == DataSubjectRequest.id)
                .where(
                    *base_filters,
                    DSRSLATracking.effective_deadline < self.utcnow(),
                    DataSubjectRequest.status.not_in(list(TERMINAL_STATUSES)),
                )
            ).scalar_one()
            or 0
        )

        fulfilled_rows = self.db.execute(
            select(DataSubjectRequest, DSRSLATracking)
            .join(DSRSLATracking, DSRSLATracking.request_id == DataSubjectRequest.id)
            .where(
                *base_filters,
                DataSubjectRequest.status.in_(["fulfilled", "partially_fulfilled"]),
                DataSubjectRequest.fulfilled_at.is_not(None),
            )
        ).all()

        if fulfilled_rows:
            avg_days_to_fulfill = round(
                sum((row.fulfilled_at - row.received_at).total_seconds() / 86400 for row, _sla in fulfilled_rows) / len(fulfilled_rows),
                2,
            )
            within_deadline = sum(1 for row, sla in fulfilled_rows if row.fulfilled_at <= sla.effective_deadline)
            sla_compliance_rate = round((within_deadline / len(fulfilled_rows)) * 100, 2)
        else:
            avg_days_to_fulfill = 0.0
            sla_compliance_rate = 100.0

        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_framework": by_framework,
            "overdue_count": overdue_count,
            "avg_days_to_fulfill": avg_days_to_fulfill,
            "sla_compliance_rate": sla_compliance_rate,
        }

    def submit_public_request(self, data) -> dict:
        payload = data.model_dump()
        org_id = payload.pop("organization_id")
        row = self.create_request(org_id, payload, created_by=None)
        return {
            "request_ref": row.request_ref,
            "response_deadline": row.response_deadline,
            "message": "Request received.",
        }


def run_daily_dsr_sla_sweep(db: Session) -> dict:
    return DSARService(db).run_sla_sweep()
