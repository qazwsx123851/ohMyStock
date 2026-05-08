# CLAUDE.md — ohMyStock 專案指引

> 給 LLM Agent 開新對話時的快速上手。詳細規格請依下方索引到 `docs/` 找。

---

## 1. 專案簡介

**ohMyStock** 是台股 AI 交易代理人 — 從選股、進場、出場到復盤改進，全流程由 LLM 自主完成的個人專案。

- **性質**：solo developer + LLM 協作的個人專案（**非** 團隊 / 企業 / SaaS）
- **使用者**：單一用戶本機 localhost
- **市場**：台灣證交所（TWSE）/ 櫃買中心（OTC）
- **執行範圍**：Paper Trading（永豐 Shioaji 模擬倉，**第一階段不接實單**）
- **階段**：Spec / Pre-implementation（設計文件完成，原始碼待開工）
- **目標**：~20 週至 MVP（v3，含 LLM 復盤閉環），預計 2026-09-15 完成

### 解決什麼問題
1. 台股研究流程仰賴人工拼接資料源（技術 / 基本 / 籌碼 / 三大法人）
2. 既有對岸 / 美股交易代理（Vibe-Trading、FinGPT）不支援台股市場結構
3. 散戶需要可重現、可回測、可審計的策略開發流程

---

## 2. 給 LLM 的協作原則（重要）

- **避免過度工程**：不要建議 CI lint、自動 schema sync 測試、跨團隊 owner table、合規部門角色分離。
- **拆檔動機**：主要是「LLM 讀單檔太貴 / 自己找東西要快」，**不是**「合規分權」。
- **單一權威 (SSOT)**：個人專案最怕「自己改一處忘另一處」，公式 / schema 重複是首要問題；改公式請只改 §5 表中「唯一權威」一欄。
- **不為 hypothetical 團隊規模設計**：目錄、流程、角色分離保持精簡。

---

## 3. 技術棧

| 層 | 選用 |
|---|---|
| Backend | Python 3.11+、Claude Agent SDK（**不用 LangChain**）、FastAPI |
| Frontend | React 19 + Vite + TypeScript + Tailwind + shadcn/ui |
| Storage | SQLite + FTS5（trade journal、memory、復盤索引） |
| Broker | 永豐金證券 Shioaji 模擬倉 |
| Data | FinMind 贊助會員 + Shioaji 即時報價 + twstock / yfinance fallback |
| LLM | Opus 4.7（關鍵決策）+ Sonnet 4.6（分析）+ Haiku 4.5（規則） |
| Deploy | Docker Compose（本機開發為主） |

預期 LLM API 月成本：USD ~$31–36（啟用 prompt cache + batch API 可降至 ~$20）。

---

## 4. 架構總覽

```
UI 層
  ├─ web-admin/   React 18 頁工作介面（Bearer token，僅本人）
  └─ web-public/  React + Canvas 2D 像素辦公室（公網、masked）
       ▲
       │ /api/admin/events (auth, raw)  /api/public/events (no auth, masked)
       │
Backend EventBus（asyncio Queue pub/sub）
  ├─ AdminEventSerializer  → 全資料
  └─ MaskedEventSerializer → 嚴格白名單
       ▲
       │ bus.emit(event)
       │
Agent 核心層（Claude Agent SDK + PreToolUse/PostToolUse Hooks 稽核）
  └─ LLM Decider Pipeline (v3)
       訊號 → entry_decision_team swarm
       → 系統覆寫（Sizing / ATR 停損 / Risk Gate）
       → Confirm Gate（OHMYSTOCK_AUTO_EXECUTE 切換）
       → 寫 Trade Journal + 送 Broker
  └─ Skills (~30) + Tools (~20) + Services
       Backtest / Paper Broker / Memory + FTS5 / Swarm DAG
       Trade Journal / Post-Trade Review / Proposal Validation
  └─ 資料層（FinMind / Shioaji / twstock / yfinance）
```

### 前後台兩專案 monorepo（v3 決策 #13）
- **`web-admin/`** — Bearer token auth；本機 / Cloudflare Tunnel；可看真 symbol/price/pnl
- **`web-public/`** — 無認證；公網（Vercel / Cloudflare Pages）；MaskedEventSerializer 強制 strip 敏感欄
- **`packages/`** — 共用 ui-tokens / api-types / event-types / api-client-public

### 自我改進閉環（v3 核心）
```
訊號偵測 → LLM 進場決策 + 倉位計算 → 結構化 Trade Journal
       → LLM 月度復盤五節點 swarm → LLM 出策略改動提案
       → WFA 樣本外驗證 → 人工 PR review
       → 合併回 cheatsheet → 下一輪生效
```

### 9 條安全防線
含 LLM 自動下單熔斷（confidence 0.7 / 單日 5 筆 / 25% 配額 / 30% 偏離等）；詳見 `docs/safety-and-simulation.md` §2.9。

---

## 5. 公式 / Schema 唯一權威表（避免 solo dev 改一處忘另一處）

| 主題 | 唯一權威 |
|---|---|
| Volatility Targeting sizing 公式 | `docs/workflow-cheatsheet.md` §6.6 |
| ATR 停損公式 | `docs/workflow-cheatsheet.md` §6.6 |
| Trade Journal schema | `docs/llm-decision-schema.md` §4 |
| Trade Journal 衍生欄位 | `docs/llm-decision-schema.md` §4.5 |
| LLM Decider 輸出約束 | `docs/llm-decision-schema.md` §2.1 |
| Phase 5 五節點 DAG 評分 | `docs/post-trade-review-rubric.md` §0–§5 |
| Risk-Off 觸發條件 | `docs/workflow-cheatsheet.md` §0 |
| K 線型態庫 | `docs/workflow-cheatsheet.md` §9 |
| 21 個 Tool 的 I/O schema | `docs/tools-contracts.md` |
| Auto-execute breaker 閾值 | `docs/safety-and-simulation.md` §2.9 |
| Phase 2B Swarm Input Assembler | `docs/design-zh-TW.md` §4.7.0 |
| Live provider error codes / freshness policy | `openspec/specs/live-providers/spec.md` |
| LLM Decider PM 節點 + §2.1 系統覆寫驗證 | `openspec/specs/entry-decider/spec.md`（archive 後）+ `src/ohmystock/decider/validator.py` |
| Confirm Gate v0 行為（human-only：confirm/reject/sweep_expired/list_pending）| `openspec/specs/confirm-gate/spec.md`（archive 後）+ `src/ohmystock/safety/confirm_gate.py` |
| Exit Engine v0 行為（daily, full-position close on stop_loss/T1/time_stop）| `openspec/specs/exit-engine/spec.md`（archive 後）+ `src/ohmystock/exit_engine/evaluator.py` |
| Auto-execute Phase 3.5 — breaker thresholds + audit row format（5 hard breakers + sizing clamp + flag/live defense-in-depth）| `openspec/specs/auto-execute/spec.md`（archive 後）+ `src/ohmystock/safety/auto_execute.py` + `OHMYSTOCK_AUTO_EXECUTE_*` 於 `src/ohmystock/config.py` |
| EventBus emitters v0 — 9 of 16 event_type wired (screener / decider / confirm-gate / journal / auto-execute) + AdminEventSerializer + admin SSE subscriber | `openspec/specs/eventbus-emitters/spec.md`（archive 後）+ `src/ohmystock/eventbus/` + `src/ohmystock/api/app.py` |
| Server action endpoints v0 — 6 admin write endpoints (screener.run / confirm-gate.{pending,confirm,reject,sweep-expired} / exit-engine.run) + unified `{ok,data,error}` envelope + per-request DB conn + no-auth invariant | `openspec/specs/server-action-endpoints/spec.md`（archive 後）+ `src/ohmystock/api/routes/` + `src/ohmystock/api/app.py` |
| web-admin Bearer auth gate — `OHMYSTOCK_ADMIN_TOKEN` ≥ 32 chars, fail-fast in `create_app()`, `require_admin` dep on every `/api/admin/*` route (REST + SSE), `AuthError` → 401 envelope (`auth_missing` / `auth_invalid`), `secrets.compare_digest` constant-time check; `/healthz` exempt | `openspec/specs/web-admin-bearer-auth/spec.md`（archive 後）+ `src/ohmystock/api/auth.py` + `OHMYSTOCK_ADMIN_TOKEN` 於 `src/ohmystock/config.py` |
| Admin read endpoints v0 — 4 GET endpoints (`journal/rows` paginated + filters, `journal/decisions/{id}` ASC ordering, `positions/open` reuses `journal.repository.open_positions`, `stats/today` single SQL aggregate over TPE day) + sub-500 limit clamp + nested-dict payload + same envelope/auth/per-request-conn invariants as write endpoints | `openspec/specs/admin-read-endpoints/spec.md`（archive 後）+ `src/ohmystock/api/routes/{journal,positions,stats}.py` + `src/ohmystock/api/app.py` |
| RS-percentile production wiring — universe-closes loader (`build_universe_closes_loader` reads `universe_daily` + `bars_daily` via `select_bars`; ≥253-row floor; no `FinMindClient` calls) + `disposition_list_cache` schema + `fetch_disposition_set` stub (cache-hit returns set, miss returns `set()`, never raises; live TWSE/OTC scrape deferred to `rs-percentile-disposition-scrape-impl`) + `_lifespan` startup wiring in `api/app.py` + `scripts/backfill_rs_rating.py` (`--days N` default 252, business-day walk Mon–Fri, idempotent re-run, `>= N*100` row-count floor → exit 1 on miss) | `openspec/specs/rs-percentile/spec.md`（archive 後）+ `src/ohmystock/sepa/rs.py` + `src/ohmystock/sepa/rs_loader.py` + `src/ohmystock/data/disposition.py` + `scripts/backfill_rs_rating.py` |
| web-admin shell — Vite 8 + React 19 + TS 6 + Tailwind v4 (zinc) + shadcn `components.json` (no CLI run) + Bearer auth lifecycle (`localStorage['ohmystock.admin.token']`, login/logout/auto-401) + `apiFetch` with `{ok,data,error}` envelope parsing + fetch-based SSE (`Authorization` header) with `[1s,2s,4s,8s,30s]` backoff and 401-abort + 18-route tree (Dashboard real, 17 stubs in `pages/stubs.tsx`) + Sidebar/TopBar/Disclaimer layout + 紅漲綠跌 semantic tokens (`--up`/`--down`/`--destructive`/`--warning`) paired with Lucide arrow glyphs (color is never the only signal) + Vite dev proxy `/api` → `localhost:8000` | `openspec/specs/web-admin-shell/spec.md`（archive 後）+ `web-admin/src/` |
| web-admin 17 頁面視覺契約（layout slots / loading-empty-error / SSE live-update / 紅漲綠跌雙重編碼 / 鍵盤可達性）— SSOT for `/chat` `/chat/:sessionId` `/swarm` `/swarm/:preset/:runId` `/backtest` `/backtest/:jobId` `/paper` `/paper/orders` `/paper/positions` `/market` `/market/:symbol` `/skills` `/skills/:name` `/memory` `/sessions` `/settings` `/audit`；後續 per-page changes 必須引用本檔對應 section 為 implementation brief | `docs/web-admin-page-designs.md` |
| web-admin Market pages — `/market` (filter form + screener.run + 6-col `<DataTable>` + SSE `pattern_detected` prepend + 5-row live feed) and `/market/:symbol` (header quote + K-line placeholder Card + 3 KPI cards + 三大法人 5x5 + Patterns 4-col table) + `GET /api/admin/market/symbols/{symbol}` aggregator (60-day default, ≤252 cap, fail-soft `null`/`[]`, 404 only on missing `bars_daily`) + 紅漲綠跌 dual-encoding（colour + Lucide arrow） | `openspec/specs/web-admin-market-pages/spec.md`（archive 後）+ `openspec/specs/admin-market-symbol-endpoint/spec.md`（archive 後）+ `src/ohmystock/api/routes/market.py` + `web-admin/src/pages/MarketPage.tsx` + `web-admin/src/pages/MarketSymbolPage.tsx` + `web-admin/src/lib/api.ts` (`getMarketSymbol` / `runScreener`) |
| web-admin Backtest pages — `/backtest` (strategy `<select>` populated from `listStrategies` + chip-input symbols + 2 date inputs + initial-capital + Cmd/Ctrl+Enter + 8-col history `<DataTable>` with 紅漲綠跌 on 年化/Sharpe/MaxDD, failed rows show `—`) and `/backtest/:jobId` (header + 4 `<KpiCard>` (年化/Sharpe/MaxDD/勝率) + labelled equity/drawdown placeholder Cards (no chart lib) + 7-col trades table + 404/error/failed-degraded states) + 4 endpoints under `/api/admin/backtest/*` (Bearer auth, `{ok,data,error}` envelope, per-request `Depends(get_db)`): `GET /strategies` (registry-driven), `POST /run` (sync; 1–50 symbols / period ≤ 5y / `invalid_input`/`input_too_large`/`missing_bars`; persists row even on engine failure with status="failed"), `GET /jobs?limit=N` (clamp 1..100, ORDER BY created_at DESC, no `result_json` leak), `GET /jobs/{id}` (FIFO trade pairing + on-the-fly drawdown derivation; 404 `not_found`) + `backtest_jobs` SQLite table (id PK / strategy / period / custom_symbols_json / initial_capital / status enum / elapsed_ms / result_json / created_at) | `openspec/specs/web-admin-backtest-pages/spec.md`（archive 後）+ `openspec/specs/admin-backtest-endpoints/spec.md`（archive 後）+ `src/ohmystock/api/routes/backtest.py` + `src/ohmystock/backtest/storage.py` + `src/ohmystock/backtest/strategy/registry.py` + `web-admin/src/pages/BacktestPage.tsx` + `web-admin/src/pages/BacktestJobPage.tsx` + `web-admin/src/lib/api.ts` (`runBacktest` / `listBacktestJobs` / `getBacktestJob` / `listStrategies`) |
| web-admin Settings page (read-only v0) — `/settings` 4-section view (API keys / Theme / Safety / Breakers) + Bearer-auth `GET /api/admin/settings`；secrets 一律以布林呈現（無前綴、無長度、無 hash）+ 白名單 redactor（**不是** `model_dump`，新增 `Settings` 欄位不會自動洩漏）+ Safety 區紅漲綠跌雙重編碼（`auto_execute=false` → `border-warning` + `AlertTriangle`；`auto_execute=true` → `border-destructive` + `AlertCircle` + 「⚠ AUTO_EXECUTE 已啟用」banner）+ 全頁 disabled 控制 + 「編輯 .env 並重啟以變更」hint；no PUT, no `.env` writeback, no theme switcher（皆為意圖性 deferred — `OHMYSTOCK_AUTO_EXECUTE` 仍以 `.env` + restart 為唯一改動路徑） | `openspec/specs/web-admin-settings-page/spec.md`（archive 後）+ `openspec/specs/admin-settings-endpoint/spec.md`（archive 後）+ `src/ohmystock/api/routes/settings.py` + `web-admin/src/pages/SettingsPage.tsx` + `web-admin/src/lib/api.ts` (`getSettings`) |
| Skill Registry foundation — `SkillSpec`（pydantic frozen + `extra="forbid"`，欄位 `name` / `description` / `category` (7-value `Literal`) / `body` / `cited_specs`）+ filesystem loader（`load_skills(dir)` / `load_skill(dir, name)`，YAML frontmatter + Markdown body，fail-loud `SkillLoadError`）+ name=stem 強制不變式 + path-traversal 防禦（`/`, `\`, `..` 進 `name` → `SkillLoadError("invalid skill name")`，BEFORE I/O）+ 10 個 seed skill 對應已部署 capability（market-data / chip-data / technical-indicators / rs-percentile / sepa-stage / sepa-trend-template / screener / phase-2b-scoring / entry-decider / exit-engine）；本 change 無 admin endpoint、無 UI、無 enabled toggle，皆為後續 `web-admin-skills-pages` 的前置 | `openspec/specs/skill-registry/spec.md`（archive 後）+ `src/ohmystock/skills/spec.py` + `src/ohmystock/skills/loader.py` + `src/ohmystock/skills/__init__.py` + `src/ohmystock/skills/registry/<10 .md>` |

完整版（含「不要在這裡改」欄位）見 `docs/README.md` §2。

---

## 6. 文件索引

### 入口
- **`README.md`** — GitHub 首頁（專案狀態、特色、架構、路線圖、免責）
- **`docs/README.md`** — 文件導覽，**任何 LLM Agent 開新對話應先讀這個**

### 核心設計（`docs/`）
| 檔案 | 用途 |
|---|---|
| `design-zh-TW.md` | 架構、模組、Tools/Skills/Memory/Backend、目錄結構、路線圖、風險登記（核心大檔） |
| `workflow-cheatsheet.md` | **交易業務邏輯 SSOT** — Phase 0–5 + §16 提案閘 + §17 文件關係表 |
| `safety-and-simulation.md` | Live/Sim 防線 9 層 + verify_simulation + 對賬機制 |
| `llm-decision-schema.md` | LLM Decider I/O JSON 規格 + Trade Journal schema（FTS5）|
| `post-trade-review-rubric.md` | Phase 5 五節點 DAG（data → attribution → aggregator → critic → proposer）評分準則 |
| `tools-contracts.md` | 21 個 `@register_tool` 工具 I/O schema 唯一權威 |
| `v3-decisions.md` | v3 已拍板決策（13 項）+ 預算追蹤 + 個人 milestone |
| `user-scenarios.md` | **Operator workflow** — Mark 在 admin 18 頁的 10 個使用情境（日 / 週 / 月 / 異常 / cold start） |

### 前端 / EventBus（v3 新增）
| 檔案 | 用途 |
|---|---|
| `frontend.md` | **後台 web-admin/** 18 頁 wireframes、路由、Zustand、design tokens |
| `frontend-public-pixel.md` | **公網 web-public/** Pixel 像素辦公室 UI、9 角色 sprite、動畫狀態機 |
| `backend-eventbus.md` | EventBus 架構 + Event Schema + Admin/Masked Serializer + 14 個 event_type |
| `auth-and-mask.md` | Bearer token auth、Mask Spec 白名單、SITC 合規策略、部署拓樸 |

### 子系統規範
- **`proposals/README.md`** — 策略改動提案（命名、frontmatter、WFA 驗證、merge 流程）
- **`reviews/README.md`** — LLM 復盤輸出（五節點 schema、_index.json）
- **`openspec/`** — OpenSpec 配置（搭配 `opsx:*` skills 使用）

---

## 7. 任務 → 該讀哪個檔（快速指引）

- 「為什麼這樣設計？」→ `docs/design-zh-TW.md` §1–§3
- 「該怎麼選股 / 進場 / 出場？」→ `docs/workflow-cheatsheet.md`（**business logic SSOT**）
- 「LLM 該輸出什麼 JSON？」→ `docs/llm-decision-schema.md` §1–§3
- 「Phase 5 復盤節點怎麼評分？」→ `docs/post-trade-review-rubric.md`
- 「live trading 安全防線是什麼？」→ `docs/safety-and-simulation.md`
- 「**後台**怎麼寫？」→ `docs/frontend.md`（web-admin/ 範圍）
- 「**公網前台** pixel 辦公室？」→ `docs/frontend-public-pixel.md`
- 「Backend 怎麼推 event 給前端？」→ `docs/backend-eventbus.md`
- 「公網要 mask 哪些欄位？admin auth 怎麼設？」→ `docs/auth-and-mask.md`
- 「`market_data_tool` 怎麼呼叫？」→ `docs/tools-contracts.md`
- 「v3 已拍板決策 / 預算 / milestone？」→ `docs/v3-decisions.md`
- 「台股市場細節（T+2、漲跌停、當沖稅）」→ `docs/design-zh-TW.md` §4.4.1
- 「Mark 平常怎麼用這套系統？admin 18 頁怎麼串？」→ `docs/user-scenarios.md`

---

## 8. 路線圖（簡）

| Phase | 範圍 | 預計完成 |
|---|---|---|
| 0 | Scaffold（環境、CLI 骨架、FastAPI、Shioaji+FinMind+Anthropic 三方連線、cost tracker） | 2026-05-12 |
| 1 | 技術 / 籌碼面 Skills + 回測引擎 | 2026-05-26 |
| 2 | Screener + 訊號偵測 + Phase 2B Swarm Input Assembler | 2026-06-16 |
| 3 | LLM Decider + Confirm Gate + Trade Journal v3 | 2026-07-07 |
| 3.5 | `OHMYSTOCK_AUTO_EXECUTE` 雙模式 + 9 條安全防線 | 2026-07-28 |
| 4 | web-admin（18 頁）+ Bearer auth（2 週） | 2026-08-11 |
| 4.5 | web-public pixel + Mask serializer + E2E 滲透測試（2 週，admin ship 後啟動） | 2026-08-25 |
| 5 | LLM 復盤五節點 swarm + 提案 → WFA → 合併閉環（含模擬 1 週緩衝） | 2026-09-15 |

---

## 9. 授權

[MIT License](LICENSE) © 2026 MarkSu
