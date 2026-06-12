/**
 * Tier 8 — Market 個股詳情（/market/:symbol）。
 *
 * fixtures（seed_db.py seed_market_symbol，symbol 3017 專屬、now-relative）：
 *   bars_daily   70 個工作日結尾貼齊今天，base 100 + i*0.5（漲 0.50/日）
 *   rs_rating    87（as of 最後 bar 日）
 *   chip 三大法人 最後 5 bar 日 (+3,000,000/-1,000,000/+500,000) 股
 *                → 張 +3,000/-1,000/+500、日合計 +2,500、KPI 5 日 +12,500
 *   pattern      e2e-mk-pattern（kind=reject、VCP breakout 0.86、無後續
 *                entry → 結局「未進場」）
 *
 * 全部出自 SQLite cache — 零外部 API。SEPA 需 252 bars，route 只切 60
 * → 決定性 null →「—」+「資料不足」（降級狀態本身就是測點）。
 */
import { test, expect } from '@playwright/test'
import { injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

test('MK-01 報價 header：價格、漲跌紅 K、收盤日、60 日 bars', async ({
  page,
}) => {
  await page.goto('/market/3017', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '3017' })).toBeVisible()

  // 最後一日 close 134.5、前日 134 → +0.50 → data-direction="up"（紅漲）。
  await expect(page.getByText('134.5', { exact: true })).toBeVisible()
  const change = page.locator('[data-direction="up"]').first()
  await expect(change).toContainText('+0.50')

  await expect(page.getByText(/以 \d{4}-\d{2}-\d{2} 收盤計/)).toBeVisible()
  await expect(page.getByText('近 60 日 OHLCV 已載入')).toBeVisible()
  await expect(page.getByText('K 線圖（圖庫待定）')).toBeVisible()
})

test('MK-02 KPI 列：RS 87、SEPA 資料不足降級、連續買超 +12,500', async ({
  page,
}) => {
  await page.goto('/market/3017', { waitUntil: 'domcontentloaded' })

  await expect(page.getByText('RS Rank')).toBeVisible()
  await expect(page.getByText('87', { exact: true })).toBeVisible()
  await expect(page.getByText(/as of \d{4}-\d{2}-\d{2}/)).toBeVisible()

  // SEPA 需 252 bars、route 只給 60 → 決定性降級。
  await expect(page.getByText('資料不足')).toBeVisible()

  // 5 日合計 (+3000-1000+500)*5 = +12,500 張（zh-TW 千分位）。
  await expect(page.getByText('+12,500')).toBeVisible()
  await expect(page.getByText('近 5 日合計（張）')).toBeVisible()
})

test('MK-03 法人表 + pattern 表：數值/方向/結局 + 點列導向 audit', async ({
  page,
}) => {
  await page.goto('/market/3017', { waitUntil: 'domcontentloaded' })

  // 三大法人 5 列；張數固定 (+3,000 / -1,000 / +500 / 合計 +2,500)。
  await expect(
    page.getByRole('heading', { name: /三大法人（近 5 日）/ }),
  ).toBeVisible()
  await expect(page.getByText('+3,000').first()).toBeVisible()
  await expect(page.getByText('-1,000').first()).toBeVisible()
  await expect(page.getByText('+2,500').first()).toBeVisible()

  // pattern 表：VCP breakout / 0.86 / 未進場。
  await expect(
    page.getByRole('heading', { name: '近期偵測 Pattern' }),
  ).toBeVisible()
  const patternRow = page
    .getByRole('row')
    .filter({ hasText: 'VCP breakout' })
  await expect(patternRow).toBeVisible()
  await expect(patternRow).toContainText('0.86')
  await expect(patternRow).toContainText('未進場')

  // 點 pattern 列 → /audit?symbol=3017&date_from=<pattern 日期>。
  await patternRow.click()
  await expect(page).toHaveURL(
    /\/audit\?symbol=3017&date_from=\d{4}-\d{2}-\d{2}/,
  )
})

test('MK-04 無資料 symbol：404 卡片 + 返回 /market', async ({ page }) => {
  await page.goto('/market/9999', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('該 symbol 無資料')).toBeVisible()
  await expect(page.getByText(/請確認代號 9999 是否正確/)).toBeVisible()
  await page.getByRole('link', { name: /返回 \/market/ }).click()
  await expect(page).toHaveURL(/\/market$/)
})
