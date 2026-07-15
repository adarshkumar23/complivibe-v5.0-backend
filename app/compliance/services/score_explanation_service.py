"""Causal score-change explanation (Phase 4).

Generalizes the driver-narrative idea in
``BoardScorecardService._score_change_summary`` into a reusable service that
explains WHY a score moved across the diffable score families:

  * ``score_snapshots``      -- org scores (control_health, ...): exact weighted
                                delta decomposition (Layer 1) + best-effort
                                entity-cause enrichment (Layer 2) + framework
                                graph-PATH legs.
  * ``entity_risk_scores``   -- composite of per-risk contributions: which
                                linked risk's contribution moved.
  * ``board_scorecard_snapshots`` -- the original driver engine, quantified.

Two things are kept strictly distinct in the output contract (design §5.4):
  * a PRECISE numeric contribution (``points_delta``) for persisted-score legs
    whose exact arithmetic decomposition is available; and
  * a PATH-only explanation (``FrameworkPath``, no ``points_delta``) for
    framework/coverage legs, which have no historical snapshot to diff and so
    are NEVER presented as a precise delta.

Layer 2 never fabricates a cause: a moved component with real event coverage is
enriched with the actual triggering entity from ``domain_events``; a component
whose change type emits no event falls back to an explicit
``underlying_data_changed`` statement.

Everything is strictly ``organization_id``-scoped (reusing Phase 2's per-hop
graph isolation). This is a read-only v1 -- no persisted explanation, no
``write_audit_log`` (documented in the design doc as appropriate only for a
future persist/alert variant).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.entity_graph_traversal_service import EntityGraphTraversalService
from app.core.event_bus import EventType
from app.models.domain_event import DomainEvent
from app.models.score_snapshot import ScoreSnapshot

# --- Layer 1 decomposition spec ------------------------------------------------
# Leaf score = base + Σ coefficient * ratio  (then clamped [0,100] + rounded).
# Coefficients fold the formula's weight AND the *100 scaling, so a term's exact
# contribution to a score delta is  coefficient * (ratio_after - ratio_before).
# Verbatim from app/services/scoring_service.py (compute_* methods).
LEAF_DECOMPOSITION: dict[str, dict] = {
    "control_health": {
        "base": 0.0,
        "terms": {
            "implemented_ratio": 55.0,
            "latest_test_pass_ratio": 45.0,
            "needs_review_ratio": -20.0,
            "open_high_critical_issue_ratio": -30.0,
        },
    },
    "evidence_readiness": {
        "base": 0.0,
        "terms": {
            "verified_coverage_ratio": 100.0,
            "expired_control_ratio": -35.0,
            "needs_review_evidence_ratio": -20.0,
        },
    },
    "risk_posture": {
        "base": 100.0,
        "terms": {
            "critical_high_ratio": -50.0,
            "without_owner_ratio": -25.0,
            "without_controls_ratio": -25.0,
            "accepted_or_mitigated_ratio": 10.0,
        },
    },
    "task_hygiene": {
        # 100*(0.6c + 0.25(1-o) + 0.15(1-u)) = 40 + 60c - 25o - 15u
        "base": 40.0,
        "terms": {
            "completion_ratio": 60.0,
            "overdue_open_ratio": -25.0,
            "urgent_open_ratio": -15.0,
        },
    },
}
COMPOSITE_TYPES = {"compliance_readiness", "governance_health"}

# Which domain event types (if any) explain a moved leaf term, and the entity
# type they carry. Terms mapped to () have NO event coverage -> graceful fallback.
TERM_EVENT_COVERAGE: dict[str, tuple[str, tuple[str, ...]]] = {
    # control_health
    "implemented_ratio": ("control", (EventType.CONTROL_STATUS_CHANGED,)),
    "needs_review_ratio": ("control", (EventType.CONTROL_STATUS_CHANGED,)),
    "latest_test_pass_ratio": ("control", ()),          # control test runs emit no event
    "open_high_critical_issue_ratio": ("issue", ()),    # issue changes emit no event
    # evidence_readiness
    "verified_coverage_ratio": ("evidence", (EventType.EVIDENCE_STATUS_CHANGED,)),
    "needs_review_evidence_ratio": ("evidence", (EventType.EVIDENCE_STATUS_CHANGED,)),
    "expired_control_ratio": ("evidence", (EventType.EVIDENCE_EXPIRED,)),
    # risk_posture
    "critical_high_ratio": ("risk", (EventType.RISK_SCORE_UPDATED,)),
    "without_owner_ratio": ("risk", ()),                # owner assignment emits no event
    "without_controls_ratio": ("risk", ()),             # link changes emit no event
    "accepted_or_mitigated_ratio": ("risk", ()),        # risk status transition emits no event
}


@dataclass
class FrameworkPath:
    """A PATH-only explanation leg -- NOT a numeric delta (design §5.4).

    Deliberately carries no ``points_delta``: framework/coverage scores have no
    historical snapshot to diff, so this is a graph path to the affected
    obligations/frameworks, never a precise contribution.
    """

    kind: str  # always "graph_path"
    from_entity_type: str
    from_entity_id: uuid.UUID
    obligations: list[dict]  # [{obligation_id, reference_code, framework_id}]
    note: str


@dataclass
class Cause:
    cause_type: str  # "event" | "underlying_data_changed"
    detail: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    before: object = None
    after: object = None
    occurred_at: datetime | None = None
    framework_paths: list[FrameworkPath] = field(default_factory=list)


@dataclass
class Contribution:
    """A PRECISE contribution to the score delta (has points_delta)."""

    component: str
    kind: str  # "leaf_term" | "component_score"
    points_delta: float
    value_before: float
    value_after: float
    coefficient: float | None = None
    causes: list[Cause] = field(default_factory=list)
    sub_contributions: list["Contribution"] = field(default_factory=list)


@dataclass
class ScoreChangeExplanation:
    family: str  # "score_snapshot" | "entity_risk_score" | "board_scorecard"
    subject: str  # snapshot_type / entity ref / scope
    from_id: uuid.UUID | None
    to_id: uuid.UUID | None
    from_at: datetime | None
    to_at: datetime | None
    observed_delta: float
    raw_delta: float
    rounding_residual: float
    explanation_kind: str  # "precise_delta"
    contributions: list[Contribution]
    narrative: str


class ScoreExplanationError(ValueError):
    pass


class ScoreExplanationService:
    _MOVE_EPSILON = 1e-9

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Layer 1: exact arithmetic decomposition ------------------------------
    @staticmethod
    def raw_score(snapshot_type: str, breakdown_json: dict) -> float:
        """Recompute the UNCLAMPED, UNROUNDED score from breakdown_json.

        For leaves: base + Σ coef*ratio. For composites: Σ weight*component_score.
        Clamping+rounding this must reproduce the stored int score (a faithfulness
        check the caller can assert against real snapshots).
        """
        if snapshot_type in LEAF_DECOMPOSITION:
            spec = LEAF_DECOMPOSITION[snapshot_type]
            total = spec["base"]
            for key, coef in spec["terms"].items():
                total += coef * float(breakdown_json.get(key, 0.0) or 0.0)
            return total
        if snapshot_type in COMPOSITE_TYPES:
            comps = breakdown_json.get("components", {}) or {}
            weights = breakdown_json.get("weights", {}) or {}
            return sum(float(weights.get(k, 0.0)) * float(comps.get(k, 0.0)) for k in comps)
        raise ScoreExplanationError(f"No decomposition spec for snapshot_type '{snapshot_type}'")

    def _decompose(self, snapshot_type: str, from_bd: dict, to_bd: dict,
                   from_at: datetime, to_at: datetime, org_id: uuid.UUID) -> list[Contribution]:
        contributions: list[Contribution] = []
        if snapshot_type in LEAF_DECOMPOSITION:
            spec = LEAF_DECOMPOSITION[snapshot_type]
            for key, coef in spec["terms"].items():
                before = float(from_bd.get(key, 0.0) or 0.0)
                after = float(to_bd.get(key, 0.0) or 0.0)
                points = coef * (after - before)
                if abs(after - before) <= self._MOVE_EPSILON:
                    continue
                contributions.append(
                    Contribution(component=key, kind="leaf_term", points_delta=points,
                                 value_before=before, value_after=after, coefficient=coef)
                )
        elif snapshot_type in COMPOSITE_TYPES:
            comps_from = from_bd.get("components", {}) or {}
            comps_to = to_bd.get("components", {}) or {}
            weights = to_bd.get("weights", {}) or {}
            for comp, weight in weights.items():
                before = float(comps_from.get(comp, 0.0) or 0.0)
                after = float(comps_to.get(comp, 0.0) or 0.0)
                if abs(after - before) <= self._MOVE_EPSILON:
                    continue
                points = float(weight) * (after - before)
                contrib = Contribution(component=comp, kind="component_score", points_delta=points,
                                       value_before=before, value_after=after, coefficient=float(weight))
                # Recurse one level: fetch the component leaf's snapshots at the
                # same two calculated_at instants and decompose which ratio moved.
                if comp in LEAF_DECOMPOSITION:
                    sub_from = self._snapshot_at(org_id, comp, from_at)
                    sub_to = self._snapshot_at(org_id, comp, to_at)
                    if sub_from is not None and sub_to is not None:
                        contrib.sub_contributions = self._decompose(
                            comp, sub_from.breakdown_json, sub_to.breakdown_json, from_at, to_at, org_id
                        )
                contributions.append(contrib)
        else:
            raise ScoreExplanationError(f"No decomposition spec for snapshot_type '{snapshot_type}'")
        contributions.sort(key=lambda c: c.points_delta)  # most-negative (biggest drop) first
        return contributions

    def _snapshot_at(self, org_id: uuid.UUID, snapshot_type: str, calculated_at: datetime) -> ScoreSnapshot | None:
        return self.db.execute(
            select(ScoreSnapshot).where(
                ScoreSnapshot.organization_id == org_id,
                ScoreSnapshot.snapshot_type == snapshot_type,
                ScoreSnapshot.calculated_at == calculated_at,
            ).order_by(ScoreSnapshot.created_at.desc())
        ).scalars().first()

    # ---- Layer 2: entity-cause enrichment (best-effort, never fabricated) -----
    def _enrich_leaf_contribution(self, org_id: uuid.UUID, contrib: Contribution,
                                  from_at: datetime, to_at: datetime) -> None:
        entity_type, event_types = TERM_EVENT_COVERAGE.get(contrib.component, (None, ()))
        if not event_types:
            # No event coverage for this change type -> explicit, non-fabricated fallback.
            contrib.causes.append(Cause(
                cause_type="underlying_data_changed",
                detail=(f"'{contrib.component}' moved {contrib.value_before}->{contrib.value_after}; "
                        "this input's change type does not emit a domain event, so no specific "
                        "triggering entity can be attributed from the event log."),
            ))
            return
        rows = self.db.execute(
            select(DomainEvent).where(
                DomainEvent.organization_id == org_id,
                DomainEvent.event_type.in_(list(event_types)),
                DomainEvent.occurred_at > from_at,
                DomainEvent.occurred_at <= to_at,
            ).order_by(DomainEvent.occurred_at.asc())
        ).scalars().all()
        if not rows:
            contrib.causes.append(Cause(
                cause_type="underlying_data_changed",
                detail=(f"'{contrib.component}' moved {contrib.value_before}->{contrib.value_after}; "
                        "no matching domain event was recorded in this window."),
            ))
            return
        for ev in rows:
            cause = Cause(
                cause_type="event",
                detail=f"{ev.entity_type} {ev.event_type}: {ev.previous_value} -> {ev.new_value}",
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                before=ev.previous_value,
                after=ev.new_value,
                occurred_at=ev.occurred_at,
            )
            # Framework/coverage leg: for a control cause, attach a graph PATH to
            # the obligations/frameworks it touches -- explicitly a path, no delta.
            if ev.entity_type == "control":
                cause.framework_paths = self._framework_paths(org_id, ev.entity_id)
            contrib.causes.append(cause)

    def _enrich_all(self, org_id: uuid.UUID, contributions: list[Contribution],
                    from_at: datetime, to_at: datetime) -> None:
        for contrib in contributions:
            if contrib.kind == "leaf_term":
                self._enrich_leaf_contribution(org_id, contrib, from_at, to_at)
            self._enrich_all(org_id, contrib.sub_contributions, from_at, to_at)

    # ---- Framework leg: graph PATH (never a numeric delta) --------------------
    def _framework_paths(self, org_id: uuid.UUID, control_id: uuid.UUID) -> list[FrameworkPath]:
        try:
            result = EntityGraphTraversalService(self.db).traverse(
                anchor_type="control", anchor_id=control_id, organization_id=org_id, max_depth=1,
            )
        except Exception:  # noqa: BLE001 - graph enrichment is best-effort
            return []
        obligation_ids = [
            n.entity_id for n in result.nodes
            if n.entity_type == "obligation" and n.depth == 1
            and "control_satisfies_obligation" in n.via_edge_types
        ]
        if not obligation_ids:
            return []
        from app.models.obligation import Obligation

        # Obligations are global framework definitions (no organization_id); the
        # org scope is already enforced by the org-scoped graph traversal above,
        # which only reaches obligations linked via THIS org's mapping rows.
        rows = self.db.execute(
            select(Obligation).where(Obligation.id.in_(obligation_ids))
        ).scalars().all()
        obligations = [
            {
                "obligation_id": str(o.id),
                "reference_code": getattr(o, "reference_code", None),
                "framework_id": str(o.framework_id) if getattr(o, "framework_id", None) else None,
            }
            for o in rows
        ]
        if not obligations:
            return []
        return [FrameworkPath(
            kind="graph_path",
            from_entity_type="control",
            from_entity_id=control_id,
            obligations=obligations,
            note="Framework/coverage leg is a graph PATH to affected obligations, "
                 "not a numeric score delta (no framework snapshot exists to diff).",
        )]

    # ---- Public: score_snapshots ---------------------------------------------
    def explain_snapshot_change(self, *, org_id: uuid.UUID, snapshot_type: str,
                                from_id: uuid.UUID | None = None,
                                to_id: uuid.UUID | None = None) -> ScoreChangeExplanation:
        if snapshot_type not in LEAF_DECOMPOSITION and snapshot_type not in COMPOSITE_TYPES:
            raise ScoreExplanationError(f"Unsupported snapshot_type '{snapshot_type}'")
        to_snap = self._require_snapshot(org_id, to_id) if to_id else self._latest_two(org_id, snapshot_type)[1]
        from_snap = self._require_snapshot(org_id, from_id) if from_id else self._latest_two(org_id, snapshot_type)[0]
        if from_snap is None or to_snap is None:
            raise ScoreExplanationError("Need at least two snapshots of this type to explain a change")
        if from_snap.snapshot_type != snapshot_type or to_snap.snapshot_type != snapshot_type:
            raise ScoreExplanationError("Snapshot type mismatch")

        contributions = self._decompose(
            snapshot_type, from_snap.breakdown_json, to_snap.breakdown_json,
            from_snap.calculated_at, to_snap.calculated_at, org_id,
        )
        self._enrich_all(org_id, contributions, from_snap.calculated_at, to_snap.calculated_at)

        raw_delta = self.raw_score(snapshot_type, to_snap.breakdown_json) - self.raw_score(snapshot_type, from_snap.breakdown_json)
        observed_delta = float(to_snap.score - from_snap.score)
        narrative = self._narrative(snapshot_type, observed_delta, from_snap.calculated_at, contributions)
        return ScoreChangeExplanation(
            family="score_snapshot", subject=snapshot_type,
            from_id=from_snap.id, to_id=to_snap.id,
            from_at=from_snap.calculated_at, to_at=to_snap.calculated_at,
            observed_delta=observed_delta, raw_delta=raw_delta,
            rounding_residual=round(observed_delta - raw_delta, 6),
            explanation_kind="precise_delta", contributions=contributions, narrative=narrative,
        )

    def _require_snapshot(self, org_id: uuid.UUID, snap_id: uuid.UUID) -> ScoreSnapshot:
        row = self.db.execute(
            select(ScoreSnapshot).where(ScoreSnapshot.organization_id == org_id, ScoreSnapshot.id == snap_id)
        ).scalar_one_or_none()
        if row is None:
            raise ScoreExplanationError("Snapshot not found")
        return row

    def _latest_two(self, org_id: uuid.UUID, snapshot_type: str) -> tuple[ScoreSnapshot | None, ScoreSnapshot | None]:
        rows = self.db.execute(
            select(ScoreSnapshot).where(
                ScoreSnapshot.organization_id == org_id, ScoreSnapshot.snapshot_type == snapshot_type,
            ).order_by(ScoreSnapshot.calculated_at.desc(), ScoreSnapshot.created_at.desc()).limit(2)
        ).scalars().all()
        if len(rows) < 2:
            return None, None
        return rows[1], rows[0]  # (previous, latest)

    # ---- Public: entity_risk_scores ------------------------------------------
    def explain_entity_risk_change(self, *, org_id: uuid.UUID, entity_type: str,
                                   entity_id: uuid.UUID) -> ScoreChangeExplanation:
        """Diff the latest two entity_risk_scores rows: which linked risk's
        weighted contribution moved. Enriched with RISK_SCORE_UPDATED causes."""
        from app.models.entity_risk_score import EntityRiskScore

        rows = self.db.execute(
            select(EntityRiskScore).where(
                EntityRiskScore.organization_id == org_id,
                EntityRiskScore.entity_type == entity_type,
                EntityRiskScore.entity_id == entity_id,
            ).order_by(EntityRiskScore.computed_at.desc()).limit(2)
        ).scalars().all()
        if len(rows) < 2:
            raise ScoreExplanationError("Need at least two entity_risk_scores rows to explain a change")
        to_row, from_row = rows[0], rows[1]

        def by_risk(components) -> dict[str, dict]:
            out: dict[str, dict] = {}
            for c in (components if isinstance(components, list) else []):
                rid = c.get("risk_id")
                if rid:
                    out[str(rid)] = c
            return out

        prev, cur = by_risk(from_row.component_risks_json), by_risk(to_row.component_risks_json)
        set_stable = set(prev.keys()) == set(cur.keys())
        contributions: list[Contribution] = []
        for rid in set(prev) | set(cur):
            wc_before = float((prev.get(rid) or {}).get("weighted_contribution") or 0.0)
            wc_after = float((cur.get(rid) or {}).get("weighted_contribution") or 0.0)
            if abs(wc_after - wc_before) <= self._MOVE_EPSILON:
                continue
            # composite = (Σ weighted_contribution / 25) * 100  => per-risk factor 4.0
            points = 4.0 * (wc_after - wc_before)
            label = (cur.get(rid) or prev.get(rid) or {}).get("risk_name") or rid
            contrib = Contribution(component=f"risk:{label}", kind="component_score", points_delta=points,
                                   value_before=wc_before, value_after=wc_after, coefficient=4.0)
            self._enrich_risk_cause(org_id, contrib, uuid.UUID(rid), from_row.computed_at, to_row.computed_at)
            contributions.append(contrib)
        contributions.sort(key=lambda c: c.points_delta)

        observed_delta = float(to_row.composite_score) - float(from_row.composite_score)
        raw_delta = 4.0 * (
            sum(float((cur.get(r) or {}).get("weighted_contribution") or 0.0) for r in cur)
            - sum(float((prev.get(r) or {}).get("weighted_contribution") or 0.0) for r in prev)
        )
        # When the risk set changes, equal_weight reweights everything -> per-risk
        # attribution is approximate, not an exact reconstruction. Say so honestly.
        kind = "precise_delta" if set_stable else "approximate_delta"
        return ScoreChangeExplanation(
            family="entity_risk_score", subject=f"{entity_type}:{entity_id}",
            from_id=from_row.id, to_id=to_row.id, from_at=from_row.computed_at, to_at=to_row.computed_at,
            observed_delta=observed_delta, raw_delta=raw_delta,
            rounding_residual=round(observed_delta - raw_delta, 6),
            explanation_kind=kind, contributions=contributions,
            narrative=self._narrative(f"{entity_type} risk score", observed_delta, from_row.computed_at, contributions),
        )

    def _enrich_risk_cause(self, org_id, contrib, risk_id, from_at, to_at) -> None:
        rows = self.db.execute(
            select(DomainEvent).where(
                DomainEvent.organization_id == org_id,
                DomainEvent.event_type == EventType.RISK_SCORE_UPDATED,
                DomainEvent.entity_type == "risk",
                DomainEvent.entity_id == risk_id,
                DomainEvent.occurred_at > from_at,
                DomainEvent.occurred_at <= to_at,
            ).order_by(DomainEvent.occurred_at.asc())
        ).scalars().all()
        if not rows:
            contrib.causes.append(Cause(
                cause_type="underlying_data_changed",
                detail=f"risk {risk_id} contribution changed; no RISK_SCORE_UPDATED event in window.",
            ))
            return
        for ev in rows:
            contrib.causes.append(Cause(
                cause_type="event", detail=f"risk {ev.event_type}: {ev.previous_value} -> {ev.new_value}",
                entity_type="risk", entity_id=ev.entity_id, before=ev.previous_value,
                after=ev.new_value, occurred_at=ev.occurred_at,
            ))

    # ---- Public: board_scorecard_snapshots (generalizes _score_change_summary) -
    def explain_board_change(self, *, org_id: uuid.UUID,
                             business_unit_id: uuid.UUID | None = None) -> ScoreChangeExplanation:
        """Quantified version of BoardScorecardService._score_change_summary:
        board score = (framework_coverage_avg + control_effectiveness_pct)/2, so
        each leg contributes 0.5 * its delta. Framework coverage here IS numeric
        (it's stored on the board snapshot), distinct from the score_snapshot
        framework-leg which is path-only."""
        from app.models.board_scorecard_snapshot import BoardScorecardSnapshot

        stmt = select(BoardScorecardSnapshot).where(BoardScorecardSnapshot.organization_id == org_id)
        if business_unit_id is not None:
            stmt = stmt.where(BoardScorecardSnapshot.business_unit_id == business_unit_id)
        rows = self.db.execute(stmt.order_by(BoardScorecardSnapshot.created_at.desc()).limit(2)).scalars().all()
        if len(rows) < 2:
            raise ScoreExplanationError("Need at least two board scorecard snapshots to explain a change")
        to_row, from_row = rows[0], rows[1]

        def eff(row) -> float:
            d = row.snapshot_data if isinstance(row.snapshot_data, dict) else {}
            return float((d.get("control_effectiveness") or {}).get("effectiveness_pct", 0.0))

        def cov(row) -> float:
            d = row.snapshot_data if isinstance(row.snapshot_data, dict) else {}
            fw = d.get("framework_readiness") or {}
            rows_ = fw.get("rows", []) if isinstance(fw, dict) else []
            return (sum(float(x.get("control_coverage_pct", 0.0)) for x in rows_) / len(rows_)) if rows_ else 0.0

        contributions: list[Contribution] = []
        for name, before, after in (
            ("control_effectiveness_pct", eff(from_row), eff(to_row)),
            ("framework_coverage_avg_pct", cov(from_row), cov(to_row)),
        ):
            if abs(after - before) <= self._MOVE_EPSILON:
                continue
            contributions.append(Contribution(component=name, kind="component_score",
                                              points_delta=0.5 * (after - before),
                                              value_before=before, value_after=after, coefficient=0.5))
        contributions.sort(key=lambda c: c.points_delta)
        observed_delta = float(to_row.overall_compliance_score) - float(from_row.overall_compliance_score)
        raw_delta = sum(c.points_delta for c in contributions)
        return ScoreChangeExplanation(
            family="board_scorecard", subject="board_scorecard",
            from_id=from_row.id, to_id=to_row.id, from_at=from_row.created_at, to_at=to_row.created_at,
            observed_delta=observed_delta, raw_delta=raw_delta,
            rounding_residual=round(observed_delta - raw_delta, 6),
            explanation_kind="precise_delta", contributions=contributions,
            narrative=self._narrative("board scorecard", observed_delta, from_row.created_at, contributions),
        )

    @staticmethod
    def _narrative(snapshot_type: str, observed_delta: float, from_at: datetime,
                   contributions: list[Contribution]) -> str:
        if not contributions or observed_delta == 0:
            return f"{snapshot_type} is unchanged since {from_at.isoformat()}."
        direction = "improved" if observed_delta > 0 else "dropped"
        drivers = "; ".join(
            f"{c.component} {'+' if c.points_delta >= 0 else ''}{round(c.points_delta, 2)}pts"
            for c in contributions[:3]
        )
        return (f"{snapshot_type} {direction} {abs(round(observed_delta,2))}pts since {from_at.isoformat()}, "
                f"driven by: {drivers}.")
