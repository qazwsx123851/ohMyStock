# web-admin-design-system Specification

## Purpose
TBD - created by archiving change web-admin-design-system-and-page-wireframes. Update Purpose after archive.

## Requirements

### Requirement: 17-page wireframe SSOT 文件
The system SHALL provide a single Markdown file at `docs/web-admin-page-designs.md` that documents the layout, interactions, and state contracts for every non-Dashboard route in `web-admin/src/router.tsx`. The file SHALL be added to `CLAUDE.md` §5 SSOT table as the authoritative source for web-admin page visual contracts. Each page section SHALL contain: route path, purpose, layout slots, primary data sources (admin API endpoints), required interactions, loading / empty / error / partial state behavior, SSE live-update regions (if any), keyboard shortcuts, and 紅漲綠跌 token application examples.

#### Scenario: SSOT file exists and lists all router stub routes
- **GIVEN** `web-admin/src/router.tsx` declares 17 non-Dashboard routes
- **WHEN** a reader opens `docs/web-admin-page-designs.md`
- **THEN** the file SHALL contain a section header (`## ` or `### `) for each of those 17 route paths
- **AND** every section SHALL include a "資料來源" subsection naming at least one admin API endpoint or "本頁無後端依賴"

#### Scenario: CLAUDE.md §5 references the SSOT
- **WHEN** a reader scans `CLAUDE.md` §5 「公式 / Schema 唯一權威表」
- **THEN** the table SHALL contain a row whose 唯一權威 column points to `docs/web-admin-page-designs.md`

#### Scenario: Page section documents every required state
- **GIVEN** any page section in `docs/web-admin-page-designs.md`
- **WHEN** a reader inspects the section
- **THEN** the section SHALL describe behavior for the states: `loading`, `empty`, `error`
- **AND** for pages that subscribe to SSE, the section SHALL describe the `live-update` region and reconnection-visible behavior

---

### Requirement: shadcn primitive 元件落地於 `components/ui/`
The system SHALL provide the following shadcn/ui primitive components as TypeScript source files under `web-admin/src/components/ui/`: `button.tsx`, `card.tsx`, `skeleton.tsx`, `table.tsx`, `badge.tsx`. Each primitive SHALL be the canonical shadcn implementation (Radix primitives + Tailwind classes + `cn` helper from `@/lib/utils`). The directory SHALL be treated as immutable third-party source; customization SHALL go through wrapper components in `web-admin/src/components/`, not through edits to `ui/` files. Other shadcn primitives (Dialog / Input / Label / Select / Tooltip / Drawer / Sheet / Tabs / Form / Toast / Popover / ScrollArea / Command) SHALL be deferred to whichever future per-page change first needs them.

#### Scenario: All five primitives compile
- **WHEN** `pnpm typecheck` runs in `web-admin/`
- **THEN** every file under `web-admin/src/components/ui/` SHALL compile without error
- **AND** each named export listed above SHALL be importable via `@/components/ui/<name>`

#### Scenario: Primitives use the cn utility
- **GIVEN** any file under `web-admin/src/components/ui/`
- **WHEN** the file is parsed
- **THEN** it SHALL import `cn` from `@/lib/utils` for className merging (no inline `clsx` / `twMerge` calls)

---

### Requirement: `DataTable` composite 元件
The system SHALL provide a `<DataTable>` component at `web-admin/src/components/data-table.tsx` with a generic `<T>` row type. The component SHALL accept props `rows: T[]`, `columns: Array<{ id: string; header: ReactNode; accessor: (row: T) => ReactNode; sortable?: boolean; align?: 'left' | 'right' | 'center' }>`, `loading?: boolean`, `error?: Error | null`, `emptyMessage?: ReactNode`, `onRowClick?: (row: T) => void`, `pageSize?: number`, `total?: number`, `page?: number`, `onPageChange?: (page: number) => void`. The component SHALL render: skeleton rows when `loading=true`, an error panel with a retry-affordance slot when `error` is non-null, the supplied `emptyMessage` when `rows.length === 0 && !loading && !error`, and otherwise a table built on shadcn `Table` primitives. Numeric-aligned columns (`align: 'right'`) SHALL apply `font-variant-numeric: tabular-nums` via the `.tabular` class.

#### Scenario: Loading state renders skeleton rows
- **GIVEN** `<DataTable rows={[]} loading={true} ... />`
- **WHEN** the component renders
- **THEN** the rendered DOM SHALL contain at least 3 elements with the shadcn `Skeleton` class
- **AND** no `<tbody>` rendered row SHALL contain real row data

#### Scenario: Empty state shows custom message
- **GIVEN** `<DataTable rows={[]} loading={false} error={null} emptyMessage="本月無交易紀錄" />`
- **WHEN** the component renders
- **THEN** the rendered DOM SHALL contain the text "本月無交易紀錄"

#### Scenario: Row click invokes handler
- **GIVEN** a `<DataTable>` with one row and `onRowClick` set
- **WHEN** the user clicks the row (mouse) or presses Enter while the row is keyboard-focused
- **THEN** `onRowClick` SHALL be invoked exactly once with that row

#### Scenario: Sortable header toggles asc → desc → unsorted
- **GIVEN** a column with `sortable: true`
- **WHEN** the user clicks the column header three times
- **THEN** the visible sort indicator SHALL cycle through ascending, descending, then no sort

---

### Requirement: `KpiCard` composite 元件（從 DashboardPage 抽出共用版）
The system SHALL provide a `<KpiCard>` component at `web-admin/src/components/kpi-card.tsx` that displays one KPI with props `label: string`, `value: ReactNode`, `direction?: 'up' | 'down' | 'neutral'`, `glyph?: 'auto' | ReactNode | null`, `loading?: boolean`. When `direction === 'up'` the value SHALL render with the `--up` token color and a Lucide `ArrowUp` icon (when `glyph === 'auto'`). When `direction === 'down'` the value SHALL render with the `--down` token color and a Lucide `ArrowDown` icon. When `direction === 'neutral'` or unset, no directional glyph SHALL render. The `DashboardPage` SHALL be migrated in this change to import `KpiCard` from this new component (replacing any inline KPI implementation), with no behavioral regression.

#### Scenario: Up direction renders red color and up arrow
- **GIVEN** `<KpiCard label="今日損益" value="+12,345" direction="up" />`
- **WHEN** the component renders
- **THEN** the value-bearing element's computed text color SHALL match the `--up` token
- **AND** the rendered DOM SHALL contain an SVG with `aria-hidden="true"` and a `lucide-arrow-up` class or equivalent identifier

#### Scenario: Down direction renders green color and down arrow
- **GIVEN** `<KpiCard label="本週實現損益" value="-3,400" direction="down" />`
- **WHEN** the component renders
- **THEN** the value-bearing element's computed text color SHALL match the `--down` token
- **AND** the rendered DOM SHALL contain a `lucide-arrow-down` SVG

#### Scenario: Loading shows skeleton
- **GIVEN** `<KpiCard label="今日損益" loading />`
- **WHEN** the component renders
- **THEN** the rendered DOM SHALL contain a shadcn `Skeleton` element in place of the value

---

### Requirement: `StatusBadge` 元件支援 7 種狀態
The system SHALL provide a `<StatusBadge>` component at `web-admin/src/components/status-badge.tsx` that accepts `status: 'pending' | 'approved' | 'rejected' | 'executed' | 'expired' | 'canceled' | 'errored'` and renders a shadcn `Badge` with both a status-specific color and a status-specific Lucide icon. Color SHALL never be the only signal — every status SHALL include a glyph or icon visible at 16 px so colorblind users can distinguish states.

#### Scenario: Each status has a unique color + glyph pair
- **WHEN** `<StatusBadge>` is rendered once for each of the 7 statuses
- **THEN** every rendered element SHALL contain an SVG icon
- **AND** no two statuses SHALL share both the same icon AND the same computed background color

#### Scenario: Errored status maps to destructive token
- **GIVEN** `<StatusBadge status="errored" />`
- **WHEN** the component renders
- **THEN** the badge's computed background or border color SHALL match the `--destructive` token

---

### Requirement: Density mode token (compact / comfortable)
The system SHALL define two CSS custom properties in `web-admin/src/index.css` under `:root`: `--density-row-h: 36px` (default `comfortable`) and `--density-row-h-compact: 28px`. Components that render tabular rows (`DataTable`, future tables) SHALL respect a `density?: 'compact' | 'comfortable'` prop, defaulting to `comfortable`. When `density='compact'`, the component SHALL apply `min-height: var(--density-row-h-compact)` to every row. The choice SHALL be local to the component (not a global theme switch in this change).

#### Scenario: Density tokens are accessible
- **WHEN** the app boots
- **THEN** `getComputedStyle(document.documentElement).getPropertyValue('--density-row-h')` SHALL return `36px`
- **AND** `--density-row-h-compact` SHALL return `28px`

#### Scenario: DataTable compact mode shrinks rows
- **GIVEN** `<DataTable density="compact" rows={[oneRow]} ... />`
- **WHEN** the component renders
- **THEN** the rendered row's computed `min-height` SHALL be 28 px

---

### Requirement: 共用元件的單元測試 + a11y 涵蓋率
The system SHALL include vitest + React Testing Library tests for each composite component (`DataTable`, `KpiCard`, `StatusBadge`). Every component test file SHALL include at least one assertion that exercises keyboard navigation (`Tab` or `Enter`) where the component supports it, and at least one assertion checking `aria-*` attributes appropriate to the component (e.g. `aria-sort` for DataTable headers, `aria-hidden` on decorative icons).

#### Scenario: Test file exists per composite component
- **WHEN** `pnpm test` runs in `web-admin/`
- **THEN** there SHALL be at least one passing test file matching `data-table.test.tsx`, `kpi-card.test.tsx`, and `status-badge.test.tsx`

#### Scenario: DataTable test verifies aria-sort and Enter row activation
- **GIVEN** the test file `data-table.test.tsx`
- **WHEN** its tests are inspected
- **THEN** at least one assertion SHALL verify that a sortable column header has `aria-sort` set to `"ascending"`, `"descending"`, or `"none"`
- **AND** at least one assertion SHALL verify that pressing `Enter` on a focused row invokes `onRowClick`
