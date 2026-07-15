"""Config-driven compound-pattern registry (Phase 3 recommendation engine).

Mirrors the spirit of Phase 2's EdgeSpec registry: each pattern is a declarative
spec describing a graph shape to match (anchor + legs connected by real Phase 2
edge types) plus real-field predicates each matched node must satisfy. Detection
is deterministic; the AI layer only narrates a match code has already confirmed.

Only the CONSERVATIVE initial set (patterns A, B, C) is registered. Patterns D/E
from the design doc are deferred. All entity types, edge types, statuses and
severities below are the REAL vocabularies audited from the codebase (see
docs/recommendation_engine_design.md sections 1 and 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Real field vocabularies (verbatim from the audited schemas/services) -----
# Risk is "open" when not in a terminal state (RiskService.score_to_severity /
# app/schemas/risk.py). Severity is a stored, derived low/medium/high/critical.
RISK_OPEN_STATUSES = ("identified", "assessing", "treatment_planned", "in_treatment", "monitored")
HIGH_CRITICAL = ("high", "critical")
# A vendor assessment is a "stale" leg when non-terminal and >= this many days
# past due_date. The codebase's own overdue check is N=0; we conservatively
# tighten to 30 (the platform's existing "materially stale" horizon).
VENDOR_STALE_MIN_OVERDUE_DAYS = 30
VENDOR_ASSESSMENT_NONTERMINAL = ("draft", "in_progress", "under_review")

ANCHOR_ROLE = "anchor"


@dataclass(frozen=True)
class Condition:
    """A predicate on one real column of a matched node's record.

    op:
      - "in"     : getattr(record, field) in value           (value is a tuple)
      - "eq"     : getattr(record, field) == value
      - "not_in" : getattr(record, field) not in value
      - "derived": dispatch to a named handler in the detector keyed by
                   (entity_type, field); value is passed to the handler
                   (e.g. vendor "__assessment_overdue_days__" with value=30).
    """

    field: str
    op: str
    value: object


@dataclass(frozen=True)
class NodePredicate:
    entity_type: str
    conditions: tuple[Condition, ...]


@dataclass(frozen=True)
class LegSpec:
    role: str
    predicate: NodePredicate
    reached_via: str          # a real Phase 2 edge_type connecting this leg in
    from_role: str = ANCHOR_ROLE  # which already-matched node this leg hangs off (depth-1 adjacency)


@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    title: str
    insight_severity: str      # severity assigned WHEN matched
    anchor_entity_type: str
    anchor_conditions: tuple[Condition, ...]
    legs: tuple[LegSpec, ...]
    narrative_template: str    # deterministic fallback; roles are {role_label} placeholders
    dedup_roles: tuple[str, ...] = ()  # roles forming the dedup key; () => anchor + all legs

    @property
    def anchor_predicate(self) -> NodePredicate:
        return NodePredicate(self.anchor_entity_type, self.anchor_conditions)

    def all_roles(self) -> tuple[str, ...]:
        return (ANCHOR_ROLE,) + tuple(leg.role for leg in self.legs)


# ---------------------------------------------------------------------------
# Initial conservative patterns (A, B, C).
# ---------------------------------------------------------------------------
PATTERN_A = PatternSpec(
    pattern_id="failed_control_stale_vendor_open_risk",
    title="Failed control on a stale vendor with an open high-severity risk",
    insight_severity="critical",
    anchor_entity_type="control",
    anchor_conditions=(Condition("status", "eq", "failed"),),
    legs=(
        LegSpec(
            role="stale_vendor",
            reached_via="vendor_provides_control",
            predicate=NodePredicate(
                "vendor",
                (Condition("__assessment_overdue_days__", "derived", VENDOR_STALE_MIN_OVERDUE_DAYS),),
            ),
        ),
        LegSpec(
            role="open_risk",
            reached_via="mitigated_by",
            predicate=NodePredicate(
                "risk",
                (
                    Condition("severity", "in", HIGH_CRITICAL),
                    Condition("status", "in", RISK_OPEN_STATUSES),
                ),
            ),
        ),
    ),
    narrative_template=(
        "Control '{anchor}' has FAILED. The vendor '{stale_vendor}' that provides it is overdue for "
        "reassessment, and the open {open_risk_severity} risk '{open_risk}' depends on this control. "
        "These three should be reviewed together as one compounding exposure."
    ),
)

PATTERN_B = PatternSpec(
    pattern_id="expired_evidence_control_open_risk",
    title="Expired evidence on a control mitigating an open high-severity risk",
    insight_severity="high",
    anchor_entity_type="control",
    anchor_conditions=(Condition("status", "in", ("implemented", "needs_review")),),
    legs=(
        LegSpec(
            role="expired_evidence",
            reached_via="control_evidenced_by",
            predicate=NodePredicate(
                "evidence",
                (Condition("freshness_status", "eq", "expired"),),
            ),
        ),
        LegSpec(
            role="open_risk",
            reached_via="mitigated_by",
            predicate=NodePredicate(
                "risk",
                (
                    Condition("severity", "in", HIGH_CRITICAL),
                    Condition("status", "in", RISK_OPEN_STATUSES),
                ),
            ),
        ),
    ),
    narrative_template=(
        "The evidence '{expired_evidence}' for control '{anchor}' has EXPIRED, while the open "
        "{open_risk_severity} risk '{open_risk}' still relies on that control. The control's assurance "
        "is lapsed exactly where a high-severity risk depends on it."
    ),
)

PATTERN_C = PatternSpec(
    pattern_id="active_incident_failed_control_stale_vendor",
    title="Active high-severity incident on a failed control with a stale vendor behind it",
    insight_severity="critical",
    anchor_entity_type="issue",
    anchor_conditions=(
        Condition("status", "in", ("open", "investigating", "mitigating")),
        Condition("severity", "in", HIGH_CRITICAL),
    ),
    legs=(
        LegSpec(
            role="failed_control",
            reached_via="issue_affects_control",
            predicate=NodePredicate(
                "control",
                (Condition("status", "in", ("failed", "needs_review")),),
            ),
        ),
        LegSpec(
            role="stale_vendor",
            reached_via="vendor_provides_control",
            from_role="failed_control",  # depth-1 FROM the failed control, not the issue
            predicate=NodePredicate(
                "vendor",
                (Condition("__assessment_overdue_days__", "derived", VENDOR_STALE_MIN_OVERDUE_DAYS),),
            ),
        ),
    ),
    narrative_template=(
        "The active {anchor_severity} incident '{anchor}' hits control '{failed_control}', which is not "
        "healthy, and that control is provided by vendor '{stale_vendor}' whose assessment is overdue. "
        "The incident, the weak control, and the stale vendor form one connected exposure."
    ),
)

PATTERN_REGISTRY: list[PatternSpec] = [PATTERN_A, PATTERN_B, PATTERN_C]


# Entity type -> (ORM model dotted path, label attribute). Kept as strings so the
# registry has no import-time dependency on the full model graph.
ENTITY_MODEL_LABELS: dict[str, tuple[str, str]] = {
    "control": ("app.models.control.Control", "title"),
    "vendor": ("app.models.vendor.Vendor", "name"),
    "risk": ("app.models.risk.Risk", "title"),
    "evidence": ("app.models.evidence_item.EvidenceItem", "title"),
    "issue": ("app.models.issue.Issue", "title"),
}


class PatternRegistryValidationError(RuntimeError):
    pass


def validate_registry(registry: list[PatternSpec] | None = None) -> None:
    """Assert every pattern's node types are real graph node types and every
    reached_via edge is a real Phase 2 edge type. Fails loudly on drift."""
    from app.compliance.services.entity_graph_registry import EDGE_REGISTRY, NODE_TYPES

    specs = PATTERN_REGISTRY if registry is None else registry
    edge_types = {s.edge_type for s in EDGE_REGISTRY}
    errors: list[str] = []
    for spec in specs:
        if spec.anchor_entity_type not in NODE_TYPES:
            errors.append(f"{spec.pattern_id}: anchor type '{spec.anchor_entity_type}' not a graph node type")
        if spec.anchor_entity_type not in ENTITY_MODEL_LABELS:
            errors.append(f"{spec.pattern_id}: anchor type '{spec.anchor_entity_type}' has no model mapping")
        roles_seen = {ANCHOR_ROLE}
        for leg in spec.legs:
            if leg.predicate.entity_type not in NODE_TYPES:
                errors.append(f"{spec.pattern_id}/{leg.role}: type '{leg.predicate.entity_type}' not a node type")
            if leg.predicate.entity_type not in ENTITY_MODEL_LABELS:
                errors.append(f"{spec.pattern_id}/{leg.role}: type '{leg.predicate.entity_type}' has no model mapping")
            if leg.reached_via not in edge_types:
                errors.append(f"{spec.pattern_id}/{leg.role}: edge '{leg.reached_via}' not a registered edge type")
            if leg.from_role not in roles_seen:
                errors.append(f"{spec.pattern_id}/{leg.role}: from_role '{leg.from_role}' not resolved before it")
            roles_seen.add(leg.role)
        for role in spec.dedup_roles:
            if role not in roles_seen:
                errors.append(f"{spec.pattern_id}: dedup_role '{role}' is not a role in the pattern")
    if errors:
        raise PatternRegistryValidationError(
            "Compound pattern registry is out of sync:\n  - " + "\n  - ".join(errors)
        )
