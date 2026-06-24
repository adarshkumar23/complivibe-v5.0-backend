from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScoreSummary(BaseModel):
    score: int
    captured_at: datetime


class ScoreSnapshotRead(BaseModel):
    id: UUID
    organization_id: UUID
    snapshot_type: str
    score: int
    grade: str
    inputs_json: dict
    breakdown_json: dict
    recommendations_json: list[str] | None = None
    calculated_at: datetime
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ScoreSnapshotMaterializeRequest(BaseModel):
    snapshot_types: list[str] | None = None
    dry_run: bool = False


class ScoreSnapshotMaterializeResponse(BaseModel):
    dry_run: bool
    snapshots: list[ScoreSnapshotRead]


class ScoreMethodologyResponse(BaseModel):
    snapshot_types: dict
    caveats: list[str]


class ScoreLatestResponse(BaseModel):
    snapshots: list[ScoreSnapshotRead]


class ScoreListResponse(BaseModel):
    snapshots: list[ScoreSnapshotRead]


class ScoreSnapshotTypeList(BaseModel):
    snapshot_type: str | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ScoreTrendPoint(BaseModel):
    calculated_at: datetime
    score: int
    grade: str


class ScoreTrendSeries(BaseModel):
    snapshot_type: str
    points: list[ScoreTrendPoint]


class ScoreTrendsResponse(BaseModel):
    days: int
    series: list[ScoreTrendSeries]


class ScoreDeltaResponse(BaseModel):
    snapshot_type: str
    latest_score: int
    previous_score: int
    delta: int
    direction: str
    latest_calculated_at: datetime
    previous_calculated_at: datetime
