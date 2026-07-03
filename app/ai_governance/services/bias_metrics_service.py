class BiasMetricsService:
    @staticmethod
    def _safe_ratio(numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return float(numerator) / float(denominator)

    @staticmethod
    def compute_bias_metrics(
        predictions: list[int | float],
        protected_attribute_values: list[int | float],
        labels: list[int | float] | None = None,
    ) -> dict:
        """
        Lightweight in-core metric estimation.
        Detailed statistical bias analysis is expected to run externally;
        this endpoint stores comparable summary indicators only.
        """
        if not predictions or not protected_attribute_values:
            return {
                "demographic_parity_ratio": 0.0,
                "group_positive_rate": {},
            }

        groups: dict[str, list[float]] = {}
        for pred, attr in zip(predictions, protected_attribute_values, strict=False):
            groups.setdefault(str(attr), []).append(float(pred))

        positive_rates: dict[str, float] = {}
        for group_name, vals in groups.items():
            if not vals:
                positive_rates[group_name] = 0.0
                continue
            positives = sum(1.0 for value in vals if value >= 0.5)
            positive_rates[group_name] = BiasMetricsService._safe_ratio(positives, len(vals))

        rates = list(positive_rates.values())
        max_rate = max(rates) if rates else 0.0
        min_rate = min(rates) if rates else 0.0

        results: dict = {
            "demographic_parity_ratio": round(BiasMetricsService._safe_ratio(min_rate, max_rate), 4) if max_rate > 0 else 0.0,
            "group_positive_rate": {k: round(v, 4) for k, v in positive_rates.items()},
        }

        if labels and len(labels) == len(predictions):
            label_pairs = [
                (float(pred), float(lbl), str(attr))
                for pred, lbl, attr in zip(predictions, labels, protected_attribute_values, strict=False)
            ]
            group_accuracy: dict[str, float] = {}
            for group_name in groups.keys():
                subset = [(pred, lbl) for pred, lbl, attr in label_pairs if attr == group_name]
                if not subset:
                    group_accuracy[group_name] = 0.0
                    continue
                correct = sum(1.0 for pred, lbl in subset if (pred >= 0.5) == (lbl >= 0.5))
                group_accuracy[group_name] = BiasMetricsService._safe_ratio(correct, len(subset))

            acc_values = list(group_accuracy.values())
            disparity = (max(acc_values) - min(acc_values)) if acc_values else 0.0
            results["group_accuracy"] = {k: round(v, 4) for k, v in group_accuracy.items()}
            results["accuracy_disparity"] = round(disparity, 4)

        return results
