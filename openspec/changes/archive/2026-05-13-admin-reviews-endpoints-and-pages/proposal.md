## Why

Phase 5 復盤 pipeline 已能寫出 `reviews/<review_id>/`（6 個檔 + `_index.json`），admin proposals 頁也已上線；但目前**沒有任何 UI 可以看 review 結果**——要讀 `report.md`、確認某條 critique 引用的 `metrics.json` 數字、或追到該次復盤產出哪些提案，都得 `cat` 檔案或在編輯器手動翻目錄。這條缺口讓「review → proposal → merge」自我改進迴圈在 admin 視角是斷的。本 change 補上 `/reviews` 列表 + `/reviews/:reviewId` 細節兩頁（read-only），對應 2 個 Bearer-auth GET endpoint，把磁碟上的 review 輸出原樣呈現出來。

## What Changes

- **新增 capability** `admin-reviews-endpoints` — 2 個 Bearer-auth GET endpoint：
  - `GET /api/admin/reviews` — 從 `<reviews_root>/_index.json` 讀出 `reviews[]` 陣列，回 paginated summary（含 status filter `?kind=` 收 `monthly`/`quarterly`/`forced`/`manual`）。`_index.json` 不存在或為空 → 200 + 空陣列。
  - `GET /api/admin/reviews/{review_id}` — 回該 review 的完整 detail：`_index.json` 的對應 row + 6 個檔的存在/路徑 + `report.md` 全文 + `proposals_created.md` 解析出的 proposal-link 表 + `metrics.overall` 摘要（從 `metrics.json` 抽 6–7 個關鍵欄位，不回完整 metrics tree）。檔缺漏（如 critic 拋例外只留半套）→ 在 payload 標 `partial: true` + 列已存在檔，不 404。
  - path-traversal 防禦對 `{review_id}` 同 admin-proposals-endpoints 的規則（`/`, `\`, `..`, `os.sep` 進 review_id → 400 `invalid_input`）。
  - `_REVIEWS_ROOT_FACTORY: Callable[[], Path]` test-override seam（mirror proposals `_PROPOSALS_ROOT_FACTORY`）。

- **新增 capability** `web-admin-reviews-pages` — 2 個 React route 取代 stub：
  - `/reviews` — h1 + 一行說明 + 5-tab status filter（全部 / monthly / quarterly / forced / manual，URL search param 持久化）+ 6-col `<DataTable>`（completed_at / review_id / kind `<Badge variant="secondary">` / period / trade_count / win_rate + pf 雙欄）。click row → `/reviews/<review_id>`。**紅漲綠跌雙重編碼**：`win_rate >= 0.5` → `text-up` + `TrendingUp`；`< 0.5` → `text-down` + `TrendingDown`。
  - `/reviews/:reviewId` — back-link + h1 + kind/period badge + 3 個 KPI Card（`trade_count` / `win_rate` / `pf`）+ "本期復盤檔案" `Card`（6 個檔的存在狀態 checklist；`partial: true` 時加 `border-warning` + `AlertTriangle` + 「部分節點未完成」標記）+ "Report" `Card` 用 `<pre className="whitespace-pre-wrap font-mono text-sm">` 渲染 `report.md` 全文（**不**用 markdown parser，鏡像 proposals detail 做法）+ "本次產出的提案" `Card` 列 `proposals_created.md` 解析出的 link 表（item click → `/proposals/<slug>`）。404 `not_found` 顯示 empty state；422 `malformed_review` 顯示 destructive Card（無 retry）。
  - **無**：edit / re-run review 按鈕、SSE live-update、`/reviews/:reviewId/critique` 子頁、markdown renderer、bulk operations、cross-period 比較圖。皆為意圖性 deferred。

- **新增 Settings 欄位** `reviews_dir: Path = Path("reviews")` 於 `src/ohmystock/config.py`（與 `proposals_dir` 對齊）。

- **新增 `Reviews` 連結到 web-admin 側邊欄** — 出現於 `Proposals` 上方（同屬 Phase 5 自我改進迴圈）。

## Capabilities

### New Capabilities
- `admin-reviews-endpoints`: Bearer-auth read-only 端點，把 `reviews/<review_id>/` 與 `reviews/_index.json` 的內容以統一 `{ok,data,error}` envelope 暴露給 web-admin。
- `web-admin-reviews-pages`: `/reviews` 列表頁與 `/reviews/:reviewId` 細節頁，read-only，鏡像 proposals 頁的設計語彙。

### Modified Capabilities
（無——本 change 不修改既有 `post-trade-review-pipeline` / `post-trade-review-cli` / `proposal-*` 任何 requirement。Settings 新增 `reviews_dir` 屬擴充而非 spec 行為變更。）

## Impact

- **Code 新增**：
  - `src/ohmystock/api/routes/reviews.py`（路由模組 + `_REVIEWS_ROOT_FACTORY` + path-traversal 防禦 + `_index.json` 讀取 + per-review 檔案探測 + `proposals_created.md` link 解析）
  - `src/ohmystock/api/app.py`（mount router）
  - `web-admin/src/pages/ReviewsPage.tsx`（列表）
  - `web-admin/src/pages/ReviewDetailPage.tsx`（細節）
  - `web-admin/src/lib/api.ts`（`listReviews` / `getReview` 兩個 fetch helper + `Review` / `ReviewDetail` / `ReviewKind` 型別）
  - `web-admin/src/App.tsx`（2 條 route + side-nav 加 `Reviews` entry）
- **Code 修改**：
  - `src/ohmystock/config.py`（新增 `reviews_dir: Path = Path("reviews")` 欄位，預設指向 repo root 同名目錄）
- **Code 刪除**：無（`/reviews` 與 `/reviews/:reviewId` 此次新增 routes，不是取代 stub——目前 web-admin 沒有 reviews stub）
- **無**：DB migration、broker / journal / pipeline 程式碼變動、新增 LLM 呼叫、新增 EventBus event。本 change 完全 read-only 對既有磁碟產物。
- **CLAUDE.md §5 SSOT table 新增一列** by archive step（pattern 同 admin-proposals-endpoints）。
