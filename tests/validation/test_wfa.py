"""Unit tests for ohmystock.validation.wfa.

Spec: openspec/changes/wfa-validation-engine/specs/wfa-validation-engine/spec.md
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import (
    ProposalDraft,
    transition_proposal,
    write_proposal,
)
from ohmystock.validation import (
    ValidationReport,
    WfaValidationError,
    WfaWindow,
    run_validation,
)
from ohmystock.validation import wfa as wfa_module
from ohmystock.validation.wfa import (
    _aggregate_oos,
    _evaluate_thresholds,
    _sharpe_gap_pct,
    _split_windows,
)


_TPE = timezone(timedelta(hours=8))
_PROPOSAL_TOPIC = "vcp-volume-threshold"


def _synthetic_bars(symbol: str, n_days: int, base_price: float) -> list[BarRow]:
    """Generate ``n_days`` business-day BarRows starting 2025-01-02.

    Prices follow a strictly-monotonic up-trend so the reference SMA-cross
    strategy never fires a crossover (all metrics zero, all aggregates 0.0,
    candidate vs. baseline deltas zero, threshold checks trivially pass).
    """
    del symbol  # name is informational only
    rows: list[BarRow] = []
    current = date(2025, 1, 2)
    i = 0
    while len(rows) < n_days:
        if current.weekday() < 5:  # Mon-Fri
            price = base_price + i * 0.5
            rows.append(
                BarRow(
                    ts=current.isoformat(),
                    o=price,
                    h=price,
                    l=price,
                    c=price,
                    v=1_000_000,
                    amount=int(price * 1_000_000),
                )
            )
            i += 1
        current = current + timedelta(days=1)
    return rows


@pytest.fixture
def synthetic_loader() -> Callable[
    [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
]:
    def _make(
        bars_by_symbol: dict[str, list[BarRow]],
    ) -> Callable[[str, str, str], list[BarRow]]:
        def loader(symbol: str, _start: str, _end: str) -> list[BarRow]:
            return bars_by_symbol.get(symbol, [])

        return loader

    return _make


def _draft(topic: str = _PROPOSAL_TOPIC) -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.4",
        created_by="wfa-test-suite",
        created_at=datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        review_id="manual-2026-04-01-to-2026-04-30",
        priority="high",
        description="VCP 量能 1.5 → 1.3。",
        motivation="metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        diff_draft="```diff\n- a\n+ b\n```",
        expected_impact="vcp.py。",
        risk_assessment="風險:過嚴漏 VCP。",
        validation_plan="WFA 5+1。",
        expected_improvement="0.565 → 0.60。",
    )


def make_validating_proposal(
    tmp_path: Path,
    *,
    topic: str = _PROPOSAL_TOPIC,
) -> Path:
    """Write a pending proposal then push it to ``validating``."""
    draft = _draft(topic=topic)
    path = write_proposal(draft, tmp_path)
    return transition_proposal(path, "validating", actor="setup")


# ---- 9.4: _split_windows happy path ----------------------------------------


def test_split_windows_5_disjoint_over_250_days() -> None:
    period = {"from": "2025-01-02", "to": "2025-12-30"}
    windows = _split_windows(period, 5, 0.7)

    assert len(windows) == 5
    for w in windows:
        assert w["in_sample"]["to"] < w["out_of_sample"]["from"]
    for i in range(len(windows) - 1):
        for j in range(i + 1, len(windows)):
            assert (
                windows[i]["out_of_sample"]["to"]
                < windows[j]["in_sample"]["from"]
            )


# ---- 9.5: _split_windows refuses degenerate input --------------------------


def test_split_windows_period_too_short_raises() -> None:
    period = {"from": "2025-01-02", "to": "2025-01-15"}  # 14 days < 5*5
    with pytest.raises(WfaValidationError) as excinfo:
        _split_windows(period, 5, 0.7)
    assert "period_too_short" in str(excinfo.value)


def test_split_windows_invalid_ratio_raises() -> None:
    period = {"from": "2025-01-02", "to": "2025-12-30"}
    with pytest.raises(WfaValidationError) as excinfo:
        _split_windows(period, 5, 0.0)
    assert "invalid_in_sample_ratio" in str(excinfo.value)


def test_split_windows_invalid_n_raises() -> None:
    period = {"from": "2025-01-02", "to": "2025-12-30"}
    with pytest.raises(WfaValidationError) as excinfo:
        _split_windows(period, 1, 0.7)
    assert "invalid_wfa_windows" in str(excinfo.value)


# ---- 9.6: dry-run skips file write + transition ----------------------------


def test_run_validation_dry_run_does_not_transition_or_write(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    slug = proposal_path.stem
    bars = {"2330": _synthetic_bars("2330", 253, 100.0)}
    loader = synthetic_loader(bars)

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
        dry_run=True,
    )

    assert isinstance(report, ValidationReport)
    assert len(report.wfa_windows) == 5
    assert report.effective_kwargs["fast"] == 10
    assert report.effective_kwargs["slow"] == 20

    assert not (proposal_path.parent / f"{slug}.validation.json").exists()
    assert proposal_path.is_file()
    text = proposal_path.read_text(encoding="utf-8")
    assert "status: validating" in text


# ---- 9.7: pass transitions to approved + moves report ----------------------


def test_run_validation_pass_transitions_to_approved_and_moves_report(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    slug = proposal_path.stem
    bars = {"2330": _synthetic_bars("2330", 253, 100.0)}
    loader = synthetic_loader(bars)

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
    )

    assert report.verdict == "pass"

    pending_dir = tmp_path / "PENDING_REVIEW"
    new_md = pending_dir / f"{slug}.md"
    new_report = pending_dir / f"{slug}.validation.json"
    assert new_md.is_file()
    assert new_report.is_file()
    assert not proposal_path.exists()

    text = new_md.read_text(encoding="utf-8")
    assert "status: approved" in text
    assert f"validation_report_path: {slug}.validation.json" in text

    payload = json.loads(new_report.read_text(encoding="utf-8"))
    assert payload["verdict"] == "pass"
    assert payload["slug"] == slug
    assert payload["effective_kwargs"]["fast"] == 10
    # Field order locked at top of payload.
    assert list(payload.keys())[:5] == [
        "proposal_id",
        "slug",
        "validated_at",
        "strategy",
        "period",
    ]


# ---- manual-verdict mode: report written, no transition --------------------
# Spec: openspec/changes/proposal-manual-verdict/specs/wfa-validation-engine/spec.md


def test_run_validation_manual_mode_writes_report_without_transition(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    slug = proposal_path.stem
    bars = {"2330": _synthetic_bars("2330", 253, 100.0)}
    loader = synthetic_loader(bars)

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
        auto_transition=False,
    )

    assert report.verdict == "pass"

    # Report written in place (proposals root)...
    report_path = tmp_path / f"{slug}.validation.json"
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "pass"

    # ...but the markdown stays put in validating, untouched.
    assert proposal_path.is_file()
    text = proposal_path.read_text(encoding="utf-8")
    assert "status: validating" in text
    assert "wfa-validator" not in text
    assert not (tmp_path / "PENDING_REVIEW" / f"{slug}.md").exists()
    assert not (tmp_path / "rejected" / f"{slug}.md").exists()


# ---- 9.8: fail transitions to rejected + reason carries failure slug -------


def test_run_validation_fail_transitions_to_rejected_with_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    slug = proposal_path.stem
    bars = {"2330": _synthetic_bars("2330", 253, 100.0)}
    loader = synthetic_loader(bars)

    # _run_one is invoked four times per window in order: baseline_is,
    # baseline_oos, candidate_is, candidate_oos. Craft candidate IS/OOS so the
    # per-window Sharpe gap (|2.0 - 0.5| / 2.0 = 0.75) exceeds the 0.30 ceiling.
    call_state = {"i": 0}

    def fake_run_one(strategy: Any, _bars: Any, _period: Any, _capital: Any) -> dict[str, float]:
        del strategy
        idx = call_state["i"] % 4
        call_state["i"] += 1
        if idx == 0:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 1:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 2:
            return {"sharpe": 2.0, "max_drawdown": -0.05, "win_rate": 0.5}
        return {"sharpe": 0.5, "max_drawdown": -0.05, "win_rate": 0.5}

    monkeypatch.setattr(wfa_module, "_run_one", fake_run_one)

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
    )

    assert report.verdict == "fail"
    assert any("sharpe_gap" in f for f in report.failures)

    rejected_dir = tmp_path / "rejected"
    new_md = rejected_dir / f"{slug}.md"
    new_report = rejected_dir / f"{slug}.validation.json"
    assert new_md.is_file()
    assert new_report.is_file()

    text = new_md.read_text(encoding="utf-8")
    assert "status: rejected" in text
    assert "sharpe_gap" in text  # rejected_reason includes the failure slug


# ---- 9.9: refuses non-validating status ------------------------------------


def test_run_validation_status_not_validating_raises(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    draft = _draft()
    pending_path = write_proposal(draft, tmp_path)  # status=pending
    loader = synthetic_loader({"2330": _synthetic_bars("2330", 253, 100.0)})

    with pytest.raises(WfaValidationError) as excinfo:
        run_validation(
            pending_path,
            strategy_name="sma_cross",
            period={"from": "2025-01-02", "to": "2025-12-30"},
            param_overrides={"fast": 10},
            universe=["2330"],
            wfa_windows=5,
            in_sample_ratio=0.7,
            initial_capital=1_000_000,
            market_data_loader=loader,
        )

    msg = str(excinfo.value)
    assert "status_not_validating" in msg
    assert "pending" in msg

    slug = pending_path.stem
    assert not (tmp_path / f"{slug}.validation.json").exists()
    assert pending_path.is_file()


# ---- 9.10: missing bars raise ---------------------------------------------


def test_run_validation_missing_bars_raises(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    loader = synthetic_loader({})

    with pytest.raises(WfaValidationError) as excinfo:
        run_validation(
            proposal_path,
            strategy_name="sma_cross",
            period={"from": "2025-01-02", "to": "2025-12-30"},
            param_overrides={"fast": 10},
            universe=["2330"],
            wfa_windows=5,
            in_sample_ratio=0.7,
            initial_capital=1_000_000,
            market_data_loader=loader,
        )
    assert "missing_bars" in str(excinfo.value)
    assert "2330" in str(excinfo.value)


# ---- 9.11: unknown strategy raises ----------------------------------------


def test_run_validation_unknown_strategy_raises(
    tmp_path: Path,
    synthetic_loader: Callable[
        [dict[str, list[BarRow]]], Callable[[str, str, str], list[BarRow]]
    ],
) -> None:
    proposal_path = make_validating_proposal(tmp_path)
    loader = synthetic_loader({"2330": _synthetic_bars("2330", 253, 100.0)})

    with pytest.raises(WfaValidationError) as excinfo:
        run_validation(
            proposal_path,
            strategy_name="made_up",
            period={"from": "2025-01-02", "to": "2025-12-30"},
            param_overrides={},
            universe=["2330"],
            wfa_windows=5,
            in_sample_ratio=0.7,
            initial_capital=1_000_000,
            market_data_loader=loader,
        )
    assert "unknown_strategy" in str(excinfo.value)
    assert "made_up" in str(excinfo.value)


# ---- 9.12: ValidationReport field order locked ----------------------------


def test_report_dataclass_field_order() -> None:
    names = [f.name for f in fields(ValidationReport)]
    assert names[:5] == [
        "proposal_id",
        "slug",
        "validated_at",
        "strategy",
        "period",
    ]
    assert names[-2:] == ["verdict", "failures"]


# ---- 9.13: threshold evaluator emits 3 failures in declared order ---------


def test_threshold_evaluator_three_failures_in_declared_order() -> None:
    candidate_gap = 0.50
    candidate_agg = {"sharpe": 0.50, "max_drawdown": -0.30, "win_rate": 0.5}
    baseline_agg = {"sharpe": 1.00, "max_drawdown": -0.10, "win_rate": 0.5}

    verdict, failures = _evaluate_thresholds(candidate_gap, candidate_agg, baseline_agg)

    assert verdict == "fail"
    assert len(failures) == 3
    assert "sharpe_gap" in failures[0]
    assert "sharpe_degradation" in failures[1]
    assert "drawdown_degradation" in failures[2]


def test_threshold_evaluator_all_pass_returns_empty_failures() -> None:
    verdict, failures = _evaluate_thresholds(
        0.18,
        {"sharpe": 1.05, "max_drawdown": -0.09, "win_rate": 0.6},
        {"sharpe": 1.00, "max_drawdown": -0.10, "win_rate": 0.55},
    )
    assert verdict == "pass"
    assert failures == []


def test_aggregate_oos_picks_min_drawdown_means_others() -> None:
    per_window = [
        {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.4},
        {"sharpe": 0.5, "max_drawdown": -0.20, "win_rate": 0.6},
    ]
    agg = _aggregate_oos(per_window)
    assert agg["sharpe"] == pytest.approx(0.75)
    assert agg["max_drawdown"] == pytest.approx(-0.20)
    assert agg["win_rate"] == pytest.approx(0.5)


def test_sharpe_gap_pct_handles_zero_is_sharpe() -> None:
    gap = _sharpe_gap_pct({"sharpe": 0.0}, {"sharpe": 0.0})
    assert gap == pytest.approx(0.0)


def test_wfa_window_is_frozen() -> None:
    w = WfaWindow(
        in_sample={"from": "2025-01-02", "to": "2025-02-28"},
        out_of_sample={"from": "2025-03-01", "to": "2025-03-15"},
        baseline_is_metrics={"sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0},
        baseline_oos_metrics={"sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0},
        candidate_is_metrics={"sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0},
        candidate_oos_metrics={"sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0},
    )
    with pytest.raises(Exception):
        w.in_sample = {}  # type: ignore[misc]
