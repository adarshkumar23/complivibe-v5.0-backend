from __future__ import annotations

from decimal import Decimal

# Per-1M-token USD list pricing, confirmed by web search on 2026-07-05 against
# https://developers.openai.com/api/docs/pricing (current OpenAI lineup) and
# https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (Azure OpenAI parity pricing).
# Kept as a plain, editable table rather than a hardcoded formula so operators can update it as
# vendors change list prices without touching calculation logic.
MODEL_PRICING_PER_MILLION_TOKENS: dict[str, dict[str, Decimal]] = {
    "gpt-5.5": {"input": Decimal("5.00"), "output": Decimal("30.00")},
    "gpt-5.4": {"input": Decimal("2.50"), "output": Decimal("15.00")},
    "gpt-5.4-mini": {"input": Decimal("0.75"), "output": Decimal("4.50")},
    "gpt-5.4-nano": {"input": Decimal("0.20"), "output": Decimal("1.25")},
    "gpt-4o": {"input": Decimal("2.50"), "output": Decimal("10.00")},
    "gpt-4o-mini": {"input": Decimal("0.15"), "output": Decimal("0.60")},
}


class UnknownModelPricingError(ValueError):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(
            f"No pricing entry for model '{model}'. Supply input_price_per_million and "
            f"output_price_per_million explicitly, or use one of: "
            f"{', '.join(sorted(MODEL_PRICING_PER_MILLION_TOKENS))}"
        )


def compute_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: Decimal | None = None,
    output_price_per_million: Decimal | None = None,
) -> Decimal:
    """Computes real $ cost from token counts and per-1M-token model pricing.

    Callers may override the built-in list price (e.g. for negotiated enterprise rates or a
    provider not in the table); otherwise the model must exist in MODEL_PRICING_PER_MILLION_TOKENS.
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("input_tokens and output_tokens must be non-negative")

    if input_price_per_million is None or output_price_per_million is None:
        entry = MODEL_PRICING_PER_MILLION_TOKENS.get(model.strip().lower())
        if entry is None:
            raise UnknownModelPricingError(model)
        input_price_per_million = input_price_per_million or entry["input"]
        output_price_per_million = output_price_per_million or entry["output"]

    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * input_price_per_million
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * output_price_per_million
    return (input_cost + output_cost).quantize(Decimal("0.000001"))
