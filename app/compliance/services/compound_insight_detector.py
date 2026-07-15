"""Deterministic compound-exposure detector (Phase 3 recommendation engine).

Code detects; AI only narrates. For each PatternSpec this:
  1. picks anchor candidates (real anchor-table query, org-scoped),
  2. resolves each leg via depth-1 adjacency from Phase 2's traversal service
     (org-isolated at every hop) + real-field predicate checks,
  3. on a full graph-connected conjunction, persists a compound_insights row with
     a deterministic TEMPLATED narrative FIRST (source of truth),
  4. writes an audit-log entry, notifies humans (separate call), then best-effort
     upgrades the narrative via Groq -- never suppressing a real detection if the
     AI step fails,
  5. deduplicates by sha256(org | pattern_id | sorted matched node type:ids).

All of this runs inside the CALLER's session (an APScheduler job with its own
committed session), never inside the event-bus publisher transaction.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance.services.compound_insight_notification_service import (
    CompoundInsightNotificationService,
)
from app.compliance.services.compound_pattern_registry import (
    ANCHOR_ROLE,
    ENTITY_MODEL_LABELS,
    PATTERN_REGISTRY,
    VENDOR_ASSESSMENT_NONTERMINAL,
    Condition,
    LegSpec,
    PatternSpec,
)
from app.compliance.services.entity_graph_traversal_service import EntityGraphTraversalService
from app.models.compound_insight import CompoundInsight
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _load_model(entity_type: str):
    dotted, label_attr = ENTITY_MODEL_LABELS[entity_type]
    module_path, cls_name = dotted.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), cls_name), label_attr


class _BoundNode:
    __slots__ = ("role", "entity_type", "entity_id", "record", "label")

    def __init__(self, role, entity_type, entity_id, record, label):
        self.role = role
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.record = record
        self.label = label


class CompoundInsightDetector:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.traversal = EntityGraphTraversalService(db)

    # ---- utcnow (overridable in tests) ------------------------------------
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    # ---- condition evaluation ---------------------------------------------
    def _vendor_assessment_overdue(self, org_id: uuid.UUID, vendor_id: uuid.UUID, days: int) -> bool:
        from app.models.vendor_assessment import VendorAssessment

        cutoff = date.today() - timedelta(days=int(days))
        row = self.db.execute(
            select(VendorAssessment.id).where(
                VendorAssessment.organization_id == org_id,
                VendorAssessment.vendor_id == vendor_id,
                VendorAssessment.status.in_(VENDOR_ASSESSMENT_NONTERMINAL),
                VendorAssessment.due_date.is_not(None),
                VendorAssessment.due_date <= cutoff,
            ).limit(1)
        ).first()
        return row is not None

    def _eval_condition(self, entity_type: str, record, cond: Condition) -> bool:
        if cond.op == "derived":
            if entity_type == "vendor" and cond.field == "__assessment_overdue_days__":
                return self._vendor_assessment_overdue(record.organization_id, record.id, cond.value)
            raise ValueError(f"Unknown derived condition {entity_type}.{cond.field}")
        actual = getattr(record, cond.field, None)
        if cond.op == "in":
            return actual in cond.value
        if cond.op == "not_in":
            return actual not in cond.value
        if cond.op == "eq":
            return actual == cond.value
        raise ValueError(f"Unknown condition op '{cond.op}'")

    def _matches(self, entity_type: str, record, conditions) -> bool:
        return all(self._eval_condition(entity_type, record, c) for c in conditions)

    def _load_record(self, entity_type: str, entity_id: uuid.UUID, org_id: uuid.UUID):
        model, label_attr = _load_model(entity_type)
        rec = self.db.execute(
            select(model).where(model.id == entity_id, model.organization_id == org_id)
        ).scalar_one_or_none()
        return rec, label_attr

    # ---- adjacency via Phase 2 traversal (org-isolated) -------------------
    def _adjacent_ids(self, from_type: str, from_id: uuid.UUID, org_id: uuid.UUID,
                      target_type: str, edge_type: str) -> list[uuid.UUID]:
        result = self.traversal.traverse(
            anchor_type=from_type, anchor_id=from_id, organization_id=org_id, max_depth=1,
        )
        return [
            n.entity_id
            for n in result.nodes
            if n.entity_type == target_type and n.depth == 1 and edge_type in n.via_edge_types
        ]

    # ---- detection --------------------------------------------------------
    def detect_for_anchor(self, org_id: uuid.UUID, pattern: PatternSpec, anchor_id: uuid.UUID):
        """Return an ordered list[_BoundNode] (anchor first) on a full match, else None."""
        anchor_rec, anchor_label_attr = self._load_record(pattern.anchor_entity_type, anchor_id, org_id)
        if anchor_rec is None or not self._matches(pattern.anchor_entity_type, anchor_rec, pattern.anchor_conditions):
            return None

        bound: dict[str, _BoundNode] = {
            ANCHOR_ROLE: _BoundNode(
                ANCHOR_ROLE, pattern.anchor_entity_type, anchor_id, anchor_rec,
                getattr(anchor_rec, anchor_label_attr, str(anchor_id)),
            )
        }

        for leg in pattern.legs:
            from_node = bound[leg.from_role]
            candidate_ids = self._adjacent_ids(
                from_node.entity_type, from_node.entity_id, org_id,
                leg.predicate.entity_type, leg.reached_via,
            )
            matched: list[_BoundNode] = []
            for cid in candidate_ids:
                rec, label_attr = self._load_record(leg.predicate.entity_type, cid, org_id)
                if rec is not None and self._matches(leg.predicate.entity_type, rec, leg.predicate.conditions):
                    matched.append(
                        _BoundNode(leg.role, leg.predicate.entity_type, cid, rec,
                                   getattr(rec, label_attr, str(cid)))
                    )
            if not matched:
                return None
            # deterministic single binding: lowest id (keeps volume ~1 per anchor)
            matched.sort(key=lambda b: str(b.entity_id))
            bound[leg.role] = matched[0]

        return [bound[role] for role in pattern.all_roles()]

    # ---- dedup / narrative ------------------------------------------------
    @staticmethod
    def dedup_key(org_id: uuid.UUID, pattern: PatternSpec, bound: list[_BoundNode]) -> str:
        roles = pattern.dedup_roles or pattern.all_roles()
        by_role = {b.role: b for b in bound}
        parts = sorted(f"{r}:{by_role[r].entity_type}:{by_role[r].entity_id}" for r in roles)
        raw = f"{org_id}|{pattern.pattern_id}|" + "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _format_values(bound: list[_BoundNode]) -> dict[str, str]:
        values: dict[str, str] = {}
        for b in bound:
            values[b.role] = str(b.label)
            sev = getattr(b.record, "severity", None)
            if sev is not None:
                values[f"{b.role}_severity"] = str(sev)
        return values

    def _templated_narrative(self, pattern: PatternSpec, bound: list[_BoundNode]) -> str:
        values = defaultdict(lambda: "?", self._format_values(bound))
        return pattern.narrative_template.format_map(values)

    @staticmethod
    def _matched_nodes_json(bound: list[_BoundNode]) -> dict:
        out: dict[str, dict] = {}
        for b in bound:
            attrs: dict[str, str] = {}
            for a in ("status", "severity", "risk_tier", "criticality", "freshness_status"):
                v = getattr(b.record, a, None)
                if v is not None:
                    attrs[a] = str(v)
            out[b.role] = {"entity_type": b.entity_type, "entity_id": str(b.entity_id), "label": str(b.label), "attrs": attrs}
        return out

    # ---- surfacing --------------------------------------------------------
    def surface(self, org_id: uuid.UUID, pattern: PatternSpec, bound: list[_BoundNode]) -> tuple[CompoundInsight, bool]:
        """Create-or-dedup the insight. Returns (insight, created)."""
        key = self.dedup_key(org_id, pattern, bound)
        existing = self.db.execute(
            select(CompoundInsight).where(
                CompoundInsight.organization_id == org_id,
                CompoundInsight.dedup_key == key,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if existing is not None:
            if existing.status == "surfaced":
                # already-known, already-shown: bump, do NOT re-notify.
                existing.detection_count = (existing.detection_count or 0) + 1
                existing.last_detected_at = now
                self.db.flush()
                return existing, False
            # a previously auto-resolved insight re-forming: reopen as a fresh surfacing.
            existing.status = "surfaced"
            existing.resolved_at = None
            existing.detection_count = (existing.detection_count or 0) + 1
            existing.last_detected_at = now
            insight = existing
            created = True
        else:
            templated = self._templated_narrative(pattern, bound)
            insight = CompoundInsight(
                organization_id=org_id,
                pattern_id=pattern.pattern_id,
                severity=pattern.insight_severity,
                status="surfaced",
                dedup_key=key,
                title=pattern.title,
                templated_narrative=templated,
                narrative_source="template",
                matched_nodes_json=self._matched_nodes_json(bound),
                detection_count=1,
                first_detected_at=now,
                last_detected_at=now,
            )
            # Concurrency guard: two scheduler runs (reactive drain + nightly
            # sweep) can race on the same (org, dedup_key). The unique constraint
            # makes a duplicate impossible; we absorb the loser's IntegrityError
            # inside a SAVEPOINT and fall through to the dedup path, so the losing
            # run continues cleanly instead of poisoning its whole batch.
            try:
                with self.db.begin_nested():
                    self.db.add(insight)
                    self.db.flush()
            except IntegrityError:
                try:
                    self.db.expunge(insight)
                except Exception:  # noqa: BLE001
                    pass
                winner = self.db.execute(
                    select(CompoundInsight).where(
                        CompoundInsight.organization_id == org_id,
                        CompoundInsight.dedup_key == key,
                    )
                ).scalar_one()
                if winner.status != "surfaced":
                    winner.status = "surfaced"
                    winner.resolved_at = None
                winner.detection_count = (winner.detection_count or 0) + 1
                winner.last_detected_at = now
                self.db.flush()
                return winner, False
            created = True

        if created and existing is not None:
            self.db.flush()  # reopen path already added to session; ensure persisted

        # Audit trail (does NOT itself notify a human).
        AuditService(self.db).write_audit_log(
            action="compound_insight.surfaced",
            entity_type="compound_insight",
            entity_id=insight.id,
            organization_id=org_id,
            after_json={
                "pattern_id": pattern.pattern_id,
                "severity": insight.severity,
                "matched_nodes": insight.matched_nodes_json,
            },
            metadata_json={"dedup_key": key},
        )

        # Best-effort AI narrative upgrade (never blocks/undoes the detection).
        self._attempt_ai_upgrade(org_id, pattern, bound, insight)

        # Explicit, separate human notification (preference-gated email).
        try:
            CompoundInsightNotificationService(self.db).notify(insight)
        except Exception:  # noqa: BLE001
            logger.warning("Compound insight notification failed; insight still surfaced", exc_info=True)

        return insight, True

    def _attempt_ai_upgrade(self, org_id, pattern, bound, insight) -> None:
        try:
            from app.ai_governance.services.ai_provider_service import AIProviderService

            payload = {
                "pattern_id": pattern.pattern_id,
                "insight_severity": pattern.insight_severity,
                "nodes": [
                    {"role": b.role, "entity_type": b.entity_type, "label": str(b.label),
                     **self._matched_nodes_json([b])[b.role]["attrs"]}
                    for b in bound
                ],
            }
            narrative, provider, byo = AIProviderService(self.db).generate_compound_narrative(
                org_id=org_id, pattern_payload=payload
            )
            insight.narrative_headline = narrative["headline"]
            insight.narrative_summary = narrative["summary"]
            insight.recommended_actions_json = narrative["recommended_actions"]
            insight.narrative_source = "ai"
            insight.provider_used = provider
            insight.used_byo_credentials = byo
            self.db.flush()
        except Exception:  # noqa: BLE001
            # Groq/Azure failure, timeout, or malformed output -> keep the template.
            logger.warning("Compound insight AI narrative upgrade failed; keeping templated narrative", exc_info=True)

    def detect_and_surface(self, org_id: uuid.UUID, pattern: PatternSpec, anchor_id: uuid.UUID):
        bound = self.detect_for_anchor(org_id, pattern, anchor_id)
        if bound is None:
            return None, False
        return self.surface(org_id, pattern, bound)

    # ---- drivers ----------------------------------------------------------
    def _anchor_candidates(self, org_id: uuid.UUID, pattern: PatternSpec) -> list[uuid.UUID]:
        model, _ = _load_model(pattern.anchor_entity_type)
        stmt = select(model.id).where(model.organization_id == org_id)
        for cond in pattern.anchor_conditions:
            if cond.op == "eq":
                stmt = stmt.where(getattr(model, cond.field) == cond.value)
            elif cond.op == "in":
                stmt = stmt.where(getattr(model, cond.field).in_(cond.value))
            elif cond.op == "not_in":
                stmt = stmt.where(getattr(model, cond.field).notin_(cond.value))
        return [r[0] for r in self.db.execute(stmt).all()]

    def run_for_candidate(self, org_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> int:
        """Event-driven path: re-check patterns touching a flagged node. Returns #created."""
        created = 0
        for pattern in PATTERN_REGISTRY:
            anchor_ids: set[uuid.UUID] = set()
            if entity_type == pattern.anchor_entity_type:
                anchor_ids.add(entity_id)
            elif entity_type in {leg.predicate.entity_type for leg in pattern.legs}:
                # flagged node is a leg -> find connected anchor candidates
                res = self.traversal.traverse(
                    anchor_type=entity_type, anchor_id=entity_id, organization_id=org_id, max_depth=2,
                )
                anchor_ids.update(
                    n.entity_id for n in res.nodes if n.entity_type == pattern.anchor_entity_type
                )
            for aid in anchor_ids:
                _, was_created = self.detect_and_surface(org_id, pattern, aid)
                if was_created:
                    created += 1
        return created

    def sweep_org(self, org_id: uuid.UUID) -> dict:
        """Full sweep for one org: detect all patterns + auto-resolve stale insights."""
        created = 0
        for pattern in PATTERN_REGISTRY:
            for aid in self._anchor_candidates(org_id, pattern):
                _, was_created = self.detect_and_surface(org_id, pattern, aid)
                if was_created:
                    created += 1
        resolved = self.auto_resolve_org(org_id)
        return {"created": created, "auto_resolved": resolved}

    def auto_resolve_org(self, org_id: uuid.UUID) -> int:
        """Auto-resolve surfaced insights whose exact conjunction no longer holds."""
        patterns_by_id = {p.pattern_id: p for p in PATTERN_REGISTRY}
        open_insights = self.db.execute(
            select(CompoundInsight).where(
                CompoundInsight.organization_id == org_id,
                CompoundInsight.status == "surfaced",
            )
        ).scalars().all()
        resolved = 0
        for insight in open_insights:
            pattern = patterns_by_id.get(insight.pattern_id)
            anchor_ref = (insight.matched_nodes_json or {}).get(ANCHOR_ROLE, {})
            anchor_id_raw = anchor_ref.get("entity_id")
            still_holds = False
            if pattern is not None and anchor_id_raw:
                bound = self.detect_for_anchor(org_id, pattern, uuid.UUID(str(anchor_id_raw)))
                if bound is not None and self.dedup_key(org_id, pattern, bound) == insight.dedup_key:
                    still_holds = True
            if not still_holds:
                insight.status = "auto_resolved"
                insight.resolved_at = self.utcnow()
                resolved += 1
        self.db.flush()
        return resolved
