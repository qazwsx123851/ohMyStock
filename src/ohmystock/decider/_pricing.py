"""LLM pricing table for the entry decider.

USD per million tokens. Mirrors ``ohmystock.observability.cost_tracker``'s
table but uses bare model names (no date suffix) as keys, since the decider
calls ``client.messages.create(model=...)`` with the value in
``Settings.decider_model`` which defaults to ``claude-opus-4-7``.

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md
"""

from __future__ import annotations


MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for the given (model, input_tokens, output_tokens).

    Raises KeyError if ``model`` is not in :data:`MODEL_PRICING_USD_PER_MTOK`.
    """
    pricing = MODEL_PRICING_USD_PER_MTOK[model]
    return (
        input_tokens / 1_000_000.0 * pricing["input"]
        + output_tokens / 1_000_000.0 * pricing["output"]
    )
