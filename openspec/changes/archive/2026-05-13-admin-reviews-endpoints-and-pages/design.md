## Context

`post-trade-review-pipeline` v0 已上線並落檔 `reviews/<review_id>/` 6 個檔 + `_index.json`；`admin-proposals-endpoints` / `web-admin-proposals-pages` 已上線且兩條 read-only 端點 + 兩個 React route 的設計語彙穩定（envelope wrapping、Bearer auth、test-override factory、path-traversal validation、無 markdown parser 的 `<pre>` 渲染、Card-per-section layout、destructive-Card error state、SSE-less data flow）。本 change 在同一條路線上加 review 視角，源於同一份磁碟產物。

`_index.json` 是首選資料來源（已被 pipeline atomic-update），但它**只含 summary 欄位**——detail view 還是得讀 review 目錄裡的 `report.md` / `metrics.json` / `proposals_created.md` 三個檔。`data.json` / `attribution.json` / `critique.md` 在 v0 **不**回傳完整內容（前兩者太大、後者要 markdown render），只在 detail payload 標檔案存在與否，讓未來版本可加路由再讀。

## Goals / Non-Goals

**Goals:**
- 把 `reviews/_index.json` 與 `reviews/<review_id>/` 暴露成 admin 視角的 2 條 GET endpoint，加上 2 個 React route 直接消費。
- 鏡像 `admin-proposals-endpoints-and-pages` 已驗證過的設計語彙：`Depends(require_admin)`、`{ok,data,error}` envelope、`_REVIEWS_ROOT_FACTORY` test seam、path-traversal-before-IO、no markdown parser、Card-per-section、無 SSE。
- 容忍中途節點失敗的半套 review：detail 回 200 + `partial: true` + 已存在檔列表，**不**回 404 / 500。
- 讓「review 產出哪些 proposal」可一鍵跳到 `/proposals/<slug>`（pages 之間的導航閉環）。

**Non-Goals:**
- 不做 review 觸發 / 重跑 / 編輯 UI；CLI `uv run ohmystock review ...` 仍是唯一寫入端。
- 不渲染 `report.md` / `critique.md` 為 markdown（用 `<pre>`，鏡像 proposals body）；markdown renderer 留待後續 change。
- 不回 `data.json` / `attribution.json` / `critique.md` 完整內容；只標檔案存在與否。
- 不做 cross-period 比較圖、KPI timeseries、`_golden/` 子集瀏覽。
- 不寫 `_index.json`、不動 pipeline、不加 EventBus event、不加排程。
- 不做 LLM cost 顯示（cost row 已寫入 `llm_costs` 表，後續可另開 change 做 `/audit` cost 子頁）。

## Decisions

### D1：以 `_index.json` 為 list endpoint 唯一來源，不掃目錄
**選擇**：`GET /api/admin/reviews` 直接 `json.load(_index.json)`，回 `reviews[]` slice（套 limit/offset + 可選 `?kind=` filter）。`_index.json` 不存在 → 200 + `{items: [], total: 0}`，**不**走 fallback 掃目錄。

**對照** admin-proposals-endpoints：proposals 走 4-dir 掃描，因為 proposal 沒有 `_index`。reviews 有 atomic-rename 維護的 `_index.json`（已由 pipeline spec 保證 single-source-of-truth），重複工是不必要的；目錄掃描還會把半套 review（pipeline 中途 crash）誤列為「完成」，反而失真。

**替代案**：（a）掃 `reviews/*/` 為主 + `_index.json` 為 cache。被否——pipeline 已保證 `_index.json` 一致，掃目錄是過度防禦。（b）合併兩者（掃目錄找 orphan review folder + `_index.json` 為主表）。被否——v0 不處理 orphan，留待 housekeeping CLI。

### D2：detail endpoint 回複合 payload，但**不**回大檔內容
**回**：`_index.json` 對應 row + 6 檔的 `{exists, path}` checklist + `report.md` 全文 + `proposals_created.md` 解析出的 `{slug, status, priority, target}[]` + `metrics.overall` 摘要（6–7 欄）。

**不回**：完整 `data.json` / `attribution.json` / `metrics.json` tree / `critique.md`。

**理由**：`data.json` 動輒 100KB+（每筆 trade 含 OHLCV + post-exit 21 日 close），browser 不需要；`attribution.json` 同理。`critique.md` 是 markdown，v0 不渲染就不送。`metrics.json` 只送 `overall` 6–7 欄夠 detail page 的 3 個 KPI Card 用。完整檔內容後續若需要可加 `/api/admin/reviews/{id}/files/{name}` 路由（**本 change 不做**）。

### D3：partial review 不是錯誤
**規則**：如果 `_index.json` 不含 `review_id`（pipeline 中途 crash 沒走到 `_index` upsert）→ detail 仍 try open `reviews/<review_id>/`；目錄存在 → 200 + `partial: true` + 已存在檔的 checklist + `summary: null`。目錄也不存在 → 404 `not_found`。

**理由**：pipeline spec 明說「任一節點拋例外 SHALL 中止 pipeline，已落檔的中間檔 SHALL 保留以利 debug」——半套 review 是合法工件，admin 必須能看到它（看到才知道在哪卡住）。

### D4：path-traversal 防禦 mirror proposals
`{review_id}` 含 `/`, `\`, `..`, `os.sep` 任一 → 400 `invalid_input`，BEFORE 任何 disk I/O。route 模組私有常數 `_INVALID_NAME_TOKENS_LOCAL` 與 proposals 各自宣告（兩者不共用 module global），由 invariant test 釘住內容相等。

**對照**：proposals 走完全相同規則。v0 一致勝過共用——共用 module 是後續 refactor 候選。

### D5：path indirection 用 `_REVIEWS_ROOT_FACTORY`
Module-level `_REVIEWS_ROOT_FACTORY: Callable[[], Path]` 預設回 `Settings().reviews_dir`。每 request 呼叫一次。測試可 `monkeypatch.setattr(routes.reviews, "_REVIEWS_ROOT_FACTORY", lambda: tmp_path)`。

**理由**：與 proposals `_PROPOSALS_ROOT_FACTORY` 完全平行；conftest 不需新增 fixture 樣板，照抄 proposals 測試的 monkeypatch 寫法即可。

### D6：proposals_created.md 解析用 regex，不用 markdown parser
`proposals_created.md` 是固定 markdown table 格式（README §4.6 範例已釘住欄位順序）。route 用單行 regex 抽 `[<topic>](<rel-path>)` 與 status / priority 欄；遇 0-row「本期無提案」字樣 → 回 `[]`。

**理由**：避免引入 markdown lib；regex 對固定欄位夠用；異常（檔存在但格式破）→ log warning + 回 `[]`，**不** 422——report.md 才是 detail 的主要內容。

### D7：list endpoint 排序與 paging 規則 mirror proposals
- ORDER BY `completed_at DESC`，ties 按 `review_id DESC`（穩定）
- `limit` 預設 50、≤200 silent clamp；`offset` <0 → 400 `invalid_input`
- `?kind=` 接 4 個 Literal (`monthly`/`quarterly`/`forced`/`manual`)；其他值 → 400 `invalid_input`

**理由**：與 proposals 端點完全平行語意，前端 hook 可同形複用。

### D8：紅漲綠跌雙重編碼（list 頁的 `win_rate` 欄）
`win_rate >= 0.5` → `text-up` + `TrendingUp` Lucide icon；`< 0.5` → `text-down` + `TrendingDown`。**Color is never the only signal**——配對 icon 確保色盲使用者仍能讀到方向。

**對照** proposals 頁刻意全用 neutral `<Badge variant="secondary">`（proposal 無價格語意）。reviews 有 metric 數字，套用 web-admin shell SSOT 的紅漲綠跌規則是合適的。

### D9：detail 頁 6 檔 checklist 用 `<CheckCircle2>` / `<Circle>` 區分
存在 → `<CheckCircle2 className="text-muted-foreground">`；缺漏 → `<Circle className="text-muted-foreground/50">`。`partial: true` 時 Card 外框 `border-warning`，並在頂端 `<AlertTriangle className="text-warning">` + 「部分節點未完成」label。

**對照** web-admin Settings 頁的 `auto_execute=false → border-warning + AlertTriangle` 規則（同 dual-encoding 模式）。

### D10：side-nav `Reviews` entry 放在 `Proposals` 上方
順序：`Dashboard / Market / Backtest / Paper / Skills / Memory / Reviews / Proposals / Sessions / Settings / Audit`。

**理由**：Phase 5 迴圈是「Review → Proposal → Merge」，UI 流由上往下也應對齊。

## Risks / Trade-offs

- **[Risk] `_index.json` 與目錄狀態漂移**（人手 rm 一個 review folder 但忘了改 `_index.json`）→ **Mitigation**：list endpoint 信任 `_index.json`（D1），detail 端會 catch `FileNotFoundError`（D3）並回 partial。housekeeping 留 v1+。
- **[Risk] `report.md` 很大時拖慢 detail response** → **Mitigation**：實測 v0 `report.md` < 50KB，整檔送出可接受；若日後超過 200KB 再加 `?body=summary` 參數。
- **[Risk] `proposals_created.md` 格式漂移**（pipeline proposer 改 markdown 樣式）→ **Mitigation**：regex 寬容（找不到 link 就回 `[]` + log warning），不 422。pipeline spec 對表頭欄位順序未強制，未來若改格式應同步更新本 change 的解析 regex。
- **[Risk] 半套 review 顯示誤導**（看到 partial 以為 review 已完成）→ **Mitigation**：detail page 顯眼的 `border-warning` Card + 中文 label「部分節點未完成」+ 6 檔 checklist。
- **[Trade-off] 不渲染 markdown** → 失去 link 可點性與 heading 樣式，但保持 v0 簡單；後續可加 react-markdown，不需改 endpoint。

## Migration Plan

無 schema migration。實作順序：

1. `Settings.reviews_dir` 欄位（最小擴充）+ 確認 `reviews/` 目錄存在於 repo root（已存在 `reviews/README.md`）
2. backend `routes/reviews.py` + mount on `app.py`
3. backend 測試（hit 真實 `tmp_path` fixture，monkeypatch factory）
4. frontend `lib/api.ts` 型別與 fetch helper
5. frontend `ReviewsPage.tsx` / `ReviewDetailPage.tsx` + route + side-nav

rollback：revert commit；無 schema、無持久狀態。

## Open Questions

無——所有 design decision 都鏡像已合併的 admin-proposals-endpoints-and-pages。若實作過程發現 partial-review 形狀比預期複雜（例如 `_index.json` row 與目錄不一致），暫停並更新 design.md 與本 change 的 spec scenarios。
