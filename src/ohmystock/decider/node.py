"""PMConclusionNode interface + Anthropic default implementation + fake.

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md

The Anthropic implementation uses ``messages.create`` with a strict-JSON
system prompt; the response text is ``json.loads``'d and validated against
``DeciderOutput``. Both parse failures and pydantic validation failures
surface as ``DeciderOutputParseError`` (with the original exception in
``cause``), so callers can write a single ``kind=reject`` reject_layer=llm
journal row regardless of which step failed.

The ``FakePMConclusionNode`` is exported from this module (not buried in
test fixtures) so orchestrator / CLI tests can import it without test-path
hacks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from ohmystock.decider._pricing import compute_cost_usd
from ohmystock.decider.models import DeciderOutput
from ohmystock.swarm.models import EntryDecisionInput


SYSTEM_PROMPT = """\
You are the PM Conclusion Node for ohMyStock — a Taiwan-stock entry decider.

You will receive an EntryDecisionInput JSON describing a single candidate \
plus market context, must-have rules, and bonus items. Your job is to decide \
`enter` / `reject` / `reduce_size` based on the SEPA framework and to emit a \
v3.1 decision JSON.

Output rules — read carefully:

1. Respond with ONLY a JSON object. No prose before or after, no markdown \
fences, no code blocks. The first character of your response MUST be `{` and \
the last character MUST be `}`.

2. The JSON object MUST conform to this schema (v3.1):

   {
     "output_schema_version": "v3.1",
     "decision_id": <copy from input.decision_id>,
     "decided_at": <ISO-8601 timestamp with +08:00 offset>,
     "model": <the model name you are running as>,
     "decision": "enter" | "reject" | "reduce_size",
     "confidence": float in [0.0, 1.0],
     "stage": 1|2|3|4 (copy from input.candidate.stage),
     "rs_percentile": int in [0, 99] (copy from input.candidate.rs_percentile),
     "trend_template_passed": int in [0, 8] (copy from candidate),
     "vcp_quality": "none" | "forming" | "textbook" | "breakout" \
(copy from candidate),
     "pivot_price": float | null (copy from candidate; positive if \
vcp_quality is textbook/breakout, else null),
     "must_have_check": [
       {"name": "trend_template_8_of_8", "pass": bool, "evidence": str},
       {"name": "stage_2_confirmed", "pass": bool, "evidence": str},
       {"name": "vcp_pivot_breakout_with_volume", "pass": bool, "evidence": str}
     ],
     "bonus_score": int in [0, 8],
     "bonus_breakdown": [{"name": str, "pass": bool, "evidence": str}, ...],
     "proposed_sizing_pct": float in [0.0, 25.0],
     "expected_holding_days": int in [1, 30],
     "reasoning": str (>= 200 characters, written in Traditional Chinese),
     "cited_skills": [str, ...] (non-empty),
     "invalidation_conditions": [str, ...],
     "risk_flags": [str, ...],
     "tool_calls_summary": [{"tool": str, "action": str, "elapsed_ms": int}, ...]
   }

3. The system layer applies these hard overrides AFTER you respond — do not \
try to circumvent them, but be aware your output will be force-rejected if \
any of these triggers fire:
   - confidence < 0.6 → forced reject
   - reasoning length < 200 chars (unicode codepoints) → forced reject
   - any must_have_check[*].pass == false → forced reject
   - bonus_score < 4 → forced reject
   - stage == 4 → forced reject (Stage 4 distribution excluded)
   - rs_percentile < 65 → must_have trend_template_8_of_8 auto-fails
   - trend_template_passed < 8 → trend_template_8_of_8 auto-fails
   - vcp_quality in {none, forming} → vcp_pivot_breakout_with_volume auto-fails
   - stage == 3 with proposed_sizing_pct > 10 → sizing capped at 10
   - any of stage / rs_percentile / trend_template_passed / vcp_quality / \
pivot_price differ from input.candidate → forced reject

4. Reasoning MUST be Traditional Chinese (繁體中文), >= 200 characters, \
covering:
   (a) which SEPA must-haves passed and how the chart confirms them,
   (b) bonus items observed,
   (c) invalidation conditions specific to this trade.

Your only job is to emit the JSON. No explanations, no apologies, no \
disclaimers."""


@dataclass(frozen=True)
class LLMUsage:
    """Token + cost summary for a single decider call."""

    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


class DeciderOutputParseError(Exception):
    """Raised when the LLM response cannot be parsed into ``DeciderOutput``.

    ``raw_text`` is truncated to 500 chars for journal storage. ``cause`` is
    the underlying exception (``json.JSONDecodeError`` or ``ValidationError``).
    """

    def __init__(self, raw_text: str, cause: Exception) -> None:
        truncated = (raw_text or "")[:500]
        super().__init__(
            f"failed to parse decider output ({type(cause).__name__}): "
            f"{truncated[:120]}"
        )
        self.raw_text = truncated
        self.cause = cause


@runtime_checkable
class PMConclusionNode(Protocol):
    """Strategy interface for the PM Conclusion Node."""

    def decide(
        self, entry_input: EntryDecisionInput
    ) -> tuple[DeciderOutput, LLMUsage]:
        ...


class AnthropicPMConclusionNode:
    """Default implementation calling the Anthropic Claude API."""

    def __init__(self, client: Any, model: str, max_tokens: int = 4096) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def decide(
        self, entry_input: EntryDecisionInput
    ) -> tuple[DeciderOutput, LLMUsage]:
        user_payload = json.dumps(
            entry_input.model_dump(mode="json"), ensure_ascii=False
        )

        response = self.client.messages.create(
            model=self.model,
            system=SYSTEM_PROMPT,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": user_payload}],
        )

        text = _extract_response_text(response)

        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeciderOutputParseError(text, exc) from exc

        try:
            output = DeciderOutput.model_validate(obj)
        except ValidationError as exc:
            raise DeciderOutputParseError(text, exc) from exc

        usage = response.usage
        input_tokens = int(usage.input_tokens)
        output_tokens = int(usage.output_tokens)
        cost = compute_cost_usd(self.model, input_tokens, output_tokens)
        return output, LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=self.model,
        )


class FakePMConclusionNode:
    """Test fixture decider that returns a pre-baked ``(DeciderOutput, LLMUsage)``.

    Set ``raise_parse_error`` to simulate a malformed LLM response.
    """

    def __init__(
        self,
        output: DeciderOutput | None = None,
        usage: LLMUsage | None = None,
        raise_parse_error: DeciderOutputParseError | None = None,
    ) -> None:
        self.output = output
        self.usage = usage or LLMUsage(
            input_tokens=0, output_tokens=0, cost_usd=0.0, model="fake://"
        )
        self.raise_parse_error = raise_parse_error
        self.calls: list[EntryDecisionInput] = []

    def decide(
        self, entry_input: EntryDecisionInput
    ) -> tuple[DeciderOutput, LLMUsage]:
        self.calls.append(entry_input)
        if self.raise_parse_error is not None:
            raise self.raise_parse_error
        if self.output is None:
            raise RuntimeError(
                "FakePMConclusionNode: no output configured and no parse "
                "error to raise"
            )
        return self.output, self.usage


def _extract_response_text(response: Any) -> str:
    """Extract the text from an Anthropic ``Message`` response.

    Accepts both real SDK responses and ``MagicMock`` doubles whose
    ``content[0].text`` is a string.
    """
    content = getattr(response, "content", None)
    if not content:
        raise DeciderOutputParseError(
            "", ValueError("response.content is empty or missing")
        )
    block = content[0]
    text = getattr(block, "text", None)
    if not isinstance(text, str):
        raise DeciderOutputParseError(
            "", ValueError("response.content[0].text is not a string")
        )
    return text
