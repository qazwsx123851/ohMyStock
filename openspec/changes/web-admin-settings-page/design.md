## Context

`Settings` (pydantic-settings, `src/ohmystock/config.py`) is loaded once at app startup and exposes ~25 fields covering API keys, broker mode, auto-execute breakers, and admin auth. Mark currently has no in-browser way to confirm what is loaded; `cat .env` over SSH is the only path. The `/settings` page in `web-admin/src/pages/stubs.tsx` is `ComingSoon`.

Existing admin endpoints (market, backtest, journal, positions, stats) all share:
- Bearer auth dep `require_admin` mounted via `app.include_router(..., dependencies=[Depends(require_admin)])`.
- Per-request `sqlite3.Connection` via `Depends(get_db)`.
- Unified `{ok, data, error}` envelope from `_envelope.to_success` / `_envelope.map_exception_to_envelope`.
- 紅漲綠跌 dual-encoding (colour + Lucide icon) on the frontend.

The settings page in `docs/web-admin-page-designs.md` §16 specifies 4 sections (API keys / Theme / Safety / Breakers) and explicitly leaves PUT for future work.

## Goals / Non-Goals

**Goals:**
- Mark can open `/settings` in admin web and see, in 4 grouped sections: which keys are set (boolean only), broker mode, current auto-execute flag, and current breaker thresholds.
- Safety section uses `--warning` Card by default and switches to `--destructive` when `auto_execute=true`, paired with `AlertTriangle` / `AlertCircle` so colour is never the only signal.
- Endpoint and page reuse existing auth/envelope/per-request-conn invariants; no new cross-cutting infra.

**Non-Goals:**
- No PUT endpoint, no `.env` writeback, no in-browser validation calls (Anthropic ping, Shioaji health-check). Hint text directs to `.env` + restart.
- No theme switcher (placeholder only — `mode: "system"` constant).
- No live-update / SSE — `Settings` is immutable for the lifetime of the process.
- No pagination / search.

## Decisions

### D1: Read-only v0 (no PUT)
**Choice:** Endpoint is `GET` only. Page renders disabled inputs.
**Rationale:**
- `OHMYSTOCK_AUTO_EXECUTE` is the live-mode kill switch (`docs/safety-and-simulation.md` §2.9). Allowing it to be flipped from a browser session — even one behind Bearer auth — adds a remote-attack surface that the existing `.env` + restart flow does not have. Defense-in-depth wins.
- pydantic-settings reads `.env` once at construction; even if we wrote `.env`, the running process would not pick it up without restart. A "save" button that doesn't take effect is worse than no button.
- Cold-start scenario §10 only requires *visibility*. Editing is a separate, optional follow-up.

**Alternatives considered:**
- *PUT with restart-required banner.* Rejected — invites the user to mutate live state and pretends it's reversible. Even without auto-execute, the audit trail of "who changed what when" is not implemented yet.
- *PUT only for non-safety knobs (theme).* Rejected — theme has no UI in this iteration, so PUT has zero target fields. Empty PUT is a maintenance burden.

### D2: Redactor returns booleans, not prefixes
**Choice:** Secret-bearing fields (`anthropic_api_key`, `shioaji_*`, `finmind_token`, `ohmystock_admin_token`) become `bool` (`true` if set and non-empty after `.strip()`, else `false`). No partial value, no prefix, no length, no last-4.
**Rationale:**
- A Bearer-token-protected endpoint that returns `sk-ant-...xyz` to a logged-in admin is a credential-exfiltration path the moment that token leaks via browser history, screenshot, or shared screen-record. Boolean carries the only signal Mark needs for cold-start ("is it set?") with zero leak risk.
- Symmetry with the design SSOT §16 wireframe `[●●●●●●● 已設定]` — UI shows masked dots regardless; payload should match.

**Alternatives considered:**
- *Return last-4 chars.* Rejected — partial values still leak entropy and don't help diagnose anything in this UI.
- *Return SHA-256 fingerprint.* Rejected — useful for verifying rotations, but no UI consumer for it; YAGNI.

### D3: 4-section grouping mirrors `docs/web-admin-page-designs.md` §16
**Choice:** Response shape is `{api_keys, theme, safety, breakers}`. Frontend renders each as a separate `Card`.
**Rationale:** SSOT for the page already groups this way; keeping the wire format aligned with the visual layout simplifies the frontend (no client-side regrouping) and matches Mark's mental model from the design doc.

### D4: `theme.mode` is a constant placeholder
**Choice:** Always returns `"system"`. No env binding, no DB persistence.
**Rationale:** `docs/web-admin-page-designs.md` §16 explicitly defers theme switch UI. Hardcoding the response now means the field exists in the contract from day one, so the future "add theme switching" change is a pure additive — no frontend re-shaping when we wire it.

### D5: Safety colour switching is a frontend concern
**Choice:** Backend returns raw `auto_execute: bool`; frontend computes whether to render the warning vs. destructive variant.
**Rationale:** Avoids putting presentation hints (`severity: "warning"`) in the API. Same pattern as `/paper` — backend ships data, frontend ships colour.

## Risks / Trade-offs

- **[Risk]** Hardcoded `theme.mode = "system"` becomes stale if a future change adds real theme persistence and forgets to update the redactor. **Mitigation:** When that change ships, it MUST update both the endpoint response and the SSOT row; the spec scenario locks the current behaviour so a regression test will fire.
- **[Risk]** Adding a new safety field to `config.py` (e.g. a 6th breaker) won't appear in `/settings` automatically — the redactor whitelists fields. **Mitigation:** Acceptable. The redactor MUST be a whitelist, not a `.dict()` dump, exactly to prevent accidentally leaking new fields. Adding fields to `/settings` is a small follow-up.
- **[Trade-off]** No PUT means Mark must SSH + edit `.env` + restart to flip `OHMYSTOCK_AUTO_EXECUTE`. This is intentional friction — the existing model is already correct; we're adding visibility, not editability.
