from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import pandas as pd

from app.satellites.llm_observability.drift_adapters import EvidentlyDriftAdapter
from app.satellites.llm_observability.fairness_adapters import AIF360FairnessAdapter, FairlearnMonitoringAdapter
from app.satellites.llm_observability.ingest_client import CoreMonitoringIngestClient
from app.satellites.llm_observability.models import MonitoringIngestTarget, ObservabilityResult

# Metric types this satellite is permitted to report, matching the check
# constraint on ai_monitoring_configs.metric_type in core (drift and bias are
# the two this satellite computes today).
DRIFT_METRIC_TYPE = "output_drift"
FAIRNESS_METRIC_TYPE = "bias_parity_gap"


def run_drift_check_and_push(
    *,
    target: MonitoringIngestTarget,
    reference_data: pd.DataFrame,
    current_data: pd.DataFrame,
) -> dict[str, Any]:
    """Computes real data-drift (Evidently DataDriftPreset) and reports it to core.

    Reports the dataset-level `share_of_drifted_columns` as the config's
    tracked value (metric_type must be `output_drift`) so core's existing
    threshold/degradation-trend/alerting pipeline in AIMonitoringService
    applies unchanged.
    """
    results = EvidentlyDriftAdapter().detect_data_drift(reference_data=reference_data, current_data=current_data)
    drift_share_result = next(r for r in results if r.metric_type == "evidently_drift_share")
    target = MonitoringIngestTarget(
        base_url=target.base_url,
        api_key=target.api_key,
        config_id=target.config_id,
        metric_type=DRIFT_METRIC_TYPE,
    )
    response = CoreMonitoringIngestClient().push(target, drift_share_result)
    return {"pushed": response, "results": [r.__dict__ for r in results]}


def run_fairness_check_and_push(
    *,
    target: MonitoringIngestTarget,
    dataframe: pd.DataFrame,
    label_column: str,
    prediction_column: str,
    protected_attribute: str,
    privileged_value: Any,
    unprivileged_value: Any,
    method: str = "aif360",
) -> dict[str, Any]:
    """Computes a real fairness metric (AIF360 disparate impact gap or Fairlearn
    demographic parity difference) and reports it to core as `bias_parity_gap`.
    """
    if method == "fairlearn":
        results = FairlearnMonitoringAdapter().assess_binary_classification(
            y_true=dataframe[label_column].tolist(),
            y_pred=dataframe[prediction_column].tolist(),
            sensitive_features=dataframe[protected_attribute].tolist(),
        )
        primary = next(r for r in results if r.metric_type == "fairlearn_demographic_parity_difference")
    elif method == "aif360":
        results = AIF360FairnessAdapter().assess_binary_classification(
            dataframe=dataframe,
            label_column=label_column,
            prediction_column=prediction_column,
            protected_attribute=protected_attribute,
            privileged_value=privileged_value,
            unprivileged_value=unprivileged_value,
        )
        # disparate_impact is a ratio (1.0 = parity); report the gap from
        # parity (|1 - disparate_impact|) so it behaves like the other
        # "smaller is better" parity-gap metrics core already understands.
        disparate_impact = next(r for r in results if r.metric_type == "aif360_disparate_impact")
        gap_value = abs(1 - disparate_impact.value)
        primary = ObservabilityResult("aif360_disparate_impact_gap", gap_value, "aif360", disparate_impact.details)
        results = [*results, primary]
    else:
        raise ValueError(f"Unknown fairness method: {method}")

    target = MonitoringIngestTarget(
        base_url=target.base_url,
        api_key=target.api_key,
        config_id=target.config_id,
        metric_type=FAIRNESS_METRIC_TYPE,
    )
    response = CoreMonitoringIngestClient().push(target, primary)
    return {"pushed": response, "results": [r.__dict__ for r in results]}


def _cli() -> None:
    """Minimal CLI so this satellite can be invoked as a standalone scheduled
    job (e.g. `python -m app.satellites.llm_observability.runner drift ...`)
    outside of the core FastAPI process, without needing a bespoke wrapper.
    """
    parser = argparse.ArgumentParser(description="Run an LLM observability satellite check and push it into core.")
    parser.add_argument("check", choices=["drift", "fairness"])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--reference-json", help="Path to reference data JSON (list of records)")
    parser.add_argument("--current-json", help="Path to current data JSON (list of records), drift only")
    parser.add_argument("--data-json", help="Path to labeled data JSON (list of records), fairness only")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--prediction-column", default="prediction")
    parser.add_argument("--protected-attribute", default="protected")
    parser.add_argument("--privileged-value", default="1")
    parser.add_argument("--unprivileged-value", default="0")
    parser.add_argument("--method", default="aif360", choices=["aif360", "fairlearn"])
    args = parser.parse_args()

    target = MonitoringIngestTarget(base_url=args.base_url, api_key=args.api_key, config_id=args.config_id)

    if args.check == "drift":
        if not args.reference_json or not args.current_json:
            print("drift requires --reference-json and --current-json", file=sys.stderr)
            raise SystemExit(2)
        reference = pd.DataFrame(json.loads(open(args.reference_json, encoding="utf-8").read()))
        current = pd.DataFrame(json.loads(open(args.current_json, encoding="utf-8").read()))
        result = run_drift_check_and_push(target=target, reference_data=reference, current_data=current)
    else:
        if not args.data_json:
            print("fairness requires --data-json", file=sys.stderr)
            raise SystemExit(2)
        data = pd.DataFrame(json.loads(open(args.data_json, encoding="utf-8").read()))
        result = run_fairness_check_and_push(
            target=target,
            dataframe=data,
            label_column=args.label_column,
            prediction_column=args.prediction_column,
            protected_attribute=args.protected_attribute,
            privileged_value=args.privileged_value,
            unprivileged_value=args.unprivileged_value,
            method=args.method,
        )
    print(json.dumps(result["pushed"]))


if __name__ == "__main__":  # pragma: no cover - exercised via unit tests calling the functions directly
    _cli()
