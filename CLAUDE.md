# CLAUDE.md — ohMyStock 專案指引

> 給 LLM Agent 開新對話時的快速上手。詳細規格請依下方索引到 `docs/` 或 `openspec/changes/archive/` 找。

---

## 1. 專案簡介

**ohMyStock** 是台股 AI 交易代理人 — 從選股、進場、出場到復盤改進，全流程由 LLM 自主完成的個人專案。

- **性質**：solo developer + LLM 協作的個人專案（**非** 團隊 / 企業 / SaaS）
- **使用者**：單一用戶本機 localhost（admin）+ 公網匿名訪客（masked feed）
- **市場**：台灣證交所（TWSE）/ 櫃買中心（OTC）
- **執行範圍**：Paper Trading（永豐 Shioaji 模擬倉，**第一階段不接實單**）
- **目前狀態**（2026-05-18）：Phase 4 / 5 mid-implementation
  - Phase 0 – 3.5 已完成（scaffold、回測、訊號、Decider、Confirm Gate、Auto-execute 9 條防線）
  - Phase 4 web-admin 全 23 頁實作完成（無 stub）
  - Phase 4.5 web-public shell + masked SSE 已完成；Canvas 2D 像素辦公室 deferred
  - Phase 5 review pipeline + proposal writer + state machine + WFA validator + admin proposals/reviews endpoints 已完成；reviews UI 與月度自動觸發 deferred
- **目標**：~20 週至 MVP（v3，含 LLM 復盤閉環），2026-09-15 完成

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
- **直接 push main**：solo dev 不開 PR，commit 完直接 push origin main。
- **OpenSpec 流程**：每個新 capability 開一個 `openspec/changes/<slug>/`（proposal + design + tasks + specs），完工後 `/opsx:archive` 搬到 `openspec/changes/archive/`，這是 capability 級別的歷史紀錄。

---

## 3. 技術棧

| 層 | 選用 |
|---|---|
| Backend | Python 3.11+、Claude Agent SDK（**不用 LangChain**）、FastAPI |
| Frontend | React 19 + Vite + TypeScript + Tailwind + shadcn/ui |
| Storage | SQLite + FTS5（trade journal、memory、chat sessions、復盤索引、backtest jobs、swarm runs） |
| Broker | 永豐金證券 Shioaji 模擬倉 |
| Data | FinMind 贊助會員 + Shioaji 即時報價 + twstock / yfinance fallback |
| LLM | Opus 4.7（關鍵決策）+ Sonnet 4.6（分析）+ Haiku 4.5（規則） |
| Deploy | Docker Compose（本機開發為主） |

預期 LLM API 月成本：USD ~$31–36（啟用 prompt cache + batch API 可降至 ~$20）。

---

## 4. 架構總覽

由上而下分四層：

**UI 層**
- `web-admin/`（React 19 + Vite + Tailwind v4 + shadcn）：23 頁工作介面，全部需 Bearer token；本機或 Cloudflare Tunnel 連線；可看真實 symbol / price / pnl。
- `web-public/`（React 19 + Vite + Tailwind v4，standalone Vite project，無 shadcn 無 Radix）：免認證；公網部署（Vercel / Cloudflare Pages）；只看得到 masked 後的事件流；Canvas 2D 像素辦公室為下一個 change。

**API / SSE 層**
- `/api/admin/*` — Bearer-auth REST + SSE，envelope 一律 `{ok, data, error}`，per-request `Depends(get_db)`，401 envelope `auth_missing` / `auth_invalid`。
- `/api/public/events` — 無認證 SSE，由 `MaskedEventSerializer` strict-whitelist 過濾（13 欄 denylist + 16 event_type 白名單 + 4-digit code → `STK-?` 替換 + `SymbolMaskTable` 把真實 symbol 換成 `STK-A..STK-Z..STK-AA`）。
- `/healthz` — 唯一免認證 admin-side endpoint。

**EventBus**
- asyncio Queue pub/sub，process-scoped。
- 21 個 `EventType`（screener / decider / confirm-gate / journal / auto-execute / swarm 5 種）。
- 雙 serializer：`AdminEventSerializer`（全資料）/ `MaskedEventSerializer`（嚴格白名單）。

**Agent 核心**
- LLM Decider Pipeline（v3）：訊號 → `entry_decision_team` swarm → 系統覆寫（Sizing / ATR 停損 / Risk Gate）→ Confirm Gate（`OHMYSTOCK_AUTO_EXECUTE` 切換）→ 寫 Trade Journal + 送 Broker。
- Skills（~10 seed registry + 仍在擴充）+ Tools（21 個 `@register_tool`）+ Services（Backtest / Paper Broker / Memory + FTS5 / Swarm DAG / Trade Journal / Post-Trade Review / Proposal Writer / WFA Validator）。
- 資料層：FinMind / Shioaji / twstock / yfinance（fallback chain）。

### 自我改進閉環（v3 核心）
1. 訊號偵測 → LLM 進場決策 + 倉位計算
2. 結構化 Trade Journal 寫入（SQLite + FTS5）
3. LLM 月度復盤 5 節點 swarm（`data_loader` → `attributor` → `aggregator` → `critic` → `proposer`）
4. LLM 出策略改動提案（`proposals/<YYYY-MM-DD>-<topic>.md`）
5. WFA 樣本外驗證（pass → `PENDING_REVIEW/`、fail → `rejected/`、人工 approve 後 → `merged/`）
6. 合併回 cheatsheet → 下一輪生效

### 9 條安全防線
LLM 自動下單熔斷（confidence 0.7 / 單日 5 筆 / 25% 配額 / 30% 偏離等）；詳見 `docs/safety-and-simulation.md` §2.9 與 `src/ohmystock/safety/auto_execute.py`。

---

## 5. SSOT 唯一權威表

改公式或 schema 請只改下方對應檔；多處出現會在這裡用 `[[duplicated]]` 標註。

### 5.1 業務邏輯 / Schema SSOT（思考時優先讀）

| 主題 | 唯一權威 |
|---|---|
| Volatility Targeting sizing 公式 | `docs/workflow-cheatsheet.md` §6.6 |
| ATR 停損公式 | `docs/workflow-cheatsheet.md` §6.6 |
| Risk-Off 觸發條件 | `docs/workflow-cheatsheet.md` §0 |
| K 線型態庫 | `docs/workflow-cheatsheet.md` §9 |
| Phase 2B Swarm Input Assembler | `docs/design-zh-TW.md` §4.7.0 |
| Trade Journal schema | `docs/llm-decision-schema.md` §4 |
| Trade Journal 衍生欄位 | `docs/llm-decision-schema.md` §4.5 |
| LLM Decider 輸出約束 | `docs/llm-decision-schema.md` §2.1 |
| Phase 5 五節點 DAG 評分 | `docs/post-trade-review-rubric.md` §0–§5 |
| 21 個 Tool 的 I/O schema | `docs/tools-contracts.md` |
| Auto-execute breaker 閾值 | `docs/safety-and-simulation.md` §2.9 |
| Live provider error codes / freshness policy | `openspec/specs/live-providers/spec.md` |
| web-admin 23 頁面視覺契約 | `docs/web-admin-page-designs.md` |

### 5.2 已 ship capability → 對應 spec + impl 路徑

每筆都是一次 `/opsx:apply` + `/opsx:archive` 的成果。完整內文在對應 archive 目錄。

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
| RS-percentile skill + FinMind wiring（universe-closes loader + disposition stub） | `archive/2026-05-06-rs-percentile-skill` + `archive/2026-05-07-rs-percentile-finmind-wiring` + `src/ohmystock/sepa/rs.py` |
| web-admin shell + auth（Vite 8 + React 19 + TS 6 + Tailwind v4 + Bearer auth lifecycle + 紅漲綠跌 semantic tokens） | `archive/2026-05-07-web-admin-shell-and-auth` + `web-admin/src/` |
| web-admin design system + 23 頁 wireframes | `archive/2026-05-08-web-admin-design-system-and-page-wireframes` + `docs/web-admin-page-designs.md` |
| web-admin Market pages + Backtest pages + Settings page + Paper overview/orders/positions + Audit page | `archive/2026-05-08-web-admin-*` + `src/ohmystock/api/routes/{market,backtest,settings}.py` + 對應 `web-admin/src/pages/` |
| Skill Registry foundation + web-admin Skills pages（10 seed skills） | `archive/2026-05-09-skill-registry-foundation` + `archive/2026-05-09-web-admin-skills-pages` + `src/ohmystock/skills/` |
| Memory store + admin-memory-endpoints + web-admin Memory page（FTS5 BM25） | `archive/2026-05-09-web-admin-memory-page-and-store` + `src/ohmystock/memory/` |
| Phase 5 review pipeline v0（5-node sequential runner + `_index.json` + `report.md`） | `archive/2026-05-10-phase5-review-mvp` + `src/ohmystock/review/` |
| Proposal markdown writer + state machine（5 status edges + 自動搬檔 + atomic write） | `archive/2026-05-10-proposal-state-machine` + `src/ohmystock/proposal/` |
| Admin proposals endpoints + pages（list/detail/transition） | `archive/2026-05-10-admin-proposals-endpoints-and-pages` + `src/ohmystock/api/routes/proposals.py` + `web-admin/src/pages/Proposal*.tsx` |
| WFA validation engine（`run_validation` 純決定性閘） | `archive/2026-05-13-wfa-validation-engine` + `src/ohmystock/validation/` + `src/ohmystock/cli/_validate_proposal.py` |
| Admin proposal validate action（`POST .../validate` + `<ValidationDialog>`） | `archive/2026-05-13-admin-proposal-validate-action` + `src/ohmystock/api/routes/proposals.py` + `web-admin/src/components/validation-dialog.tsx` |
| Admin reviews endpoints + pages | `archive/2026-05-13-admin-reviews-endpoints-and-pages` + `web-admin/src/pages/Reviews*.tsx` |
| Admin swarm endpoints + pages + EventType 16→21 | `archive/2026-05-13-admin-swarm-endpoints-and-pages` + `src/ohmystock/swarm_runs/` + `web-admin/src/pages/Swarm*.tsx` |
| Admin chat sessions endpoints + pages（single-agent chat runtime） | `archive/2026-05-15-admin-chat-sessions-endpoints-and-pages` + `src/ohmystock/chat/` + `web-admin/src/pages/ChatSession*.tsx` |
| Public SSE channel + masked serializer + web-public shell | `archive/2026-05-15-web-public-shell-and-mask` + `src/ohmystock/eventbus/{mask_table,serializers}.py` + `src/ohmystock/api/routes/public_events.py` + `web-public/` |

---

## 6. 文件索引

### 入口
- `README.md` — GitHub 首頁（專案狀態、特色、架構、路線圖、免責）
- `docs/README.md` — 文件導覽，**任何 LLM Agent 開新對話應先讀這個**

### 核心設計（`docs/`）

| 檔案 | 用途 |
|---|---|
| `design-zh-TW.md` | 架構、模組、Tools/Skills/Memory/Backend、目錄結構、路線圖、風險登記（核心大檔） |
| `workflow-cheatsheet.md` | **交易業務邏輯 SSOT** — Phase 0–5 + §16 提案閘 + §17 文件關係表 |
| `safety-and-simulation.md` | Live/Sim 防線 9 層 + verify_simulation + 對賬機制 |
| `llm-decision-schema.md` | LLM Decider I/O JSON 規格 + Trade Journal schema（FTS5）|
| `post-trade-review-rubric.md` | Phase 5 五節點 DAG 評分準則 |
| `tools-contracts.md` | 21 個 `@register_tool` 工具 I/O schema 唯一權威 |
| `v3-decisions.md` | v3 已拍板決策（13 項）+ 預算追蹤 + 個人 milestone |
| `user-scenarios.md` | **Operator workflow** — Mark 在 admin 23 頁的 10 個使用情境 |

### 前端 / EventBus

| 檔案 | 用途 |
|---|---|
| `frontend.md` | 後台 `web-admin/` 頁面 wireframes、路由、Zustand、design tokens |
| `web-admin-page-designs.md` | **23 頁面視覺契約 SSOT** — layout slots / loading-empty-error / SSE / 紅漲綠跌雙重編碼 |
| `frontend-public-pixel.md` | 公網 `web-public/` Pixel 像素辦公室 UI、9 角色 sprite、動畫狀態機 |
| `backend-eventbus.md` | EventBus 架構 + Event Schema + Admin/Masked Serializer + 21 個 event_type |
| `auth-and-mask.md` | Bearer token auth、Mask Spec 白名單、SITC 合規策略、部署拓樸 |

### 子系統規範
- `proposals/README.md` — 策略改動提案（命名、frontmatter、WFA 驗證、merge 流程）
- `reviews/README.md` — LLM 復盤輸出（五節點 schema、`_index.json`）
- `openspec/` — OpenSpec 配置（搭配 `opsx:*` skills 使用），`openspec/changes/archive/` 為 capability 級歷史

---

## 7. 任務 → 該讀哪個檔（快速指引）

- 「為什麼這樣設計？」→ `docs/design-zh-TW.md` §1–§3
- 「該怎麼選股 / 進場 / 出場？」→ `docs/workflow-cheatsheet.md`（**business logic SSOT**）
- 「LLM 該輸出什麼 JSON？」→ `docs/llm-decision-schema.md` §1–§3
- 「Phase 5 復盤節點怎麼評分？」→ `docs/post-trade-review-rubric.md`
- 「live trading 安全防線是什麼？」→ `docs/safety-and-simulation.md`
- 「後台怎麼寫？」→ `docs/web-admin-page-designs.md`（視覺契約）+ `docs/frontend.md`
- 「公網前台 pixel 辦公室？」→ `docs/frontend-public-pixel.md`
- 「Backend 怎麼推 event 給前端？」→ `docs/backend-eventbus.md`
- 「公網要 mask 哪些欄位？admin auth 怎麼設？」→ `docs/auth-and-mask.md`
- 「`market_data_tool` 怎麼呼叫？」→ `docs/tools-contracts.md`
- 「v3 已拍板決策 / 預算 / milestone？」→ `docs/v3-decisions.md`
- 「台股市場細節（T+2、漲跌停、當沖稅）」→ `docs/design-zh-TW.md` §4.4.1
- 「Mark 平常怎麼用這套系統？」→ `docs/user-scenarios.md`
- 「目前哪些 capability 已 ship？」→ §5.2 或 `ls openspec/changes/archive/`
- 「跑月度復盤？」→ `uv run ohmystock review --from <YYYY-MM-DD> --to <YYYY-MM-DD>`（先試 `--dry-run --json` 估 token / cost）

---

## 8. 路線圖

狀態符號：✅ 已 ship / 🟡 主體完成、有 deferred 子項 / ⏳ 未開始

| Phase | 範圍 | 預計完成 | 狀態 |
|---|---|---|---|
| 0 | Scaffold（環境、CLI 骨架、FastAPI、Shioaji+FinMind+Anthropic 三方連線、cost tracker） | 2026-05-12 | ✅ |
| 1 | 技術 / 籌碼面 Skills + 回測引擎 | 2026-05-26 | ✅ |
| 2 | Screener + 訊號偵測 + Phase 2B Swarm Input Assembler | 2026-06-16 | ✅ |
| 3 | LLM Decider + Confirm Gate + Trade Journal v3 | 2026-07-07 | ✅ |
| 3.5 | `OHMYSTOCK_AUTO_EXECUTE` 雙模式 + 9 條安全防線 | 2026-07-28 | ✅ |
| 4 | web-admin（23 頁）+ Bearer auth | 2026-08-11 | ✅ |
| 4.5 | web-public pixel + Mask serializer + E2E 滲透測試 | 2026-08-25 | 🟡（shell + mask ✅、pixel 辦公室 + 生產部署 ⏳） |
| 5 | LLM 復盤五節點 swarm + 提案 → WFA → 合併閉環 | 2026-09-15 | 🟡（pipeline / proposals / WFA / validate / admin endpoints ✅、月度自動觸發 + reviews UI 強化 ⏳） |

### 進度評估
進度顯著超前原時程（今天 2026-05-18，原 Phase 4 預計 2026-08-11 完成）。剩餘未 ship 子項：
- `web-public-pixel-office-mvp`（Canvas 2D + 9 角色 sprite + 動畫狀態機）
- 月度復盤自動觸發（cron / scheduler）
- EventBus 剩 7 個 unwired emitter（屬於各自 producing capability）
- 生產部署（Cloudflare Tunnel / Vercel / 收窄 CORS / rate limit）

---

## 9. 授權

[MIT License](LICENSE) © 2026 MarkSu
