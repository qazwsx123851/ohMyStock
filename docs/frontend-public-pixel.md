# Frontend — Public Pixel UI（`web-public/`）

> **版本**：v1.0 ｜ **建立日期**：2026-04-27
> **對應程式**：`web-public/src/`
> **權威來源**：本檔為 **公網 pixel 像素辦公室 UI**（場景 / 角色 / 動畫狀態機 / Canvas 架構 / event 對應）的唯一權威。
> **相關章節**：[`backend-eventbus.md`](backend-eventbus.md)（event_type 來源）/ [`auth-and-mask.md`](auth-and-mask.md)（Mask Spec）/ [`frontend.md`](frontend.md)（後台 web-admin/）

對標 [pablodelucca/pixel-agents](https://github.com/pablodelucca/pixel-agents)，但訊號來源從「Claude Code JSONL」改為「ohMyStock backend EventBus」（[`backend-eventbus.md`](backend-eventbus.md)）。

---

## 1. 用途與設計目標

把 ohMyStock 系統內 LLM agents 的「選股 → 決策 → 下單 → 復盤 → 提案」全流程**擬人化為像素角色在虛擬辦公室工作**的場景，作為對外公開作品集 / demo。

**設計目標：**
- 訪客無需登入即可看到「AI 助手正在做什麼」的即時動畫
- 嚴格 mask：訪客永遠拿不到 `symbol`、`price`、`pnl_twd` 等敏感欄位
- 視覺風格：復古 2D 像素辦公室，retro game 質感
- 技術棧重用：React 19 + Vite + TypeScript（與 web-admin 共用 monorepo packages）

---

## 2. 技術棧

| 領域 | 選擇 | 理由 |
|---|---|---|
| 基底 | React 19 + Vite + TypeScript | 與 web-admin 同棧，monorepo 共用工具鏈 |
| 渲染 | **Canvas 2D**（原生 API） | pixel-agents 使用；GPU 加速、能處理 60fps 角色動畫 |
| 動畫 / 遊戲迴圈 | 自寫 `requestAnimationFrame` + 固定 tick rate（30 ticks/sec） | 不引入 PixiJS（450KB+ overkill） |
| 尋路 | 自寫 BFS（grid 16×16 ~ 32×24） | grid 小、不需 A*；BFS ~50 行 |
| 狀態 | Zustand（client）+ EventSource（live SSE） | 簡單；server 推 → store 更新 → Canvas 重繪 |
| 樣式 | Tailwind CSS v4（共用 `packages/ui-tokens`） | 與 web-admin 一致 |
| UI 元件（非 Canvas） | shadcn/ui（精選：Banner、Tooltip、Sheet） | DisclaimerBanner、AgentInfoPanel |
| Sprite 載入 | `<img>` 預載 + `OffscreenCanvas` 切片 | 一張 sprite sheet 含 9 角色 × 4 方向 × 4 frame |
| 路由 | React Router v7（Web 場景頁、About 頁） | 與 web-admin 一致 |
| 國際化 | `i18next`（zh-TW / en） | 公網需英文 SEO + 海外訪客 |

**估算 bundle**：~120KB gzip（React + Tailwind + Zustand + i18n + 自寫 Canvas，無 PixiJS / Phaser）。

---

## 3. 場景設計

### 3.1 Office Layout（grid 24×16）

```
   0    4    8   12   16   20   24
 0 ┌────────────┬─────────────────┐
   │ 📺 行情大廳 │ 🔬 K 線分析室    │
 4 │  Scanner   │ PatternAnalyst  │
   ├────────────┼─────────────────┤
 8 │ 💼 決策桌  │ 📚 圖書館        │
   │  Decider   │ Librarian       │
12 │  Trader    │ (FTS5 Q&A)      │
   ├────────────┼─────────────────┤
16 │ 🧪 實驗室  │ 📋 會議室        │
   │ Validator  │ Reviewer ×5     │
   └────────────┴─────────────────┘
   底部跑馬燈 + DisclaimerBanner
```

### 3.2 區域語意

| 區域 | grid 範圍 | 主要角色 | 動畫主題 |
|---|---|---|---|
| 行情大廳 | (0,0)–(11,3) | Scanner | 大螢幕跑「半導體強 / 金融弱」滾動字幕 |
| K 線分析室 | (12,0)–(23,3) | PatternAnalyst | 顯示 K 線型態 overlay（VCP / 杯柄 / 旗形） |
| 決策桌 | (0,4)–(11,11) | Decider, Trader | 桌前角色 + speech bubble 顯示 reasoning_summary |
| 圖書館 | (12,4)–(23,11) | Librarian | 書架背景 + 角色翻書動作 |
| 實驗室 | (0,12)–(11,15) | Validator | 試管 / 圖表動畫 |
| 會議室 | (12,12)–(23,15) | Reviewer ×5 | 圓桌 + 5 角色依序起立發言 |
| 公布欄 | (5,11)–(8,12)（穿插） | Proposer | 釘紙動作；status 顏色貼紙 |

---

## 4. 角色 Sprite 規格

### 4.1 Sprite Sheet 結構

每個角色一張 sprite sheet：`web-public/public/sprites/<character>.png`

- 尺寸：4 方向（down / up / left / right）× 4 frame（idle / walk1 / walk2 / action）= 16 cells
- 每 cell：32×32 px
- 整張 sheet：128×128 px

**例：** `decider.png`

```
  ↓idle  ↓walk1 ↓walk2 ↓action
  ↑idle  ↑walk1 ↑walk2 ↑action
  ←idle  ←walk1 ←walk2 ←action
  →idle  →walk1 →walk2 →action
```

### 4.2 9 個角色清單

| character_id | 中文名 | 對應 ohMyStock 元件 | 預設座位 (grid x,y) | 主要 event |
|---|---|---|---|---|
| `scanner` | 掃盤員 | `screener_tool` | (3, 2) | `screener_started` / `screener_completed` |
| `pattern_analyst` | 型態分析師 | `vcp_detector` / `pattern_lib` | (16, 2) | `pattern_detected` |
| `decider` | 決策官 | `entry_decision_team` swarm | (4, 8) | `decider_thinking` / `decision_made` |
| `trader` | 下單員 | Confirm Gate + Broker | (8, 8) | `awaiting_confirm` / `order_sent` |
| `librarian` | 圖書館員 | Trade Journal Service | (18, 8) | `journal_written` / `journal_queried` |
| `reviewer_1..5` | 五節點檢討團 | `post_trade_review_team` | (14–22, 14) 圓桌 | `review_node_started` / `review_completed` |
| `proposer` | 提案員 | `proposal_tool` | 流動，初始 (10, 11) | `proposal_created` |
| `validator` | 驗證員 | Proposal Validation Service | (4, 14) | `wfa_started` / `wfa_passed` / `wfa_failed` |
| `guard` | 警衛 | Risk Gate | 入口 (0, 8) | `risk_off_triggered` |

> Sprite 來源：v1 使用開源 [Metro City pixel pack](https://itch.io/) 或自繪（後續決定，見 plan「後續決定點」）。

---

## 5. 動畫狀態機

### 5.1 通用 Character States

```
        ┌──────┐
        │ idle │◄──────────────┐
        └──┬───┘               │
           │ event arrives     │
           ▼                   │
       ┌────────┐              │
       │ walking│ (BFS path)   │
       └───┬────┘              │
           │ arrived           │
           ▼                   │
       ┌────────┐              │
       │ acting │ (event-      │
       └───┬────┘   specific)  │
           │ action done       │
           └───────────────────┘
```

### 5.2 角色專屬 Action 狀態

| 角色 | action 狀態 | 觸發 event | 視覺表現 |
|---|---|---|---|
| Scanner | `scanning` | `screener_started` | 在大廳 4 個座標來回走 5 秒 + 大螢幕 scroll |
| Scanner | `report` | `screener_completed` | 走到看板，speech bubble: 「找到 N 檔候選」 |
| PatternAnalyst | `marking` | `pattern_detected` | 站桌前，speech bubble: pattern 名稱 + score |
| Decider | `thinking` | `decider_thinking` | 桌前坐下，頭頂跑 `...` 動畫 |
| Decider | `decided` | `decision_made` | speech bubble: `STK-X (conf 0.72) → entry` |
| Trader | `waiting_confirm` | `awaiting_confirm` | 抬頭等待 + 倒數計時泡泡 |
| Trader | `sending_order` | `order_sent` | 走到電話 / 終端送單動作 |
| Librarian | `writing` / `searching` | `journal_written` / `journal_queried` | 翻書 / 翻卡片動畫 |
| Reviewer N | `speaking` | `review_node_started` (node_index=N) | 第 N 位起立 speech bubble |
| Reviewer 全體 | `dispersing` | `review_completed` | 散會走出會議室 |
| Proposer | `pinning` | `proposal_created` | 走到公布欄釘紙 + 顏色狀態 |
| Validator | `experimenting` | `wfa_started` | 試管動畫 |
| Validator | `pass` / `fail` | `wfa_passed` / `wfa_failed` | 綠勾 / 紅 X icon 升起 |
| Guard | `alarm` | `risk_off_triggered` | 拉黃色封鎖線 + 警示音 |

### 5.3 State Machine 程式骨架

```ts
// web-public/src/canvas/characterStateMachine.ts
type CharacterState =
  | { kind: 'idle' }
  | { kind: 'walking'; path: GridPos[]; pathIdx: number }
  | { kind: 'acting'; action: string; startedAt: number; durationMs: number; bubble?: string };

interface Character {
  id: string;
  pos: GridPos;
  facing: 'down' | 'up' | 'left' | 'right';
  state: CharacterState;
  spriteSheet: HTMLImageElement;
}

function tick(char: Character, now: number) {
  switch (char.state.kind) {
    case 'idle':
      return; // 等下一個 event
    case 'walking':
      // BFS 路徑前進，每 tick 移動 1 格
      if (char.state.pathIdx >= char.state.path.length) {
        char.state = { kind: 'acting', action: char.pendingAction, ... };
      } else {
        char.pos = char.state.path[char.state.pathIdx++];
      }
      return;
    case 'acting':
      if (now - char.state.startedAt >= char.state.durationMs) {
        char.state = { kind: 'idle' };
      }
      return;
  }
}
```

---

## 6. Event → Character Action 對應表

接收 [`backend-eventbus.md`](backend-eventbus.md) §3.2 的 14 個 event_type，路由到對應角色：

```ts
// web-public/src/lib/eventToAction.ts
export const EVENT_ROUTER: Record<string, (event: PublicEvent) => CharacterAction> = {
  screener_started: (e) => ({
    targetCharId: 'scanner',
    action: 'scanning',
    durationMs: 5000,
    bubble: `掃 ${e.payload.universe_size} 檔...`,
  }),
  screener_completed: (e) => ({
    targetCharId: 'scanner',
    action: 'report',
    durationMs: 3000,
    bubble: `找到 ${e.payload.candidate_count} 檔候選`,
  }),
  pattern_detected: (e) => ({
    targetCharId: 'pattern_analyst',
    action: 'marking',
    durationMs: 2000,
    bubble: `${e.payload.pattern} ${e.payload.masked_symbol} (score ${e.payload.score.toFixed(2)})`,
  }),
  decider_thinking: (e) => ({
    targetCharId: 'decider',
    action: 'thinking',
    durationMs: 4000,
    bubble: `scoring ${e.payload.masked_symbol}...`,
  }),
  decision_made: (e) => ({
    targetCharId: 'decider',
    action: 'decided',
    durationMs: 3000,
    bubble: `${e.payload.masked_symbol} (conf ${e.payload.confidence.toFixed(2)}) → ${e.payload.action}`,
  }),
  awaiting_confirm: (e) => ({
    targetCharId: 'trader',
    action: 'waiting_confirm',
    durationMs: 30 * 60 * 1000,  // 最多 30 分鐘
    bubble: `等待 confirm: ${e.payload.masked_symbol}`,
  }),
  order_sent: (e) => ({
    targetCharId: 'trader',
    action: 'sending_order',
    durationMs: 2000,
    bubble: `送單 ${e.payload.masked_symbol}`,
  }),
  journal_written: (e) => ({
    targetCharId: 'librarian',
    action: 'writing',
    durationMs: 1500,
    bubble: `寫入 ${e.payload.journal_kind}`,
  }),
  journal_queried: (e) => ({
    targetCharId: 'librarian',
    action: 'searching',
    durationMs: 1500,
    bubble: `查詢 (${e.payload.result_count} 筆)`,
  }),
  review_node_started: (e) => ({
    targetCharId: `reviewer_${e.payload.node_index}`,
    action: 'speaking',
    durationMs: 5000,
    bubble: e.payload.node_name,
  }),
  review_completed: (e) => ({
    targetCharId: 'reviewer_1',  // 由 reviewer_1 觸發 dispersing
    action: 'dispersing',
    durationMs: 3000,
    bubble: `產出 ${e.payload.proposals_created_count} 提案`,
  }),
  proposal_created: (e) => ({
    targetCharId: 'proposer',
    action: 'pinning',
    durationMs: 4000,
    bubble: `[${e.payload.priority}] ${e.payload.target_section}`,
  }),
  wfa_started: () => ({
    targetCharId: 'validator',
    action: 'experimenting',
    durationMs: 6000,
    bubble: 'WFA 驗證中...',
  }),
  wfa_passed: () => ({
    targetCharId: 'validator',
    action: 'pass',
    durationMs: 2000,
    bubble: '✓ 通過',
  }),
  wfa_failed: () => ({
    targetCharId: 'validator',
    action: 'fail',
    durationMs: 2000,
    bubble: '✗ 失敗',
  }),
  risk_off_triggered: (e) => ({
    targetCharId: 'guard',
    action: 'alarm',
    durationMs: 8000,
    bubble: `⚠ ${e.payload.reason_category} (${e.payload.severity})`,
  }),
};
```

---

## 7. 資料流與 Canvas 渲染

### 7.1 主迴圈

```ts
// web-public/src/canvas/gameLoop.ts
import { useStore } from '@/stores/scene';

const TICK_HZ = 30;
const MS_PER_TICK = 1000 / TICK_HZ;

function startLoop(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext('2d')!;
  let lastTick = performance.now();

  function frame(now: number) {
    const elapsed = now - lastTick;
    if (elapsed >= MS_PER_TICK) {
      const characters = useStore.getState().characters;
      for (const char of characters) {
        tick(char, now);
      }
      render(ctx, characters);
      lastTick = now;
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
```

### 7.2 SSE 連接

```ts
// web-public/src/hooks/usePublicSSE.ts
import { useEffect } from 'react';
import { useStore } from '@/stores/scene';
import { EVENT_ROUTER } from '@/lib/eventToAction';

export function usePublicSSE(url = '/api/public/events') {
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      const router = EVENT_ROUTER[event.event_type];
      if (router) {
        const action = router(event);
        useStore.getState().enqueueAction(action);
      }
      // 同時寫進 Activity Timeline
      useStore.getState().pushTimeline(event);
    };
    es.onerror = () => {
      // 自動重連（EventSource 內建）
    };
    return () => es.close();
  }, [url]);
}
```

### 7.3 Action Queue（避免角色同時被多個 event 搶）

```ts
// web-public/src/stores/scene.ts
interface SceneState {
  characters: Character[];
  actionQueue: Record<string, CharacterAction[]>;  // by character_id
  timeline: PublicEvent[];
  enqueueAction: (action: CharacterAction) => void;
  pushTimeline: (event: PublicEvent) => void;
}

// enqueueAction 邏輯：
// - 該角色 idle → 立即執行
// - 該角色 acting → push queue，等 idle 再 dequeue
// - queue 上限 5；超過丟掉最舊（避免 backlog 失真）
```

---

## 8. 互動

### 8.1 點角色看資訊

```ts
// 點 Decider → 開 Sheet 顯示：
{
  agent: 'decider',
  current_state: 'thinking',
  recent_events: [  // 最近 5 筆（masked）
    { time: '13:30:15', summary: 'STK-X confidence 0.72 → entry' },
    { time: '13:25:01', summary: 'STK-Y confidence 0.45 → skip' },
  ],
  total_decisions_today: 7,
  // 注意：不顯示 reasoning 全文（只顯示 reasoning_summary）；不顯示 confidence 列表細節（避免反推 mask 表）
}
```

### 8.2 底部 Activity Timeline

橫向 marquee + 可點開展開模式：

```
[09:00] Scanner: 掃 1700 檔  →  [09:02] Scanner: 找到 12 檔
                              →  [13:30] Decider: STK-X (conf 0.72) → entry
                              →  [13:31] Trader: 等待 confirm STK-X ...
```

---

## 9. Mask Spec（cross-reference）

完整 Mask Spec 見 [`auth-and-mask.md`](auth-and-mask.md) §3。

**前端額外責任：**
- 不在 UI 顯示**任何不在 [`backend-eventbus.md`](backend-eventbus.md) §4.2 PUBLIC_WHITELIST** 的欄位（即使後端意外送出，UI 也不該渲染）
- speech bubble 文字若含 4 位數數字（防後端漏網），前端二次 strip
- 不寫 cookie / localStorage 任何 PII
- 不發 analytics（避免 IP 蒐集疑慮）

---

## 10. 目錄結構（web-public/）

```
web-public/
├── package.json
├── vite.config.ts
├── tailwind.config.ts          # extends packages/ui-tokens
├── public/
│   ├── sprites/
│   │   ├── scanner.png         # 128×128 sprite sheet
│   │   ├── pattern_analyst.png
│   │   ├── decider.png
│   │   ├── trader.png
│   │   ├── librarian.png
│   │   ├── reviewer_1.png ... reviewer_5.png
│   │   ├── proposer.png
│   │   ├── validator.png
│   │   ├── guard.png
│   │   └── _office_bg.png      # 場景背景
│   ├── robots.txt              # Allow / Disallow /api
│   └── favicon.ico
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── routes.tsx              # / Office / About
    ├── pages/
    │   ├── OfficeScene.tsx     # Canvas 主場景
    │   ├── ActivityTimeline.tsx
    │   └── About.tsx           # 完整免責 + 專案介紹
    ├── canvas/
    │   ├── gameLoop.ts
    │   ├── pathfind.ts         # BFS
    │   ├── render.ts           # ctx.drawImage 切片 sprite
    │   ├── characterStateMachine.ts
    │   └── characters/
    │       ├── Scanner.ts      # 角色配置（座位 / 預設動作）
    │       ├── PatternAnalyst.ts
    │       └── ... (9 個)
    ├── hooks/
    │   └── usePublicSSE.ts
    ├── lib/
    │   ├── eventToAction.ts    # EVENT_ROUTER（§6）
    │   └── apiClient.ts        # /api/public REST helper
    ├── stores/
    │   └── scene.ts            # Zustand
    ├── components/
    │   ├── DisclaimerBanner.tsx  # ⚠️ 不可關閉
    │   ├── AgentInfoSheet.tsx
    │   └── TimelineMarquee.tsx
    ├── locales/
    │   ├── zh-TW.json
    │   └── en.json
    └── styles/
        └── globals.css
```

---

## 11. 效能預算

| 指標 | 目標 |
|---|---|
| Bundle gzip | < 150 KB |
| Lighthouse Performance | > 90 |
| LCP | < 1.5 s |
| Tick rate | 30 Hz 穩定（節能模式 15 Hz） |
| FPS | 60（Canvas 內部 30 tick + 插值） |
| SSE 重連 | EventSource 內建，斷線 < 5s 重連 |
| Sprite 預載 | 9 角色 + bg < 500 KB 總 PNG |

---

## 12. 部署

| 環境 | URL | 備註 |
|---|---|---|
| Dev | `http://localhost:5173` | Vite dev server，proxy `/api` → backend localhost |
| Production | `https://ohmystock.example.com`（暫定） | Vercel / Cloudflare Pages，自動 HTTPS |
| Backend public API | proxy 透過 Vercel Rewrite 或同 domain | 見 [`auth-and-mask.md`](auth-and-mask.md) §5 |

---

## 13. 後續決定點

- Sprite 來源：自繪 vs 買 itch.io 付費資源 vs Metro City 開源
- 是否加音效（角色動作 / 警示）— v1 預設關
- Layout Editor（pixel-agents 有）— v1 不做，固定場景即可
- i18n 是否上 ja / ko（Vibe-Trading 有日文社群）

---

## 14. FAQ

**Q：為什麼不直接 fork pixel-agents？**
A：pixel-agents 是 VS Code Webview 工具，依賴 Claude Code JSONL 結構；ohMyStock 訊號來源不同（backend EventBus），且要嚴格 mask、嵌入網頁而非 IDE。技術精神參考，程式從零寫。

**Q：訪客拿到的 masked_symbol（STK-X）會跨 session 一致嗎？**
A：不會。Backend `SymbolMaskTable` 在 process 重啟時重置（[`backend-eventbus.md`](backend-eventbus.md) §4.3），刻意設計避免訪客累積對映表反推。

**Q：如果 backend 沒事件可推（半夜 / 週末），UI 會空嗎？**
A：UI 顯示「目前 idle，等待開盤 09:00」+ 角色靜態 idle 動畫；底部 Activity Timeline 顯示最近 24 小時歷史 event（從 backend `/api/public/recent_events?limit=50` 拉，同樣 masked）。

**Q：Canvas 不支援 SSR / SEO 不友善？**
A：Canvas 是純 client；SEO 靠 `<noscript>` fallback + 靜態 About 頁 + meta tag（[`auth-and-mask.md`](auth-and-mask.md) §4.4）。本站作品集 / demo 性質，SEO 主要靠 GitHub 反向連結。
