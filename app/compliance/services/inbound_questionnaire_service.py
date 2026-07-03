import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from statistics import median

from fastapi import HTTPException, status
from sqlalchemy import cast, or_, select, String
from sqlalchemy.orm import Session

from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.inbound_questionnaire_item import InboundQuestionnaireItem
from app.models.inbound_questionnaire_session import InboundQuestionnaireSession
from app.models.obligation import Obligation
from app.services.audit_service import AuditService


class InboundQuestionnaireService:
    CERT_KEYWORDS = ("soc2", "soc 2", "iso27001", "iso 27001", "pci", "hipaa", "gdpr", "fedramp")
    STOP_WORDS = {
        "does",
        "have",
        "your",
        "that",
        "with",
        "this",
        "from",
        "what",
        "will",
        "when",
        "which",
        "where",
        "their",
        "there",
        "about",
        "should",
        "would",
        "could",
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _clip(value: str | None, size: int = 500) -> str | None:
        if not value:
            return value
        return value[:size]

    @staticmethod
    def _to_date(value: datetime | date | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return value.date()

    @staticmethod
    def _to_datetime(value: datetime | date | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime(value.year, value.month, value.day, tzinfo=UTC)

    def _render_answer_template(self, item: InboundQuestionnaireItem, match: dict | None, *, conflict: bool = False) -> str:
        if conflict:
            return (
                "Potential inconsistency detected. Multiple sources "
                "with conflicting signals found. Manual review "
                "required."
            )

        if match is None:
            return (
                "Manual review required. No supporting evidence, "
                "policy, or certification was found for this item."
            )

        source_type = match["source_type"]
        source_title = match.get("source_title") or "source"
        source_date = str(match.get("source_date") or "unknown")
        source_excerpt = (match.get("source_excerpt") or "").strip()

        if source_type == "evidence":
            return (
                "Yes. Based on '{source_title}', evidence shows "
                "this practice is implemented as of {source_date}."
            ).format(source_title=source_title, source_date=source_date)
        if source_type == "control":
            return (
                "Our '{source_title}' control demonstrates "
                "compliance with {framework_ref} as of "
                "{source_date}."
            ).format(
                source_title=source_title,
                framework_ref=item.framework_ref or "the referenced framework",
                source_date=source_date,
            )
        if source_type == "certification":
            return (
                "We maintain an active {source_title}, "
                "valid until {source_date}."
            ).format(source_title=source_title, source_date=source_date)
        if source_type == "policy":
            return (
                "Our '{source_title}' addresses this requirement. "
                "{source_excerpt}"
            ).format(source_title=source_title, source_excerpt=source_excerpt)
        if source_type == "previous_answer":
            return (
                "Based on a previously approved response: "
                "{source_excerpt}"
            ).format(source_excerpt=source_excerpt)

        return (
            "Manual review required. No supporting evidence, "
            "policy, or certification was found for this item."
        )

    def _build_match(
        self,
        *,
        source_type: str,
        source_id: uuid.UUID,
        source_title: str,
        source_excerpt: str | None,
        source_date: date | None,
        source_updated_at: datetime | None,
        base_score: int,
        base_reason: str,
        is_inactive: bool = False,
        is_unapproved: bool = False,
        previous_answer_reuse: bool = False,
        signal: str = "yes",
    ) -> dict:
        score = base_score
        reason_parts: list[str] = [f"{base_reason} Score: {base_score} (base)"]
        normalized_updated_at = source_updated_at
        if normalized_updated_at is not None and normalized_updated_at.tzinfo is None:
            normalized_updated_at = normalized_updated_at.replace(tzinfo=UTC)

        recent_bonus = 0
        if normalized_updated_at is not None and normalized_updated_at >= self.utcnow() - timedelta(days=90):
            recent_bonus = 10
            score += recent_bonus
            reason_parts.append("+ 10 (recent)")

        previous_bonus = 0
        if source_type == "previous_answer" and previous_answer_reuse:
            previous_bonus = 20
            score += previous_bonus
            reason_parts.append("+ 20 (previously approved answer reuse)")

        if is_inactive:
            score -= 30
            reason_parts.append("- 30 (source is expired/inactive)")

        if is_unapproved:
            score -= 40
            reason_parts.append("- 40 (source is draft/unapproved)")

        score = max(0, min(100, int(score)))

        if normalized_updated_at is not None and normalized_updated_at < self.utcnow() - timedelta(days=90):
            age_days = (self.utcnow().date() - normalized_updated_at.date()).days
            reason_parts.append(f"Source is {age_days} days old")

        return {
            "source_type": source_type,
            "source_id": source_id,
            "source_title": source_title,
            "source_excerpt": self._clip(source_excerpt),
            "source_date": source_date,
            "confidence_score": score,
            "confidence_reason": ". ".join(reason_parts) + ".",
            "signal": signal,
        }

    def require_session(self, org_id: uuid.UUID, session_id: uuid.UUID) -> InboundQuestionnaireSession:
        row = self.db.execute(
            select(InboundQuestionnaireSession).where(
                InboundQuestionnaireSession.id == session_id,
                InboundQuestionnaireSession.organization_id == org_id,
                InboundQuestionnaireSession.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbound questionnaire session not found")
        return row

    def require_item(self, org_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID) -> InboundQuestionnaireItem:
        row = self.db.execute(
            select(InboundQuestionnaireItem).where(
                InboundQuestionnaireItem.id == item_id,
                InboundQuestionnaireItem.session_id == session_id,
                InboundQuestionnaireItem.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbound questionnaire item not found")
        return row

    def create_session(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> InboundQuestionnaireSession:
        row = InboundQuestionnaireSession(
            organization_id=org_id,
            title=data.title,
            sender_name=data.sender_name,
            sender_email=data.sender_email,
            description=data.description,
            due_date=data.due_date,
            status="draft",
            total_questions=0,
            drafted_count=0,
            approved_count=0,
            sent_count=0,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.session_created",
            entity_type="inbound_questionnaire_session",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"title": row.title, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_session(self, org_id: uuid.UUID, session_id: uuid.UUID) -> InboundQuestionnaireSession:
        return self.require_session(org_id, session_id)

    def list_sessions(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[InboundQuestionnaireSession]:
        stmt = select(InboundQuestionnaireSession).where(
            InboundQuestionnaireSession.organization_id == org_id,
            InboundQuestionnaireSession.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(InboundQuestionnaireSession.status == status_value)
        return self.db.execute(
            stmt.order_by(InboundQuestionnaireSession.created_at.desc()).offset(skip).limit(limit)
        ).scalars().all()

    def add_item(self, org_id: uuid.UUID, session_id: uuid.UUID, data, *, actor_user_id: uuid.UUID | None = None) -> InboundQuestionnaireItem:
        session = self.require_session(org_id, session_id)
        row = InboundQuestionnaireItem(
            organization_id=org_id,
            session_id=session.id,
            question_text=data.question_text,
            question_type=data.question_type,
            category_tag=data.category_tag,
            framework_ref=data.framework_ref,
            order_index=data.order_index,
            status="pending",
            requires_human_review=True,
        )
        self.db.add(row)
        session.total_questions = int(session.total_questions or 0) + 1
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.item_added",
            entity_type="inbound_questionnaire_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"session_id": str(session.id), "order_index": row.order_index},
            metadata_json={"source": "api"},
        )
        return row

    def bulk_add_items(
        self,
        org_id: uuid.UUID,
        session_id: uuid.UUID,
        items: list,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> dict:
        added = 0
        for item in items:
            self.add_item(org_id, session_id, item, actor_user_id=actor_user_id)
            added += 1

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.items_bulk_added",
            entity_type="inbound_questionnaire_session",
            entity_id=session_id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"added": added},
            metadata_json={"source": "api"},
        )
        return {"added": added, "session_id": session_id}

    def list_items(self, org_id: uuid.UUID, session_id: uuid.UUID) -> list[InboundQuestionnaireItem]:
        _ = self.require_session(org_id, session_id)
        return self.db.execute(
            select(InboundQuestionnaireItem)
            .where(
                InboundQuestionnaireItem.organization_id == org_id,
                InboundQuestionnaireItem.session_id == session_id,
            )
            .order_by(InboundQuestionnaireItem.order_index.asc(), InboundQuestionnaireItem.created_at.asc())
        ).scalars().all()

    def get_item(self, org_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID) -> InboundQuestionnaireItem:
        _ = self.require_session(org_id, session_id)
        return self.require_item(org_id, session_id, item_id)

    def _signal_from_text(self, text: str | None) -> str:
        if not text:
            return "unknown"
        normalized = text.lower()
        if "yes" in normalized:
            return "yes"
        if "no" in normalized:
            return "no"
        return "unknown"

    def _extract_policy_excerpt(self, policy: CompliancePolicy) -> str:
        if policy.description:
            return policy.description
        if policy.notes:
            return policy.notes
        if policy.tags_json is not None:
            return str(policy.tags_json)
        return policy.title

    def _match_evidence(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> dict | None:
        if not item.category_tag:
            return None

        candidates = self.db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.status != "archived",
                EvidenceItem.review_status == "verified",
            )
            .order_by(EvidenceItem.collected_at.desc(), EvidenceItem.created_at.desc())
        ).scalars().all()

        matched: EvidenceItem | None = None
        for row in candidates:
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            if str(metadata.get("category_tag") or "").strip() == str(item.category_tag).strip():
                matched = row
                break
        if matched is None:
            return None

        source_dt = matched.collected_at or matched.updated_at
        is_inactive = matched.status != "active" or matched.freshness_status == "expired"
        is_unapproved = matched.review_status != "verified"

        return self._build_match(
            source_type="evidence",
            source_id=matched.id,
            source_title=matched.title,
            source_excerpt=matched.description,
            source_date=self._to_date(matched.collected_at),
            source_updated_at=self._to_datetime(source_dt),
            base_score=35,
            base_reason=f"Approved evidence '{matched.title}' matched by category tag.",
            is_inactive=is_inactive,
            is_unapproved=is_unapproved,
            signal="yes",
        )

    def _match_control(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> dict | None:
        if not item.framework_ref:
            return None

        ref = item.framework_ref.strip()
        if not ref:
            return None

        prefix = ref.split()[0]
        stmt = (
            select(Control, Framework, Obligation)
            .join(ControlObligationMapping, ControlObligationMapping.control_id == Control.id)
            .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
            .join(Framework, Framework.id == Obligation.framework_id)
            .where(
                Control.organization_id == org_id,
                Control.status == "implemented",
                ControlObligationMapping.organization_id == org_id,
                ControlObligationMapping.status == "active",
                Obligation.status == "active",
                or_(
                    Framework.name.ilike(f"{prefix}%"),
                    Framework.code.ilike(f"{prefix}%"),
                    Obligation.reference_code.ilike(f"%{ref}%"),
                    Control.control_code.ilike(f"%{ref}%"),
                ),
            )
            .order_by(Control.updated_at.desc(), Control.created_at.desc())
        )
        row = self.db.execute(stmt).first()
        if row is None:
            return None

        control, _framework, obligation = row

        linked_evidence = self.db.execute(
            select(EvidenceItem)
            .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
            .where(
                EvidenceControlLink.organization_id == org_id,
                EvidenceControlLink.control_id == control.id,
                EvidenceControlLink.link_status == "active",
                EvidenceItem.organization_id == org_id,
                EvidenceItem.status != "archived",
            )
            .order_by(EvidenceItem.collected_at.desc(), EvidenceItem.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        source_excerpt = control.description or control.implementation_notes
        source_dt = control.updated_at
        if linked_evidence is not None:
            source_excerpt = linked_evidence.description or source_excerpt
            source_dt = linked_evidence.collected_at or linked_evidence.updated_at or source_dt

        is_inactive = control.status != "implemented"
        is_unapproved = False

        return self._build_match(
            source_type="control",
            source_id=control.id,
            source_title=control.title,
            source_excerpt=source_excerpt,
            source_date=self._to_date(source_dt),
            source_updated_at=self._to_datetime(source_dt),
            base_score=25,
            base_reason=f"Implemented control '{control.title}' matched framework reference '{obligation.reference_code}'.",
            is_inactive=is_inactive,
            is_unapproved=is_unapproved,
            signal="yes",
        )

    def _match_certification(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> dict | None:
        haystack = f"{item.question_text} {item.category_tag or ''}".lower()
        keyword = next((k for k in self.CERT_KEYWORDS if k in haystack), None)
        if keyword is None:
            return None

        cert = self.db.execute(
            select(ComplianceCertification)
            .where(
                ComplianceCertification.organization_id == org_id,
                ComplianceCertification.deleted_at.is_(None),
                ComplianceCertification.status == "active",
                ComplianceCertification.name.ilike(f"%{keyword}%"),
            )
            .order_by(ComplianceCertification.valid_until.desc(), ComplianceCertification.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if cert is None:
            return None

        expired = cert.valid_until is not None and cert.valid_until < self.utcnow().date()
        return self._build_match(
            source_type="certification",
            source_id=cert.id,
            source_title=cert.name,
            source_excerpt=cert.notes,
            source_date=cert.valid_until,
            source_updated_at=self._to_datetime(cert.valid_until or cert.updated_at),
            base_score=25,
            base_reason=f"Active certification '{cert.name}' matched certification keyword '{keyword}'.",
            is_inactive=cert.status != "active" or expired,
            is_unapproved=cert.status == "draft",
            signal="yes",
        )

    def _policy_tokens(self, text: str) -> set[str]:
        tokens: set[str] = set()
        for token in text.split():
            cleaned = "".join(ch for ch in token.lower() if ch.isalnum() or ch in {"_", "-"})
            if len(cleaned) > 4 and cleaned not in self.STOP_WORDS:
                tokens.add(cleaned)
        return tokens

    def _match_policy(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> dict | None:
        tokens = self._policy_tokens(item.question_text)
        if not tokens:
            return None

        matched: CompliancePolicy | None = None
        for token in sorted(tokens):
            row = self.db.execute(
                select(CompliancePolicy)
                .where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicy.status == "approved",
                    CompliancePolicy.archived_at.is_(None),
                    or_(
                        CompliancePolicy.title.ilike(f"%{token}%"),
                        CompliancePolicy.description.ilike(f"%{token}%"),
                        CompliancePolicy.notes.ilike(f"%{token}%"),
                        cast(CompliancePolicy.tags_json, String).ilike(f"%{token}%"),
                    ),
                )
                .order_by(CompliancePolicy.updated_at.desc(), CompliancePolicy.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                matched = row
                break

        if matched is None:
            return None

        return self._build_match(
            source_type="policy",
            source_id=matched.id,
            source_title=matched.title,
            source_excerpt=self._extract_policy_excerpt(matched),
            source_date=matched.review_due_date or matched.effective_date,
            source_updated_at=matched.updated_at,
            base_score=15,
            base_reason=f"Active policy '{matched.title}' matched by keyword overlap.",
            is_inactive=matched.status == "archived" or matched.archived_at is not None,
            is_unapproved=matched.status in {"draft", "under_review"},
            signal="yes",
        )

    def _source_still_valid(self, org_id: uuid.UUID, row: InboundQuestionnaireItem) -> bool:
        if row.source_type is None or row.source_id is None:
            return False

        if row.source_type == "evidence":
            source = self.db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.id == row.source_id,
                    EvidenceItem.organization_id == org_id,
                )
            ).scalar_one_or_none()
            return bool(source and source.status == "active" and source.review_status == "verified")

        if row.source_type == "control":
            source = self.db.execute(
                select(Control).where(
                    Control.id == row.source_id,
                    Control.organization_id == org_id,
                )
            ).scalar_one_or_none()
            return bool(source and source.status == "implemented")

        if row.source_type == "certification":
            source = self.db.execute(
                select(ComplianceCertification).where(
                    ComplianceCertification.id == row.source_id,
                    ComplianceCertification.organization_id == org_id,
                    ComplianceCertification.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if source is None or source.status != "active":
                return False
            if source.valid_until is not None and source.valid_until < self.utcnow().date():
                return False
            return True

        if row.source_type == "policy":
            source = self.db.execute(
                select(CompliancePolicy).where(
                    CompliancePolicy.id == row.source_id,
                    CompliancePolicy.organization_id == org_id,
                )
            ).scalar_one_or_none()
            return bool(source and source.status == "approved" and source.archived_at is None)

        if row.source_type == "previous_answer":
            source = self.db.execute(
                select(InboundQuestionnaireItem).where(
                    InboundQuestionnaireItem.id == row.source_id,
                    InboundQuestionnaireItem.organization_id == org_id,
                    InboundQuestionnaireItem.status == "approved",
                    InboundQuestionnaireItem.final_answer_text.is_not(None),
                )
            ).scalar_one_or_none()
            return source is not None

        return False

    def _match_previous_answer(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> dict | None:
        if not item.category_tag:
            return None

        source = self.db.execute(
            select(InboundQuestionnaireItem)
            .where(
                InboundQuestionnaireItem.organization_id == org_id,
                InboundQuestionnaireItem.category_tag == item.category_tag,
                InboundQuestionnaireItem.status == "approved",
                InboundQuestionnaireItem.final_answer_text.is_not(None),
            )
            .order_by(InboundQuestionnaireItem.reviewed_at.desc(), InboundQuestionnaireItem.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if source is None:
            return None

        signal = self._signal_from_text(source.final_answer_text)
        match = self._build_match(
            source_type="previous_answer",
            source_id=source.id,
            source_title="Previously approved answer",
            source_excerpt=source.final_answer_text,
            source_date=self._to_date(source.reviewed_at),
            source_updated_at=source.reviewed_at or source.updated_at,
            base_score=20,
            base_reason="Previous approved answer matched by category tag.",
            previous_answer_reuse=True,
            signal=signal,
        )

        if not self._source_still_valid(org_id, source):
            penalized = max(0, int(match["confidence_score"]) - 30)
            match["confidence_score"] = penalized
            match["confidence_reason"] = match["confidence_reason"].rstrip(".") + ". - 30 (source is expired/inactive)."

        return match

    def _detect_conflict(self, matches: list[dict]) -> bool:
        if len(matches) < 2:
            return False
        signals = {m.get("signal") for m in matches if m.get("signal") in {"yes", "no"}}
        return "yes" in signals and "no" in signals

    def _run_matching_engine(self, org_id: uuid.UUID, item: InboundQuestionnaireItem) -> tuple[dict | None, bool, list[dict]]:
        matches: list[dict] = []

        evidence = self._match_evidence(org_id, item)
        if evidence is not None:
            matches.append(evidence)
            if int(evidence["confidence_score"]) >= 60:
                return evidence, False, matches

        control = self._match_control(org_id, item)
        if control is not None:
            matches.append(control)
            if int(control["confidence_score"]) >= 60:
                return control, False, matches

        certification = self._match_certification(org_id, item)
        if certification is not None:
            matches.append(certification)
            if int(certification["confidence_score"]) >= 60:
                return certification, False, matches

        policy = self._match_policy(org_id, item)
        if policy is not None:
            matches.append(policy)
            if int(policy["confidence_score"]) >= 60:
                return policy, False, matches

        previous_answer = self._match_previous_answer(org_id, item)
        if previous_answer is not None:
            matches.append(previous_answer)
            if int(previous_answer["confidence_score"]) >= 60:
                return previous_answer, False, matches

        if not matches:
            return None, False, matches

        best = max(matches, key=lambda m: int(m["confidence_score"]))
        conflict = self._detect_conflict(matches)
        if conflict:
            best = dict(best)
            best["confidence_score"] = max(0, int(best["confidence_score"]) - 40)
            best["confidence_reason"] = (
                "Conflicting sources detected: evidence suggests "
                "Yes, but conflicting response text was found. "
                "Score penalized."
            )
        return best, conflict, matches

    def draft_item(self, org_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None) -> InboundQuestionnaireItem:
        session = self.require_session(org_id, session_id)
        item = self.require_item(org_id, session_id, item_id)

        best_match, conflict, _matches = self._run_matching_engine(org_id, item)
        previous_status = item.status

        item.requires_human_review = True
        if best_match is None:
            item.suggested_answer_text = self._render_answer_template(item, None)
            item.source_type = None
            item.source_id = None
            item.source_title = None
            item.source_excerpt = None
            item.source_date = None
            item.confidence_score = 0
            item.confidence_reason = "No reliable source found. Manual review required."
            item.status = "needs_review"
        else:
            item.source_type = best_match.get("source_type")
            item.source_id = best_match.get("source_id")
            item.source_title = best_match.get("source_title")
            item.source_excerpt = best_match.get("source_excerpt")
            item.source_date = best_match.get("source_date")
            item.confidence_score = int(best_match.get("confidence_score") or 0)
            item.confidence_reason = best_match.get("confidence_reason")
            item.suggested_answer_text = self._render_answer_template(item, best_match, conflict=conflict)
            item.status = "drafted" if not conflict else "needs_review"

        if previous_status == "pending":
            session.drafted_count = int(session.drafted_count or 0) + 1
        if session.status == "draft":
            session.status = "in_progress"

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.item_drafted",
            entity_type="inbound_questionnaire_item",
            entity_id=item.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "session_id": str(session.id),
                "status": item.status,
                "source_type": item.source_type,
                "confidence_score": item.confidence_score,
            },
            metadata_json={"source": "api"},
        )
        return item

    def draft_all_items(self, org_id: uuid.UUID, session_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None) -> dict:
        _ = self.require_session(org_id, session_id)
        pending = self.db.execute(
            select(InboundQuestionnaireItem).where(
                InboundQuestionnaireItem.organization_id == org_id,
                InboundQuestionnaireItem.session_id == session_id,
                InboundQuestionnaireItem.status == "pending",
            )
        ).scalars().all()

        drafted = 0
        needs_review = 0
        no_source = 0
        for row in pending:
            result = self.draft_item(org_id, session_id, row.id, actor_user_id=actor_user_id)
            if result.source_type is not None:
                drafted += 1
            if result.status == "needs_review":
                needs_review += 1
            if result.source_type is None:
                no_source += 1

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.all_drafted",
            entity_type="inbound_questionnaire_session",
            entity_id=session_id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"drafted": drafted, "needs_review": needs_review, "no_source": no_source},
            metadata_json={"source": "api"},
        )
        return {
            "drafted": drafted,
            "needs_review": needs_review,
            "no_source": no_source,
            "session_id": session_id,
        }

    def review_item(
        self,
        org_id: uuid.UUID,
        session_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        action: str,
        reviewer_id: uuid.UUID,
        review_notes: str | None = None,
        edited_answer: str | None = None,
    ) -> InboundQuestionnaireItem:
        session = self.require_session(org_id, session_id)
        item = self.require_item(org_id, session_id, item_id)

        if action not in {"approve", "edit", "reject"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review action")

        if action == "approve":
            item.final_answer_text = edited_answer or item.suggested_answer_text
            item.status = "approved"
            session.approved_count = int(session.approved_count or 0) + 1
            audit_action = "inbound_questionnaire.item_approved"
        elif action == "edit":
            if not edited_answer:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="edited_answer is required for edit")
            item.final_answer_text = edited_answer
            item.status = "approved"
            session.approved_count = int(session.approved_count or 0) + 1
            audit_action = "inbound_questionnaire.item_edited"
        else:
            item.status = "rejected"
            item.final_answer_text = None
            audit_action = "inbound_questionnaire.item_rejected"

        item.reviewer_id = reviewer_id
        item.reviewed_at = self.utcnow()
        item.review_notes = review_notes
        item.requires_human_review = True

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action=audit_action,
            entity_type="inbound_questionnaire_item",
            entity_id=item.id,
            organization_id=org_id,
            actor_user_id=reviewer_id,
            after_json={"status": item.status},
            metadata_json={"source": "api"},
        )
        return item

    def mark_item_sent(self, org_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID, *, user_id: uuid.UUID) -> InboundQuestionnaireItem:
        session = self.require_session(org_id, session_id)
        item = self.require_item(org_id, session_id, item_id)
        if item.status != "approved":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only approved items can be marked sent")

        item.status = "sent"
        session.sent_count = int(session.sent_count or 0) + 1
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.item_sent",
            entity_type="inbound_questionnaire_item",
            entity_id=item.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": item.status},
            metadata_json={"source": "api"},
        )
        return item

    def mark_session_completed(self, org_id: uuid.UUID, session_id: uuid.UUID, *, user_id: uuid.UUID) -> InboundQuestionnaireSession:
        session = self.require_session(org_id, session_id)
        items = self.list_items(org_id, session_id)
        if any(item.status not in {"approved", "sent"} for item in items):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Session has unreviewed items.")

        session.status = "completed"
        session.completed_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="inbound_questionnaire.session_completed",
            entity_type="inbound_questionnaire_session",
            entity_id=session.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": session.status},
            metadata_json={"source": "api"},
        )
        return session

    def get_response_time_metrics(
        self,
        org_id: uuid.UUID,
        *,
        session_id: uuid.UUID | None = None,
    ) -> dict:
        if session_id is not None:
            sessions = [self.require_session(org_id, session_id)]
        else:
            sessions = self.db.execute(
                select(InboundQuestionnaireSession).where(
                    InboundQuestionnaireSession.organization_id == org_id,
                    InboundQuestionnaireSession.deleted_at.is_(None),
                )
            ).scalars().all()

        durations_hours: list[float] = []
        sessions_still_pending = 0

        for session in sessions:
            terminal_dt = session.completed_at
            if terminal_dt is None and session.status == "completed":
                # Backward compatibility for rows completed before completed_at existed.
                terminal_dt = session.updated_at

            if terminal_dt is None:
                sessions_still_pending += 1
                continue

            delta_hours = (terminal_dt - session.created_at).total_seconds() / 3600
            durations_hours.append(max(0.0, delta_hours))

        if durations_hours:
            avg_hours = round(sum(durations_hours) / len(durations_hours), 2)
            median_hours = round(float(median(durations_hours)), 2)
            fastest_hours = round(min(durations_hours), 2)
            slowest_hours = round(max(durations_hours), 2)
        else:
            avg_hours = None
            median_hours = None
            fastest_hours = None
            slowest_hours = None

        return {
            "session_id": session_id,
            "avg_response_time_hours": avg_hours,
            "median_response_time_hours": median_hours,
            "fastest_response_time_hours": fastest_hours,
            "slowest_response_time_hours": slowest_hours,
            "sessions_analyzed": len(durations_hours),
            "sessions_still_pending": sessions_still_pending,
        }

    def get_session_summary(self, org_id: uuid.UUID, session_id: uuid.UUID) -> dict:
        _ = self.require_session(org_id, session_id)
        items = self.list_items(org_id, session_id)

        total_questions = len(items)
        drafted_count = sum(1 for item in items if item.status in {"drafted", "needs_review", "approved", "sent", "rejected"})
        approved_count = sum(1 for item in items if item.status == "approved")
        sent_count = sum(1 for item in items if item.status == "sent")
        needs_review_count = sum(1 for item in items if item.status in {"needs_review", "rejected"})

        scores = [int(item.confidence_score) for item in items if item.confidence_score is not None]
        avg_confidence_score = int(round(sum(scores) / len(scores))) if scores else 0
        high_confidence_items = sum(1 for item in items if (item.confidence_score or 0) >= 70)
        low_confidence_items = sum(1 for item in items if (item.confidence_score or 0) < 40)

        distribution = Counter(item.source_type or "no_source" for item in items)
        source_type_distribution = {
            "evidence": int(distribution.get("evidence", 0)),
            "control": int(distribution.get("control", 0)),
            "policy": int(distribution.get("policy", 0)),
            "certification": int(distribution.get("certification", 0)),
            "previous_answer": int(distribution.get("previous_answer", 0)),
            "no_source": int(distribution.get("no_source", 0)),
        }

        return {
            "total_questions": total_questions,
            "drafted_count": drafted_count,
            "approved_count": approved_count,
            "sent_count": sent_count,
            "needs_review_count": needs_review_count,
            "avg_confidence_score": avg_confidence_score,
            "high_confidence_items": high_confidence_items,
            "low_confidence_items": low_confidence_items,
            "source_type_distribution": source_type_distribution,
        }

    def soft_delete_session(self, org_id: uuid.UUID, session_id: uuid.UUID, *, user_id: uuid.UUID) -> InboundQuestionnaireSession:
        session = self.require_session(org_id, session_id)
        if session.status not in {"draft", "archived"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only draft or archived sessions can be deleted",
            )

        session.deleted_at = self.utcnow()
        self.db.flush()
        return session
