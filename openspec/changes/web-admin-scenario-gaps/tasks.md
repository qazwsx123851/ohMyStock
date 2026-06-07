## 0. 前置確認（已解，見 design Resolved）

- [x] 0.1 risk gate 現況：僅 1/5 條件實作（TAIEX MA60）→ 決策補齊 5 條
- [x] 0.2 月度熔斷：月度 PnL 已可算（`monthly_realized_pnl_pct`）→ 決策只做顯示
- [x] 0.3 confirm qty：超名目上限 409 / 偏離公式 clamp+標記
- [x] 0.4 盤點完成：SPY/VIX 復用既有 `get_kline`（yfinance, `^VIX`）；TWD 走 yfinance `USDTWD=X`（需新 forex source）；外資台指期走 FinMind `TaiwanFuturesInstitutionalInvestors`（需新 `FinMindClient` 方法）。接線點：`swarm/_live_market.py` `_UNWIRED_SIGNALS` diagnostics dict

## 1. DB-B1 Dashboard risk gate 三色燈（P0，完整補 5 條）— 實作順序：**後排（最後做）**

> 決策：成本遠高於其餘 8 項且觸及 market data 核心（VIX/TWD symbol 格式不符 `get_kline` regex，需改核心或繞 cache）+ 新增 forex source / FinMind 期貨方法。其餘 8 項（第 2–9 組）先完成。採接法 A（獨立模組純顯示，不動 risk_off）。

- [ ] 1.1 後端：新增 market risk gate 判定模組，補齊 4 條 stub 條件（SPY 5日跌幅 / VIX 門檻 / TWD 貶值 / 外資台指期淨空連3日新高），資料源依 0.4；判定沿用 `workflow-cheatsheet.md` §0，不重抄公式
- [ ] 1.2 後端：三色燈映射（green/yellow/red）+ 組裝 `risk_gate:{ status, triggers }` 進 dashboard summary（admin-read-endpoints）
- [ ] 1.3 後端：判定模組單元測試（各條件觸發 + 組合 + 三態映射）+ endpoint 欄位測試
- [ ] 1.4 前端：DashboardPage 加三色燈元件 + triggers 清單（red 可見觸發條件）
- [ ] 1.5 前端：Vitest 覆蓋三狀態渲染
- [ ] 1.6 文件：web-admin-user-testing-spec.md DB-B1 由 [BLOCKED] 改 [可測]

## 2. DB-B2 Dashboard 月度熔斷 banner（P0）

- [ ] 2.1 後端：dashboard summary 加 `monthly_breaker:{ tripped, month_pnl_pct }`
- [ ] 2.2 後端：熔斷觸發/未觸發測試
- [ ] 2.3 前端：DashboardPage 加紅色 banner（禁新進場提示 + 須跑月度復盤）
- [ ] 2.4 前端：Vitest 覆蓋 tripped true/false
- [ ] 2.5 文件：DB-B2 改 [可測]

## 3. CG-B2 reject 自訂原因輸入（P1）

- [ ] 3.1 前端：PaperOverviewPage reject 改開 dialog 收 reason、移除寫死 `user_reject`、空白前端擋下
- [ ] 3.2 前端：Vitest 覆蓋輸入原因送出 + 空白擋下
- [ ] 3.3 文件：CG-B2 改 [可測]

## 4. CG-B1 confirm 二次輸入張數（P1）

- [ ] 4.1 後端：提取 sizing clamp 為共用函式（human/auto path 共用），不改 auto path 既有行為
- [ ] 4.2 後端：ConfirmRequest 加 optional `override_qty`；confirm 套防線（超 25% 名目→409、偏離公式 >30%→clamp+標記）
- [ ] 4.3 後端：測試（範圍內 / 名目超限 409 / 偏離 clamp+標記 / 不帶 override 向後相容）
- [ ] 4.4 前端：PaperOverviewPage confirm 加 ConfirmDialog（顯示建議張數、可覆寫、送 override_qty、顯示 clamped 提示）
- [ ] 4.5 前端：Vitest 覆蓋覆寫送出 + 沿用建議 + clamped 提示
- [ ] 4.6 文件：CG-B1 改 [可測]

## 5. ST-B1 Settings 連線測試（P1）

- [ ] 5.1 後端：新增 `POST /api/admin/settings/test-connection`（shioaji/finmind 輕量呼叫，不下單/不耗額度）
- [ ] 5.2 後端：測試（成功 / 失敗不洩漏金鑰 / 不支援 provider 400）
- [ ] 5.3 前端：SettingsPage 各 provider 連線測試按鈕 + 結果呈現
- [ ] 5.4 前端：Vitest 覆蓋成功/失敗呈現
- [ ] 5.5 文件：ST-B1 改 [可測]

## 6. ME-B1 Memory 寫入個人偏好（P1）

- [x] 6.1 後端：MemoryStore 加 insert（FTS5 觸發器同步）+ 測試（insert 後可 list/search）
- [x] 6.2 後端：新增 `POST /api/admin/memory/rows`（kind 限制、content 非空驗證）+ 測試
- [ ] 6.3 前端：MemoryPage 加寫入表單（kind/content/tags/source）+ 成功刷新 + 必填驗證
- [ ] 6.4 前端：Vitest 覆蓋寫入成功刷新 + 必填擋下
- [ ] 6.5 文件：ME-B1 改 [可測]

## 7. DB-B3 Dashboard 成本進度條（P2）

- [ ] 7.1 後端：dashboard summary 加 `cost:{ used_usd, budget_usd, pct }`（讀 cost-tracking + 預算上限 config）
- [ ] 7.2 前端：DashboardPage 成本改進度條（≥80% 橘色）
- [ ] 7.3 前端：Vitest 覆蓋變色閾值
- [ ] 7.4 文件：DB-B3 改 [可測]

## 8. ST-B2 Settings 剩餘額度 / 模型分布（P2）

- [ ] 8.1 後端：settings payload 加 `budget:{ used_usd, budget_usd, remaining_usd, model_mix }`（讀 cost-tracking）
- [ ] 8.2 後端：測試欄位
- [ ] 8.3 前端：SettingsPage 唯讀顯示額度與模型分布
- [ ] 8.4 文件：ST-B2 改 [可測]

## 9. PR-B1 Proposal Re-validate 按鈕（P2）

- [ ] 9.1 前端：ProposalDetailPage 可重驗狀態加 `[Re-validate]`，帶入 localStorage lastValidation 重開 ValidationDialog
- [ ] 9.2 前端：Vitest 覆蓋帶入上次參數 / 無紀錄用預設
- [ ] 9.3 文件：PR-B1 改 [可測]

## 10. 收尾

- [ ] 10.1 lib/api.ts 補齊新 endpoint 型別
- [ ] 10.2 同步 web-admin-user-testing-spec.md 落差總表（已補實作的 D 標記 done）
- [ ] 10.3 capability-map.md 加一列指向本 change archive
- [ ] 10.4 全測試綠（後端 pytest + web-admin Vitest + 受影響 E2E）
