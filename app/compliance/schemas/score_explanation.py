from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FrameworkPathOut(BaseModel):
    """A PATH-only framework/coverage leg. Has NO points_delta by construction
    (design §5.4): it is a graph path to affected obligations, never a numeric
    score delta. `kind` is fixed to "graph_path" so a client can never confuse it
    with a precise contribution."""

    kind: Literal["graph_path"] = "graph_path"
    from_entity_type: str
    from_entity_id: uuid.UUID
    obligations: list[dict[str, Any]]
    note: str


class CauseOut(BaseModel):
    cause_type: Literal["event", "underlying_data_changed"]
    detail: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    before: Any = None
    after: Any = None
    occurred_at: datetime | None = None
    framework_paths: list[FrameworkPathOut] = Field(default_factory=list)


class ContributionOut(BaseModel):
    """A PRECISE contribution to the score delta -- always carries points_delta."""

    component: str
    kind: Literal["leaf_term", "component_score"]
    points_delta: float
    value_before: float
    value_after: float
    coefficient: float | None = None
    causes: list[CauseOut] = Field(default_factory=list)
    sub_contributions: list["ContributionOut"] = Field(default_factory=list)


class ScoreChangeExplanationOut(BaseModel):
    family: Literal["score_snapshot", "entity_risk_score", "board_scorecard"]
    subject: str
    from_id: uuid.UUID | None
    to_id: uuid.UUID | None
    from_at: datetime | None
    to_at: datetime | None
    observed_delta: float
    raw_delta: float
    rounding_residual: float
    explanation_kind: Literal["precise_delta", "approximate_delta"]
    contributions: list[ContributionOut]
    narrative: str


def _framework_path_out(fp) -> FrameworkPathOut:
    return FrameworkPathOut(
        from_entity_type=fp.from_entity_type, from_entity_id=fp.from_entity_id,
        obligations=fp.obligations, note=fp.note,
    )


def _cause_out(c) -> CauseOut:
    return CauseOut(
        cause_type=c.cause_type, detail=c.detail, entity_type=c.entity_type, entity_id=c.entity_id,
        before=c.before, after=c.after, occurred_at=c.occurred_at,
        framework_paths=[_framework_path_out(fp) for fp in c.framework_paths],
    )


def _contribution_out(c) -> ContributionOut:
    return ContributionOut(
        component=c.component, kind=c.kind, points_delta=c.points_delta,
        value_before=c.value_before, value_after=c.value_after, coefficient=c.coefficient,
        causes=[_cause_out(x) for x in c.causes],
        sub_contributions=[_contribution_out(s) for s in c.sub_contributions],
    )


def explanation_out(exp) -> ScoreChangeExplanationOut:
    return ScoreChangeExplanationOut(
        family=exp.family, subject=exp.subject, from_id=exp.from_id, to_id=exp.to_id,
        from_at=exp.from_at, to_at=exp.to_at, observed_delta=exp.observed_delta,
        raw_delta=exp.raw_delta, rounding_residual=exp.rounding_residual,
        explanation_kind=exp.explanation_kind,
        contributions=[_contribution_out(c) for c in exp.contributions], narrative=exp.narrative,
    )
