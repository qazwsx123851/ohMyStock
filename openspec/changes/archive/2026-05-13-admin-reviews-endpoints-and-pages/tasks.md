## 1. Settings 與 backend 路由骨架

- [x] 1.1 在 `src/ohmystock/config.py` 的 `Settings` class 新增欄位 `reviews_dir: Path = Path("reviews")`（與 `proposals_dir` 對齊；不加 env-var override，預設指向 repo root 同名目錄）
- [x] 1.2 新增 `src/ohmystock/api/routes/reviews.py`：宣告 `router = APIRouter(dependencies=[Depends(require_admin)])`（**不**用 `prefix=`，每個 handler 寫完整 path `@router.get("/api/admin/reviews")` — 鏡像 `routes/proposals.py`）、`_REVIEWS_ROOT_FACTORY: Callable[[], Path] = lambda: Settings().reviews_dir`、`_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)`（同 `proposals.py` 命名）、`_ALLOWED_KINDS: tuple[str, ...] = ("monthly", "quarterly", "forced", "manual")`、`logger = logging.getLogger(__name__)`（同 `proposals.py` — 不加底線前綴）
- [x] 1.3 在 `src/ohmystock/api/app.py` 引入並 `app.include_router(reviews_router)`（在現有 `proposals_router` 之後）

## 2. backend list endpoint

- [x] 2.1 實作 `_load_index(reviews_root: Path) -> tuple[list[dict], int]`：開 `<root>/_index.json`，FileNotFoundError → `([], 0)`；`json.JSONDecodeError` → 拋 `ReviewIndexCorrupted("reviews index is corrupted")` 自訂 exception
- [x] 2.2 實作 `GET /` handler：query params `kind: str | None`、`limit: int = 50`、`offset: int = 0`；步驟 a) 驗 `offset >= 0` 否則 400 `invalid_input`；b) 驗 `limit >= 1` 否則 400 `invalid_input`；c) `limit = min(limit, 200)`；d) 驗 `kind` ∈ `_ALLOWED_KINDS` 或 `None` 否則 400 `invalid_input`；e) 讀 index、套 kind filter；f) sort by `(completed_at, review_id)` desc；g) slice `[offset:offset+limit]`；h) 回 `to_success({"items": ..., "total": ..., "limit": ..., "offset": ..., "has_more": ...})`
- [x] 2.3 把 `ReviewIndexCorrupted` 加進 `map_exception_to_envelope`（500 `internal_error`，固定 message 「reviews index is corrupted」，不洩漏 stack trace）

## 3. backend detail endpoint

- [x] 3.1 實作 `_validate_review_id(review_id: str) -> None`：任一 `_INVALID_NAME_TOKENS` token 出現於 `review_id` → 拋 `HTTPException(400, "invalid_input: review_id contains forbidden token")`；BEFORE 任何 disk I/O
- [x] 3.2 實作 `_probe_files(review_dir: Path) -> dict[str, dict[str, Any]]`：對 6 個固定檔名各回 `{"exists": <bool>, "path": "<review_id>/<filename>" if exists else None}`
- [x] 3.3 實作 `_parse_proposals_created(path: Path) -> list[dict]`：regex 抽 `[<topic>](../../proposals/<slug>.md)` 與後續 3 column；遇 `本期無提案` → 回 `[]`；任何 parse error → `_logger.warning(...)` 後回 `[]`
- [x] 3.4 實作 `_extract_metrics_overall(path: Path) -> dict | None`：`json.load(metrics.json)`、回 `overall` dict 的 6 個固定 key；任一 key 缺 → 該 key 設 0；檔不存在 → `None`
- [x] 3.5 實作 `GET /{review_id}` handler：a) `_validate_review_id`；b) 取 `reviews_root`；c) 找 `_index.json` 對應 row → `summary`；d) `review_dir = root / review_id`、`dir_exists = review_dir.is_dir()`；e) 若 `summary is None and not dir_exists` → 404 `not_found`；f) `files = _probe_files(review_dir)`；g) `report = (review_dir / "report.md").read_text(encoding="utf-8") if files.report_md.exists else None`；h) `metrics_overall = _extract_metrics_overall(...)`；i) `proposals_created = _parse_proposals_created(...)`；j) `partial = (summary is None) or any(not f["exists"] for f in files.values())`；k) 回 `to_success({...})`

## 4. backend 測試

- [x] 4.1 新增 `tests/api/routes/test_reviews_endpoint.py`，建立 fixtures：`tmp_reviews_root` (monkeypatch `_REVIEWS_ROOT_FACTORY`)、`fake_index(rows: list[dict])`、`fake_review_dir(review_id, files: dict[str, str])`
- [x] 4.2 List 端測試:5 scenarios from spec — 200 mixed-kind、sort order、missing _index、empty reviews array、corrupted _index 500
- [x] 4.3 List 端 kind filter 測試:3 scenarios — narrow to one、invalid kind 400、zero matches empty
- [x] 4.4 List 端 pagination 測試:4 scenarios — limit clamp、offset<0 400、limit<1 400、has_more correctness
- [x] 4.5 Detail 端測試:6 scenarios — complete review、partial (critique crash)、proposals_created parsed、empty proposals_created、malformed proposals_created warning + empty list、path-traversal (3 sub-scenarios)
- [x] 4.6 Detail 404 測試:3 scenarios — neither dir nor index 404、dir only 200 partial、index only 200 partial
- [x] 4.7 Bearer auth 測試:2 scenarios — 401 missing on list、401 invalid on detail
- [x] 4.8 Reviews root indirection invariant:1 test 確認 `_REVIEWS_ROOT_FACTORY()` 預設回 `Settings().reviews_dir` 且 monkeypatch 生效
- [x] 4.9 Path-traversal invariant:1 test 確認 `set(routes.reviews._INVALID_NAME_TOKENS) == set(routes.proposals._INVALID_NAME_TOKENS)`（鎖兩條路由的安全策略一致）

## 5. frontend API client

- [x] 5.1 在 `web-admin/src/lib/api.ts` 新增 type alias `ReviewKind = "monthly" | "quarterly" | "forced" | "manual"`
- [x] 5.2 新增 `interface Review`（list summary, 8 keys 對齊後端 `ReviewSummary`）
- [x] 5.3 新增 `interface ReviewDetail`（review_id / partial / summary / files / report / metrics_overall / proposals_created），含 nested `ReviewFileStatus = { exists: bool; path: string | null }` 與 `ProposalCreatedRow`
- [x] 5.4 新增 `listReviews(params: { kind?: ReviewKind; limit?: number; offset?: number })`，內部 `apiFetch<ReviewsListResponse>` 並組裝 `?kind=...&limit=...&offset=...`
- [x] 5.5 新增 `getReview(reviewId: string)`，內部 `apiFetch<ReviewDetail>('/api/admin/reviews/' + encodeURIComponent(reviewId))`

## 6. frontend `/reviews` 列表頁

- [x] 6.1 新增 `web-admin/src/pages/ReviewsPage.tsx`：useSearchParams 讀 `kind` (`undefined` 表全部)、`useQuery(['reviews', kind], () => listReviews({ kind }))`
- [x] 6.2 渲染 page header `<h1>Reviews</h1>` + 一行說明
- [x] 6.3 渲染 5-tab `<KindTabs>` 自訂 button-group（**不**是 shadcn `<Tabs>` primitive；鏡像 `ProposalsPage.tsx` 的 `<StatusTabs>` 樣式：`role="tablist"`、`inline-flex rounded-md border border-input bg-muted/40 p-1`、每 tab 是 `<button role="tab" aria-selected>` 切 `bg-background shadow-sm`）；5 tabs 為 全部 / monthly / quarterly / forced / manual；change 寫回 URL search params；`全部` 對應 `searchParams.delete('kind')`
- [x] 6.4 渲染 7-col `<DataTable>`：完成時間（`YYYY-MM-DD`、title 完整 ISO、font-mono text-xs）、review_id（font-medium）、kind Badge、period（`MM-DD → MM-DD`、text-muted-foreground）、trade_count（右對齊）、win_rate（右對齊百分比 + 領頭 `TrendingUp/Down` icon、`>= 0.5` 用 text-up）、pf（右對齊 2-decimal + 領頭 `TrendingUp/Down` icon、`>= 1` 用 text-up）；所有 Trending icon `aria-hidden`
- [x] 6.5 row click + Enter → `navigate('/reviews/' + row.review_id)`
- [x] 6.6 loading state:8 個 `<Skeleton>` row
- [x] 6.7 empty (filter): "目前 <kind> 沒有 review" + Button「回到全部」
- [x] 6.8 empty (overall): "尚無 review；執行 `uv run ohmystock review --from ... --to ...` 產出第一份"
- [x] 6.9 error state: destructive Card with role="alert"、AlertCircle icon、`Button` 「重試」

## 7. frontend `/reviews/:reviewId` 細節頁

- [x] 7.1 新增 `web-admin/src/pages/ReviewDetailPage.tsx`:`const { reviewId } = useParams<{ reviewId: string }>()`、`useQuery(['review', reviewId], () => getReview(reviewId!))`
- [x] 7.2 渲染 header row:back-link「← Reviews」、`<h1>{reviewId}</h1>`、kind Badge、period 行
- [x] 7.3 partial banner:當 `data.partial` 為 true 時渲染 `Card border-warning` + `AlertTriangle` icon + 「部分節點未完成」label
- [x] 7.4 3 KPI Cards (條件:`data.summary !== null`):trade_count / win_rate / pf，套用 `>= 0.5` / `>= 1` 的 dual-encoding 規則
- [x] 7.5「本期復盤檔案」Card:6-row dense checklist (CheckCircle2 with `aria-label="已產出"` / Circle with `aria-label="缺漏"` 切換)，每 row `py-1.5`：filename `text-sm` + path `text-xs font-mono text-muted-foreground`，缺漏列 path 槽顯示 `—`
- [x] 7.6「Report」Card:`<pre className="whitespace-pre-wrap font-mono text-sm">{data.report}</pre>`；`data.report === null` 時整個 Card 不渲染
- [x] 7.7「本次產出的提案」Card:4-col table (slug / status / priority / target)，每 row 是 `<Link to={"/proposals/" + row.slug}>`；空陣列時顯示「本期無提案」
- [x] 7.8 404 empty state:`Card role="status"`（**不**是 `role="alert"`）+ `PackageSearch` icon + 「Review not found: {reviewId}」+ Link to `/reviews`
- [x] 7.9 其他 error 狀態:destructive Card with role="alert" + 「重試」按鈕

## 8. frontend route 與 side-nav

- [x] 8.1 在 `web-admin/src/App.tsx` 新增 2 條 route:`{ path: '/reviews', element: <ReviewsPage /> }` 與 `{ path: '/reviews/:reviewId', element: <ReviewDetailPage /> }`
- [x] 8.2 在 sidebar 設定（`web-admin/src/components/Sidebar.tsx` 或同等檔）新增 `Reviews` entry，icon = `ClipboardList`，**放在 `Proposals` 上方**
- [x] 8.3 確認 `/reviews/:reviewId` 觸發時 sidebar `Reviews` entry 顯示 active 樣式

## 9. 收尾

- [x] 9.1 從 repo root 跑 `uv run pytest tests/api/routes/test_reviews_endpoint.py -v`，確認全綠
- [x] 9.2 從 `web-admin/` 跑 `pnpm typecheck`（或 `pnpm tsc --noEmit`），確認無 TS 錯誤
- [x] 9.3 手動 smoke:`uv run uvicorn ohmystock.api.app:app --reload`、`pnpm dev`、登入 admin、開 `/reviews` 與 `/reviews/<an-existing-review-id>`，確認 6 區塊 + checklist + KPI + 提案連結都對
- [x] 9.4 跑 `openspec validate admin-reviews-endpoints-and-pages --strict`，確認 spec 全綠
