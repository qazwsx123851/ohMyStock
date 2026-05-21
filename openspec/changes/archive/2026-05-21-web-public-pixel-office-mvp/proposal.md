## Why

`web-public/` 目前只有 shell + DisclaimerBanner + `/api/public/events` masked SSE 管線（`archive/2026-05-15-web-public-shell-and-mask`），訪客看不到任何 agent 動態。Phase 4.5 仍欠最後一塊：把 LLM agent 全流程**擬人化**為像素角色在虛擬辦公室工作的 Canvas 2D 場景。完成後 web-public 才有公開作品集 / demo 的價值，Phase 4.5 才算收尾。

設計權威已落在 `docs/frontend-public-pixel.md`（14 章節 + 角色 / 場景 / state machine / event 路由全寫死）— 此 change 只把 spec 轉成可實作條目。

## What Changes

- 在現有 `web-public/` Vite 專案內新增 Canvas 2D 像素辦公室場景（grid 24×16、cell 16×16 px、邏輯解析度 384×256，CSS 整數 2× upscale 到 768×512）
- 視覺風格鎖定 **Pokémon Gen 2（Game Boy Color）** 美學：5–6 色限制調色盤（charcoal 牆 / 雙階灰條紋地板 / 芥末黃家具 / 橘紅 accent / 天藍 highlight）、tile 化家具、無 anti-aliasing、`image-rendering: pixelated`
- 6 區域：行情大廳 / K 線分析室 / 決策桌 / 圖書館 / 實驗室 / 會議室
- 實作 9 個角色 sprite（`scanner` / `pattern_analyst` / `decider` / `trader` / `librarian` / `reviewer_1..5` / `proposer` / `validator` / `guard`，共 13 個 character instance），每個 4 方向 × 4 frame，sprite 16×16 px、sheet 64×64 px、限定調色盤
- 實作三態 character state machine（`idle` / `walking` BFS / `acting`）+ per-character action queue（上限 5）
- 接 `/api/public/events` SSE → `EVENT_ROUTER` → 對應角色 action + speech bubble；timeline marquee 顯示最近事件
- 新增 Zustand `scene` store（characters / actionQueue / timeline）+ `usePublicSSE` hook
- 互動：點角色開 `AgentInfoSheet`（顯示該角色最近 5 筆 masked 事件，**不**顯示 reasoning 全文）
- 前端二次 mask 防線：speech bubble 若含 4-digit 數字 strip 為 `STK-?`；不寫 cookie / localStorage / analytics
- 加 `i18next`（zh-TW / en）+ `<noscript>` SEO fallback + About 頁
- **不在 MVP 範圍**：背景音效、Layout Editor、`/api/public/recent_events` 冷啟動 backfill 端點（idle 時 UI 顯示「等待開盤」即可）、ja / ko i18n

## Capabilities

### New Capabilities
- `web-public-pixel-office`: Canvas 2D 像素辦公室場景、9 角色 sprite + 13 character instance、三態 state machine、SSE → action 路由器、前端 mask 防線、Lighthouse / bundle 效能預算

### Modified Capabilities
（無 — 後端 `/api/public/events` 與 `MaskedEventSerializer` 已由 `eventbus-public-mask` 與 `admin-public-events-endpoint` 規範完成；本 change 純前端消費）

## Impact

- **新增程式**：`web-public/src/canvas/`、`web-public/src/stores/scene.ts`、`web-public/src/hooks/usePublicSSE.ts`、`web-public/src/lib/eventToAction.ts`、`web-public/src/components/{AgentInfoSheet,TimelineMarquee}.tsx`、`web-public/src/pages/{OfficeScene,About}.tsx`、`web-public/src/locales/`
- **新增 asset**：`web-public/public/sprites/*.png`（v1 由 runtime placeholder generator 產生 Gen 2 風格 16×16 sprite，sheet 64×64；正式 sprite 後續換貼圖即可，介面不變）
- **新增 token**：`web-public/src/styles/palette.ts` — 凍結 Gen 2 5–6 色 hex 常數，所有 Canvas fill / Tailwind theme extend 必須引用
- **依賴新增**：`zustand`、`i18next`、`react-i18next`（總計 < 30KB gzip）
- **不動的層**：backend Python、`/api/public/events` payload schema、`MaskedEventSerializer` 白名單、`SymbolMaskTable`、web-admin
- **路由變更**：`web-public/src/router.tsx` 加 `/`（OfficeScene）與 `/about` 兩條路徑；現有 placeholder 頁面退場
- **效能預算**：bundle < 150KB gzip（含 React）、Lighthouse Performance > 90、LCP < 1.5s、Canvas 30 tick/s
- **文件**：`CLAUDE.md` §5.2 與 §8 在 archive 後補上對應 SSOT row 與 Phase 4.5 ✅
