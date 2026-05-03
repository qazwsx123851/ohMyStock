"""Settings loader (pydantic-settings, reads .env + env vars).

Fields mirror keys in repo-root .env.example. All fields are Optional /
have defaults so Settings() can be constructed without any env present;
downstream code is responsible for asserting required values before use.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str | None = None

    shioaji_api_key: str | None = None
    shioaji_secret_key: str | None = None
    shioaji_ca_path: str | None = None
    shioaji_ca_passwd: str | None = None
    shioaji_person_id: str | None = None

    finmind_token: str | None = None

    ohmystock_llm_degrade: str | None = None
    ohmystock_db_path: str = "~/.ohmystock/journal.db"
    ohmystock_log_level: str = "INFO"

    # web-admin Bearer auth — see openspec/specs/web-admin-bearer-auth/spec.md
    # (after archive). Default None lets Settings() construct without env;
    # ohmystock.api.auth._validate_admin_token() enforces presence + length
    # at app startup so CLI / tests that import Settings remain unaffected.
    ohmystock_admin_token: str | None = None

    # Phase 3 LLM Decider PM node configuration. Defaults to opus-4-7 for
    # production decisions; tests / dev can override with a fake:// scheme
    # (allowed only when ohmystock_allow_fake_decider=true). Env keys are
    # OHMYSTOCK_DECIDER_MODEL / OHMYSTOCK_ALLOW_FAKE_DECIDER (case-insensitive).
    ohmystock_decider_model: str = "claude-opus-4-7"
    ohmystock_allow_fake_decider: bool = False

    # Paper-account starting equity in TWD. Used by live providers to compute
    # exposure_pct and monthly_pnl_pct. Default matches docs/frontend.md §17 and
    # tools-contracts.md §backtest defaults.
    starting_equity_twd: int = 1_000_000

    # Confirm Gate v0 — see openspec/specs/confirm-gate/spec.md (after archive).
    # Timeout for pending_confirm entries (sweep_expired uses this). Default 30
    # min mirrors v3-decisions #11. Capital used by gate to compute qty until
    # Sizing Service ships.
    ohmystock_confirm_timeout_minutes: int = 30
    ohmystock_default_capital_twd: int = 1_000_000

    # Broker mode. Defaults to shioaji-sim (matches docs/safety-and-simulation.md
    # §2.2). Live mode requires explicit env override and the auto-execute
    # validator below forbids it being combined with auto-execute=true.
    ohmystock_broker: Literal["mock", "shioaji-sim", "shioaji-live"] = (
        "shioaji-sim"
    )

    # Auto-execute Phase 3.5 — see openspec/specs/auto-execute/spec.md
    # (after archive). All defaults match cheatsheet §6.7 and safety §2.9.
    ohmystock_auto_execute: bool = False
    ohmystock_auto_execute_daily_limit: int = 5
    ohmystock_auto_execute_min_confidence: float = 0.7
    ohmystock_auto_execute_max_notional_pct: float = 0.25
    ohmystock_auto_execute_max_sizing_deviation: float = 0.30
    ohmystock_auto_execute_loss_lockout_hours: int = 24
    ohmystock_auto_execute_loss_pct_threshold: float = -0.05
    ohmystock_auto_execute_account_equity_twd: int = 1_000_000

    @field_validator(
        "ohmystock_confirm_timeout_minutes",
        "ohmystock_default_capital_twd",
        "ohmystock_auto_execute_daily_limit",
        "ohmystock_auto_execute_loss_lockout_hours",
        "ohmystock_auto_execute_account_equity_twd",
    )
    @classmethod
    def _must_be_positive(cls, value: int, info) -> int:  # noqa: ANN001
        if value <= 0:
            raise ValueError(
                f"{info.field_name} must be a positive integer, got {value}"
            )
        return value

    @model_validator(mode="after")
    def forbid_auto_execute_in_live(self) -> "Settings":
        """Defense-in-depth: refuse to start with OHMYSTOCK_AUTO_EXECUTE=true
        when OHMYSTOCK_BROKER=shioaji-live.

        Live mode requires human confirm per docs/safety-and-simulation.md §2.9.
        """
        if (
            self.ohmystock_auto_execute
            and self.ohmystock_broker == "shioaji-live"
        ):
            raise RuntimeError(
                "Refusing to start: OHMYSTOCK_AUTO_EXECUTE=true is not allowed "
                "when OHMYSTOCK_BROKER=shioaji-live. Live mode requires human "
                "confirm."
            )
        return self
