"""Pydantic v3.1 ``DeciderOutput`` model.

Mirror of ``docs/llm-decision-schema.md`` §2 (PM 結論節點輸出 schema).
Reuses ``VcpQuality`` / ``StageLiteral`` from ``ohmystock.swarm.models`` so
the decider and the input assembler share a single literal source.

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ohmystock.swarm.models import StageLiteral, VcpQuality


OutputSchemaVersion = Literal["v3.1"]
DecisionEnum = Literal["enter", "reject", "reduce_size"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, strict=False)


class MustHaveCheck(_Strict):
    name: str
    pass_: bool = Field(alias="pass")
    evidence: str

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class BonusBreakdown(_Strict):
    name: str
    pass_: bool = Field(alias="pass")
    evidence: str

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class ToolCallSummary(_Strict):
    tool: str
    action: str
    elapsed_ms: int


class DeciderOutput(_Strict):
    """v3.1 PM Conclusion Node output.

    Pydantic-layer constraints: enums, ranges, must-have count, pivot/vcp
    invariant. Higher-level rules in §2.1 (confidence floor, bonus floor,
    reasoning length, candidate cross-check) are enforced by
    ``ohmystock.decider.validator.validate_decider_output`` post-parse.
    """

    output_schema_version: OutputSchemaVersion = "v3.1"
    decision_id: str = Field(min_length=1)
    decided_at: str = Field(min_length=1)
    model: str = Field(min_length=1)

    decision: DecisionEnum
    confidence: float = Field(ge=0.0, le=1.0)

    stage: StageLiteral
    rs_percentile: int = Field(ge=0, le=99)
    trend_template_passed: int = Field(ge=0, le=8)
    vcp_quality: VcpQuality
    pivot_price: float | None

    must_have_check: list[MustHaveCheck]
    bonus_score: int = Field(ge=0, le=8)
    bonus_breakdown: list[BonusBreakdown] = Field(default_factory=list)

    proposed_sizing_pct: float = Field(ge=0.0, le=25.0)
    expected_holding_days: int = Field(ge=1, le=30)
    reasoning: str

    cited_skills: list[str] = Field(min_length=1)
    invalidation_conditions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    tool_calls_summary: list[ToolCallSummary] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_must_have_count(self) -> "DeciderOutput":
        if len(self.must_have_check) != 3:
            raise ValueError(
                f"must_have_check must have exactly 3 entries, got "
                f"{len(self.must_have_check)}"
            )
        return self

    @model_validator(mode="after")
    def _check_pivot_invariant(self) -> "DeciderOutput":
        needs_pivot = self.vcp_quality in ("textbook", "breakout")
        if needs_pivot and (self.pivot_price is None or self.pivot_price <= 0):
            raise ValueError(
                "pivot_price must be a positive float when "
                f"vcp_quality={self.vcp_quality!r}"
            )
        if not needs_pivot and self.pivot_price is not None:
            raise ValueError(
                "pivot_price must be None when "
                f"vcp_quality={self.vcp_quality!r}"
            )
        return self
