# capability-map — 已 ship capability → spec + impl

每筆都是一次 `/opsx:apply` + `/opsx:archive` 的成果。完整內文在對應 `openspec/changes/archive/<slug>/` 目錄。

> 想知道「目前最新狀態」、「還有什麼沒 ship」：`ls openspec/changes/archive/ | sort` + `git log --oneline -20`。本表是已 ship 索引，不含 in-progress。

## 索引（依 archive 日期）

| Capability | 主要 spec + impl |
|---|---|
| Scaffold / CLI skeleton / FastAPI bootstrap | `archive/2026-04-27-*` / `archive/2026-04-28-fastapi-bootstrap` |
| External connectors（FinMind/Shioaji/Anthropic）+ cost tracker | `archive/2026-04-29-external-connectors-and-cost` |
| Market data fetch + cache、Chip data、Technical indicators、SEPA trend template + stage、Screener | `archive/2026-04-30-*` |
| Live providers（freshness policy / error codes） | `archive/2026-05-01-live-providers` + `openspec/specs/live-providers/spec.md` |
| Phase 2B Swarm Input Assembler + scoring engine + SEPA subscorers | `archive/2026-05-01-phase-2b-*` + `src/ohmystock/scoring/` |
| Entry Decider PM node + §2.1 系統覆寫驗證 | `archive/2026-05-02-entry-decider-pm-node` + `src/ohmystock/decider/validator.py` |
| Confirm Gate v0（human-only confirm/reject/sweep_expired/list_pending） | `archive/2026-05-02-confirm-gate-v0` + `src/ohmystock/safety/confirm_gate.py` |
| Exit Engine v0（daily, full-position close on stop_loss/T1/time_stop） | `archive/2026-05-02-exit-engine-v0` + `src/ohmystock/exit_engine/evaluator.py` |
| Auto-execute Phase 3.5（5 hard breakers + sizing clamp） | `archive/2026-05-02-auto-execute-toggle-and-breakers` + `src/ohmystock/safety/auto_execute.py` + `OHMYSTOCK_AUTO_EXECUTE_*` 於 `src/ohmystock/config.py` |
| EventBus emitters v0（9 of 21 event_type wired + AdminEventSerializer） | `archive/2026-05-02-eventbus-emitters-v0` + `src/ohmystock/eventbus/` |
| Server action endpoints v0（6 admin write endpoints + envelope） | `archive/2026-05-02-server-action-endpoints-v0` + `src/ohmystock/api/routes/` |
| Read-side admin endpoints v0（journal/positions/stats） | `archive/2026-05-03-read-side-admin-endpoints-v0` + `src/ohmystock/api/routes/{journal,positions,stats}.py` |
| web-admin Bearer auth gate（`OHMYSTOCK_ADMIN_TOKEN` ≥ 32 chars） | `archive/2026-05-03-web-admin-bearer-auth-v0` + `src/ohmystock/api/auth.py` |
| RS-percentile skill + FinMind wiring | `archive/2026-05-06-rs-percentile-skill` + `archive/2026-05-07-rs-percentile-finmind-wiring` + `src/ohmystock/sepa/rs.py` |
| web-admin shell + auth（Vite 8 + React 19 + TS 6 + Tailwind v4 + Bearer lifecycle + 紅漲綠跌 semantic tokens） | `archive/2026-05-07-web-admin-shell-and-auth` + `web-admin/src/` |
| web-admin design system + 23 頁 wireframes | `archive/2026-05-08-web-admin-design-system-and-page-wireframes` + `docs/web-admin-page-designs.md` |
| web-admin Market / Backtest / Settings / Paper / Audit pages | `archive/2026-05-08-web-admin-*` + `src/ohmystock/api/routes/{market,backtest,settings}.py` + `web-admin/src/pages/` |
| Skill Registry foundation + web-admin Skills pages（10 seed） | `archive/2026-05-09-skill-registry-foundation` + `archive/2026-05-09-web-admin-skills-pages` + `src/ohmystock/skills/` |
| Memory store + admin-memory-endpoints + web-admin Memory page（FTS5 BM25） | `archive/2026-05-09-web-admin-memory-page-and-store` + `src/ohmystock/memory/` |
| Phase 5 review pipeline v0（5-node sequential runner + `_index.json` + `report.md`） | `archive/2026-05-10-phase5-review-mvp` + `src/ohmystock/review/` |
| Proposal markdown writer + state machine（5 status edges + 自動搬檔 + atomic write） | `archive/2026-05-10-proposal-state-machine` + `src/ohmystock/proposal/` |
| Admin proposals endpoints + pages | `archive/2026-05-10-admin-proposals-endpoints-and-pages` + `src/ohmystock/api/routes/proposals.py` + `web-admin/src/pages/Proposal*.tsx` |
| WFA validation engine（`run_validation` 純決定性閘） | `archive/2026-05-13-wfa-validation-engine` + `src/ohmystock/validation/` + `src/ohmystock/cli/_validate_proposal.py` |
| Admin proposal validate action（`POST .../validate` + `<ValidationDialog>`） | `archive/2026-05-13-admin-proposal-validate-action` + `src/ohmystock/api/routes/proposals.py` + `web-admin/src/components/validation-dialog.tsx` |
| Admin reviews endpoints + pages | `archive/2026-05-13-admin-reviews-endpoints-and-pages` + `web-admin/src/pages/Reviews*.tsx` |
| Admin swarm endpoints + pages + EventType 16→21 | `archive/2026-05-13-admin-swarm-endpoints-and-pages` + `src/ohmystock/swarm_runs/` + `web-admin/src/pages/Swarm*.tsx` |
| Admin chat sessions endpoints + pages（single-agent chat runtime） | `archive/2026-05-15-admin-chat-sessions-endpoints-and-pages` + `src/ohmystock/chat/` + `web-admin/src/pages/ChatSession*.tsx` |
| Public SSE channel + masked serializer + web-public shell | `archive/2026-05-15-web-public-shell-and-mask` + `src/ohmystock/eventbus/{mask_table,serializers}.py` + `src/ohmystock/api/routes/public_events.py` + `web-public/` |
| web-public Pixel 辦公室 MVP（Canvas 2D Gen 2 / 13 chars / SSE → action / palette / mask defense） | `archive/2026-05-21-web-public-pixel-office-mvp` + `web-public/src/{canvas,components,hooks,lib,locales,pages,stores,styles,types}/` + `openspec/specs/web-public-pixel-office/spec.md` |
