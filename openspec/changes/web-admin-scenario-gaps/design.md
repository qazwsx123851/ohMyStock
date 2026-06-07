## Context

`docs/web-admin-user-testing-spec.md` 盤點出 9 項 web-admin 未實作功能（落差 D2–D6、D8–D11），橫跨 Dashboard、Confirm Gate、Settings、Memory、Proposal 五個區塊，前後端皆有。本 change 在既有架構上補齊，不引入新框架。所有交易公式（risk-off / sizing / 月度熔斷）已有 SSOT（`docs/workflow-cheatsheet.md` §0、§6.6、`docs/safety-and-simulation.md` §2.9），後端只回「狀態/旗標」，**不重抄公式**。

## Goals / Non-Goals

**Goals:**
- 9 項缺口補齊後，對應 `[BLOCKED]` 測試情境可轉 `[可測]`。
- 後端新增/擴充以最小 endpoint 面達成；前端沿用既有 shadcn 元件與 `lib/api.ts` 型別模式。
- confirm qty 覆寫**強制**通過 sizing clamp 防線，不可繞過安全閘。

**Non-Goals:**
- 不做 Settings 全面可寫（API key / breaker 仍以 .env 為主）；只加連線測試 + 唯讀額度/模型顯示。
- 不重算任何交易公式，一律引用 SSOT。
- 不處理落差 D1（Confirm Gate 路由）、D7（validate 自動轉狀態）— 這兩項屬「改文件」，另行處理。

## Decisions

**D-1 Dashboard summary 來源（DB-B1/B2/B3）**
- 決策：擴充既有 `GET /api/admin/stats/today`（或新增 `GET /api/admin/stats/dashboard`）回傳 `risk_gate:{ status: "green"|"yellow"|"red", triggers: string[] }`、`monthly_breaker:{ tripped: bool, month_pnl_pct }`、`cost:{ used_usd, budget_usd, pct }`。
- 理由：Dashboard 已 poll stats/today（30s），集中一個 summary endpoint 最省。risk gate / 月度 PnL / 成本皆讀既有來源（risk gate 計算、journal 月度 PnL、cost-tracking），endpoint 僅組裝、不計算公式。
- 替代：三個獨立 endpoint — 否決，徒增 poll 與複雜度。
- 待確認：risk gate 狀態目前是否有可直接讀的執行期來源（見 Open Questions）。

**D-2 confirm qty 覆寫（CG-B1）**
- 決策：`ConfirmRequest` 加 optional `override_qty: int | null`。提取現有 clamp 為共用函式供 human/auto 兩 path 復用。confirm 收到 override_qty 時套兩層防線：
  - **超 25% 名目上限（Breaker 5 語意）→ 回 409** `qty_exceeds_notional_limit`（含上限值），人工輸入的硬界不可無聲截斷。
  - **偏離系統公式 >30%（Step 8 語意）→ clamp 到較保守值 + 回 200 標記 `clamped:true`**。
- 理由：保留人工微調空間，但安全閘不可繞過；對「絕對金額硬界」硬拒、對「相對偏差」透明截斷，沿用 auto-execute 既有兩種防線語意。
- 替代：完全信任使用者 qty — 否決，違反防線設計。

**D-3 連線測試 endpoint（ST-B1）**
- 決策：新增 `POST /api/admin/settings/test-connection` body `{ provider: "shioaji"|"finmind" }`，回 `{ ok, latency_ms?, error? }`。後端對該 provider 做輕量呼叫（Shioaji：login 狀態 / FinMind：最小 quota 查詢）。
- 理由：sim 倉 + 贊助會員，輕量 ping 即可排錯，不下單、不耗額度。
- 替代：前端直連 — 否決，金鑰不可出前端。

**D-4 Memory write（ME-B1）**
- 決策：新增 `POST /api/admin/memory/rows` body `{ kind, content, tags?, source? }`，回新建 row。`MemoryStore` 加 `insert()`；FTS5 既有 INSERT 觸發器自動同步索引。kind 限既有 4 種（note/lesson/proposal/review_summary）。
- 理由：read-only 是 v0 刻意限制，cold start §10 需要寫偏好，現解除。schema 不變、僅加寫入路徑。
- 替代：另開偏好專用表 — 否決，memory_rows 已足夠（用 kind=note + tag 區分）。

**D-5 Settings 額度/模型分布（ST-B2）**
- 決策：settings payload 新增 `budget` 區塊回 `{ used_usd, budget_usd, remaining_usd, model_mix:{ opus, sonnet, haiku } }`，讀 cost-tracking。前端唯讀顯示。
- 理由：與 D-1 cost 同源，集中於 cost-tracking 既有統計。

**D-6 Re-validate（PR-B1）— 現況已滿足，無需改動**
- 調查結論：`ValidationDialog` 開啟時已從 localStorage `ohmystock.admin.lastValidation` 帶入上次參數；validating 的 `[Run Validation…]` 即重驗。rejected 後端 validate 要求 `status=validating`（不可重驗）+ PR-05 終態守恆。PR-B1 兩個 scenario 已被現有 Run Validation 覆蓋，標 done、不寫多餘程式。

**D-7 reject 原因輸入（CG-B2）**
- 決策：PaperOverviewPage reject 改為開小 dialog 收 `reason`，移除寫死的 `user_reject`。後端契約不變（reason 已必填）。

## Risks / Trade-offs

- [risk gate 無現成執行期狀態來源] → 若無，DB-B1 後端需從既有訊號（指數/VIX/TWD/外資）即時組裝；本 change 只讀不算公式，狀態判定沿用 `workflow-cheatsheet.md` §0 既有實作（若尚未有實作則本項需先補後端計算，工時上調）。
- [confirm qty 繞過 clamp] → 強制 service 端 clamp，前端 dialog 僅 UX，伺服器為唯一裁決點。
- [連線測試耗額度] → FinMind 用最小查詢；Shioaji 只查 login 狀態，不下單。
- [一個 change 偏大（10 capability delta）] → tasks 依 P0→P1→P2 分批實作、分批驗測，降低單批風險。

## Resolved（後端現況調查 2026-06-07）

1. **risk gate 狀態（DB-B1）**：後端僅實作 5 條觸發條件中的 1 條（TAIEX 跌破 60MA，`swarm/_live_market.py::_evaluate_taiex_risk_off()` 回 bool），其餘 4 條為 stub `"unknown"`。無 API、無三色燈映射、無持久化。risk_off_triggered event 只在 auto-execute 熔斷時發、非市場層級。**決策：完整補齊 5 條**（SPY 5日 / VIX / TWD / 外資台指期）。
   - **接法 A（純顯示，已拍板）**：新建獨立 `market_risk_gate` 模組計算 5 條 + 三色燈，**只供 Dashboard summary 顯示**；**不連動 swarm `risk_off`、不改 Phase 2B 評分/交易行為**（與 DB-B2「只顯示」同界線）。Dashboard 可標註「評分目前僅採 TAIEX」。
   - 資料源（tasks 0.4）：SPY/VIX → `get_kline`（yfinance `^VIX`）；TWD → yfinance `USDTWD=X`（新 forex source）；外資台指期 → FinMind `TaiwanFuturesInstitutionalInvestors`（新 `FinMindClient` 方法）。
2. **月度熔斷（DB-B2）**：月度 PnL 計算已有（`journal/repository.py::monthly_realized_pnl_pct()`）；門檻 -8% 在 SSOT 但 `config.py` 無常數、validator 未檢查、無 API。**決策：只做顯示**（config 加門檻常數 + summary 回 `tripped`/`month_pnl_pct` + banner）；enforcement（禁新進場/全平/validator 檢查）不在本 change。
3. **confirm qty（CG-B1）**：clamp 防線現只在 auto-execute path（`auto_execute.py` Step 8 偏離 clamp、Breaker 5 名目超限拒絕）；confirm service 用 `_compute_qty()`、無 clamp。**決策：提取 clamp 為共用函式，confirm 加 `override_qty`；超 25% 名目上限 → 409，偏離系統公式 >30% → clamp + 回應標記 `clamped`。**
