"""Walk-forward validation engine — library entry point.

Spec: openspec/changes/wfa-validation-engine/specs/wfa-validation-engine/spec.md

Pure-deterministic gate between ``validating`` and ``approved`` proposal states:
splits the requested period into N disjoint chunks (IS/OOS per chunk), runs the
baseline + candidate strategies through ``run_backtest`` over each window's IS
and OOS slice, aggregates per-window OOS metrics, evaluates three threshold
checks (Sharpe gap, Sharpe degradation, MDD degradation), writes a
``<slug>.validation.json`` sibling-of-proposal report, and finally calls
``transition_proposal`` to move the proposal to ``approved`` (pass) or
``rejected`` (fail).
"""

from __future__ import annotations

import inspect
import json
import logging
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from ohmystock.backtest.engine import run_backtest
from ohmystock.backtest.strategy.registry import available_strategies
from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import parse_proposal, transition_proposal


logger = logging.getLogger(__name__)


# Threshold constants (spec D4 + Requirement "Three pass conditions").
_THRESHOLDS: dict[str, float] = {
    "sharpe_gap_max": 0.30,
    "sharpe_relative_min": 0.95,
    "drawdown_relative_max": 1.20,
}
_DEFAULT_WFA_WINDOWS = 5
_DEFAULT_IS_RATIO = 0.7
_REPORT_SUFFIX = ".validation.json"
_TPE_TZ = timezone(timedelta(hours=8))
_EPS = 1e-9
_METRIC_KEYS: tuple[str, ...] = ("sharpe", "max_drawdown", "win_rate")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---- Public dataclasses + exception --------------------------------------


@dataclass(frozen=True)
class WfaWindow:
    """One walk-forward window — IS + OOS slices + per-side metrics.

    Field order matches the spec's serialised layout exactly. ``in_sample``
    and ``out_of_sample`` are ``{"from": ISO_DATE, "to": ISO_DATE}`` dicts;
    the four metric dicts carry the ``{sharpe, max_drawdown, win_rate}``
    subset of ``compute_metrics`` output.
    """

    in_sample: dict[str, str]
    out_of_sample: dict[str, str]
    baseline_is_metrics: dict[str, Any]
    baseline_oos_metrics: dict[str, Any]
    candidate_is_metrics: dict[str, Any]
    candidate_oos_metrics: dict[str, Any]


@dataclass(frozen=True)
class ValidationReport:
    """Full validation result — written verbatim to disk as JSON.

    Field order is part of the public contract (asserted in
    ``test_report_dataclass_field_order``) so the on-disk JSON reads
    top-down as ``metadata → windows → aggregates → thresholds → verdict``.
    """

    proposal_id: str
    slug: str
    validated_at: str
    strategy: str
    period: dict[str, str]
    param_overrides: dict[str, Any]
    effective_kwargs: dict[str, Any]
    universe: list[str]
    wfa_windows: list[WfaWindow]
    baseline_oos_aggregate: dict[str, float]
    candidate_oos_aggregate: dict[str, float]
    candidate_is_oos_sharpe_gap_pct: float
    deltas: dict[str, float]
    thresholds: dict[str, float]
    verdict: Literal["pass", "fail"]
    failures: list[str]


class WfaValidationError(RuntimeError):
    """Raised when ``run_validation`` cannot start or complete cleanly.

    The first-line token (``status_not_validating`` / ``unknown_strategy`` /
    ``period_too_short`` / ``missing_bars: <sym>`` / ``backtest_failed: ...``
    / ``window_has_no_bars: ...`` / ``invalid_in_sample_ratio: ...`` /
    ``invalid_wfa_windows: ...``) is the stable identifier callers/tests
    pattern-match on.
    """


# ---- Frontmatter peek (status only — body parsed by parse_proposal) ------


def _read_frontmatter(path: Path) -> dict[str, str]:
    """Return the YAML-ish ``key: value`` frontmatter as a flat dict.

    Mirrors ``api.routes.proposals._read_frontmatter`` but raises rather
    than silently returning ``None`` — the validator wants fail-loud.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise WfaValidationError(
            f"malformed_proposal: no frontmatter in {path.name}"
        )
    out: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep != ":":
            continue
        out[key.strip()] = value.strip()
    return out


# ---- Window splitter (pure, no I/O) --------------------------------------


def _split_windows(
    period: dict[str, str], n: int, is_ratio: float
) -> list[dict[str, dict[str, str]]]:
    """Split ``period`` into ``n`` disjoint chunks; return IS/OOS subwindows.

    Each chunk is ``floor(total_days / n)`` calendar days; the last chunk
    absorbs the remainder so the entire requested period is covered. The
    first ``is_ratio`` of each chunk is the IS slice; the remaining tail
    is the OOS slice. Adjacent OOS windows are strictly disjoint by
    construction.
    """
    if n < 2:
        raise WfaValidationError(
            f"invalid_wfa_windows: n must be >= 2, got {n}"
        )
    if not (0.0 < is_ratio < 1.0):
        raise WfaValidationError(
            f"invalid_in_sample_ratio: must be in (0, 1), got {is_ratio}"
        )

    start = date.fromisoformat(period["from"])
    end = date.fromisoformat(period["to"])
    total_days = (end - start).days + 1
    if total_days < n * 5:
        raise WfaValidationError(
            f"period_too_short: {total_days} calendar days < n*5={n * 5} "
            f"(period={period['from']}..{period['to']}, wfa_windows={n})"
        )

    chunk_days = total_days // n
    windows: list[dict[str, dict[str, str]]] = []
    for i in range(n):
        chunk_start_offset = i * chunk_days
        # Last chunk absorbs any remainder so end-of-period is covered.
        chunk_end_offset = (i + 1) * chunk_days - 1
        if i == n - 1:
            chunk_end_offset = total_days - 1

        is_len = max(1, int(math.floor(chunk_days * is_ratio)))
        # Bound: IS must leave at least 1 day for OOS.
        chunk_len = chunk_end_offset - chunk_start_offset + 1
        if is_len >= chunk_len:
            is_len = chunk_len - 1

        is_from = start + timedelta(days=chunk_start_offset)
        is_to = start + timedelta(days=chunk_start_offset + is_len - 1)
        oos_from = start + timedelta(days=chunk_start_offset + is_len)
        oos_to = start + timedelta(days=chunk_end_offset)

        windows.append(
            {
                "in_sample": {"from": is_from.isoformat(), "to": is_to.isoformat()},
                "out_of_sample": {
                    "from": oos_from.isoformat(),
                    "to": oos_to.isoformat(),
                },
            }
        )

    # Defensive invariant — disjointness guaranteed by construction but
    # asserted explicitly so a future refactor cannot silently break it.
    for i in range(len(windows) - 1):
        if windows[i]["out_of_sample"]["to"] >= windows[i + 1]["in_sample"]["from"]:
            raise WfaValidationError(
                "invariant_violation: adjacent windows overlap "
                f"({windows[i]['out_of_sample']['to']} >= "
                f"{windows[i + 1]['in_sample']['from']})"
            )
    return windows


# ---- Backtest invocation helpers -----------------------------------------


def _slice_bars(
    all_bars: dict[str, list[BarRow]], period: dict[str, str]
) -> dict[str, list[BarRow]]:
    """Return per-symbol bars whose ts lies in ``[period.from, period.to]``.

    Symbols with no bars in the window are silently dropped from the
    result dict so ``run_backtest`` doesn't error on empty-per-symbol
    inputs. If every symbol ends up empty, raises ``window_has_no_bars``.
    """
    out: dict[str, list[BarRow]] = {}
    for sym, bars in all_bars.items():
        rows = [b for b in bars if period["from"] <= b["ts"] <= period["to"]]
        if rows:
            out[sym] = rows
    if not out:
        raise WfaValidationError(
            f"window_has_no_bars: no symbol has bars in "
            f"{period['from']}..{period['to']}"
        )
    return out


def _run_one(
    strategy: Any,
    bars_by_symbol: dict[str, list[BarRow]],
    period: dict[str, str],
    initial_capital: int | float,
) -> dict[str, float]:
    """Run one backtest, return the ``{sharpe, max_drawdown, win_rate}`` subset.

    Re-raises ``run_backtest`` envelope errors as ``WfaValidationError`` so
    callers see one exception type for "I cannot validate this".
    """
    envelope = run_backtest(
        strategy,
        bars_by_symbol,
        period=period,
        initial_capital=initial_capital,
    )
    if not envelope["ok"]:
        err = envelope["error"] or {}
        raise WfaValidationError(
            f"backtest_failed: {err.get('code', 'UNKNOWN')}: "
            f"{err.get('message', '<no-message>')}"
        )
    metrics = envelope["data"]["metrics"]
    return {key: float(metrics.get(key, 0.0)) for key in _METRIC_KEYS}


# ---- OOS aggregator + threshold evaluator --------------------------------


def _aggregate_oos(per_window_metrics: list[dict[str, float]]) -> dict[str, float]:
    """Aggregate per-window OOS metrics into a single dict.

    * ``sharpe`` — arithmetic mean across windows.
    * ``max_drawdown`` — ``min`` (most-negative = deepest) across windows.
    * ``win_rate`` — arithmetic mean across windows.
    """
    if not per_window_metrics:
        return {"sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0}
    n = len(per_window_metrics)
    sharpe = sum(m["sharpe"] for m in per_window_metrics) / n
    max_drawdown = min(m["max_drawdown"] for m in per_window_metrics)
    win_rate = sum(m["win_rate"] for m in per_window_metrics) / n
    return {
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
    }


def _sharpe_gap_pct(is_metrics: dict[str, float], oos_metrics: dict[str, float]) -> float:
    """Compute per-window IS-OOS Sharpe gap fraction.

    Returns ``abs(IS - OOS) / max(abs(IS), eps)`` — a unitless ratio
    bounded below by 0 (no gap) with no upper bound.
    """
    is_sharpe = float(is_metrics.get("sharpe", 0.0))
    oos_sharpe = float(oos_metrics.get("sharpe", 0.0))
    return abs(is_sharpe - oos_sharpe) / max(abs(is_sharpe), _EPS)


def _evaluate_thresholds(
    candidate_gap: float,
    candidate_agg: dict[str, float],
    baseline_agg: dict[str, float],
) -> tuple[Literal["pass", "fail"], list[str]]:
    """Evaluate the three pass conditions in declared order.

    Each condition is checked independently; ``failures`` lists every
    failing condition in declared order (no short-circuit) so a human
    auditor sees the full picture.
    """
    failures: list[str] = []

    gap_max = _THRESHOLDS["sharpe_gap_max"]
    if candidate_gap >= gap_max:
        failures.append(
            f"sharpe_gap: actual={candidate_gap:.4f} >= threshold={gap_max:.4f}"
        )

    rel_min = _THRESHOLDS["sharpe_relative_min"]
    cand_sharpe = candidate_agg["sharpe"]
    base_sharpe = baseline_agg["sharpe"]
    sharpe_floor = base_sharpe * rel_min
    if cand_sharpe < sharpe_floor:
        failures.append(
            f"sharpe_degradation: actual={cand_sharpe:.4f} < "
            f"threshold={sharpe_floor:.4f} (baseline_sharpe={base_sharpe:.4f} "
            f"* {rel_min:.4f})"
        )

    dd_max = _THRESHOLDS["drawdown_relative_max"]
    cand_mdd_abs = abs(candidate_agg["max_drawdown"])
    base_mdd_abs = abs(baseline_agg["max_drawdown"])
    mdd_ceiling = base_mdd_abs * dd_max
    if cand_mdd_abs > mdd_ceiling:
        failures.append(
            f"drawdown_degradation: actual={cand_mdd_abs:.4f} > "
            f"threshold={mdd_ceiling:.4f} (baseline_mdd_abs={base_mdd_abs:.4f} "
            f"* {dd_max:.4f})"
        )

    verdict: Literal["pass", "fail"] = "pass" if not failures else "fail"
    return verdict, failures


# ---- Report writer + state-transition wiring ------------------------------


def _write_report_atomic(target_path: Path, report: ValidationReport) -> None:
    """Atomically write ``report`` as JSON to ``target_path``.

    Strategy: ``NamedTemporaryFile`` in the destination directory, write +
    flush + fsync + ``os.replace``. Mid-write crash leaves either the old
    file or no file — never a half-written one.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        asdict(report), ensure_ascii=False, indent=2, sort_keys=False
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target_path.parent,
            delete=False,
            suffix=".validation.json.tmp",
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target_path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _transition_after_verdict(
    proposal_path: Path,
    slug: str,
    verdict: Literal["pass", "fail"],
    failures: list[str],
    report_path: Path,
) -> Path:
    """Drive the proposal markdown to ``approved``/``rejected`` and co-locate the report.

    ``transition_proposal`` moves the markdown across the legal edge; this
    helper then mirrors the move for the sibling ``<slug>.validation.json``
    so the relative path stored in the markdown's frontmatter keeps
    resolving correctly.
    """
    if verdict == "pass":
        new_path = transition_proposal(
            proposal_path,
            "approved",
            actor="wfa-validator",
            validation_report_path=Path(f"{slug}{_REPORT_SUFFIX}"),
        )
    else:
        reason = "; ".join(failures)[:200] if failures else "wfa_validation_failed"
        new_path = transition_proposal(
            proposal_path,
            "rejected",
            actor="wfa-validator",
            reason=reason,
        )

    if new_path.parent != proposal_path.parent:
        new_report_path = new_path.parent / report_path.name
        new_report_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(report_path, new_report_path)
    return new_path


# ---- Strategy default kwargs --------------------------------------------


def _strategy_default_kwargs(cls: type) -> dict[str, Any]:
    """Extract default kwargs from ``cls.__init__`` signature.

    Required-positional / *args / **kwargs / self are skipped. Defaults
    are the source of truth for the baseline strategy; the candidate is
    constructed from ``default_kwargs | param_overrides``.
    """
    sig = inspect.signature(cls.__init__)
    out: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if param.default is inspect.Parameter.empty:
            continue
        out[name] = param.default
    return out


def _resolve_strategy_class(strategy_name: str) -> type:
    """Look up ``strategy_name`` in the registry; raise if absent.

    Walks ``ohmystock.backtest.strategy`` once to find a class whose
    instance has ``name == strategy_name``. Reuses ``available_strategies()``
    for the membership check so the validator and the admin UI see the
    same strategy set.
    """
    registered = {entry["name"] for entry in available_strategies()}
    if strategy_name not in registered:
        raise WfaValidationError(
            f"unknown_strategy: {strategy_name}"
        )
    # Find the class object by walking the strategy package.
    from ohmystock.backtest import strategy as strategy_pkg

    for attr_name in dir(strategy_pkg):
        cls = getattr(strategy_pkg, attr_name, None)
        if not inspect.isclass(cls):
            continue
        if not (
            callable(getattr(cls, "warmup_bars", None))
            and callable(getattr(cls, "on_bar", None))
        ):
            continue
        try:
            instance = cls()
        except Exception:  # noqa: BLE001 — broken strategies degrade gracefully
            continue
        if getattr(instance, "name", None) == strategy_name:
            return cls
    raise WfaValidationError(f"unknown_strategy: {strategy_name}")


# ---- Orchestrator --------------------------------------------------------


def run_validation(
    proposal_path: Path,
    *,
    strategy_name: str,
    period: dict[str, str],
    param_overrides: dict[str, Any],
    universe: list[str],
    wfa_windows: int = _DEFAULT_WFA_WINDOWS,
    in_sample_ratio: float = _DEFAULT_IS_RATIO,
    initial_capital: int | float,
    market_data_loader: Callable[[str, str, str], list[BarRow]],
    dry_run: bool = False,
) -> ValidationReport:
    """Validate a ``validating`` proposal via walk-forward analysis.

    See module docstring for the high-level flow. The function is fully
    deterministic given the same inputs: no LLM, no network, no clock-
    dependent branches other than ``validated_at``.
    """
    if not universe:
        raise WfaValidationError("invalid_universe: universe is empty")

    fm = _read_frontmatter(proposal_path)
    status = fm.get("status", "")
    proposal_id = fm.get("proposal_id") or proposal_path.stem
    slug = proposal_path.stem

    if status != "validating":
        raise WfaValidationError(
            f"status_not_validating: actual={status or '<missing>'}"
        )

    # parse_proposal validates body shape; we discard the result.
    parse_proposal(proposal_path)

    strategy_cls = _resolve_strategy_class(strategy_name)

    try:
        default_kwargs = _strategy_default_kwargs(strategy_cls)
    except Exception as exc:  # noqa: BLE001
        raise WfaValidationError(
            f"strategy_introspection_failed: {type(exc).__name__}: {exc}"
        ) from exc
    effective_kwargs = {**default_kwargs, **param_overrides}

    try:
        baseline_strategy = strategy_cls(**default_kwargs)
    except Exception as exc:  # noqa: BLE001
        raise WfaValidationError(
            f"baseline_construct_failed: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        candidate_strategy = strategy_cls(**effective_kwargs)
    except Exception as exc:  # noqa: BLE001
        raise WfaValidationError(
            f"candidate_construct_failed: {type(exc).__name__}: {exc}"
        ) from exc

    raw_windows = _split_windows(period, wfa_windows, in_sample_ratio)

    all_bars: dict[str, list[BarRow]] = {}
    for sym in universe:
        bars = list(market_data_loader(sym, period["from"], period["to"]))
        if not bars:
            raise WfaValidationError(f"missing_bars: {sym}")
        all_bars[sym] = bars

    wfa_window_records: list[WfaWindow] = []
    baseline_oos_per_window: list[dict[str, float]] = []
    candidate_oos_per_window: list[dict[str, float]] = []
    candidate_per_window_gaps: list[float] = []

    for window in raw_windows:
        is_period = window["in_sample"]
        oos_period = window["out_of_sample"]

        is_bars = _slice_bars(all_bars, is_period)
        oos_bars = _slice_bars(all_bars, oos_period)

        baseline_is = _run_one(baseline_strategy, is_bars, is_period, initial_capital)
        baseline_oos = _run_one(baseline_strategy, oos_bars, oos_period, initial_capital)
        candidate_is = _run_one(candidate_strategy, is_bars, is_period, initial_capital)
        candidate_oos = _run_one(candidate_strategy, oos_bars, oos_period, initial_capital)

        baseline_oos_per_window.append(baseline_oos)
        candidate_oos_per_window.append(candidate_oos)
        candidate_per_window_gaps.append(_sharpe_gap_pct(candidate_is, candidate_oos))

        wfa_window_records.append(
            WfaWindow(
                in_sample=is_period,
                out_of_sample=oos_period,
                baseline_is_metrics=baseline_is,
                baseline_oos_metrics=baseline_oos,
                candidate_is_metrics=candidate_is,
                candidate_oos_metrics=candidate_oos,
            )
        )

    baseline_oos_aggregate = _aggregate_oos(baseline_oos_per_window)
    candidate_oos_aggregate = _aggregate_oos(candidate_oos_per_window)

    if candidate_per_window_gaps:
        candidate_is_oos_sharpe_gap_pct = (
            sum(candidate_per_window_gaps) / len(candidate_per_window_gaps)
        )
    else:
        candidate_is_oos_sharpe_gap_pct = 0.0

    verdict, failures = _evaluate_thresholds(
        candidate_is_oos_sharpe_gap_pct,
        candidate_oos_aggregate,
        baseline_oos_aggregate,
    )

    deltas = {
        "sharpe": candidate_oos_aggregate["sharpe"] - baseline_oos_aggregate["sharpe"],
        "max_drawdown": (
            candidate_oos_aggregate["max_drawdown"]
            - baseline_oos_aggregate["max_drawdown"]
        ),
        "win_rate": (
            candidate_oos_aggregate["win_rate"] - baseline_oos_aggregate["win_rate"]
        ),
    }

    validated_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")
    report = ValidationReport(
        proposal_id=proposal_id,
        slug=slug,
        validated_at=validated_at,
        strategy=strategy_name,
        period=dict(period),
        param_overrides=dict(param_overrides),
        effective_kwargs=dict(effective_kwargs),
        universe=list(universe),
        wfa_windows=wfa_window_records,
        baseline_oos_aggregate=baseline_oos_aggregate,
        candidate_oos_aggregate=candidate_oos_aggregate,
        candidate_is_oos_sharpe_gap_pct=candidate_is_oos_sharpe_gap_pct,
        deltas=deltas,
        thresholds=dict(_THRESHOLDS),
        verdict=verdict,
        failures=failures,
    )

    if dry_run:
        return report

    report_path = proposal_path.parent / f"{slug}{_REPORT_SUFFIX}"
    _write_report_atomic(report_path, report)
    _transition_after_verdict(proposal_path, slug, verdict, failures, report_path)
    return report


# ---- Public surface check ------------------------------------------------


def _validation_report_field_names() -> tuple[str, ...]:
    """Return field names of ``ValidationReport`` for the order-invariance test."""
    return tuple(f.name for f in fields(ValidationReport))
