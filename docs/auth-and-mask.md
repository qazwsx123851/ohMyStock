# Auth & Mask — 後台認證、公開資料 Mask、合規策略

> **版本**：v1.0 ｜ **建立日期**：2026-04-27
> **對應程式**：`backend/ohmystock/auth/`、`backend/ohmystock/eventbus/serializers/public.py`、`web-public/src/components/DisclaimerBanner.tsx`
> **權威來源**：本檔為 **後台 auth + 公網 mask 策略 + SITC 合規**的唯一權威。
> **相關章節**：[`backend-eventbus.md`](backend-eventbus.md)（Serializer 程式規格）/ [`frontend-public-pixel.md`](frontend-public-pixel.md) / [`safety-and-simulation.md`](safety-and-simulation.md)（live/sim 防線）

---

## 1. 用途

ohMyStock v3 採前後台兩專案 monorepo（web-public + web-admin），對應後端兩條 SSE channel + 兩組 REST endpoint（admin / public）。本檔規範：

1. **Admin 認證**：誰能登入後台、token 怎麼簽發、middleware 如何保護
2. **Public Mask**：哪些欄位可以對公網露、哪些絕對不能
3. **合規免責**：SITC 投顧執照風險規避 + 免責 banner 文案
4. **部署拓樸**：admin / public / backend 各自部署在哪、誰能連誰

---

## 2. 後台認證設計

### 2.1 適用範圍

所有 `/api/admin/*` 端點（含 SSE `/api/admin/events` 與 REST CRUD）必須經過 `require_admin` dependency。

### 2.2 v1 機制（推薦）：簡單 Bearer Token + 限定 user

考量單一使用者（依 v1 決策 #6）+ 不想處理 OAuth callback：

```python
# backend/ohmystock/auth.py
import os
import secrets
from fastapi import Header, HTTPException

ADMIN_TOKEN = os.environ["OHMYSTOCK_ADMIN_TOKEN"]  # 啟動時 fail-fast 若未設

def require_admin(authorization: str | None = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    # 用 secrets.compare_digest 防 timing attack
    if not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token")
```

**Token 產生：**

```bash
# 啟動 backend 前，本機產一次：
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 寫入 .env：
OHMYSTOCK_ADMIN_TOKEN=<上面那段>
```

**前端使用：**

```ts
// web-admin/src/lib/api/client.ts
const token = import.meta.env.VITE_ADMIN_TOKEN;  // 從 .env.local 讀
fetch('/api/admin/events', {
  headers: { Authorization: `Bearer ${token}` },
});
```

> ⚠️ `VITE_ADMIN_TOKEN` 會被打進 admin bundle。**這是可接受的** — 因為 admin app 只在本機 / Tunnel 後跑，bundle 不對公網暴露（見 §5）。

### 2.3 v2 升級路徑（暫不做）

| 條件觸發 | 升級方案 |
|---|---|
| 想加第二個用戶（家人 demo） | JWT + 簡單 user table |
| 想從外網 admin（手機 / 出差） | GitHub OAuth（限 `qazwsx123851`） |
| 想 Audit 誰在何時操作 | 加 `auth_log` 表 |

### 2.4 反向防呆

- Backend 啟動時若 `OHMYSTOCK_ADMIN_TOKEN` 未設或長度 < 32 → **拒絕啟動**
- 全 `/api/admin/*` 路由必須掛 `Depends(require_admin)`；CI 加 lint 檢查（grep 確認）

---

## 3. 公開資料 Mask Spec

### 3.1 完整欄位表

| 欄位 | 對 web-public | 對 web-admin | 備註 |
|---|---|---|---|
| `symbol`（4 位數股票代號） | ❌ | ✅ | 公網一律換 `STK-A..STK-Z`（見 [`backend-eventbus.md`](backend-eventbus.md) §4.3 `SymbolMaskTable`） |
| `company_name`（公司中文/英文名） | ❌ | ✅ | 同上，可換成 `industry_hint`（產業類別） |
| `price`（進場 / 出場價） | ❌ | ✅ | 公網不顯示 |
| `expected_price`（預期成交價） | ❌ | ✅ | 公網不顯示 |
| `quantity`（部位數量 / 張數） | ❌ | ✅ | 公網不顯示 |
| `pnl_twd`（P&L 絕對值，TWD） | ❌ | ✅ | 公網只顯示百分比，且只在彙總層級 |
| 單筆 P&L 百分比 | ⚠️ | ✅ | 只在彙總（如「最近 5 筆平均 +1.2%」）顯示 |
| `confidence` 分數 | ✅ | ✅ | 0.00–1.00 浮點，可公開 |
| `reasoning`（原始 LLM 思考） | ❌ | ✅ | 含真 symbol，禁公開 |
| `reasoning_summary`（mask 過 4 位數代號） | ✅ | ✅ | 公網用此版本 |
| `industry_hint`（產業類別） | ✅ | ✅ | 「半導體」「金融」「電子零組件」等大類 |
| `pattern`（K 線型態名） | ✅ | ✅ | VCP / 杯柄 / 旗形等型態名公開 OK |
| 提案 metadata（status / priority / target_section） | ✅ | ✅ | 提案流程透明 |
| 提案 diff 內容（cheatsheet 文字改動） | ✅ | ✅ | 是規則改動，非個股建議 |
| 帳號 / API key / Shioaji ID / broker_order_id | ❌ | ✅ | 後台也加 mask 顯示（如 `F12***6789`） |
| Risk Gate 觸發次數 / category | ✅ | ✅ | 不含具體部位 |
| 月度 win_rate / PF / Sharpe | ✅ | ✅ | 彙總統計 |
| `query`（FTS5 查詢字串） | ❌ | ✅ | 可能含 symbol |
| `failure_reason`（WFA 失敗細節） | ❌ | ✅ | 透露策略弱點 |

### 3.2 實作位置

| 層 | 檔案 | 機制 |
|---|---|---|
| Event serialize | `backend/ohmystock/eventbus/serializers/public.py` | `PUBLIC_WHITELIST` + `DENYLIST_FIELDS`（[`backend-eventbus.md`](backend-eventbus.md) §4.2） |
| REST DTO | `backend/ohmystock/api/public/dto.py` | Pydantic models 只含白名單欄位 |
| 4 位數代號 strip | 同 serializer | `TWSE_CODE_RE = re.compile(r"\b\d{4}\b")` |
| 帳號顯示 mask（後台） | `web-admin/src/components/MaskedAccount.tsx` | `F12***6789` 顯示 |

### 3.3 SymbolMaskTable session 設計

- **Session = process 生命週期**：backend 重啟時 mask table 重置，STK-A 可能對應到不同 symbol
- **理由**：避免訪客長期觀察累積對映表反推真實 symbol
- **副作用**：跨 session 比較（「昨天 STK-X」vs「今天 STK-X」）對訪客無意義；對自己（在後台）看 raw symbol 無影響

---

## 4. SITC 投顧執照合規策略

### 4.1 法規簡述

《證券投資顧問事業管理規則》：未取得 SITC 執照不得對特定多數人「直接或間接從事證券投資分析活動」並從中取得報酬。**雖然本專案不收費**，但「公開明牌」仍可能被認定為實質投顧行為。

### 4.2 規避原則

| 原則 | 實作 |
|---|---|
| 不公開特定股票代號 / 公司名 | Mask Spec §3.1 嚴格執行 |
| 不公開「應買 / 應賣」行為，只公開「系統正在分析」事實 | `decision_made` 只露 `confidence` + `action: "entry"\|"skip"` + `masked_symbol` |
| 全頁顯眼免責 | DisclaimerBanner（不可關閉） |
| 強調教育 / 研究目的 | 每頁 `<meta name="description">` 含「education / demo」 |
| 不收費 / 不接受訂閱 | 整站無 paywall、無 email 收集表單 |

### 4.3 免責 Banner 文案

**繁中版本（公網預設）：**

```
⚠️ 本網站為 AI 系統運作展示，非投資建議。
   所有股票代號（STK-A、STK-B 等）為虛構代換，不對應任何真實標的。
   過往任何績效數字皆不代表未來表現。
```

**英文版本（為 SEO + 國際訪客備）：**

```
⚠️ This site is a technical demo of an AI agent system.
   It is NOT investment advice. All ticker symbols (STK-A, STK-B, ...) are
   anonymized placeholders and do not correspond to any real instrument.
   Past performance shown does not guarantee future results.
```

**位置：**
- 首頁頂部 sticky banner（不可 dismiss）
- 每個場景 footer 重複
- About 頁完整版（含本檔 §4.1 法規說明 + 開發者個人聲明）

### 4.4 SEO Meta

```html
<meta name="description" content="ohMyStock — Open-source educational demo of an AI agent system that simulates Taiwan stock market trading workflow. NOT investment advice." />
<meta name="robots" content="index, follow" />
<meta property="og:title" content="ohMyStock — AI Trading Agent Demo" />
<meta property="og:description" content="Watch pixel-art agents demonstrate an end-to-end LLM-driven trading research workflow. Educational only." />
```

### 4.5 robots.txt（web-public）

```
User-agent: *
Allow: /
Disallow: /api/
```

允許首頁與場景頁被索引（為了作品集曝光），但 disallow `/api/` 避免爬蟲打 SSE。

---

## 5. 部署拓樸

### 5.1 元件部署位置

| 元件 | 部署位置 | 對外暴露？ | 備註 |
|---|---|---|---|
| **web-public/** | Vercel / Cloudflare Pages | ✅ 公網 | CDN + 自動 HTTPS + 免費 tier |
| **web-admin/** | localhost:5174 / Cloudflare Tunnel | ❌（Tunnel 需 access policy） | 本機開發為主；遠端時開 Tunnel + Cloudflare Access 限定 email |
| **Backend public endpoint** | Cloudflare Tunnel → 本機 / 自管 VPS | ✅（僅 `/api/public/*`） | Vercel Rewrite proxy `/api` → backend domain |
| **Backend admin endpoint** | 同 backend host，但 only LAN IP / Tunnel + Bearer token | ❌ | 雙重保險：網路層 + token 層 |

### 5.2 拓樸圖

```
                    Internet
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   Vercel (web-public)  CF Tunnel     [絕不對外的]
        │              │              backend admin endpoints
        │ /api proxy   │              │
        ▼              ▼              ▲
   ┌────────────────────────────────────────────┐
   │  Backend (FastAPI)                          │
   │    /api/public/*  ← 對外，masked            │
   │    /api/admin/*   ← bearer token + LAN IP  │
   └────────────────────────────────────────────┘
                       │
                       ▼
                    本機 LLM Agent + SQLite

   web-admin/ 跑在 localhost:5174 → 直連 backend localhost
   出差時 → Cloudflare Tunnel + Cloudflare Access (Google OAuth, 限 mark1234549@gmail.com)
```

### 5.3 防護層次

| 層 | 機制 | 失守的話 |
|---|---|---|
| 網路層 | admin endpoint 只接 LAN IP / Tunnel | 仍有 token 擋 |
| Token 層 | `OHMYSTOCK_ADMIN_TOKEN` 32 字元 urlsafe | 仍有 IP 限制擋 |
| Bundle 層 | web-admin 不上 Vercel；訪客拿不到 admin code | — |
| Mask 層 | Backend serializer 強制 strip | `/api/public/*` 永遠看不到敏感欄位 |
| UI 層 | DisclaimerBanner 不可關閉 | 訪客明確知道是 demo |

---

## 6. E2E 測試（Playwright）

### 6.1 Mask 滲透測試

```ts
// e2e/test_public_mask.spec.ts
import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('public endpoint never leaks real symbol', async ({ page }) => {
  // 1. 開公開首頁
  await page.goto('https://ohmystock.example.com/');

  // 2. 攔截所有 SSE 回應 60 秒
  const events: string[] = [];
  page.on('response', async (response) => {
    if (response.url().includes('/api/public/events')) {
      events.push(await response.text());
    }
  });
  await page.waitForTimeout(60_000);

  const allText = events.join('\n');

  // 3. 斷言無 4 位數股票代號
  expect(allText).not.toMatch(/\b\d{4}\b/);

  // 4. 斷言無黑名單欄位名
  for (const banned of ['"symbol"', '"company_name"', '"price"', '"pnl_twd"',
                         '"account_id"', '"api_key"', '"broker_order_id"',
                         '"reasoning"', '"query"', '"failure_reason"']) {
    expect(allText).not.toContain(banned);
  }

  // 5. 斷言無常見公司名（從 fixture 載入 50 大上市公司中文名）
  const blacklist = JSON.parse(
    await readFile('e2e/fixtures/twse_top50_names.json', 'utf-8')
  );
  for (const name of blacklist) {
    expect(allText).not.toContain(name);
  }
});

test('admin endpoint requires bearer token', async ({ request }) => {
  // 無 token → 401
  const r1 = await request.get('https://admin.tunnel/api/admin/events');
  expect(r1.status()).toBe(401);

  // 錯 token → 401
  const r2 = await request.get('https://admin.tunnel/api/admin/events', {
    headers: { Authorization: 'Bearer wrong-token-here' },
  });
  expect(r2.status()).toBe(401);
});
```

### 6.2 Bundle 隔離測試

```bash
# 在 CI 跑：
pnpm --filter web-public build
grep -rE "(account_id|api_key|/api/admin)" web-public/dist/ && exit 1 || echo OK
```

---

## 7. 違規 / 漏洞應變

| 情境 | 立即動作 |
|---|---|
| 發現 mask 漏網（如 reasoning_summary 含 `2330`） | 1. 把 web-public 從 Vercel 暫時下線 2. backend 加單元測試 reproduce 3. 修 serializer 4. 重 deploy |
| 收到金管會 / 證期局來信 | 1. 立刻把 web-public 下線 2. 保留 access log 3. 找律師 4. 視情況轉私域（invite-only） |
| Admin token 外洩 | 1. backend 啟動腳本立即輪換 `OHMYSTOCK_ADMIN_TOKEN` 2. CF Tunnel access policy 重發 3. 檢查 audit log 4. 後續 v2 升 GitHub OAuth |

---

## 8. FAQ

**Q：個人專案不收費也要避 SITC？**
A：實務上罰過的案例多為「對特定多數人公開、引導獲利期待」的個人 telegram 群、YouTube 頻道，雖無收費也被認定。本專案策略：**完全不公開個股建議**，只展示「系統流程」，安全邊際最大。

**Q：為什麼 admin token 寫在 web-admin 的 `.env.local`？不安全嗎？**
A：web-admin **不對公網部署**，bundle 只在本機 / Tunnel 後跑，訪客拿不到 bundle。即使被拿到，token 還可在 backend 一鍵輪換。

**Q：產業類別會不會也太透露？**
A：產業大類（半導體 / 金融 / 電子）公開無妨；但**子類別**（如「IC 設計」「晶圓代工」）若僅有少數公司會等同點名，故 `industry_hint` 只允許 §3.1 表中的大類粒度。

**Q：自己上後台會不會被 4G IP 變動鎖死？**
A：會。設計時 admin endpoint 默認只開 `127.0.0.1` + Tunnel IP，本機開發時走 localhost 直連。出差時用 CF Tunnel + Access policy（Google OAuth 限定 email），不依賴 IP 白名單。
