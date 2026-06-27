try:
    from fairlearn.metrics import demographic_parity_ratio

    FAIRLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FAIRLEARN_AVAILABLE = False

try:
    from aif360.datasets import BinaryLabelDataset
    from aif360.metrics import BinaryLabelDatasetMetric

    AIF360_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    AIF360_AVAILABLE = False


class BiasMetricsService:
    @staticmethod
    def compute_bias_metrics(
        predictions: list[int | float],
        protected_attribute_values: list[int | float],
        labels: list[int | float] | None = None,
    ) -> dict:
        """
        CALLED ONLY when user explicitly submits sample data via POST /compute-bias.
        NEVER called automatically.
        NEVER called on real production traffic.
        Input: customer-provided sample data only.
        """
        results: dict = {}
        if FAIRLEARN_AVAILABLE:
            try:
                results["demographic_parity_ratio"] = demographic_parity_ratio(
                    labels if labels else predictions,
                    sensitive_features=protected_attribute_values,
                )
            except Exception as exc:  # pragma: no cover - defensive metrics guard
                results["demographic_parity_ratio_error"] = str(exc)
        else:
            results["demographic_parity_ratio_error"] = "fairlearn is not installed"

        if labels and AIF360_AVAILABLE:
            try:
                import pandas as pd

                df = pd.DataFrame(
                    {
                        "prediction": predictions,
                        "label": labels,
                        "protected": protected_attribute_values,
                    }
                )
                dataset = BinaryLabelDataset(
                    df=df,
                    label_names=["label"],
                    protected_attribute_names=["protected"],
                )
                metric = BinaryLabelDatasetMetric(
                    dataset,
                    privileged_groups=[{"protected": 1}],
                    unprivileged_groups=[{"protected": 0}],
                )
                results["disparate_impact"] = metric.disparate_impact()
                results["statistical_parity_difference"] = metric.statistical_parity_difference()
            except Exception as exc:  # pragma: no cover - defensive metrics guard
                results["aif360_error"] = str(exc)

        return results
