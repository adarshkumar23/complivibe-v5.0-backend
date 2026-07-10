from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.satellites.llm_observability.models import ObservabilityResult


class EvidentlyDriftAdapter:
    """Detects data/output drift with Evidently's DataDriftPreset."""

    def detect_data_drift(
        self,
        *,
        reference_data: pd.DataFrame,
        current_data: pd.DataFrame,
        numerical_columns: list[str] | None = None,
    ) -> list[ObservabilityResult]:
        from evidently.legacy.metric_preset import DataDriftPreset
        from evidently.legacy.pipeline.column_mapping import ColumnMapping
        from evidently.legacy.report import Report

        if reference_data.empty or current_data.empty:
            raise ValueError("reference_data and current_data are required for drift detection")
        # Evidently auto-detects each column's type (numerical/categorical) from
        # its cardinality relative to sample size, and picks a default
        # statistical test the same way. On small samples of continuous data
        # with few duplicate values, both heuristics can land on a
        # chi-squared-style test with near-zero expected cell counts per bin --
        # unreliable and prone to false positives (confirmed empirically: a
        # 5-vs-5 sample of near-identical values was flagged as 100% drifted
        # under the defaults). Callers with genuinely continuous columns (e.g.
        # a scalar monitoring metric sampled over time) should pass
        # `numerical_columns` to get both the correct column type AND a forced
        # KS-test, which behaves correctly at these sample sizes.
        if numerical_columns:
            column_mapping = ColumnMapping(numerical_features=numerical_columns)
            report = Report(metrics=[DataDriftPreset(num_stattest="ks")])
        else:
            column_mapping = None
            report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference_data, current_data=current_data, column_mapping=column_mapping)
        payload = report.as_dict()
        dataset_metric = next(
            (item for item in payload.get("metrics", []) if item.get("metric") == "DatasetDriftMetric"),
            {"result": {}},
        )
        result = dataset_metric.get("result") or {}
        # `share_of_drifted_columns` (the actual computed share) is a
        # legitimate 0.0 when nothing drifted -- `or`-chaining onto
        # `drift_share` (the *configured* DataDriftPreset threshold, e.g. the
        # default 0.5) would silently misreport a healthy 0-drift result as
        # 50% drift share, since Python's `or` treats 0.0 as falsy.
        share_of_drifted = result.get("share_of_drifted_columns")
        drift_share = float(share_of_drifted if share_of_drifted is not None else (result.get("drift_share") or 0.0))
        drifted_columns = int(result.get("number_of_drifted_columns") or 0)
        dataset_drift = bool(result.get("dataset_drift"))
        details = {"dataset_drift": dataset_drift, "drifted_columns": drifted_columns, "raw_result": result}
        return [
            ObservabilityResult("evidently_drift_share", decimal_from_float(drift_share), "evidently", details),
            ObservabilityResult("evidently_drifted_columns", Decimal(drifted_columns), "evidently", details),
        ]


# Vendor-neutral alias: some callers (e.g. AIMonitoringService) must never
# reference third-party tool names in their own source (customer-facing
# config/dashboard responses are derived from that file) -- the vendor name
# stays confined to this adapter module, and those callers import the alias
# instead of the class above directly.
DistributionDriftDetector = EvidentlyDriftAdapter


class NannyMLPerformanceAdapter:
    """Label-free performance estimation with NannyML CBPE."""

    def estimate_binary_performance(
        self,
        *,
        reference_data: pd.DataFrame,
        analysis_data: pd.DataFrame,
        y_pred_proba: str,
        y_pred: str,
        y_true: str,
        metric: str = "roc_auc",
        chunk_size: int = 5,
    ) -> ObservabilityResult:
        import nannyml as nml

        cbpe = nml.CBPE(
            metrics=[metric],
            y_pred_proba=y_pred_proba,
            y_pred=y_pred,
            y_true=y_true,
            problem_type="classification_binary",
            chunk_size=chunk_size,
        )
        cbpe.fit(reference_data)
        estimate = cbpe.estimate(analysis_data)
        result_frame = estimate.to_df()
        metric_values = result_frame[(metric, "value")].dropna().astype(float)
        mean_value = float(metric_values.mean()) if not metric_values.empty else 0.0
        alert_column = (metric, "alert")
        alert_count = int(result_frame[alert_column].fillna(False).astype(bool).sum()) if alert_column in result_frame else 0
        return ObservabilityResult(
            metric_type=f"nannyml_estimated_{metric}",
            value=decimal_from_float(mean_value),
            source_tool="nannyml",
            details={"metric": metric, "chunk_count": int(len(result_frame)), "alert_count": alert_count},
        )


def build_sample_drift_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    reference = pd.DataFrame({"score": [0.1, 0.2, 0.3, 0.4, 0.5], "label": [0, 0, 1, 1, 1]})
    current = pd.DataFrame({"score": [0.6, 0.7, 0.8, 0.9, 1.0], "label": [1, 1, 1, 1, 1]})
    return reference, current


def build_sample_nannyml_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    reference = pd.DataFrame(
        {
            "y_true": [0, 0, 1, 1, 0, 1, 0, 1, 0, 1],
            "y_pred": [0, 0, 1, 1, 0, 1, 0, 1, 0, 1],
            "y_pred_proba": [0.1, 0.2, 0.8, 0.9, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9],
        }
    )
    analysis = pd.DataFrame(
        {
            "y_pred": [0, 1, 1, 1, 0, 0, 0, 1, 1, 1],
            "y_pred_proba": [0.2, 0.7, 0.6, 0.85, 0.4, 0.45, 0.2, 0.75, 0.55, 0.65],
        }
    )
    return reference, analysis
