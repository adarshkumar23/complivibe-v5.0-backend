import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.services.audit_service import AuditService


class EvidenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def calculate_freshness_status(cls, valid_until: datetime | None) -> str:
        if valid_until is None:
            return "unknown"

        now = cls.now()
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until < now:
            return "expired"
        if valid_until <= now + timedelta(days=30):
            return "expiring_soon"
        return "current"

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def require_evidence_in_org(self, organization_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        evidence = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == evidence_id,
                EvidenceItem.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return evidence

    def set_review_status_and_emit(
        self,
        organization_id: uuid.UUID,
        evidence_id: uuid.UUID,
        *,
        review_status: str,
        review_notes: str | None,
        reviewed_by_user_id: uuid.UUID,
        triggered_by: str = "user_action",
    ) -> tuple[EvidenceItem, str]:
        evidence = self.require_evidence_in_org(organization_id, evidence_id)
        previous_status = evidence.review_status
        evidence.review_status = review_status
        evidence.review_notes = review_notes
        evidence.reviewed_by_user_id = reviewed_by_user_id
        evidence.reviewed_at = self.now()
        self.db.flush()

        if previous_status != evidence.review_status:
            EventBus.get_instance().emit(
                EventType.EVIDENCE_STATUS_CHANGED,
                EventPayload(
                    org_id=organization_id,
                    entity_type="evidence",
                    entity_id=evidence.id,
                    event_type=EventType.EVIDENCE_STATUS_CHANGED,
                    previous_value=previous_status,
                    new_value=evidence.review_status,
                    triggered_by=triggered_by,
                    db=self.db,
                ),
            )

        return evidence, previous_status

    def readiness_summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        total_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                )
            ).scalar_one()
        )

        verified_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "verified",
                )
            ).scalar_one()
        )

        needs_review_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                )
            ).scalar_one()
        )

        rejected_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "rejected",
                )
            ).scalar_one()
        )

        expired_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        controls_total = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )

        controls_with_any_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                )
            ).scalar_one()
        )

        controls_with_verified_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "verified",
                )
            ).scalar_one()
        )

        controls_with_expired_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        return {
            "total_evidence_items": total_evidence_items,
            "verified_evidence_items": verified_evidence_items,
            "needs_review_evidence_items": needs_review_evidence_items,
            "rejected_evidence_items": rejected_evidence_items,
            "expired_evidence_items": expired_evidence_items,
            "controls_with_verified_evidence": controls_with_verified_evidence,
            "controls_without_evidence": max(0, controls_total - controls_with_any_evidence),
            "controls_with_expired_evidence": controls_with_expired_evidence,
        }

    def create_imported_evidence(
        self,
        *,
        organization_id: uuid.UUID,
        title: str,
        description: str | None,
        evidence_type: str,
        source_import_tool: str,
        collected_at: datetime | None,
        original_created_at: datetime | None,
        actor_user_id: uuid.UUID | None,
        write_audit: bool = True,
    ) -> EvidenceItem:
        row = EvidenceItem(
            organization_id=organization_id,
            title=title,
            description=description,
            evidence_type=evidence_type,
            source="imported",
            source_import_tool=source_import_tool,
            status="active",
            review_status="not_reviewed",
            freshness_status="unknown",
            collected_at=collected_at,
            original_created_at=original_created_at,
            uploaded_by_user_id=actor_user_id,
            metadata_json={"source_import_tool": source_import_tool},
        )
        self.db.add(row)
        self.db.flush()

        # Every imported-evidence creation gets an audit trail. The cloud-connector
        # ingest path relies on this (it writes no audit of its own). Bulk import
        # already logs an import.evidence.* row per item, so it opts out via
        # write_audit=False to avoid a duplicate.
        if write_audit:
            AuditService(self.db).write_audit_log(
                action="evidence.imported",
                entity_type="evidence_item",
                entity_id=row.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "title": row.title,
                    "status": row.status,
                    "source": "imported",
                    "source_import_tool": source_import_tool,
                },
                metadata_json={"source": "imported", "source_import_tool": source_import_tool},
            )
        return row

    @staticmethod
    def effective_submitted_at(evidence_item: EvidenceItem) -> datetime:
        if evidence_item.source == "imported":
            return evidence_item.original_created_at or evidence_item.collected_at or evidence_item.created_at
        return evidence_item.collected_at or evidence_item.created_at

    def find_active_duplicate_by_checksum(
        self, organization_id: uuid.UUID, checksum_sha256: str | None
    ) -> EvidenceItem | None:
        """Content-based dedup: an evidence item with the same checksum already
        active (not archived) in this org is a genuine duplicate document, regardless
        of which ingestion path (manual/webhook/email/form) it came in through."""
        if not checksum_sha256:
            return None
        return self.db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.checksum_sha256 == checksum_sha256,
                EvidenceItem.status != "archived",
            )
            .order_by(EvidenceItem.created_at.asc())
        ).scalars().first()

    def _link_evidence_to_control(
        self,
        *,
        organization_id: uuid.UUID,
        evidence: EvidenceItem,
        target_control_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        link_confidence: str,
        link_rationale: str | None,
        source: str,
        request_ip: str | None,
        request_user_agent: str | None,
    ) -> EvidenceControlLink:
        self.require_control_in_org(organization_id, target_control_id)
        now = self.now()
        existing_link = self.db.execute(
            select(EvidenceControlLink).where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.evidence_item_id == evidence.id,
                EvidenceControlLink.control_id == target_control_id,
            )
        ).scalar_one_or_none()
        if existing_link is not None:
            if existing_link.link_status != "active":
                existing_link.link_status = "active"
                existing_link.confidence = link_confidence
                existing_link.rationale = link_rationale
                existing_link.linked_by_user_id = actor_user_id
                existing_link.linked_at = now
                existing_link.unlinked_at = None
                self.db.flush()
            return existing_link

        link = EvidenceControlLink(
            organization_id=organization_id,
            evidence_item_id=evidence.id,
            control_id=target_control_id,
            link_status="active",
            confidence=link_confidence,
            rationale=link_rationale,
            linked_by_user_id=actor_user_id,
            linked_at=now,
        )
        self.db.add(link)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence.control_linked",
            entity_type="evidence_control_link",
            entity_id=link.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "evidence_item_id": str(evidence.id),
                "control_id": str(target_control_id),
                "link_status": link.link_status,
                "confidence": link.confidence,
            },
            metadata_json={"source": source},
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
        return link

    def create_evidence_item(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        title: str,
        description: str | None = None,
        evidence_type: str = "other",
        source: str = "manual",
        file_name: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        checksum_sha256: str | None = None,
        external_reference_url: str | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        collected_at: datetime | None = None,
        metadata_json: dict | None = None,
        target_control_id: uuid.UUID | None = None,
        link_confidence: str = "manual_confirmed",
        link_rationale: str | None = None,
        request_ip: str | None = None,
        request_user_agent: str | None = None,
        audit_metadata: dict | None = None,
    ) -> tuple[EvidenceItem, EvidenceControlLink | None, bool]:
        """Returns (evidence_item, control_link_or_none, is_duplicate). When a checksum
        match against an existing active evidence item is found, no new EvidenceItem row
        is created -- the existing one is reused (and linked to target_control_id if
        provided) so duplicate submissions never silently create disconnected rows."""
        if valid_from and valid_until and valid_until < valid_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="valid_until cannot be earlier than valid_from")
        if size_bytes is not None and size_bytes < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="size_bytes cannot be negative")
        if not title.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")

        duplicate = self.find_active_duplicate_by_checksum(organization_id, checksum_sha256)
        if duplicate is not None:
            meta = dict(duplicate.metadata_json or {})
            submissions = meta.get("duplicate_submissions")
            if not isinstance(submissions, list):
                submissions = []
            submissions.append(
                {
                    "detected_at": self.now().isoformat(),
                    "source": source,
                    "title": title.strip(),
                }
            )
            meta["duplicate_submissions"] = submissions
            meta["duplicate_submission_count"] = len(submissions)
            duplicate.metadata_json = meta
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="evidence.duplicate_detected",
                entity_type="evidence_item",
                entity_id=duplicate.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "checksum_sha256": checksum_sha256,
                    "duplicate_submission_count": meta["duplicate_submission_count"],
                },
                metadata_json=(audit_metadata or {"source": source}),
                ip_address=request_ip,
                user_agent=request_user_agent,
            )

            dup_link: EvidenceControlLink | None = None
            if target_control_id is not None:
                dup_link = self._link_evidence_to_control(
                    organization_id=organization_id,
                    evidence=duplicate,
                    target_control_id=target_control_id,
                    actor_user_id=actor_user_id,
                    link_confidence=link_confidence,
                    link_rationale=link_rationale,
                    source=source,
                    request_ip=request_ip,
                    request_user_agent=request_user_agent,
                )
            return duplicate, dup_link, True

        evidence = EvidenceItem(
            organization_id=organization_id,
            title=title.strip(),
            description=description,
            evidence_type=evidence_type,
            source=source,
            status="active",
            review_status="not_reviewed",
            freshness_status=self.calculate_freshness_status(valid_until),
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            external_reference_url=external_reference_url,
            valid_from=valid_from,
            valid_until=valid_until,
            collected_at=collected_at,
            uploaded_by_user_id=actor_user_id,
            metadata_json=metadata_json,
        )
        self.db.add(evidence)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence.created",
            entity_type="evidence_item",
            entity_id=evidence.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "title": evidence.title,
                "status": evidence.status,
                "review_status": evidence.review_status,
                "freshness_status": evidence.freshness_status,
            },
            metadata_json=(audit_metadata or {"source": source}),
            ip_address=request_ip,
            user_agent=request_user_agent,
        )

        link: EvidenceControlLink | None = None
        if target_control_id is not None:
            link = self._link_evidence_to_control(
                organization_id=organization_id,
                evidence=evidence,
                target_control_id=target_control_id,
                actor_user_id=actor_user_id,
                link_confidence=link_confidence,
                link_rationale=link_rationale,
                source=source,
                request_ip=request_ip,
                request_user_agent=request_user_agent,
            )

        return evidence, link, False

    def list_control_gaps(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """readiness_summary() only ever reported bare counts (e.g. "3 controls without
        evidence"). This reports exactly *which* controls those are and *why* they don't
        count as covered: never linked to any active evidence at all, linked only to
        evidence that has since expired, been rejected on review, or is still awaiting
        review -- paginated so this stays cheap for organizations with thousands of
        controls."""
        controls = self.db.execute(
            select(Control)
            .where(Control.organization_id == organization_id, Control.status != "archived")
            .order_by(Control.created_at.asc())
        ).scalars().all()

        # Batch-fetch the best (most-recent, active) link+evidence pair per control in a
        # single query rather than one query per control.
        link_rows = self.db.execute(
            select(EvidenceControlLink, EvidenceItem)
            .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
            .where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.link_status == "active",
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status != "archived",
            )
            .order_by(EvidenceItem.created_at.desc())
        ).all()

        best_evidence_by_control: dict[uuid.UUID, EvidenceItem] = {}
        for link, evidence in link_rows:
            # First row per control (by the ORDER BY above) is verified if any is
            # verified; otherwise keep the most recent as the representative gap reason.
            existing = best_evidence_by_control.get(link.control_id)
            if existing is None:
                best_evidence_by_control[link.control_id] = evidence
            elif existing.review_status != "verified" and evidence.review_status == "verified":
                best_evidence_by_control[link.control_id] = evidence

        gaps: list[dict] = []
        for control in controls:
            evidence = best_evidence_by_control.get(control.id)
            if evidence is None:
                gaps.append({"control_id": control.id, "control_name": control.title, "reason": "never_linked"})
            elif evidence.review_status == "rejected":
                gaps.append({"control_id": control.id, "control_name": control.title, "reason": "linked_but_rejected"})
            elif evidence.freshness_status == "expired":
                gaps.append({"control_id": control.id, "control_name": control.title, "reason": "linked_but_expired"})
            elif evidence.review_status != "verified":
                gaps.append({"control_id": control.id, "control_name": control.title, "reason": "linked_but_not_reviewed"})

        total = len(gaps)
        page = gaps[offset : offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "items": page}
