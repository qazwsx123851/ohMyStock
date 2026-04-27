# ohMyStock

> 台股 AI 交易代理人 — 從選股、進場、出場到復盤改進，全流程由 LLM 模型自主完成；模擬交易、可審計、可回測。

---

## 專案狀態

- **階段**：Spec / Pre-implementation（設計文件完成，原始碼待開工）
- **目標**：~16 週至 MVP（v3，含 LLM 復盤閉環）
- **執行範圍**：Paper Trading（永豐 Shioaji 模擬倉，**第一階段不接實單**）
- **市場**：台灣證交所（TWSE）/ 櫃買中心（OTC）
- **使用模式**：單一使用者本機 localhost（個人專案，非 SaaS）

---

## 解決什麼問題

1. **台股研究流程仰賴人工拼接資料源** — 技術面、基本面、籌碼面、三大法人、融資融券、產業輪動需要逐項蒐集整理。
2. **既有對岸/美股交易代理（Vibe-Trading、FinGPT 等）不支援台股市場結構** — T+2 交割、±10% 漲跌停、當沖證交稅減半、除權除息、處置股、借券賣出 vs 融券差異。
3. **散戶/自營交易者需要可重現、可回測、可審計的策略開發流程** — 而不是黑箱訊號。

---

## 核心特色

- **LLM Decider 自動進場決策 + Confirm Gate** — 人工確認預設；可切自動執行模式（受 9 條安全防線約束）
- **Trade Journal 結構化思考鏈 + FTS5 全文索引** — 每筆決策的 reasoning、confidence、輸入特徵全保存可查
- **月度 LLM 復盤五節點 swarm** — 資料 → 歸因 → 聚合 → 批判 → 提案
- **策略改動提案閉環** — LLM 出提案 → WFA 樣本外驗證 → 人工 PR review → 合併 cheatsheet → 下一輪生效
- **9 條 Live/Sim 安全防線** — 含 LLM 自動下單熔斷（單日筆數、confidence 門檻、25% 配額、30% 偏離等）

---

## 系統架構

```
UI 層（CLI / React Web / REST + SSE）
  └─ Agent 核心層（Claude Agent SDK + PreToolUse/PostToolUse Hooks 稽核）
      └─ LLM Decider Pipeline（v3）
         │  訊號 → entry_decision_team swarm
         │  → 系統覆寫（Sizing 公式 / ATR 停損 / Risk Gate）
         │  → Confirm Gate（OHMYSTOCK_AUTO_EXECUTE 切換）
         │  → 寫 Trade Journal + 送 Broker
         └─ Skills (~30) + Tools (~20) + Services
             │  Backtest / Paper Broker / Memory + FTS5 / Swarm DAG
             │  Trade Journal Service / Post-Trade Review Service / Proposal Validation
             └─ 資料層（FinMind / Shioaji / twstock / yfinance）
```

詳細架構與模組設計：[`docs/design-zh-TW.md`](docs/design-zh-TW.md) §3–§4

---

## 網頁呈現

採**前後台兩專案 monorepo** 架構：

### 後台（Admin Panel） — `web-admin/`
- **對象**：只有用戶本人（Bearer token auth）
- **技術**：React 19 + Vite + TypeScript + Tailwind + shadcn/ui
- **頁面**：18 個 wireframes 完整工作介面（Dashboard / Chat / Backtest / Paper Trading / Settings / Audit 等），設計細節 → [`docs/frontend.md`](docs/frontend.md)
- **內容**：交易資訊 + AI 觀點視角（決策思考鏈、復盤批判、提案佐證、Confirm Dialog）
- **部署**：localhost / Cloudflare Tunnel（不對公網）

### 前台（Public Pixel UI） — `web-public/`
- **對象**：任何訪客（無認證、嚴格 mask）
- **技術**：React 19 + Vite + TypeScript + Canvas 2D（pixel art 像素辦公室）
- **內容**：把 LLM agents 擬人化為 9 個像素角色（掃盤員 / 決策官 / 圖書館員 / 提案員 / 警衛 …），即時動畫呈現「AI 助手在工作」
- **靈感來源**：[pablodelucca/pixel-agents](https://github.com/pablodelucca/pixel-agents)
- **設計細節** → [`docs/frontend-public-pixel.md`](docs/frontend-public-pixel.md)
- **資料管線** → [`docs/backend-eventbus.md`](docs/backend-eventbus.md)（Backend EventBus 雙通道）
- **合規與 Mask** → [`docs/auth-and-mask.md`](docs/auth-and-mask.md)
- **部署**：Vercel / Cloudflare Pages（公網）

---

## 技術棧

| 層 | 選用 |
|---|---|
| Backend | Python 3.11+、Claude Agent SDK（**不用 LangChain**） |
| Frontend | React 19 + Vite + TypeScript + Tailwind + shadcn/ui |
| Storage | SQLite + FTS5（trade journal、memory、復盤索引） |
| Broker | 永豐金證券 Shioaji 模擬倉 |
| Data | FinMind 贊助會員（籌碼面）+ Shioaji 即時報價 + twstock / yfinance fallback |
| Deploy | Docker Compose（本機開發為主） |
| LLM 模型 | Opus 4.7（關鍵決策）+ Sonnet 4.6（分析）+ Haiku 4.5（規則檢查） |

預期 LLM API 月成本：USD ~$31–36（啟用 prompt cache + batch API 可降至 ~$20）。

---

## 目錄結構

```
ohMyStock/
├── README.md         本檔（GitHub 首頁）
├── docs/             設計文件 — 見 docs/README.md 索引
├── proposals/        LLM 產出的策略改動提案 — 見 proposals/README.md
├── reviews/          LLM 復盤輸出（自我改進迴圈記憶） — 見 reviews/README.md
├── openspec/         OpenSpec 配置
└── (src/, web/, scripts/ — 待實作)
```

---

## 文件導覽

**新進來想了解整體：**
- 設計細節（架構/模組/Schema/路線圖） → [`docs/`](docs/README.md)（先讀此索引）
- 交易業務邏輯 SSOT（Phase 0–5、進場、出場、風控） → [`docs/workflow-cheatsheet.md`](docs/workflow-cheatsheet.md)

**子系統規範：**
- 策略改動提案流程（命名、frontmatter、WFA 驗證） → [`proposals/README.md`](proposals/README.md)
- LLM 復盤輸出規範（五節點 schema、_index.json） → [`reviews/README.md`](reviews/README.md)

**特定主題：**
- LLM Decider I/O JSON 規格 + Trade Journal schema → [`docs/llm-decision-schema.md`](docs/llm-decision-schema.md)
- Live/Sim 安全防線 9 層 + 對賬機制 → [`docs/safety-and-simulation.md`](docs/safety-and-simulation.md)
- 21 個 Tool I/O 唯一權威 → [`docs/tools-contracts.md`](docs/tools-contracts.md)
- v3 已拍板決策 + 預算追蹤 → [`docs/v3-decisions.md`](docs/v3-decisions.md)
- Phase 5 復盤評分準則 → [`docs/post-trade-review-rubric.md`](docs/post-trade-review-rubric.md)

---

## 路線圖

| Phase | 範圍 |
|---|---|
| Phase 0 | 基礎建設（環境、資料源接入、CLI 骨架） |
| Phase 1 | 技術 / 籌碼面 Skills + 回測引擎 |
| Phase 2 | Screener + 訊號偵測 + Phase 2B Swarm Input Assembler |
| Phase 3 | LLM Decider + Confirm Gate + Trade Journal v3 |
| Phase 3.5 | `OHMYSTOCK_AUTO_EXECUTE` 雙模式 + 9 條安全防線 |
| Phase 4a | `web-admin/` Admin Panel（18 頁 wireframes 實作） |
| Phase 4b | `web-public/` Pixel UI（像素辦公室 + 9 角色） |
| Phase 4c | Backend EventBus + Auth middleware + MaskedEventSerializer |
| Phase 4d | E2E Mask 滲透測試（Playwright 驗證公開端點 0 漏網） |
| Phase 5 | LLM 復盤五節點 swarm + 提案 → WFA → 合併閉環 |

---

## 免責聲明

> **本專案僅供研究與個人模擬交易使用，不構成任何投資建議。**
>
> - 第一階段不接實單，僅透過永豐 Shioaji 模擬倉執行 paper trading
> - 任何 LLM 產出的選股、進場、出場、策略改動建議，**使用者需自行判斷風險並承擔後果**
> - 台灣證期局相關規範（投顧執照、SITC、廣告法等）由使用者自行注意
> - 過往回測績效不代表未來表現
> - **公開展示之前台所有股票代號（STK-A、STK-B 等）為虛構代換，不對應任何真實標的**；詳見 [`docs/auth-and-mask.md`](docs/auth-and-mask.md) §3 Mask Spec

---

## 授權

[MIT License](LICENSE) © 2026 MarkSu
