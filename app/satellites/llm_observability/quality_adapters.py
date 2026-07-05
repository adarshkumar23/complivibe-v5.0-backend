from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import pandas as pd
from deepeval.metrics import HallucinationMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.satellites.llm_observability.models import ObservabilityResult


class DeterministicHallucinationJudge(DeepEvalBaseLLM):
    """Local deterministic DeepEval judge for library-level validation without an external LLM key."""

    def load_model(self) -> "DeterministicHallucinationJudge":
        return self

    def get_model_name(self) -> str:
        return "deterministic-hallucination-judge"

    def generate(self, prompt: str, *args: Any, **kwargs: Any) -> Any:
        schema = kwargs.get("schema")
        prompt_lower = str(prompt).lower()
        if schema is not None and "Verdicts" in str(schema):
            verdict = "no" if "force_local_contradiction" in prompt_lower else "yes"
            reason = "The output is unsupported by the provided context." if verdict == "no" else "The output is supported by the provided context."
            return schema(verdicts=[{"verdict": verdict, "reason": reason}])
        if schema is not None:
            try:
                return schema(reason="Deterministic local judge completed hallucination scoring.")
            except Exception:
                pass
        if "verdict" in prompt_lower:
            return json.dumps({"verdicts": [{"verdict": "yes", "reason": "supported"}]})
        return json.dumps({"reason": "Deterministic local judge completed hallucination scoring."})

    async def a_generate(self, prompt: str, *args: Any, **kwargs: Any) -> Any:
        return self.generate(prompt, *args, **kwargs)


class DeepEvalHallucinationAdapter:
    def __init__(self, model: DeepEvalBaseLLM | None = None) -> None:
        self.model = model or DeterministicHallucinationJudge()

    def score(self, *, prompt: str, actual_output: str, context: list[str], threshold: float = 0.5) -> ObservabilityResult:
        test_case = LLMTestCase(input=prompt, actual_output=actual_output, context=context)
        metric = HallucinationMetric(threshold=threshold, model=self.model, include_reason=True, async_mode=False)
        score = Decimal(str(metric.measure(test_case, _show_indicator=False)))
        return ObservabilityResult(
            metric_type="hallucination_score",
            value=score,
            source_tool="deepeval",
            details={"success": metric.success, "reason": metric.reason, "threshold": threshold},
        )


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what", "when",
    "where", "which", "who", "why", "will", "with",
}


def _keyword_set(text: str) -> set[str]:
    tokens = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    return {token for token in tokens if token not in _STOPWORDS and len(token) > 1}


class RAGRetrievalQualityAdapter:
    """Deterministic retrieval-quality scoring for RAG pipelines: are the retrieved chunks
    actually relevant to the query? This is independent of (and complements) hallucination/
    faithfulness scoring, which only checks whether the *answer* is supported by whatever was
    retrieved -- a bad retriever that returns irrelevant chunks would not show up there.
    """

    def score_retrieval_relevance(self, *, query: str, retrieved_contexts: list[str]) -> ObservabilityResult:
        if not query.strip():
            raise ValueError("query is required")
        if not retrieved_contexts:
            raise ValueError("retrieved_contexts must contain at least one chunk")

        query_tokens = _keyword_set(query)
        per_chunk_scores: list[float] = []
        for chunk in retrieved_contexts:
            chunk_tokens = _keyword_set(chunk)
            if not query_tokens or not chunk_tokens:
                per_chunk_scores.append(0.0)
                continue
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
            per_chunk_scores.append(overlap)

        relevance_score = sum(per_chunk_scores) / len(per_chunk_scores) if per_chunk_scores else 0.0
        low_relevance_chunks = sum(1 for score in per_chunk_scores if score < 0.2)
        return ObservabilityResult(
            metric_type="retrieval_relevance_score",
            value=decimal_from_float(relevance_score),
            source_tool="heuristic_retrieval_quality",
            details={
                "chunk_count": len(retrieved_contexts),
                "per_chunk_scores": [round(s, 6) for s in per_chunk_scores],
                "low_relevance_chunk_count": low_relevance_chunks,
            },
        )


class GiskardScanAdapter:
    """Runs Giskard bias/robustness scans on a provided prediction function and dataframe."""

    def scan_classification(
        self,
        *,
        dataframe: pd.DataFrame,
        target: str,
        prediction_function: Any,
        feature_names: list[str],
        classification_labels: list[Any],
        detectors: str = "performance",
        cat_columns: list[str] | None = None,
    ) -> ObservabilityResult:
        import giskard

        wrapped_model = giskard.Model(
            prediction_function,
            model_type="classification",
            classification_labels=classification_labels,
            feature_names=feature_names,
        )
        dataset = giskard.Dataset(dataframe, target=target, cat_columns=cat_columns)
        report = giskard.scan(wrapped_model, dataset, only=detectors, verbose=False, max_issues_per_detector=10)
        issue_count = len(getattr(report, "issues", []))
        return ObservabilityResult(
            metric_type="giskard_issue_count",
            value=Decimal(issue_count),
            source_tool="giskard",
            details={"detectors": detectors, "issue_count": issue_count},
        )


def build_sample_giskard_dataframe(row_count: int = 120) -> pd.DataFrame:
    rows = []
    for idx in range(row_count):
        positive = idx % 2 == 0
        rows.append(
            {
                "text": "good helpful answer" if positive else "bad harmful answer",
                "group": "a" if idx < int(row_count * 0.66) else "b",
                "label": 1 if positive else 0,
            }
        )
    return pd.DataFrame(rows)


def sample_giskard_predict_proba(dataframe: pd.DataFrame) -> list[list[float]]:
    rows: list[list[float]] = []
    for text in dataframe["text"]:
        rows.append([0.05, 0.95] if "good" in text or "helpful" in text else [0.85, 0.15])
    return rows
