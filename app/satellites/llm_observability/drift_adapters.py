from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.satellites.llm_observability.models import ObservabilityResult


class EvidentlyDriftAdapter:
    """Detects data/output drift with Evidently's DataDriftPreset."""

    def detect_data_drift(self, *, reference_data: pd.DataFrame, current_data: pd.DataFrame) -> list[ObservabilityResult]:
        from evidently.legacy.metric_preset import DataDriftPreset
        from evidently.legacy.report import Report

        if reference_data.empty or current_data.empty:
            raise ValueError("reference_data and current_data are required for drift detection")
        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference_data, current_data=current_data)
        payload = report.as_dict()
        dataset_metric = next(
            (item for item in payload.get("metrics", []) if item.get("metric") == "DatasetDriftMetric"),
            {"result": {}},
        )
        result = dataset_metric.get("result") or {}
        drift_share = float(result.get("share_of_drifted_columns") or result.get("drift_share") or 0.0)
        drifted_columns = int(result.get("number_of_drifted_columns") or 0)
        dataset_drift = bool(result.get("dataset_drift"))
        details = {"dataset_drift": dataset_drift, "drifted_columns": drifted_columns, "raw_result": result}
        return [
            ObservabilityResult("evidently_drift_share", decimal_from_float(drift_share), "evidently", details),
            ObservabilityResult("evidently_drifted_columns", Decimal(drifted_columns), "evidently", details),
        ]


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
