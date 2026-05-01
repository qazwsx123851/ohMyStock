"""Phase 3 LLM Decider — PM Conclusion node + §2.1 system override.

Public API:

- ``decide_entry`` — top-level orchestrator (LLM call → validate → journal +
  llm_costs, atomic).
- ``OrchestrationResult`` / ``ValidationResult`` — result dataclasses.
- ``DeciderOutput`` — Pydantic v3.1 model for the LLM JSON output.
- ``PMConclusionNode`` Protocol + ``AnthropicPMConclusionNode`` default impl.
- ``FakePMConclusionNode`` — test fixture, returns a pre-baked output.
- ``LLMUsage`` — token + cost summary returned alongside the decision.
- ``DeciderOutputParseError`` — raised when the LLM response is not parseable
  into ``DeciderOutput``.
- ``validate_decider_output`` — pure §2.1 validator over a parsed output.
- ``MODEL_PRICING_USD_PER_MTOK`` / ``compute_cost_usd`` — pricing helpers.

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md
"""

from ohmystock.decider._pricing import (
    MODEL_PRICING_USD_PER_MTOK,
    compute_cost_usd,
)
from ohmystock.decider.models import (
    BonusBreakdown,
    DeciderOutput,
    MustHaveCheck,
    ToolCallSummary,
)
from ohmystock.decider.node import (
    AnthropicPMConclusionNode,
    DeciderOutputParseError,
    FakePMConclusionNode,
    LLMUsage,
    PMConclusionNode,
    SYSTEM_PROMPT,
)
from ohmystock.decider.orchestrator import (
    OrchestrationResult,
    decide_entry,
    default_decision_id,
    system_clock,
)
from ohmystock.decider.validator import (
    ValidationResult,
    validate_decider_output,
)

__all__ = [
    "AnthropicPMConclusionNode",
    "BonusBreakdown",
    "DeciderOutput",
    "DeciderOutputParseError",
    "FakePMConclusionNode",
    "LLMUsage",
    "MODEL_PRICING_USD_PER_MTOK",
    "MustHaveCheck",
    "OrchestrationResult",
    "PMConclusionNode",
    "SYSTEM_PROMPT",
    "ToolCallSummary",
    "ValidationResult",
    "compute_cost_usd",
    "decide_entry",
    "default_decision_id",
    "system_clock",
    "validate_decider_output",
]
