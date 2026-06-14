# Design — web-admin 淺/深主題切換

**日期**：2026-06-14
**範圍**：web-admin（後台）新增淺色/深色主題切換。

## 目標

讓 `index.css` 已完整定義、目前因 `index.html` 寫死 `class="dark"` 而成為死碼的 light token 復活，並提供使用者手動切換 + 記憶偏好。

## 需求（已與 boss 確認）

- **兩態**：`'light' | 'dark'`，預設 `'dark'`（維持現狀）。
- **不偵測系統偏好**（不使用 `prefers-color-scheme`）。
- **記憶偏好**：localStorage 持久化，重整後沿用。
- **首屏零閃爍（FOUC）**：採方案 A — `index.html` `<head>` 內嵌 inline script，在 React 掛載前就套好主題 class。
- **切換鈕**：TopBar 內，沿用現有 icon 按鈕樣式；`lucide` Sun/Moon 圖示。

## 非目標

- 不做三態（系統/淺/深）。
- 不偵測 `prefers-color-scheme`。
- 不改 `index.css` 既有 token（light/dark 兩套皆已齊全）。
- 不做主題切換動畫過場。

## 架構

主題狀態的唯一權威是 `<html>` 的 `.dark` class；React 與 inline script 都只讀寫它 + localStorage，互不持有重複狀態。

### 1. localStorage 契約

- key：`ohmystock.admin.theme`
- value：`'light' | 'dark'`
- 無值 / 解析失敗 → 視為 `'dark'`（預設）。

### 2. `index.html` — inline script（FOUC 防護）

移除 `<html>` 寫死的 `class="dark"`，改在 `<head>` 最前面加一段同步 inline script：

```html
<script>
  (function () {
    try {
      var t = localStorage.getItem('ohmystock.admin.theme');
      if (t !== 'light') document.documentElement.classList.add('dark');
    } catch (e) {
      document.documentElement.classList.add('dark');
    }
  })();
</script>
```

- 同步執行、在任何畫面繪製前完成 → 零閃爍。
- 唯一「主題判定」的程式邏輯與下方 store 對齊：只有明確存 `'light'` 才走淺色，其餘一律深色。

### 3. `stores.ts` — `useUiStore` 擴充

於既有 `useUiStore`（目前管 sidebar 收合）加入主題狀態，沿用同檔案的 localStorage try/catch 模式：

```ts
type UiState = {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  theme: 'light' | 'dark'
  toggleTheme: () => void
}
```

- 初始值 `initialTheme()`：讀 localStorage，非 `'light'` 一律回 `'dark'`（與 inline script 同邏輯）。
- `toggleTheme()`：翻轉值 → 寫 localStorage → 同步 `document.documentElement.classList.toggle('dark', next === 'dark')`。

> 註：初始 class 已由 inline script 設好，store 初值只需與 DOM 現況一致，不需在 mount 時再套一次（避免雙重來源）。

### 4. `layout.tsx` — TopBar 切換鈕

在 `TopBar` 的 `ml-auto` 群組內、`TpeClock` 之前，加一顆按鈕：

- 深色時顯示 `Sun`（語意：點我變亮）；淺色時顯示 `Moon`。
- `onClick={toggleTheme}`，`aria-label` 隨主題切換（「切換為淺色」/「切換為深色」）。
- className 沿用登出鈕同款（`cursor-pointer` + `focus-visible:ring-2 focus-visible:ring-ring` + hover）。

## 資料流

```
重整 → index.html inline script 讀 localStorage → 設 <html>.dark
     → React 掛載，useUiStore.theme 初值與 DOM 一致
使用者點切換鈕 → toggleTheme() → 翻 state + 寫 localStorage + toggle <html>.dark
     → Tailwind v4 .dark 變體即時重算所有 token → 全頁變色
```

## 錯誤處理

- localStorage 存取全程 try/catch（沿用既有模式）；失敗時退回預設深色，功能不中斷。

## 測試

- `stores.ts`：`toggleTheme` 翻轉值、寫 localStorage、套用/移除 `.dark`（jsdom 下驗 `document.documentElement.classList`）。
- `layout.tsx`：TopBar 渲染切換鈕、點擊呼叫 toggle、`aria-label` 隨主題變化。
- 既有 light token 對比度於設計階段已定（`index.css`），本次不另測色彩對比。

## 影響檔案

- `web-admin/index.html`（移除寫死 class + 加 inline script）
- `web-admin/src/stores.ts`（擴充 useUiStore）
- `web-admin/src/components/layout.tsx`（TopBar 切換鈕）
- 對應測試檔
