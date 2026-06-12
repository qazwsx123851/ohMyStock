/**
 * Tier 3 — 讀取面 GWT 情境（docs/web-admin-user-testing-spec.md）。
 *
 * DB-01 KPI 卡 / DB-02 LiveFeed SSE / DB-B1 risk gate 三色燈 /
 * DB-B2 月度熔斷 banner / DB-B3 成本進度條 /
 * AU-01 多選 kind filter / AU-02 空結果+清空 / AU-03 status badge 推斷 /
 * PP-01 距停損%/距T1% / PP-02 紅漲綠跌雙重編碼 / PP-03 detail toggle+缺值。
 *
 * Fixtures（seed_db.py）：journal audit rows ×5 kind、開倉 e2e-pp-01/02
 * （2330 帶完整價位、0050 缺 t1/time-stop）。DB-B1 走真 yfinance/FinMind，
 * 斷言接受三色任一（unknown≠觸發）；DB-B2 以 stats API 真值決定 banner 斷言。
 */
import { test, expect } from '@playwright/test'
import { AUTH_HEADERS, injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

// ---------------------------------------------------------------------------
// DB — Dashboard
// ---------------------------------------------------------------------------

test.describe('DB Dashboard', () => {
  test('DB-01 KPI 卡：三卡渲染數值', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    for (const label of ['今日已實現損益', '持倉檔數', '待確認']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }
  })

  test('DB-B1 risk gate 三色燈：狀態與文案一致', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    const light = page.locator('[data-risk-status]')
    await expect(light).toBeVisible()
    await expect(light).toContainText(/Risk-On（綠）|注意（黃）|Risk-Off（紅）/, {
      timeout: 30_000,
    })
    const status = await light.getAttribute('data-risk-status')
    expect(['green', 'yellow', 'red']).toContain(status)
    const expected = {
      green: 'Risk-On（綠）',
      yellow: '注意（黃）',
      red: 'Risk-Off（紅）',
    }[status as 'green' | 'yellow' | 'red']
    await expect(light).toContainText(expected)
  })

  test('DB-B2 月度熔斷 banner：與 stats API 真值一致', async ({ page }) => {
    const stats = await page.request.get('/api/admin/stats/today', {
      headers: AUTH_HEADERS,
    })
    const tripped = (await stats.json()).data.monthly_breaker?.tripped === true

    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('今日已實現損益', { exact: true })).toBeVisible()
    if (tripped) {
      await expect(page.getByText('月度熔斷已觸發', { exact: false })).toBeVisible()
      await expect(page.getByText('禁止新進場至月底', { exact: false })).toBeVisible()
    } else {
      await expect(page.getByText('月度熔斷已觸發', { exact: false })).toBeHidden()
    }
  })

  test('DB-B3 成本進度條：used/budget 文字 + ≥80% 變色旗標', async ({
    page,
  }) => {
    const stats = await page.request.get('/api/admin/stats/today', {
      headers: AUTH_HEADERS,
    })
    const cost = (await stats.json()).data.cost
    const warn = cost.pct >= 80

    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('本月 LLM 成本')).toBeVisible()
    const bar = page.getByRole('progressbar').first()
    await expect(bar).toHaveAttribute('data-warn', warn ? 'true' : 'false')
    await expect(page.getByText(/USD/).first()).toBeVisible()
  })

  test('DB-02 LiveFeed SSE：dry-run validate 觸發 wfa 事件即時入列', async ({
    page,
  }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('即時事件')).toBeVisible()

    // 後端觸發（dry-run 不變動任何狀態）→ SSE 推播 → LiveFeed 出現 wfa 事件。
    const resp = await page.request.post(
      '/api/admin/proposals/2026-01-03-e2e-pr02f/validate',
      {
        headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
        data: {
          strategy: 'sma_cross',
          period: { from: '2025-01-02', to: '2025-12-30' },
          param_overrides: ['fast=10'],
          universe: ['2330'],
          wfa_windows: 5,
          in_sample_ratio: 0.7,
          initial_capital: 1000000,
          dry_run: true,
        },
      },
    )
    expect(resp.status()).toBe(200)

    await expect(
      page.locator('li', { hasText: 'wfa_started' }).first(),
    ).toBeVisible({ timeout: 15_000 })
  })
})

// ---------------------------------------------------------------------------
// AU — Audit
// ---------------------------------------------------------------------------

test.describe('AU Audit', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/audit', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('套用')).toBeVisible()
  })

  test('AU-01 多選 kind filter：只勾 reject/expire → 列表只剩該兩類', async ({
    page,
  }) => {
    // 預設全勾：先取消 entry / exit / auto_execute_audit。
    for (const kind of ['entry', 'exit', 'auto_execute_audit']) {
      await page.locator(`input[name="${kind}"]`).uncheck()
    }
    await page.getByRole('button', { name: '套用' }).click()

    await expect(page).toHaveURL(/kind=reject/)
    await expect(page).toHaveURL(/kind=expire/)
    await expect(page.getByText('e2e-au-rej')).toBeVisible()
    await expect(page.getByText('e2e-au-exp')).toBeVisible()
    // entry/exit/auto_execute_audit 列不出現。
    await expect(page.getByText('e2e-au-auto')).toBeHidden()
    await expect(page.locator('tbody').getByText('e2e-pp-01')).toBeHidden()
  })

  test('AU-02 空結果 + 清空 filter', async ({ page }) => {
    await page.getByPlaceholder('2330').fill('ZZZZ')
    await page.getByRole('button', { name: '套用' }).click()
    await expect(page.getByText('此 filter 無紀錄')).toBeVisible()

    await page.getByRole('button', { name: '清空 filter' }).click()
    await expect(page.getByText('e2e-au-rej')).toBeVisible()
  })

  test('AU-03 status badge 推斷：entry→已執行、reject→已拒絕', async ({
    page,
  }) => {
    // 以 decision_id filter 鎖定單列斷言 badge。
    await page.getByPlaceholder('d-129').fill('e2e-au-trade')
    await page.getByRole('button', { name: '套用' }).click()
    const entryRow = page.locator('tbody tr', { hasText: 'entry' }).first()
    await expect(entryRow.getByText('已執行')).toBeVisible()

    await page.getByPlaceholder('d-129').fill('e2e-au-rej')
    await page.getByRole('button', { name: '套用' }).click()
    await expect(
      page.locator('tbody tr').first().getByText('已拒絕'),
    ).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// PP — Positions
// ---------------------------------------------------------------------------

test.describe('PP Positions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/paper/positions', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('2330', { exact: true })).toBeVisible()
  })

  test('PP-01 距停損% / 距T1% 計算（回歸鎖定）', async ({ page }) => {
    // 2330：entry 600 / 停損 570（-5%）/ T1 660（+10%）。
    const row = page.locator('tbody tr', { hasText: '2330' })
    await expect(row).toContainText('570.00')
    await expect(row).toContainText('660.00')

    await row.click()
    const panel = page.locator('[data-testid="positions-detail-panel"]')
    await expect(panel).toBeVisible()
    await expect(panel.getByText('停損距離：').locator('..')).toContainText('-5')
    await expect(panel.getByText('T1 距離：').locator('..')).toContainText('+10')
    await expect(
      panel.locator('[data-direction="down"]').first(),
    ).toBeVisible()
    await expect(panel.locator('[data-direction="up"]').first()).toBeVisible()
  })

  test('PP-02 紅漲綠跌 + 方向 icon 雙重編碼', async ({ page }) => {
    const upCells = page.locator('tbody [data-direction="up"]')
    const count = await upCells.count()
    expect(count).toBeGreaterThanOrEqual(2)
    // 色 + 箭頭雙編碼（不可只靠顏色）。
    const first = upCells.first()
    await expect(first).toHaveClass(/text-up/)
    await expect(first.locator('svg')).toBeVisible()
    await expect(first).toContainText('多')
  })

  test('PP-03 detail toggle + 缺值欄位顯示 —', async ({ page }) => {
    const row2330 = page.locator('tbody tr', { hasText: '2330' })
    await row2330.click()
    await expect(
      page.locator('[data-testid="positions-detail-panel"]'),
    ).toBeVisible()
    // 再點同列 → 收合。
    await row2330.click()
    await expect(
      page.locator('[data-testid="positions-detail-panel"]'),
    ).toBeHidden()

    // 0050 缺 t1_target / time_stop_date → 表格列與 detail 以 — 呈現。
    const row0050 = page.locator('tbody tr', { hasText: '0050' })
    await expect(row0050).toContainText('—')
    await row0050.click()
    const panel = page.locator('[data-testid="positions-detail-panel"]')
    await expect(panel).toBeVisible()
    await expect(panel.getByText('T1 距離：').locator('..')).toContainText('—')
    await expect(panel.getByText('Time stop：').locator('..')).toContainText('—')
  })
})
