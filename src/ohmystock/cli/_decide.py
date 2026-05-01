"""``ohmystock decide`` — run the PM decider against a single candidate.

End-to-end flow:
1. Load ``Settings``; refuse ``fake://`` model unless ``OHMYSTOCK_ALLOW_FAKE_DECIDER=true``.
2. Assemble an ``EntryDecisionInput`` via the live providers (delegated to
   ``ohmystock.cli._assemble._run_assemble``).
3. Open SQLite at ``OHMYSTOCK_DB_PATH``, run ``init_schema``.
4. Build an ``AnthropicPMConclusionNode``, run ``decide_entry``.
5. Print stdout summary (or JSON with ``--json``) and exit with the right code.

Exit codes:
- 0: ``decision == "enter"`` (kind=entry pending_confirm written)
- 1: ``decision == "reject"`` (kind=reject reject_layer=llm written)
- 2: assembler / input error (no journal row written)
- 3: orchestrator/LLM internal error (parse error, etc.; reject row IS written)
- 4: refused to use fake decider in non-test env

WARNING: this command writes pending_confirm entries; broker submission is
not yet wired. Confirm Gate + auto-execute are Phase 3.5.

Spec: openspec/changes/entry-decider-pm-node/specs/cli-and-config/spec.md
"""

from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from ohmystock.config import Settings
from ohmystock.decider.node import (
    AnthropicPMConclusionNode,
    DeciderOutputParseError,
    FakePMConclusionNode,
    PMConclusionNode,
)
from ohmystock.decider.orchestrator import OrchestrationResult, decide_entry
from ohmystock.journal.schema import init_schema


_FAKE_PREFIX = "fake://"
_TPE_TZ = timezone(timedelta(hours=8))


def _build_decider(settings: Settings) -> PMConclusionNode:
    """Return an Anthropic-backed decider, or a fake when explicitly allowed."""
    model = settings.ohmystock_decider_model
    if model.startswith(_FAKE_PREFIX):
        if not settings.ohmystock_allow_fake_decider:
            typer.echo(
                "refused to use fake decider in non-test env "
                f"(OHMYSTOCK_DECIDER_MODEL={model!r}, "
                "set OHMYSTOCK_ALLOW_FAKE_DECIDER=true to override)",
                err=True,
            )
            raise typer.Exit(4)
        return FakePMConclusionNode()

    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        typer.echo(
            "ANTHROPIC_API_KEY is not set; cannot run real decider", err=True
        )
        raise typer.Exit(3)
    client = Anthropic(api_key=settings.anthropic_api_key)
    return AnthropicPMConclusionNode(client, model)


def _open_journal_db(settings: Settings) -> sqlite3.Connection:
    path = Path(settings.ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _result_dict(result: OrchestrationResult) -> dict:
    cost_usd = result.llm_cost.cost_usd if result.llm_cost is not None else 0.0
    return {
        "decision_id": result.decision_id,
        "decision": result.final.decision,
        "written_kind": result.written_kind,
        "force_reject_reason": result.force_reject_reason,
        "cost_usd": cost_usd,
    }


def _print_summary(result: OrchestrationResult) -> None:
    cost_usd = result.llm_cost.cost_usd if result.llm_cost is not None else 0.0
    typer.echo(f"decision: {result.final.decision}")
    typer.echo(f"decision_id: {result.decision_id}")
    typer.echo(f"force_reject_reason: {result.force_reject_reason}")
    typer.echo(f"cost_usd: {cost_usd}")


def decide(
    symbol: str = typer.Option(..., "--symbol", help="台股代號（例如 2330）"),
    asof: str = typer.Option(..., "--asof", help="評分日期 YYYY-MM-DD"),
    json_out: bool = typer.Option(
        False,
        "--json/--no-json",
        help="以 JSON dump 輸出（含 decision_id / decision / force_reject_reason / cost_usd）",
    ),
) -> None:
    """Run the PM Decider on SYMBOL and write a pending_confirm or reject row.

    WARNING: This command writes pending_confirm entries; broker submission
    is not yet wired (Confirm Gate is Phase 3.5).
    """
    settings = Settings()
    decider = _build_decider(settings)

    from ohmystock.cli._assemble import _run_assemble
    from ohmystock.swarm import AssemblerInputError, LiveProviderError

    trigger_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")

    try:
        entry_input = _run_assemble(
            symbol=symbol, asof=asof, trigger_at=trigger_at
        )
    except (AssemblerInputError, LiveProviderError) as exc:
        typer.echo(f"entry_input_assembly_failed: {exc}", err=True)
        raise typer.Exit(2)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"entry_input_assembly_failed: {exc}", err=True)
        raise typer.Exit(2)

    conn = _open_journal_db(settings)
    try:
        result = decide_entry(entry_input, conn=conn, decider=decider)
    except DeciderOutputParseError:
        tb_lines = traceback.format_exc().splitlines()[:5]
        typer.echo("DeciderOutputParseError:", err=True)
        for line in tb_lines:
            typer.echo(line, err=True)
        raise typer.Exit(3)
    except Exception:  # noqa: BLE001
        tb_lines = traceback.format_exc().splitlines()[:5]
        for line in tb_lines:
            typer.echo(line, err=True)
        raise typer.Exit(3)
    finally:
        conn.close()

    if json_out:
        sys.stdout.write(
            json.dumps(_result_dict(result), ensure_ascii=False) + "\n"
        )
    else:
        _print_summary(result)

    if result.written_kind == "entry":
        raise typer.Exit(0)
    raise typer.Exit(1)
