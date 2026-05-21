## Context

`web-public/` 已具備 SSE 與 mask 後端管線（`archive/2026-05-15-web-public-shell-and-mask`），但前端只有 `App.tsx` shell + `DisclaimerBanner` + 一個 placeholder 頁。`docs/frontend-public-pixel.md` 已把場景 / 角色 / state machine / event 路由全寫死，本 design 只解釋為何依照 SSOT 實作、邊界在哪、以及 MVP 與 v2 的取捨。

現況：
- Vite 8 + React 19 + TS 6 + Tailwind v4，無 shadcn / Radix（standalone 專案）
- `vitest` + `@playwright/test` 已可用
- backend 推送 16 個 `event_type`（`docs/backend-eventbus.md` §3.2），已透過 `MaskedEventSerializer` strict-whitelist
- backend `SymbolMaskTable` process-scoped 重置（FAQ Q2）

約束：
- bundle < 150KB gzip（含 React）— 排除 PixiJS / Phaser
- 必須能在無 SSE 事件時（夜間 / 假日）展示 idle 場景
- 訪客拿不到任何不在 PUBLIC_WHITELIST 的欄位（前端要二次防漏）
- 個人專案，不為團隊 / 多 reviewer 工作流設計

## Goals / Non-Goals

**Goals:**
- Canvas 2D 6 區域場景（grid 24×16），13 character instance 同時渲染
- 三態 character state machine + per-character action queue（cap 5）
- `/api/public/events` SSE 自動連線 / 重連 + 16 個 `event_type` → action 對映
- 前端二次 mask（speech bubble 4-digit strip）+ 不寫 cookie / localStorage / analytics
- 點角色開 `AgentInfoSheet`（最近 5 筆 masked 事件，不顯示 reasoning_full）
- 底部 timeline marquee + DisclaimerBanner（不可關閉）
- i18next zh-TW / en，About 頁含免責 + 專案介紹
- Lighthouse Performance > 90、LCP < 1.5s、30 tick / s 穩定

**Non-Goals:**
- 背景音效（v1 預設關）
- Layout Editor（pixel-agents 有；固定場景即可）
- ja / ko i18n（v1 只 zh-TW + en）
- `/api/public/recent_events` 冷啟動 backfill 端點（屬後端 change；MVP idle 顯示「等待開盤 09:00」）
- pixel art 自繪資產 pipeline（v1 用開源 Metro City 或佔位灰階）
- 部署（Vercel / Cloudflare Pages / Tunnel）— 屬 `production-deploy` change
- 7 個未接的 EventBus emitter（屬各 producing capability）

## Decisions

### D1. Canvas 2D 原生 API，不引入 PixiJS / Phaser
- **選擇**：`HTMLCanvasElement.getContext('2d')` + `requestAnimationFrame` + 自寫 30 tick loop；邏輯解析度 384×256 px（24×16 grid × 16 px cell，對齊 GBC 原生像素密度），CSS 整數 `transform: scale(2)` 上採樣到 768×512 顯示
- **理由**：PixiJS ~450KB gzip、Phaser ~900KB；MVP 場景 24×16 grid + 13 character × 16 frame sprite，原生 `ctx.drawImage` 切片即可。bundle 預算容不下遊戲引擎。16 px tile 是 Gen 2 風格基準，整數 upscale 才能保持像素銳利
- **替代**：PixiJS（被 bundle size 否決）／ Three.js（2D 場景殺雞用牛刀）／ DOM 渲染 13 角色（每 tick reflow 撐不到 30Hz）／ 32×32 tile（會破壞 GBC palette + tile 比例感）

### D2. 30 tick fixed timestep，render 用 rAF 60Hz 插值
- **選擇**：`MS_PER_TICK = 1000/30`；render frame 內依 `(now - lastTick) / MS_PER_TICK` 線性插值 character 位置
- **理由**：30 tick 對 SSE 事件密度足夠（最高 ~2 event/sec）；rAF 60Hz 渲染保持視覺流暢；節能模式（document.hidden）降至 15 tick
- **替代**：純 60 tick（多 2× CPU 無收益）／ 純事件驅動無 tick（state machine 難處理 walking 中途）

### D3. BFS 尋路，不用 A*
- **理由**：grid 24×16 = 384 格、障礙物只有桌椅靜態 ~20 格；BFS ~50 行、最壞 384 次擴展 < 1ms。A* 需 heuristic + open set + tie-break，過度工程
- **替代**：A*（grid 太小）／ 直線（無法繞桌椅）／ 預計算路徑表（場景固定但維護成本高）

### D4. Per-character action queue (cap 5)，oldest-drop backpressure
- **選擇**：每角色一個 FIFO queue；該角色 idle 立即執行，acting 中 push queue；queue 滿則丟最舊
- **理由**：避免單一角色被高頻事件灌爆而表現失真；丟最舊比丟最新更符合「展示最近狀態」
- **替代**：cap 1 直接覆寫（會丟太多脈絡）／ 無限 queue（會 backlog 延遲到不真實）／ 全域 queue（角色間 head-of-line blocking）

### D5. Zustand store，不引入 Redux
- **理由**：web-admin 已用 Zustand；store 結構單純（characters / actionQueue / timeline）；Redux 樣板太重
- **替代**：Redux Toolkit（不需要 time-travel）／ React Context（13 character × 30Hz 更新會嚴重 re-render）

### D6. 前端 mask 防線：speech bubble 過 4-digit regex
- **選擇**：在 `EVENT_ROUTER` 產出 bubble 文字後，用 `/\b\d{4}\b/g` → `STK-?` 二次 strip
- **理由**：後端 `MaskedEventSerializer` 已 whitelist + 4-digit denylist（`archive/2026-05-15-...`），前端為 defense-in-depth；萬一後端漏，UI 不應渲染真 symbol
- **替代**：信任後端（單點失效風險高）／ 全文 hash（無法閱讀）

### D7. 不寫 cookie / localStorage / analytics
- **選擇**：i18next 語系選擇用 `URLSearchParams`（`?lang=en`）或 `<html lang>` fallback；無 GA / Plausible / Sentry
- **理由**：訪客匿名、避免 IP 蒐集疑慮、避免 GDPR / SITC 合規負擔（`docs/auth-and-mask.md`）
- **替代**：用 localStorage 記語系（違反非寫策略；URL param 已足夠）

### D8. Pokémon Gen 2 (GBC) 視覺風格 + runtime placeholder sprite
- **選擇**：鎖定 5–6 色 GBC 風格調色盤（見下表 §Visual Palette），所有 Canvas fill / sprite / 區域底色 / Tailwind theme 必須引用 `src/styles/palette.ts` 凍結常數。MVP build 用程式繪製 placeholder（16 cell × 16 px，palette-constrained：頭部圓圈 + 身體梯形 + 帽子色塊區分角色 id），整張 sheet 由 `<canvas>` runtime 生成（不打進 bundle）。家具用程式繪製 tile（櫃台 / 書架 / 桌子）同樣 palette-constrained
- **理由**：(a) 個人專案無美術時間自繪 Gen 2 風格 sprite；(b) 真實 GBC 美學由 palette + 16 px tile + 銳利邊緣三條件即可重現，runtime 生成成本低於採購授權；(c) 介面不變 → 正式 sprite 後續換貼圖即可
- **替代**：itch.io Gen 2-style asset pack（授權檢查未完成、配色不一致）／ 自繪（無時間）／ AI 生圖（風格不穩定、palette 控制困難）

#### Visual Palette（凍結；所有渲染都引用）

| Token | Hex | 用途 |
|---|---|---|
| `--gb-wall` | `#2b2b2b` | 牆 / 邊框 / 字 |
| `--gb-floor-dark` | `#a0a0a0` | 地板深條紋 |
| `--gb-floor-light` | `#d8d8d8` | 地板淺底 |
| `--gb-furniture` | `#e8b840` | 家具主色（櫃台、書架、桌子） |
| `--gb-furniture-shadow` | `#a07820` | 家具陰影 / 底邊 |
| `--gb-accent` | `#e84020` | 角色帽子 / 重要圖標 / Risk-Off 警示 |
| `--gb-highlight` | `#80b8e8` | 螢幕 / 水紋 highlight |

#### Sprite 規格

- 單 cell：16×16 px（不再是 32×32）
- 4 方向 × 4 frame = 16 cell；整張 sheet 64×64 px
- 渲染：`ctx.drawImage(sheet, sx, sy, 16, 16, dx, dy, 16, 16)`，sx/sy 為 16 的倍數
- 邊緣硬切（無 AA），CSS `image-rendering: pixelated` + `canvas` 屬性 `imageSmoothingEnabled = false`

#### 地板樣式

- 24 列水平條紋：偶數 row = `--gb-floor-light`、奇數 row = `--gb-floor-dark`，每條紋 1 px
- 區域邊界用 `--gb-wall` 1 px 線描，標籤字體 6 px monospace

### D9. SSE 用瀏覽器原生 `EventSource`
- **理由**：MaskedEventSerializer 已輸出標準 `text/event-stream`；EventSource 內建斷線重連；無需 axios / fetch streaming
- **替代**：WebSocket（後端未開、無雙向需求）／ fetch + ReadableStream（要自寫重連）

### D10. 路由用既有 React Router v7
- **選擇**：`/` → OfficeScene、`/about` → About；不加更多頁
- **理由**：v7 已在 dependencies；場景單頁即可，About 為合規 / SEO 需要
- **替代**：純 SPA 無路由（About 仍要獨立可分享 URL）

## Risks / Trade-offs

| 風險 | 緩解 |
|---|---|
| [13 char × 30 tick 渲染 jank] | 啟動先 benchmark；超標降回 15 tick；render 只重畫 dirty cell |
| [SSE 高頻事件灌爆 queue → action 滯後] | per-char queue cap 5 oldest-drop；timeline marquee 仍保留全部事件當 source of truth |
| [後端漏 mask → 前端二次防線失效] | 4-digit regex 只是第二道；後端 archive 已有單元測試覆蓋；接受殘餘風險（個人專案） |
| [佔位 sprite 視覺粗糙 → demo 效果差] | 接受；MVP 重點是「動起來」；資產正式化排在後續 change |
| [iOS Safari Canvas 2D 兼容] | 用標準 API（drawImage / fillRect / fillText）；不用 OffscreenCanvas 主執行緒 fallback |
| [bundle 超過 150KB] | 啟動量 `vite build` 後跑 `rollup-plugin-visualizer` 一次；zustand 4KB、i18next core 14KB、React 19 ~45KB 都已知 |
| [SSR / SEO 不支援] | About 頁靜態化 + `<noscript>` fallback；專案性質為作品集，SEO 主要靠 GitHub 反向連結 |
| [節能模式切換不順] | `document.visibilitychange` 降頻；不暫停 SSE 連線（重連成本高於閒置） |

## Migration Plan

非破壞性 — `web-public/` 是 standalone Vite app，現有 placeholder 直接被 `OfficeScene` 取代：

1. 加依賴：`zustand` / `i18next` / `react-i18next` → `npm install` in `web-public/`
2. 加程式：依 `docs/frontend-public-pixel.md` §10 目錄結構建檔
3. 改 `router.tsx`：`/` → `<OfficeScene />`、`/about` → `<About />`
4. 改 `App.tsx`：保留 `DisclaimerBanner`、新增 `TimelineMarquee` 在 footer 上方
5. 測：`npm run test`（vitest unit）+ `npm run e2e`（playwright smoke：載入、canvas 出現、SSE 連線狀態）
6. `npm run build`、人工開 `npm run preview` 看視覺
7. `git commit` + `git push origin main`（solo dev，不開 PR）
8. `/opsx:archive web-public-pixel-office-mvp`（自動同步 spec 到 `openspec/specs/web-public-pixel-office/`）
9. 補 `CLAUDE.md` §5.2 與 §8

**Rollback**：`git revert` 該 commit；`web-public/` 退回現有 placeholder 狀態。後端不動。

## Open Questions

- 是否要在 footer 顯示「最後事件時間」debug 資訊？— **暫定**：MVP 不加，過於工程化
- `AgentInfoSheet` 用原生 `<dialog>` 還是手刻 Sheet？— **暫定**：手刻（無 shadcn / Radix；Sheet 邏輯 ~30 行）
- timeline 保留筆數？— **暫定**：cap 100（記憶體 < 50KB）；marquee 顯示最近 8 筆滾動
- 視覺風格 token 是否複用 web-admin 的紅漲綠跌？— **不**：web-public 與交易方向無關，採用中性 zinc + accent 色
- Canvas resize 策略？— **暫定**：固定 768×512 邏輯像素 + CSS `image-rendering: pixelated`；視窗縮放靠 CSS scale
