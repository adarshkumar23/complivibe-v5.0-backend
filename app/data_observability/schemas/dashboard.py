from datetime import datetime

from pydantic import BaseModel


class AssetCoverageRead(BaseModel):
    total_assets: int
    classified_count: int
    confirmed_count: int
    classification_coverage_pct: float
    by_sensitivity_tier: dict[str, int]
    needs_review_count: int


class QualityMetricsRead(BaseModel):
    readings_last_7d: int
    breach_count_7d: int
    pass_count_7d: int
    breach_rate_7d: float


class AccessAnomaliesRead(BaseModel):
    anomaly_count_7d: int
    active_incidents: int
    by_severity: dict[str, int]


class RetentionDashboardRead(BaseModel):
    assets_with_policy: int
    pending_reviews: int
    retention_compliance_rate: float


class DataObligationCoverageRead(BaseModel):
    total_assets: int
    linked_assets: int
    unlinked_assets: int
    coverage_pct: float
    by_link_type: dict[str, int]
    by_framework: dict[str, dict]


class DataObservabilityDashboardRead(BaseModel):
    asset_coverage: AssetCoverageRead
    quality_metrics: QualityMetricsRead
    access_anomalies: AccessAnomaliesRead
    retention: RetentionDashboardRead
    data_obligation_coverage: DataObligationCoverageRead
    generated_at: datetime | str
