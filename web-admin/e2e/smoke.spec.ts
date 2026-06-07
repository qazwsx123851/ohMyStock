import { test, expect, type Page } from '@playwright/test'
import { ADMIN_TOKEN, PREVIEW_URL, TOKEN_STORAGE_KEY } from './constants'

// Static (non-parameterized) routes + their TopBar <h1> title (from
// web-admin/src/components/layout.tsx TITLE_BY_PATH). Detail routes
// (:symbol/:jobId/:slug/...) need seeded ids and are out of scope for v0 smoke.
const PAGES: { path: string; title: string }[] = [
  { path: '/', title: 'Dashboard' },
  { path: '/chat', title: '對話模式' },
  { path: '/swarm', title: 'Swarm' },
  { path: '/backtest', title: '回測' },
  { path: '/paper', title: '模擬交易' },
  { path: '/paper/orders', title: '委託歷史' },
  { path: '/market', title: '市場掃描' },
  { path: '/skills', title: 'Skills' },
  { path: '/memory', title: '長期記憶' },
  { path: '/sessions', title: '對話歷史' },
  { path: '/reviews', title: 'Reviews' },
  { path: '/proposals', title: 'Proposals' },
  { path: '/settings', title: '設定' },
]

// Benign console noise that must not fail a smoke run (empty-data 404s, SSE
// reconnects, dev-tools nags, favicon). Anything else is treated as a failure.
const CONSOLE_WHITELIST: RegExp[] = [
  /favicon/i,
  /EventSource/i,
  /ResizeObserver/i,
  /React DevTools/i,
  /Failed to load resource.*\b404\b/i,
  /net::ERR_/i,
]

function trackErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(`PAGEERROR: ${e.message}`))
  return errors
}

test.describe('web-admin smoke', () => {
  test.beforeEach(async ({ context }) => {
    // Inject the Bearer token before any app script runs so the zustand auth
    // store picks it up at init and AuthGuard lets us through (skips /login).
    await context.addInitScript(
      ([key, value]) => window.localStorage.setItem(key, value),
      [TOKEN_STORAGE_KEY, ADMIN_TOKEN] as const,
    )
  })

  for (const { path, title } of PAGES) {
    test(`page loads: ${path}`, async ({ page }) => {
      const errors = trackErrors(page)

      const resp = await page.goto(path, { waitUntil: 'domcontentloaded' })
      expect(resp?.status() ?? 0, 'navigation HTTP status').toBeLessThan(400)

      // Auth gate passed -> not bounced to /login.
      await expect(page).not.toHaveURL(/\/login/)

      // App shell + correct page rendered. Pages can render their own <h1>, so
      // scope to the TopBar (banner) heading to stay unambiguous.
      await expect(page.getByRole('navigation', { name: '主導覽' })).toBeVisible()
      await expect(
        page.getByRole('banner').getByRole('heading', { level: 1 }),
      ).toHaveText(title)

      const unexpected = errors.filter(
        (e) => !CONSOLE_WHITELIST.some((re) => re.test(e)),
      )
      expect(unexpected, `console errors on ${path}`).toEqual([])
    })
  }

  // FIXED: PaperPositionsPage now reads the { items, asof_iso, count } envelope
  // via apiFetch<PositionsOpenResponse> and `data?.items ?? []`, mirroring
  // PaperOverviewPage. (Field-name mismatch between OpenPosition and the backend
  // PositionItem is a separate, pre-existing concern — see api.ts.)
  test('page loads: /paper/positions', async ({ page }) => {
    const errors = trackErrors(page)
    const resp = await page.goto('/paper/positions', {
      waitUntil: 'domcontentloaded',
    })
    expect(resp?.status() ?? 0).toBeLessThan(400)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.getByRole('navigation', { name: '主導覽' })).toBeVisible()
    await expect(
      page.getByRole('banner').getByRole('heading', { level: 1 }),
    ).toHaveText('持倉明細')
    const unexpected = errors.filter(
      (e) => !CONSOLE_WHITELIST.some((re) => re.test(e)),
    )
    expect(unexpected).toEqual([])
  })

  // FIXED: journal `kind` taxonomy is now SSOT-aligned — JOURNAL_KIND_ALL holds
  // exactly the 5 backend _VALID_KINDS (docs/llm-decision-schema.md §4), and the
  // backend accepts a repeatable `kind` query param (IN-clause) so the multi-
  // select filter actually filters instead of 400-ing on the last value.
  test('page loads: /audit', async ({ page }) => {
    const errors = trackErrors(page)
    const resp = await page.goto('/audit', { waitUntil: 'domcontentloaded' })
    expect(resp?.status() ?? 0).toBeLessThan(400)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.getByRole('navigation', { name: '主導覽' })).toBeVisible()
    await expect(
      page.getByRole('banner').getByRole('heading', { level: 1 }),
    ).toHaveText('稽核日誌')
    const unexpected = errors.filter(
      (e) => !CONSOLE_WHITELIST.some((re) => re.test(e)),
    )
    expect(unexpected).toEqual([])
  })

  test('auth gate redirects unauthenticated to /login', async ({ browser }) => {
    // Fresh context with no token injected.
    const ctx = await browser.newContext({ baseURL: PREVIEW_URL })
    const page = await ctx.newPage()
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
    await expect(
      page.getByRole('heading', { name: 'ohMyStock 後台登入' }),
    ).toBeVisible()
    await ctx.close()
  })
})
