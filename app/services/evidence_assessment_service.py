"""Evidence-vault AI-assist drain: the ONLY writer of evidence_ai_assessments.

Runs in an APScheduler job's OWN committed session (the pbc_scheduler wrapper
commits). For each event-flagged candidate it READS the evidence item + its
linked control for context, extracts document text (R2 bytes -> external URL ->
none), asks the Groq/Azure chain for an ASSESSMENT (never a verdict), and writes
exactly one evidence_ai_assessments row. On ANY failure it still writes a row
with status 'unable_to_assess' + the reason -- the evidence itself is never
touched, blocked, or failed.

ISOLATION: this module issues INSERTs against evidence_ai_assessments and
UPDATEs the processed_at flag on evidence_ai_assessment_candidates ONLY. Every
reference to evidence_items / evidence_control_links / controls is a read
(select). It emits no events and calls no other system.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.evidence_assessment_ai import generate_evidence_assessment
from app.core.config import get_settings
from app.core.url_security import assert_public_http_url
from app.models.control import Control
from app.models.evidence_ai_assessment import EvidenceAiAssessment, EvidenceAiAssessmentCandidate
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.services.object_storage_service import ObjectStorageService

logger = logging.getLogger(__name__)

_DRAIN_BATCH = 100
_MAX_EXTRACT_CHARS = 12_000
_MAX_FETCH_BYTES = 26_214_400


def _extract_from_bytes(data: bytes, mime_type: str | None, file_name: str | None) -> str | None:
    """Best-effort text extraction. Returns None if the format is not extractable."""
    mt = (mime_type or "").lower()
    name = (file_name or "").lower()
    try:
        if mt == "application/pdf" or name.endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text or None
        if name.endswith(".docx") or "openxmlformats-officedocument.wordprocessingml" in mt:
            import docx

            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs) or None
        if mt.startswith("text/") or mt in {"application/json", "application/xml"} or name.endswith(
            (".txt", ".csv", ".json", ".xml")
        ):
            return data.decode("utf-8", errors="replace") or None
    except Exception:  # noqa: BLE001 -- extraction is best-effort; unreadable -> None
        logger.warning("Evidence text extraction failed for mime=%s name=%s", mime_type, file_name)
        return None
    return None


def extract_text(evidence: EvidenceItem, *, storage: ObjectStorageService | None = None) -> tuple[str | None, str]:
    """Prefer real R2 file bytes; fall back to external URL fetch; else None.

    Returns (text_or_None, content_source in {'r2_file','external_url','none'}).
    """
    storage = storage or ObjectStorageService()

    if evidence.storage_key and evidence.storage_provider == "cloudflare_r2" and storage.is_configured:
        try:
            data = storage.download_bytes(evidence.storage_key)
            text = _extract_from_bytes(data, evidence.mime_type, evidence.file_name)
            return (text[:_MAX_EXTRACT_CHARS] if text else None), "r2_file"
        except Exception:  # noqa: BLE001
            logger.warning("Evidence R2 download/extract failed for %s", evidence.id)
            return None, "r2_file"

    if evidence.external_reference_url:
        try:
            assert_public_http_url(evidence.external_reference_url, field_name="external_reference_url")
            import httpx

            with httpx.Client(timeout=10.0, follow_redirects=True) as http:
                resp = http.get(evidence.external_reference_url)
                resp.raise_for_status()
                data = resp.content[:_MAX_FETCH_BYTES]
            ctype = resp.headers.get("content-type", "").split(";")[0].strip() or evidence.mime_type
            text = _extract_from_bytes(data, ctype, evidence.file_name)
            return (text[:_MAX_EXTRACT_CHARS] if text else None), "external_url"
        except Exception:  # noqa: BLE001
            logger.warning("Evidence external-URL fetch/extract failed for %s", evidence.id)
            return None, "external_url"

    return None, "none"


def _linked_control(db: Session, evidence: EvidenceItem) -> Control | None:
    link = db.execute(
        select(EvidenceControlLink)
        .where(
            EvidenceControlLink.evidence_item_id == evidence.id,
            EvidenceControlLink.organization_id == evidence.organization_id,
            EvidenceControlLink.link_status == "active",
        )
        .limit(1)
    ).scalar_one_or_none()
    if link is None:
        return None
    return db.execute(select(Control).where(Control.id == link.control_id)).scalar_one_or_none()


def _build_payload(evidence: EvidenceItem, control: Control | None, extracted_text: str | None) -> dict:
    return {
        "evidence": {
            "title": evidence.title,
            "evidence_type": evidence.evidence_type,
            "mime_type": evidence.mime_type,
            "file_name": evidence.file_name,
            "description": evidence.description,
            "valid_from": evidence.valid_from,
            "valid_until": evidence.valid_until,
        },
        "linked_control": (
            {
                "code": getattr(control, "code", None),
                "title": getattr(control, "title", None),
                "description": getattr(control, "description", None),
            }
            if control is not None
            else None
        ),
        "extracted_text": extracted_text,
    }


def assess_one(db: Session, candidate: EvidenceAiAssessmentCandidate) -> EvidenceAiAssessment | None:
    """Assess a single candidate's evidence item; write exactly one assessment row.

    Returns the row (or None if the evidence no longer exists). Never raises for an
    AI failure -- that becomes an 'unable_to_assess' row.
    """
    evidence = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.id == candidate.evidence_item_id,
            EvidenceItem.organization_id == candidate.organization_id,
        )
    ).scalar_one_or_none()
    if evidence is None:
        return None

    control = _linked_control(db, evidence)
    extracted_text, content_source = extract_text(evidence)
    payload = _build_payload(evidence, control, extracted_text)

    status = "unable_to_assess"
    appears_to_be = appears_to_cover = None
    missing: list = []
    explanation = "The AI assessment could not be produced."
    provider_used = None
    used_byo = None

    try:
        result, provider_used, used_byo = generate_evidence_assessment(
            db, org_id=candidate.organization_id, payload=payload
        )
        status = result["ai_assessment_status"]
        appears_to_be = result["appears_to_be"]
        appears_to_cover = result["appears_to_cover"]
        missing = result["missing_or_mismatched"]
        explanation = result["explanation"]
    except Exception as exc:  # noqa: BLE001 -- fallback discipline: never block evidence
        logger.warning("Evidence assessment fell back to unable_to_assess for %s: %s", evidence.id, exc)
        if content_source == "none" or not extracted_text:
            explanation = (
                "No readable document content was available to assess (the file could not be "
                "retrieved or extracted), so no suggestion can be offered."
            )
        else:
            explanation = f"The AI assessment service was unavailable ({type(exc).__name__}); please retry later."

    assessment = EvidenceAiAssessment(
        organization_id=candidate.organization_id,
        evidence_item_id=evidence.id,
        ai_assessment_status=status,
        appears_to_be=appears_to_be,
        appears_to_cover=appears_to_cover,
        missing_or_mismatched_json=missing,
        explanation=explanation,
        linked_control_id=(control.id if control is not None else None),
        content_source=content_source,
        extracted_text_chars=len(extracted_text or ""),
        provider_used=provider_used,
        used_byo_credentials=used_byo,
    )
    db.add(assessment)
    db.flush()
    return assessment


def run_evidence_assessment_candidate_drain(db: Session) -> dict:
    """Process event-flagged evidence-assessment candidates. Flush-only."""
    candidates = db.execute(
        select(EvidenceAiAssessmentCandidate)
        .where(EvidenceAiAssessmentCandidate.processed_at.is_(None))
        .order_by(EvidenceAiAssessmentCandidate.flagged_at.asc())
        .limit(_DRAIN_BATCH)
    ).scalars().all()

    now = datetime.now(UTC)
    created = 0
    for candidate in candidates:
        try:
            if assess_one(db, candidate) is not None:
                created += 1
        except Exception:  # noqa: BLE001 -- one bad candidate must not stop the batch
            logger.exception("Evidence assessment drain failed for candidate %s", candidate.id)
        candidate.processed_at = now
    db.flush()
    return {"records_processed": len(candidates), "created": created}
