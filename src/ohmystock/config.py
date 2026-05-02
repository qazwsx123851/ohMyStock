"""Settings loader (pydantic-settings, reads .env + env vars).

Fields mirror keys in repo-root .env.example. All fields are Optional /
have defaults so Settings() can be constructed without any env present;
downstream code is responsible for asserting required values before use.
"""

from __future__ import annotations

from pydantic import field_validator
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

    ohmystock_auto_execute: str | None = None
    ohmystock_llm_degrade: str | None = None
    ohmystock_db_path: str = "~/.ohmystock/journal.db"
    ohmystock_log_level: str = "INFO"

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

    @field_validator(
        "ohmystock_confirm_timeout_minutes",
        "ohmystock_default_capital_twd",
    )
    @classmethod
    def _must_be_positive(cls, value: int, info) -> int:  # noqa: ANN001
        if value <= 0:
            raise ValueError(
                f"{info.field_name} must be a positive integer, got {value}"
            )
        return value
