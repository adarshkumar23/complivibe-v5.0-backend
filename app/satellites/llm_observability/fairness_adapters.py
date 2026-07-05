from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.satellites.llm_observability.models import ObservabilityResult


class AIF360FairnessAdapter:
    """Formal fairness assessment using AIF360's BinaryLabelDataset metrics."""

    def assess_binary_classification(
        self,
        *,
        dataframe: pd.DataFrame,
        label_column: str,
        prediction_column: str,
        protected_attribute: str,
        privileged_value: Any,
        unprivileged_value: Any,
    ) -> list[ObservabilityResult]:
        from aif360.datasets import BinaryLabelDataset
        from aif360.metrics import BinaryLabelDatasetMetric, ClassificationMetric

        required = [label_column, prediction_column, protected_attribute]
        missing = [column for column in required if column not in dataframe.columns]
        if missing:
            raise ValueError(f"Missing required fairness columns: {', '.join(missing)}")

        actual = BinaryLabelDataset(
            df=dataframe[[label_column, protected_attribute]].copy(),
            label_names=[label_column],
            protected_attribute_names=[protected_attribute],
            favorable_label=1,
            unfavorable_label=0,
        )
        predicted_df = dataframe[[prediction_column, protected_attribute]].rename(columns={prediction_column: label_column}).copy()
        predicted = BinaryLabelDataset(
            df=predicted_df,
            label_names=[label_column],
            protected_attribute_names=[protected_attribute],
            favorable_label=1,
            unfavorable_label=0,
        )
        groups = {
            "privileged_groups": [{protected_attribute: privileged_value}],
            "unprivileged_groups": [{protected_attribute: unprivileged_value}],
        }
        dataset_metric = BinaryLabelDatasetMetric(actual, **groups)
        classification_metric = ClassificationMetric(actual, predicted, **groups)
        details = {"protected_attribute": protected_attribute, "privileged_value": privileged_value, "unprivileged_value": unprivileged_value}
        return [
            ObservabilityResult("aif360_mean_difference", decimal_from_float(dataset_metric.mean_difference()), "aif360", details),
            ObservabilityResult("aif360_disparate_impact", decimal_from_float(dataset_metric.disparate_impact()), "aif360", details),
            ObservabilityResult("aif360_equal_opportunity_difference", decimal_from_float(classification_metric.equal_opportunity_difference()), "aif360", details),
            ObservabilityResult("aif360_average_odds_difference", decimal_from_float(classification_metric.average_odds_difference()), "aif360", details),
        ]


class FairlearnMonitoringAdapter:
    """Lightweight continuous fairness monitoring using Fairlearn metrics."""

    def assess_binary_classification(
        self,
        *,
        y_true: list[int],
        y_pred: list[int],
        sensitive_features: list[Any],
    ) -> list[ObservabilityResult]:
        from fairlearn.metrics import MetricFrame, demographic_parity_difference, equalized_odds_difference, selection_rate

        frame = MetricFrame(
            metrics={"selection_rate": selection_rate},
            y_true=y_true,
            y_pred=y_pred,
            sensitive_features=sensitive_features,
        )
        dp_diff = demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive_features)
        eo_diff = equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive_features)
        return [
            ObservabilityResult(
                "fairlearn_demographic_parity_difference",
                decimal_from_float(dp_diff),
                "fairlearn",
                {"selection_rate_by_group": frame.by_group.to_dict()},
            ),
            ObservabilityResult(
                "fairlearn_equalized_odds_difference",
                decimal_from_float(eo_diff),
                "fairlearn",
                {"selection_rate_by_group": frame.by_group.to_dict()},
            ),
        ]


def build_sample_fairness_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "label": [1, 1, 1, 0, 1, 0, 0, 0],
            "prediction": [1, 1, 0, 0, 1, 0, 0, 1],
            "protected": [1, 1, 1, 1, 0, 0, 0, 0],
        }
    )
