"""§2.1 system-override validator for ``DeciderOutput``.

Pure function: given the LLM raw output and the candidate snapshot from
``EntryDecisionInput``, returns a :class:`ValidationResult` describing
whether the system force-rejects the decision and which overrides were
applied (e.g., stage-3 sizing cap).

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md
SSOT: docs/llm-decision-schema.md §2.1
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ohmystock.decider.models import DeciderOutput, MustHaveCheck
from ohmystock.swarm.models import CandidateSnapshot


_REQUIRED_MUST_HAVE_NAMES = frozenset(
    {
        "trend_template_8_of_8",
        "stage_2_confirmed",
        "vcp_pivot_breakout_with_volume",
    }
)
_RS_PERCENTILE_FLOOR = 65
_TREND_TEMPLATE_FLOOR = 8
_VCP_AUTOFAIL = frozenset({"none", "forming"})
_BONUS_FLOOR = 4
_REASONING_MIN_CHARS = 200
_HOLDING_DAYS_MIN = 1
_HOLDING_DAYS_MAX = 30
_SIZING_MIN = 0.0
_SIZING_MAX = 25.0
_STAGE_3_SIZING_CAP = 10.0
_CONFIDENCE_FLOOR = 0.6


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of :func:`validate_decider_output`.

    - ``final_decision``: a (possibly modified) copy of the LLM output. If
      ``force_reject_reason`` is set, ``final_decision.decision`` is forced
      to ``"reject"``; otherwise it equals the LLM's original decision.
    - ``force_reject_reason``: ``None`` when the LLM passed all §2.1
      checks; otherwise a stable string code (e.g.,
      ``"confidence_below_0_6"``, ``"stage_4_excluded"``) suitable for
      journal storage.
    - ``applied_overrides``: human-readable list of overrides applied (e.g.,
      ``"stage_3_sizing_capped:18.0->10.0"``, or
      ``"force_rejected:<reason>"``).
    """

    final_decision: DeciderOutput
    force_reject_reason: str | None = None
    applied_overrides: list[str] = field(default_factory=list)


def validate_decider_output(
    raw: DeciderOutput, candidate: CandidateSnapshot
) -> ValidationResult:
    """Apply ``docs/llm-decision-schema.md`` §2.1 to ``raw``.

    Rules are checked in a fixed order; the first violation determines the
    reject reason. After all reject checks pass, the stage-3 sizing cap is
    applied last and never causes a force-reject.
    """
    reject = _first_reject_reason(raw, candidate)
    if reject is not None:
        forced = raw.model_copy(update={"decision": "reject"})
        return ValidationResult(
            final_decision=forced,
            force_reject_reason=reject,
            applied_overrides=[f"force_rejected:{reject}"],
        )

    overrides: list[str] = []
    final = raw
    if raw.stage == 3 and raw.proposed_sizing_pct > _STAGE_3_SIZING_CAP:
        overrides.append(
            f"stage_3_sizing_capped:{raw.proposed_sizing_pct}->"
            f"{_STAGE_3_SIZING_CAP}"
        )
        final = raw.model_copy(
            update={"proposed_sizing_pct": _STAGE_3_SIZING_CAP}
        )

    return ValidationResult(
        final_decision=final,
        force_reject_reason=None,
        applied_overrides=overrides,
    )


def _first_reject_reason(
    raw: DeciderOutput, candidate: CandidateSnapshot
) -> str | None:
    """Return the first §2.1 violation, or ``None`` if all checks pass."""

    if raw.confidence < _CONFIDENCE_FLOOR:
        return "confidence_below_0_6"

    reasoning_len = len(raw.reasoning)
    if reasoning_len < _REASONING_MIN_CHARS:
        return f"reasoning_too_short:{reasoning_len}"

    if len(raw.cited_skills) == 0:
        return "cited_skills_empty"

    if not (
        _HOLDING_DAYS_MIN <= raw.expected_holding_days <= _HOLDING_DAYS_MAX
    ):
        return f"holding_days_out_of_range:{raw.expected_holding_days}"

    if not (_SIZING_MIN <= raw.proposed_sizing_pct <= _SIZING_MAX):
        return f"sizing_out_of_range:{raw.proposed_sizing_pct}"

    if raw.stage == 4:
        return "stage_4_excluded"

    diverged_field = _first_diverged_field(raw, candidate)
    if diverged_field is not None:
        return f"llm_diverged_from_candidate:{diverged_field}"

    raw_names = {item.name for item in raw.must_have_check}
    if raw_names != _REQUIRED_MUST_HAVE_NAMES:
        return "must_have_names_invalid"

    failed_name = _first_must_have_failure(raw.must_have_check, candidate)
    if failed_name is not None:
        return f"must_have_failed:{failed_name}"

    if raw.bonus_score < _BONUS_FLOOR:
        return f"bonus_score_below_4:{raw.bonus_score}"

    return None


def _first_diverged_field(
    raw: DeciderOutput, candidate: CandidateSnapshot
) -> str | None:
    """Return the first SEPA field where the LLM disagrees with the candidate."""

    pairs: tuple[tuple[str, object, object], ...] = (
        ("stage", raw.stage, candidate.stage),
        ("rs_percentile", raw.rs_percentile, candidate.rs_percentile),
        (
            "trend_template_passed",
            raw.trend_template_passed,
            candidate.trend_template_passed,
        ),
        ("vcp_quality", raw.vcp_quality, candidate.vcp_quality),
        ("pivot_price", raw.pivot_price, candidate.pivot_price),
    )
    for name, lhs, rhs in pairs:
        if lhs != rhs:
            return name
    return None


def _first_must_have_failure(
    checks: list[MustHaveCheck], candidate: CandidateSnapshot
) -> str | None:
    """Return the first must_have name that fails after applying §2.1 auto-fails.

    Auto-fail rules (system overrides what the LLM declared):
    - candidate.rs_percentile < 65 OR candidate.trend_template_passed < 8
      → ``trend_template_8_of_8`` is treated as failed regardless of LLM.
    - candidate.vcp_quality in {none, forming}
      → ``vcp_pivot_breakout_with_volume`` is treated as failed.
    """
    auto_fail_trend = (
        candidate.rs_percentile < _RS_PERCENTILE_FLOOR
        or candidate.trend_template_passed < _TREND_TEMPLATE_FLOOR
    )
    auto_fail_vcp = candidate.vcp_quality in _VCP_AUTOFAIL

    for item in checks:
        effective_pass = item.pass_
        if item.name == "trend_template_8_of_8" and auto_fail_trend:
            effective_pass = False
        elif item.name == "vcp_pivot_breakout_with_volume" and auto_fail_vcp:
            effective_pass = False
        if not effective_pass:
            return item.name
    return None
