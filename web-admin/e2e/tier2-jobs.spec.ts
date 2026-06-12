/**
 * Tier 2 — 觸發長任務 GWT 情境（docs/web-admin-user-testing-spec.md）。
 *
 * SW-01 swarm 觸發 → 導向 DAG / SW-02 DAG 節點狀態 /
 * BT-01 backtest 提交 → 列表刷新 / BT-02 結果頁 / BT-03 表單驗證錯誤 /
 * SC-01 screener 觸發 → 就地結果 / SC-02 screener SSE 事件。
 *
 * Swarm 一律走 dry-run（不呼叫 LLM、不寫檔、零成本）；backtest 同步執行、
 * 吃 seeded bars_daily（2330 上漲盤）；screener 用 custom universe + 過去
 * asof 以走快取路徑。
 */
import { test, expect } from '@playwright/test'
import { AUTH_HEADERS, injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

// ---------------------------------------------------------------------------
// SW — Swarm
// ---------------------------------------------------------------------------

test('SW-01 swarm 觸發（dry-run）→ 導向 run 詳情頁', async ({ page }) => {
  // dry-run 為同步執行，journal 資料多時可超過預設 30s。
  test.setTimeout(180_000)
  await page.goto('/swarm', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('main').getByRole('heading', { name: 'Swarm' }),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Run…' }).first().click()
  // dry-run 預設勾選（安全預設）。
  await expect(page.locator('#swarm-dry-run')).toBeChecked()
  await page.getByLabel('起始日').fill(isoDaysAgo(30))
  await page.getByLabel('結束日').fill(isoDaysAgo(0))

  const respPromise = page.waitForResponse(
    (r) => r.url().includes('/api/admin/swarm/runs'),
    { timeout: 150_000 },
  )
  await page.getByRole('button', { name: 'Submit' }).click()
  const resp = await respPromise
  expect(resp.status()).toBeLessThan(300)
  const row = (await resp.json()).data
  expect(['completed', 'failed']).toContain(row.status)

  // toast + 導向 /swarm/:preset/:runId。
  await expect(page).toHaveURL(new RegExp(`/swarm/${row.preset}/${row.id}`))
  await expect(page.getByText('run_id')).toBeVisible()
  await expect(page.locator('code', { hasText: row.id }).first()).toBeVisible()
})

test('SW-02 run 詳情頁：DAG 節點呈現各自終態', async ({ page }) => {
  // 取最近一筆 run（SW-01 產生）直接進詳情頁。
  const runs = await page.request.get('/api/admin/swarm/runs?limit=1', {
    headers: AUTH_HEADERS,
  })
  const item = (await runs.json()).data.items?.[0]
  expect(item).toBeTruthy()

  await page.goto(`/swarm/${item.preset}/${item.id}`, {
    waitUntil: 'domcontentloaded',
  })
  await expect(page.getByText('run_id')).toBeVisible()
  // 狀態 badge（completed → secondary / failed → destructive）。
  await expect(page.getByText(item.status, { exact: true }).first()).toBeVisible()
  // 節點 DAG stepper 渲染（phase5-review preset 五節點；內容區塊展開後才有
  // id，恆在的是 aria-controls 的 toggle 列）。
  const nodeRows = page.locator('[aria-controls^="swarm-node-"]')
  expect(await nodeRows.count()).toBeGreaterThanOrEqual(5)
})

// ---------------------------------------------------------------------------
// BT — Backtest
// ---------------------------------------------------------------------------

test('BT-01 backtest 提交 → 同步完成 → 歷史列表刷新', async ({ page }) => {
  await page.goto('/backtest', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('main').getByRole('heading', { name: '回測', exact: true }),
  ).toBeVisible()

  await page.getByLabel('strategy').selectOption('sma_cross')
  await page.getByLabel('custom symbols input').fill('2330')
  await page.getByLabel('custom symbols input').press('Enter')
  await expect(page.locator('[data-chip]', { hasText: '2330' })).toBeVisible()
  await page.getByLabel('period from').fill('2025-01-02')
  await page.getByLabel('period to').fill('2025-12-30')

  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/api/admin/backtest/run'),
  )
  await page.getByRole('button', { name: '跑回測' }).click()
  const resp = await respPromise
  expect(resp.status()).toBe(200)
  const data = (await resp.json()).data
  expect(data.status).toBe('completed')

  // 歷史列表刷新出現新 job（完成 badge）。
  await expect(page.getByText('完成').first()).toBeVisible()
  await expect(
    page.locator('tbody tr', { hasText: '2025-01-02' }).first(),
  ).toBeVisible()
})

test('BT-02 點列 → 結果頁渲染指標', async ({ page }) => {
  await page.goto('/backtest', { waitUntil: 'domcontentloaded' })
  // BT-01 已產生至少一筆 completed job。
  const row = page.locator('tbody tr', { hasText: '完成' }).first()
  await expect(row).toBeVisible()
  await row.click()
  await expect(page).toHaveURL(/\/backtest\/[0-9a-f-]+/i)
  // 結果頁渲染（期間資訊存在，不綁定特定數值）。
  await expect(page.getByText(/2025-01-02/).first()).toBeVisible()
})

test('BT-03 表單驗證：無 symbols 提交 → 錯誤卡 + 可重試', async ({
  page,
}) => {
  await page.goto('/backtest', { waitUntil: 'domcontentloaded' })
  await page.getByLabel('period from').fill('2025-01-02')
  await page.getByLabel('period to').fill('2025-12-30')

  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/api/admin/backtest/run'),
  )
  await page.getByRole('button', { name: '跑回測' }).click()
  const resp = await respPromise
  expect(resp.status()).toBeGreaterThanOrEqual(400)

  await expect(page.getByText('backtest.run 失敗', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: '重試' })).toBeVisible()
})

// ---------------------------------------------------------------------------
// SC — Screener
// ---------------------------------------------------------------------------

test('SC-01 screener 觸發（custom universe）→ 就地顯示結果或無命中', async ({
  page,
}) => {
  await page.goto('/market', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('main').getByRole('heading', { name: '市場掃描' }),
  ).toBeVisible()

  await page.getByLabel('universe').selectOption('custom')
  await page.getByLabel('custom symbols input').fill('2330')
  await page.getByLabel('custom symbols input').press('Enter')
  await page.getByLabel('asof date').fill('2025-12-30')

  const respPromise = page.waitForResponse(
    (r) => r.url().includes('/api/admin/screener/run'),
    { timeout: 60_000 },
  )
  await page.getByRole('button', { name: '跑 screener' }).click()
  const resp = await respPromise

  if (resp.status() === 200) {
    // 就地結果：命中表格或「本次掃描無命中」。
    await expect(
      page
        .getByText('本次掃描無命中')
        .or(page.locator('tbody tr').first()),
    ).toBeVisible({ timeout: 15_000 })
  } else {
    // 資料來源不可用時：錯誤卡就地顯示（不導頁、不崩潰）。
    await expect(
      page.getByText('screener.run 失敗', { exact: false }),
    ).toBeVisible()
  }
})

test('SC-02 screener SSE：started/completed 事件進 Dashboard LiveFeed', async ({
  page,
}) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('即時事件')).toBeVisible()

  const resp = await page.request.post('/api/admin/screener/run', {
    headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
    data: {
      universe: 'custom',
      custom_symbols: ['2330'],
      asof_date: '2025-12-30',
    },
    timeout: 60_000,
  })
  // 不論 screener 成敗，started 事件都應已推播。
  expect([200, 422, 500, 502, 503]).toContain(resp.status())

  await expect(
    page.locator('li', { hasText: 'screener_started' }).first(),
  ).toBeVisible({ timeout: 15_000 })
})
