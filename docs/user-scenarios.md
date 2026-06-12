# 使用者情境（Operator Workflow）

> **角色**：Mark（系統擁有者，唯一 admin 使用者）
> **視角**：作為 operator 在 web-admin 的 18 頁中如何使用本系統。
> **不在範圍**：公網訪客（→ `frontend-public-pixel.md`）、Agent 內部執行（→ `design-zh-TW.md` §3、`workflow-cheatsheet.md`）。
> **配對讀**：`workflow-cheatsheet.md` §1 = Agent 自動觸發排程；本檔 = Mark 對著 admin UI 做什麼。
> **最後更新**：2026-04-27（初稿）

---

## 0. 情境總覽矩陣

| # | 情境 | 觸發 | Phase | 主要頁面 | 耗時 |
|---|------|------|-------|----------|------|
| 1 | Pre-market 5 分鐘 routine | 每交易日 08:30 | Phase 0 | `/`, `/paper` | 5 分 |
| 2 | Intraday signal → Confirm Gate | 盤中事件觸發 | Phase 3 模式 A | `/paper`（Confirm Gate 內嵌） | 2-5 分/筆 |
| 3 | Post-close 持倉檢視 | 每交易日 14:00 後 | Phase 4 | `/paper`, `/paper/positions` | 10-15 分 |
| 4 | 週五選股 deep dive | 週五 17:30+ | Phase 1 | `/`, `/swarm/:preset/:runId`, `/market/:symbol` | 30-60 分 |
| 5 | 月營收掃描檢視 | 每月 1-10 日 19:30+ | Phase 1.5 | `/`, `/market/:symbol` | 10-20 分 |
| 6 | 月底復盤 + 提案 PR review | 月底（最後交易日後） | Phase 5 | `/reviews/:id`, `/proposals/:id` | 30-90 分 |
| 7 | Backtest 一個 ad-hoc 想法 | 任意（idea 浮現時） | — | `/backtest`, `/backtest/:jobId` | 5-30 分 |
| 8 | Risk-Off 觸發應對 | 系統旗標 = Risk-Off | Phase 0 異常 | `/`, `/paper`, `/audit` | 5-10 分 |
| 9 | 系統失敗 fallback | 連線/額度/budget 異常 | — | `/settings`, `/audit` | 5-15 分 |
| 10 | 首次安裝 / cold start | 第一次 run | — | `/settings`, `/skills` | 60-120 分 |

**Cadence 覆蓋**：日（1, 2, 3）、週（4）、月（5, 6）、異常（8, 9）、一次性（10）、ad-hoc（7） — 5 種 + ad-hoc 全覆蓋。

---

## §1 Pre-market 5 分鐘 routine

**Trigger**：每交易日 08:30（開盤前 30 分鐘）

**Goal**：1 分鐘內判斷今天是否要進場、有沒有需要 confirm 的 LLM 決策、有沒有風險訊號需要警覺。

**主要頁面**
- `/` Dashboard（§17.B） — 風險面板、權益曲線、watchlist、本月 LLM 成本
- `/paper` Paper Trading（§17.H） — 月度熔斷距離、持倉概況
- `/paper` 決策審核（§17.Q，Confirm Gate 內嵌於 Paper Overview） — 若昨晚 Phase 2B 推出待 confirm 決策

**Mark 做的決定**
- 看 Dashboard 頂部 Risk Gate 燈：🟢 → 正常；🟡 → 仔細看 watchlist；🔴 → 跳到 §8 Risk-Off 流程
- 看「今日待辦」面板有沒有 ≥ 65 score 的待 confirm；有就點 `/paper` 進 §2 流程
- 看本月 LLM 成本進度條：≥ 80% 橘色 → 提醒自己今日少跑 ad-hoc swarm

**LLM 做的決定（昨晚已完成）**
- Phase 2B（17:30）已重評分 watchlist
- Phase 0 開盤前 09:30 會再跑一次 risk-off check（這時還沒跑）

**失敗 fallback**
- Dashboard load 失敗 → 直接看 `/audit` 最後一筆 risk-gate event 確認旗標狀態
- 月度熔斷已觸發（月 PnL ≤ -8%）→ Dashboard 應顯示紅色 banner，今日全平且禁止新進場（`workflow-cheatsheet.md` §0 月度熔斷）

**預估耗時**：5 分鐘（含喝咖啡）

**引用**
- `workflow-cheatsheet.md` §0 Risk Gate / 月度熔斷
- `frontend.md` §17.B Dashboard、§17.H Paper、§17.Q 決策審核（實作內嵌於 `/paper`）
- `safety-and-simulation.md` §2.11 LLM 成本軟熔斷

---

## §2 Intraday signal → Confirm Gate

**Trigger**：盤中（11:00 / 13:00 Phase 2A 掃描結果）或前晚 Phase 2B 評分達 score ≥ 65 → LLM Decider 跑完產出 `pending` 決策 → Mark 收到通知。

**Goal**：在 expire 倒數歸零前（預設 22:14 同日），判斷是否 confirm LLM 提案、reject、或讓它過期。

**主要頁面**
- `/paper`（§17.Q，Confirm Gate 內嵌）— 待 confirm 決策佇列

**Mark 做的決定**
- 展開 reasoning 區塊：看 Must-have 3/3 是否扎實、加分項命中哪幾項、cited skills 是否合理
- 看系統覆寫了什麼：例如 LLM 提案 22% sizing → 系統覆寫 18%（取較保守者，公式見 `workflow-cheatsheet.md` §6.6）
- 評估 Mark 自己的 mental check：這檔最近有沒有什麼 LLM 看不到的個人理由（例如「我前年在這檔被套過」） → 寫進 reject reason
- 點 `[✓ Confirm]` 或 `[✗ Reject]`；前者觸發 ConfirmDialog 二次輸入張數

**LLM 做的決定（已完成）**
- 跑完 `entry_decision_team` swarm
- 評分 confidence、寫 thesis、決定 action（enter / reduce_size / skip）
- 系統已套 Volatility Targeting + ATR 停損 + Risk Gate 全部硬性閘

**失敗 fallback**
- Confidence < 0.7 → 自動模式下會被防線 9 熔斷拒單（仍會出現在佇列但標 `auto_blocked`），Mark 仍可手動 confirm
- 22:14 倒數結束 Mark 還沒看 → 自動 expire，寫 journal `kind=expire`，下次再有訊號重來
- LLM 提案 sizing 偏離系統公式 > 30% → 防線 9 直接 reject（見 `safety-and-simulation.md` §2.9）

**預估耗時**：每筆 2-5 分鐘；單日上限 5 筆（防線 9）

**引用**
- `workflow-cheatsheet.md` §6.7 模式 A 人工 confirm、§6.8 必須記錄欄位
- `llm-decision-schema.md` §2.1 LLM 輸出嚴格約束、§4 Trade Journal schema
- `frontend.md` §17.Q 互動約束（實作內嵌於 `/paper`）
- `safety-and-simulation.md` §2.9 防線 9（LLM 自動下單熔斷）

---

## §3 Post-close 持倉檢視

**Trigger**：每交易日 14:00（盤後）— Phase 4 持倉檢視 + Phase 2B 重評分都會在 17:30 自動跑，但 Mark 在收盤後就會想先看一眼。

**Goal**：確認今日成交是否如預期、停損/停利是否需要手動覆寫、有沒有持倉達 7 日未達 +3% 該倉位減半。

**主要頁面**
- `/paper`（§17.H）— 帳戶權益、持倉表（停損 / 衛星 / 持有日數）
- `/paper/positions`（§17.P）— 顯示成本、PnL、距停損 %、距 T1 %
- `/paper/orders`（§17.P）— 今日成交回單

**Mark 做的決定**
- 持倉表逐檔掃：紅色（虧損逼近停損）→ 決定守還是先停損出場
- 看「持有日數」：≥ 7 日且 PnL < +3% → 評估倉位減半（時間停損規則見 `workflow-cheatsheet.md` §7.B）
- 點個別持倉 `[出 50%]` / `[全出]` 觸發手動出場單

**LLM 做的決定**
- 17:30 後 Phase 4 swarm 會自動跑「論點失效檢查」(`thesis_invalidation`) 並標出建議出場標的
- Phase 2B 17:30 後重評分既有持倉，分數掉太多會在隔日 Phase 4 提示

**失敗 fallback**
- 14:00 看時 Phase 4 還沒跑（17:30 才會跑）→ 看的只是當日成交，論點失效要等晚上
- 出場單失敗（Shioaji sim error）→ 系統會 retry 3 次後寫 `kind=order_failed` 到 audit log；Mark 隔日早上要在 §1 routine 補處理

**預估耗時**：10-15 分鐘

**引用**
- `workflow-cheatsheet.md` §7 Phase 4（A 停損 / B 時間停損 / C 停利 / D 論點失效 / E 移動停利）
- `frontend.md` §17.H Paper、§17.P 子頁
- `llm-decision-schema.md` §4 出場 journal 欄位

---

## §4 週五選股 deep dive

**Trigger**：週五 17:30 後 — Phase 1 漏斗四層 swarm 跑完，產出 10-15 檔候選 → watchlist 已更新。

**Goal**：人工複查 LLM 推上來的候選，刪掉 Mark 覺得不對的、加進自己看到 LLM 漏掉的，作為下週交易的 universe。

**主要頁面**
- `/` Dashboard watchlist 區（§17.B）— Top 5 概覽
- `/swarm/:preset/:runId`（§17.E）— 看 weekly screening swarm 各節點輸出
- `/market/:symbol`（§17.I）— 個股深入研究（K 線 + 籌碼 Tab + 基本面 Tab）

**Mark 做的決定**
- 從 Dashboard watchlist 進入個股頁，掃 K 線型態（VCP / 杯柄 / 平台突破，型態庫見 `workflow-cheatsheet.md` §9）
- 籌碼 Tab 看三大法人 / 借券 / 個股期 OI；不對勁的標記移出 watchlist
- 「+ 加入 watchlist」可以手動加 LLM 沒選到的；輸入 memory 為什麼加（會進 `/memory`）
- 高比重決策（例如 portfolio top pick）可以額外開 Chat (`/chat`) 跟 LLM 對話深入研究

**LLM 做的決定（已完成）**
- 跑完漏斗四層：N 排除 → 量化初篩 → 產業熱度 → 籌碼確認 → 技術精選
- 產出 watchlist + 每檔 score（v2 公式：技 35 + 籌 45 + 產 10 + 情緒 10）

**失敗 fallback**
- swarm 失敗（FinMind 未回應）→ 看 `/audit` 確認 retry 次數；通常自動重跑 1 次，仍失敗會在 Dashboard 顯示黃色警告
- watchlist 太少（< 5 檔）→ 可能是 Risk-Off 狀態下漏斗已主動限縮，正常行為

**預估耗時**：30-60 分鐘（這是 Mark 一週最花時間的時段）

**引用**
- `workflow-cheatsheet.md` §2 Phase 1 漏斗四層、§9 K 線型態庫
- `frontend.md` §17.B Dashboard、§17.E Swarm DAG、§17.I 個股頁

---

## §5 月營收掃描檢視

**Trigger**：每月 1-10 日 19:30 後 — Phase 1.5 swarm 跑完月營收動能標的篩選。

**Goal**：把月營收創新高 / 年增 > 30% 的標的快速掃過，加入 monthly-revenue-watch（與 weekly-screening watchlist 並存）。

**主要頁面**
- `/` Dashboard 近期 Run 區（§17.B）— 點開 monthly revenue scan 結果
- `/market/:symbol`（§17.I）— 個股基本面 Tab 看月營收趨勢

**Mark 做的決定**
- 對於入選標的，判斷是否「真實成長」還是「基期低」 → 看 12 個月趨勢圖
- 加入 watchlist 或丟掉

**LLM 做的決定（已完成）**
- 篩選條件：月營收 YoY > 30% / 連 3 個月 YoY > 20% / 月營收 6 個月新高（任一）
- 排除：股價 > 500 / 已在持倉

**失敗 fallback**
- 月營收公告延遲 → swarm 會在 1-10 日每日 19:00 重跑
- 沒有任何標的入選 → 正常（保守期不勉強加倉）

**預估耗時**：10-20 分鐘

**引用**
- `workflow-cheatsheet.md` §3 Phase 1.5 月營收掃描

---

## §6 月底復盤 + 提案 PR review

**Trigger**：每月最後交易日收盤後 — Phase 5 五節點 swarm 跑完，產出 `reviews/{YYYY-MM}.md` + 0 至 N 個 `proposals/{YYYY-MM-DD-slug}.md`。

**Goal**：吸收當月績效歸因、審核 LLM 出的策略改動提案、決定是否合併到 cheatsheet（這是整個自我改進閉環的人工關卡）。

**主要頁面**
- `/reviews/:id`（§17.R）— 復盤摘要 / 歸因 / 命中率時序 / 提案列表
- `/proposals/:id`（§17.S）— 個別提案的 diff、動機、WFA 報告、merge 按鈕

**Mark 做的決定**
- Review 看完後決定：是否同意 LLM 的歸因敘事？哪幾筆「`thesis_failed_loss`」要列入下月重點觀察？
- 對每個 proposal：
  - WFA 報告通過（OOS 改善 + 樣本內外落差 < 30% + Robust ±10% 衰減 < 50% + 黃金樣本不退化）才看
  - 通過後仍要人工判斷：這個改動會不會讓策略 overfit 到這個月特殊行情
  - `[✓ Merge to v3.1]` 觸發 ConfirmDialog；merge 後自動 bump cheatsheet 版本
  - 不通過：`[✗ Reject]` 寫拒絕原因、或 `[Re-validate]` 換參數重跑 WFA

**LLM 做的決定（已完成）**
- 跑完 5 節點 DAG：data_loader → attributor → aggregator → critic → proposer
- 評分準則見 `post-trade-review-rubric.md` §0–§5
- LLM 不可直接 commit cheatsheet，必須走人工 PR review

**失敗 fallback**
- WFA 全部不過 → 該月 0 個提案，正常（不勉強改）
- 連續 3 個月 0 提案 → Mark 自己要 reflect 是不是策略已經到瓶頸（手動 ad-hoc 觸發 critic 節點）

**預估耗時**：30-90 分鐘（提案多時可拆兩個晚上）

**引用**
- `workflow-cheatsheet.md` §15 Phase 5、§16 提案 → 驗證 → 合併
- `post-trade-review-rubric.md` §0–§5 五節點評分準則
- `frontend.md` §17.R `/reviews/:id`、§17.S `/proposals/:id`
- `proposals/README.md`、`reviews/README.md`

---

## §7 Backtest 一個 ad-hoc 想法

**Trigger**：Mark 看到一篇文章 / 想到一個 idea，想驗證「如果加這個條件回去 4 年 backtest 會更好嗎？」

**Goal**：5-30 分鐘內跑出回測結果，判斷這個 idea 是不是有 alpha；好的話走 §6 提案流程正式提交。

**主要頁面**
- `/backtest`（§17.F）— 設定策略 / 標的 / 期間 / 參數
- `/backtest/:jobId`（§17.G）— 摘要、權益曲線、回撤、月報酬熱力、診斷

**Mark 做的決定**
- 選 base 策略（例如 `tw_momentum_swing`）+ 改動什麼參數
- 啟用 Walk-Forward？啟用 Optuna 最佳化？
- 看結果：Sharpe ≥ 1.5、樣本內外落差 < 15%、MDD < -15% → 算可接受
- 結果好 → 開 PR 把 idea 寫成 `proposals/{date}-{slug}.md`，走 §6 merge 流程
- 結果差 → 至少寫進 `/memory` 標 negative finding，避免日後 re-investigate

**LLM 做的決定**
- 純 backtest 不涉及 LLM；除非 Mark 在 `/chat` 找 LLM 一起設計參數區間

**失敗 fallback**
- backtest 跑超過 5 分鐘還沒結束 → 通常是 Optuna 跑太多 trial；後台 cancel
- 結果 too good to be true（Sharpe > 3）→ 多半 lookahead bias，回去檢查 data leakage

**預估耗時**：5-30 分鐘

**引用**
- `frontend.md` §17.F `/backtest`、§17.G Result
- `workflow-cheatsheet.md` §16 提案閘 WFA 驗證標準

---

## §8 Risk-Off 觸發應對

**Trigger**：Phase 0 任一條件觸發（加權跌破 60MA / SPY 5 日 < -3% / VIX > 25 / TWD 1 日貶值 > 0.5% / 外資台指期淨空連 3 日新高） → Dashboard 旗標轉🔴。

**Goal**：5 分鐘內理解觸發原因、確認系統已自動禁止新進場 + 上移所有停損 2%、決定是否額外手動避險。

**主要頁面**
- `/` Dashboard 風險面板（§17.B）— 看哪一條觸發
- `/paper`（§17.H）— 確認所有持倉停損已上移 2%
- `/audit`（§17.O）— 看 risk-off event 的 timestamp + payload

**Mark 做的決定**
- 確認 Dashboard 顯示紅色 banner、新進場 button 已 disabled
- 評估是否手動買 0050 反一短期避險（Risk-Off 模式規則允許）
- 若是月度熔斷觸發（不同事件） → 系統強制全平 + 寫 audit log；Mark 此時必須觸發月度復盤才解鎖

**LLM 做的決定**
- 系統公式自動處理（停損上移、新進場禁止）
- LLM Decider 在 Risk-Off 期間任何 entry 都會被 Risk Gate 一票否決，連到不了 confirm gate

**失敗 fallback**
- Risk-Off 旗標誤觸發（資料源錯誤）→ 在 `/audit` 看 risk-gate event 的原始數值；確認後可在 `/settings` 危險區手動 override（會寫 audit log）
- 系統沒自動上移停損 → bug，去 `/audit` 找原因，最壞情況手動逐檔調整 `/paper/positions`

**預估耗時**：5-10 分鐘

**引用**
- `workflow-cheatsheet.md` §0 Risk-Off 觸發條件 / 模式規則 / 月度熔斷
- `frontend.md` §17.B Dashboard、§17.H Paper、§17.O Audit

---

## §9 系統失敗 fallback

**Trigger**：以下任一：Shioaji 連線斷 / FinMind 額度滿 / Anthropic API budget 達 80% / 任一 swarm 連續 2 次失敗。

**Goal**：判斷今日是否還能正常交易、需不需要人工介入、有沒有資料缺口要補。

**主要頁面**
- `/settings`（§17.N）— Shioaji / FinMind 連線測試、API key 狀態、剩餘額度
- `/audit`（§17.O）— 失敗事件 timeline

**Mark 做的決定**
- Shioaji 斷線 → `/settings` 點連線測試；通常重連即可，極端情況改用 twstock fallback 看資料但不下單
- FinMind 額度滿 → 該日 Phase 1.5 / Phase 2B 籌碼計算可能不完整；考慮今日不開新倉
- API budget 達 80% → Dashboard 已轉橘；100% 觸發軟熔斷（全 Sonnet，Opus 暫停） → 月底前盡量少跑 ad-hoc swarm
- API budget 達 100% → 軟熔斷生效；Mark 可在 `/settings` Safety tab 看當前模型分布

**LLM 做的決定**
- 系統會 retry 3 次後寫 `kind=*_failed` 到 audit log
- 達 budget 軟熔斷時自動切 Sonnet（不需人工介入）

**失敗 fallback**
- Shioaji token 過期（每日午夜後常見）→ 系統會在隔日 09:30 Phase 0 失敗時通知；Mark 在 `/settings` Shioaji tab 重新登入
- FinMind 額度即將滿 → 提前升級會員（已贊助會員仍有上限）；fallback 至 twstock 籌碼粒度會較粗

**預估耗時**：5-15 分鐘

**引用**
- `safety-and-simulation.md` §2.11 LLM 成本軟熔斷
- `design-zh-TW.md` Shioaji SDK 限制、FinMind / twstock fallback
- `frontend.md` §17.N Settings、§17.O Audit

---

## §10 首次安裝 / cold start

**Trigger**：第一次跑這套系統（或重置 Docker volume 後重來）。

**Goal**：60-120 分鐘內完成所有 API key 設定、Skill 套件 enable、跑通一次 weekly screening 確認 end-to-end 沒問題。

**主要頁面**
- `/settings`（§17.N）— 所有 API keys、Shioaji 模擬倉重置、預設模型
- `/skills`（§17.J）— 30 個內建 skill 確認啟用狀態
- `/swarm`（§17.D）— 手動觸發一次 weekly screening 驗證
- `/memory`（§17.L）— 寫入 baseline 偏好（風險偏好、不交易類型、月薪能承受波動）

**Mark 做的決定**
- 填入 Anthropic API key + 預算上限（預設 $50/月，見 v3 決策 #15）
- 填 Shioaji api_key/secret_key + 啟用模擬倉
- 填 FinMind token（贊助會員）
- 在 `/memory` 寫入個人偏好（範例見 §17.L wireframe：偏好高股息、不交易 KY 股、月薪 8 萬可承受月度 -10%）
- 在 `/swarm` 手動跑一次 weekly screening 驗證 end-to-end

**LLM 做的決定**
- cold start 時 LLM 還沒任何上下文，第一次跑會耗較多 prompt token；之後 prompt cache 命中率會回升

**失敗 fallback**
- 任一 API 連線測試失敗 → 看 error message + 比對 `design-zh-TW.md` §1 三方連線需求
- 第一次 swarm 跑出來結果空（沒入選任何標的）→ 可能 Risk-Off 觸發或 FinMind 資料缺；先看 `/audit`

**預估耗時**：60-120 分鐘（一次性）

**引用**
- `frontend.md` §17.N Settings、§17.J Skills、§17.D Swarm、§17.L Memory
- `design-zh-TW.md` §1 三方連線需求 + cost tracker
- `v3-decisions.md` 決策 #15 預算

---

## 附錄：18 頁 admin 涵蓋檢查

| 頁面 (§17.X) | 路由 | 出現於情境 |
|---|---|---|
| A Layout | (共用骨架) | 全部 |
| B Dashboard | `/` | §1, §4, §5, §8 |
| C Chat | `/chat` | §4（option） |
| D Swarm 入口 | `/swarm` | §10 |
| E Swarm DAG | `/swarm/:preset/:runId` | §4 |
| F Backtest | `/backtest` | §7 |
| G Backtest Result | `/backtest/:jobId` | §7 |
| H Paper | `/paper` | §1, §3, §8 |
| I 個股頁 | `/market/:symbol` | §4, §5 |
| J Skills 列表 | `/skills` | §10 |
| K Skill Editor | `/skills/:name` | (進階編輯，未在 routine 情境出現) ⚠ |
| L Memory | `/memory` | §4, §10 |
| M Sessions | `/sessions` | (FTS5 搜尋，ad-hoc 用) ⚠ |
| N Settings | `/settings` | §9, §10 |
| O Audit | `/audit` | §8, §9 |
| P Paper 子頁 | `/paper/orders\|positions\|equity` | §3 |
| Q 決策審核 | `/paper`（內嵌） | §1, §2 |
| R 復盤 | `/reviews/:id` | §6 |
| S 提案 | `/proposals/:id` | §6 |

**未出現頁面**：K Skill Editor、M Sessions — 兩者都是「需要時才用」的 ad-hoc 工具，不在 routine 動線。保留。
