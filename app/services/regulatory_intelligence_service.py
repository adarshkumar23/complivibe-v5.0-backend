from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.regulatory_change_alert import RegulatoryChangeAlert
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

EU_FEED_URLS = [
    "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162",  # Parliament and Council legislation
    "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222",  # Official Journal L acts
]
NIST_DRAFTS_URL = "https://csrc.nist.gov/CSRC/media/feeds/pubs/drafts-open-for-comment.json"

FRAMEWORK_KEYWORDS: dict[str, list[str]] = {
    "GDPR": ["gdpr", "general data protection regulation", "regulation (eu) 2016/679", "data protection"],
    "DORA": ["dora", "digital operational resilience", "regulation (eu) 2022/2554"],
    "NIS2": ["nis2", "nis 2", "directive (eu) 2022/2555", "network and information systems"],
    "EU_AI_ACT": ["artificial intelligence act", "ai act", "regulation (eu) 2024/1689", "high-risk ai"],
    "NIST_800_53": ["800-53", "sp 800-53", "security and privacy controls"],
    "NIST_AI_RMF": ["ai risk management framework", "ai rmf", "nist ai"],
    "NIST_CSF": ["cybersecurity framework", "csf 2.0", "nist csf"],
    "INDIA_DPDP": ["digital personal data protection", "dpdp", "data protection board of india", "meity"],
}
EU_FRAMEWORK_CODES = {"GDPR", "DORA", "NIS2", "EU_AI_ACT"}
NIST_FRAMEWORK_CODES = {"NIST_800_53", "NIST_AI_RMF", "NIST_CSF"}
DPDP_FRAMEWORK_CODES = {"INDIA_DPDP"}


@dataclass(frozen=True)
class FeedSource:
    key: str
    name: str
    url: str | None
    framework_codes: set[str]
    parser: str


@dataclass(frozen=True)
class FeedItem:
    source_key: str
    source_name: str
    source_url: str | None
    item_id: str
    title: str
    summary: str | None
    item_url: str | None
    published_at: datetime | None
    raw: dict[str, Any]


SOURCES = [
    FeedSource("eurlex_legislation", "EUR-Lex Parliament and Council legislation RSS", EU_FEED_URLS[0], EU_FRAMEWORK_CODES, "rss"),
    FeedSource("eurlex_oj_l", "EUR-Lex Official Journal L RSS", EU_FEED_URLS[1], EU_FRAMEWORK_CODES, "rss"),
    FeedSource("nist_csrc_drafts", "NIST CSRC draft publications JSON", NIST_DRAFTS_URL, NIST_FRAMEWORK_CODES, "nist_json"),
    FeedSource("meity_dpdp", "MeitY DPDP public update feed", None, DPDP_FRAMEWORK_CODES, "missing"),
]


def _clean_text(value: str | None, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    if max_len is not None:
        return text[:max_len]
    return text


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


class RegulatoryIntelligenceService:
    def __init__(self, db: Session, http_client: httpx.Client | None = None) -> None:
        self.db = db
        self.http_client = http_client

    def list_alerts(self, org_id: uuid.UUID, *, status_filter: str | None = None, framework_code: str | None = None) -> list[RegulatoryChangeAlert]:
        stmt = select(RegulatoryChangeAlert).where(RegulatoryChangeAlert.organization_id == org_id)
        if status_filter is not None:
            if status_filter not in {"new", "acknowledged"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status must be new or acknowledged")
            stmt = stmt.where(RegulatoryChangeAlert.status == status_filter)
        if framework_code is not None:
            stmt = stmt.where(RegulatoryChangeAlert.framework_code == framework_code)
        return self.db.execute(stmt.order_by(RegulatoryChangeAlert.detected_at.desc())).scalars().all()

    def get_framework_impact(self, org_id: uuid.UUID, framework_code: str | None) -> dict[str, Any]:
        """Compute, live, which of the org's own obligations/controls this framework change actually touches.

        Recomputed on every read (not cached at alert-creation time) because an org's obligation
        applicability/implementation status changes independently of when the regulatory change was
        detected — a stale snapshot would mislead a compliance officer about current exposure.
        """
        empty: dict[str, Any] = {
            "impacted_obligation_count": 0,
            "impacted_open_obligation_count": 0,
            "impacted_control_count": 0,
            "impacted_obligation_samples": [],
        }
        if framework_code is None:
            return empty
        framework = self.db.execute(select(Framework).where(Framework.code == framework_code)).scalar_one_or_none()
        if framework is None:
            return empty
        obligations = self.db.execute(
            select(Obligation).where(Obligation.framework_id == framework.id, Obligation.status == "active")
        ).scalars().all()
        if not obligations:
            return empty
        obligation_ids = [o.id for o in obligations]
        states = {
            s.obligation_id: s
            for s in self.db.execute(
                select(OrganizationObligationState).where(
                    OrganizationObligationState.organization_id == org_id,
                    OrganizationObligationState.obligation_id.in_(obligation_ids),
                )
            ).scalars().all()
        }
        # An obligation with no org state yet is "pending" review (not yet ruled out) — treat as
        # in-scope until the org explicitly marks it not_applicable.
        applicable = [o for o in obligations if states.get(o.id) is None or states[o.id].applicability_status != "not_applicable"]
        open_obligations = [
            o for o in applicable if states.get(o.id) is None or states[o.id].implementation_status != "implemented"
        ]
        control_count = 0
        if applicable:
            control_count = self.db.execute(
                select(func.count(func.distinct(ControlObligationMapping.control_id))).where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.obligation_id.in_([o.id for o in applicable]),
                    ControlObligationMapping.status == "active",
                )
            ).scalar_one()
        return {
            "impacted_obligation_count": len(applicable),
            "impacted_open_obligation_count": len(open_obligations),
            "impacted_control_count": int(control_count or 0),
            "impacted_obligation_samples": [
                {"reference_code": o.reference_code, "title": o.title} for o in open_obligations[:5]
            ],
        }

    def _severity_for_impact(self, impact: dict[str, Any]) -> str:
        open_count = impact["impacted_open_obligation_count"]
        if open_count >= 5:
            return "high"
        if open_count >= 1:
            return "medium"
        return "low"

    def acknowledge_alert(self, org_id: uuid.UUID, alert_id: uuid.UUID, actor_user_id: uuid.UUID) -> RegulatoryChangeAlert:
        row = self.db.execute(
            select(RegulatoryChangeAlert).where(
                RegulatoryChangeAlert.id == alert_id,
                RegulatoryChangeAlert.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regulatory alert not found")
        if row.status == "acknowledged":
            return row
        row.status = "acknowledged"
        row.acknowledged_at = datetime.now(UTC)
        row.acknowledged_by_user_id = actor_user_id
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="regulatory_alert.acknowledged",
            entity_type="regulatory_change_alert",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"status": row.status, "framework_code": row.framework_code, "source_key": row.source_key},
            metadata_json={"source": "api"},
        )
        return row

    def poll_public_feeds(self) -> dict[str, int | list[dict[str, str]]]:
        active = self._active_frameworks_by_org()
        active_codes = set().union(*active.values()) if active else set()
        created = 0
        source_errors: list[dict[str, str]] = []
        for source in SOURCES:
            if not (source.framework_codes & active_codes):
                continue
            try:
                items = self._fetch_source(source)
            except Exception as exc:
                logger.warning("Regulatory feed source error", extra={"source_key": source.key, "error": str(exc)})
                source_errors.append({"source_key": source.key, "error": str(exc)[:500]})
                self._record_source_error(source, str(exc))
                continue
            for item in items:
                matches = self._matched_framework_codes(item, source.framework_codes & active_codes)
                for org_id, org_codes in active.items():
                    for framework_code in sorted(matches & org_codes):
                        if self._create_alert_if_new(org_id, item, framework_code):
                            created += 1
        return {"created": created, "source_errors": source_errors, "records_processed": created + len(source_errors)}

    def _active_frameworks_by_org(self) -> dict[uuid.UUID, set[str]]:
        rows = self.db.execute(
            select(OrganizationFramework.organization_id, Framework.code)
            .join(Framework, Framework.id == OrganizationFramework.framework_id)
            .where(OrganizationFramework.status == "active", Framework.status == "active")
        ).all()
        active: dict[uuid.UUID, set[str]] = {}
        for org_id, code in rows:
            active.setdefault(org_id, set()).add(code)
        return active

    def _fetch_source(self, source: FeedSource) -> list[FeedItem]:
        if source.parser == "missing" or not source.url:
            raise RuntimeError("No official public RSS/Atom feed is configured for this source; public HTML pages exist but no stable feed endpoint was verified")
        client = self.http_client or httpx.Client(timeout=15.0, follow_redirects=True)
        close_client = self.http_client is None
        try:
            response = client.get(source.url, headers={"User-Agent": "CompliVibe-Regulatory-Intelligence/1.0"})
            response.raise_for_status()
            if source.parser == "rss":
                return self._parse_rss(source, response.text)
            if source.parser == "nist_json":
                return self._parse_nist_json(source, response.text)
            raise RuntimeError(f"Unsupported parser {source.parser}")
        finally:
            if close_client:
                client.close()

    def _parse_rss(self, source: FeedSource, xml_text: str) -> list[FeedItem]:
        root = ET.fromstring(xml_text)
        items: list[FeedItem] = []
        for item in root.findall(".//item"):
            title = _clean_text(item.findtext("title"), max_len=500) or "Untitled regulatory update"
            summary = _clean_text(item.findtext("description"))
            link = _clean_text(item.findtext("link"), max_len=1000)
            guid = _clean_text(item.findtext("guid"), max_len=1000) or link or title
            published = _parse_datetime(item.findtext("pubDate"))
            item_id = self._source_item_id(source.key, guid, title)
            items.append(FeedItem(source.key, source.name, source.url, item_id, title, summary, link, published, {"guid": guid}))
        return items

    def _parse_nist_json(self, source: FeedSource, text: str) -> list[FeedItem]:
        payload = json.loads(text.lstrip("\ufeff"))
        items: list[FeedItem] = []
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                continue
            title = _clean_text(entry.get("title"), max_len=500) or "Untitled NIST publication"
            summary = _clean_text(entry.get("summary"))
            link = entry.get("id") or entry.get("link")
            published = _parse_datetime(entry.get("updated") or entry.get("published"))
            item_id = self._source_item_id(source.key, str(link or title), title)
            items.append(FeedItem(source.key, source.name, source.url, item_id, title, summary, str(link) if link else None, published, entry))
        return items

    def _matched_framework_codes(self, item: FeedItem, candidate_codes: set[str]) -> set[str]:
        haystack = " ".join([item.title or "", item.summary or "", item.item_url or ""]).lower()
        matches = {code for code in candidate_codes if any(keyword in haystack for keyword in FRAMEWORK_KEYWORDS.get(code, []))}
        return matches

    def _create_alert_if_new(self, org_id: uuid.UUID, item: FeedItem, framework_code: str) -> bool:
        existing = self.db.execute(
            select(RegulatoryChangeAlert.id).where(
                RegulatoryChangeAlert.organization_id == org_id,
                RegulatoryChangeAlert.source_key == item.source_key,
                RegulatoryChangeAlert.source_item_id == item.item_id,
                RegulatoryChangeAlert.framework_code == framework_code,
            )
        ).first()
        if existing is not None:
            return False
        keywords = ", ".join(FRAMEWORK_KEYWORDS.get(framework_code, [])[:4])
        impact = self.get_framework_impact(org_id, framework_code)
        severity = self._severity_for_impact(impact)
        match_reason = (
            f"Matched active framework {framework_code} using keywords: {keywords}. "
            f"Org exposure at detection time: {impact['impacted_obligation_count']} applicable obligation(s), "
            f"{impact['impacted_open_obligation_count']} not yet fully implemented, "
            f"{impact['impacted_control_count']} active control(s) mapped."
        )
        row = RegulatoryChangeAlert(
            organization_id=org_id,
            source_key=item.source_key,
            source_name=item.source_name,
            source_url=item.source_url,
            source_item_id=item.item_id,
            framework_code=framework_code,
            title=item.title,
            summary=item.summary,
            item_url=item.item_url,
            published_at=item.published_at,
            status="new",
            severity=severity,
            match_reason=match_reason,
            raw_item_json=item.raw,
        )
        try:
            with self.db.begin_nested():
                self.db.add(row)
                self.db.flush()
        except IntegrityError:
            # Two concurrent poll runs raced on the same (org, source, item, framework) tuple;
            # the unique constraint caught it, so this item is already recorded — not an error.
            logger.info(
                "Duplicate regulatory alert suppressed by unique constraint",
                extra={"organization_id": str(org_id), "source_key": item.source_key, "framework_code": framework_code},
            )
            return False
        AuditService(self.db).write_audit_log(
            action="regulatory_alert.created",
            entity_type="regulatory_change_alert",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"framework_code": framework_code, "source_key": item.source_key, "title": item.title},
            metadata_json={"source": "scheduler"},
        )
        return True

    def _record_source_error(self, source: FeedSource, error: str) -> None:
        item_id = self._source_item_id(source.key, "source_error", datetime.now(UTC).strftime("%Y-%m-%d"))
        existing = self.db.execute(
            select(RegulatoryChangeAlert).where(
                RegulatoryChangeAlert.organization_id.is_(None),
                RegulatoryChangeAlert.source_key == source.key,
                RegulatoryChangeAlert.source_item_id == item_id,
                RegulatoryChangeAlert.status == "source_error",
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.error_message = error[:2000]
            existing.detected_at = datetime.now(UTC)
            return
        self.db.add(
            RegulatoryChangeAlert(
                organization_id=None,
                source_key=source.key,
                source_name=source.name,
                source_url=source.url,
                source_item_id=item_id,
                framework_code=None,
                title=f"Regulatory source error: {source.name}",
                summary="Feed polling failed; this does not mean there were no regulatory changes.",
                status="source_error",
                severity="low",
                match_reason="Source polling error; retained for operational visibility.",
                raw_item_json={},
                error_message=error[:2000],
            )
        )
        self.db.flush()

    def _source_item_id(self, source_key: str, stable_id: str, title: str) -> str:
        return hashlib.sha256(f"{source_key}|{stable_id}|{title}".encode("utf-8")).hexdigest()[:64]


def run_daily_regulatory_change_poll(db: Session) -> dict[str, int | list[dict[str, str]]]:
    return RegulatoryIntelligenceService(db).poll_public_feeds()
