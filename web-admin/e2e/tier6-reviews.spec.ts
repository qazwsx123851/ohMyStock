/**
 * Tier 6 — Reviews（/reviews, /reviews/:id）。
 *
 * fixtures（seed_db.py seed_reviews → REVIEWS_DIR temp 目錄）：
 *   2026-05-e2e-monthly   monthly、6 檔齊全（partial=false）、提案表 1 列
 *                         連到 terminal 提案 e2e-pr05m（tier1 跑完仍穩定）
 *   2026-04-e2e-quarterly quarterly、只有 report.md（partial=true）
 */
import { test, expect } from '@playwright/test'
import { injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

test('RV-01 列表：兩列 + kind badge + 共 N/N 筆', async ({ page }) => {
  await page.goto('/reviews', { waitUntil: 'domcontentloaded' })
  // TopBar h1 與頁面 h1 同名 — scope main 避開 strict violation。
  await expect(
    page.getByRole('main').getByRole('heading', { name: 'Reviews' }),
  ).toBeVisible()
  await expect(page.getByText('共 2/2 筆')).toBeVisible()

  const monthlyRow = page
    .getByRole('row')
    .filter({ hasText: '2026-05-e2e-monthly' })
  await expect(monthlyRow).toBeVisible()
  await expect(monthlyRow).toContainText('monthly')
  await expect(monthlyRow).toContainText('58.3%')
  await expect(monthlyRow).toContainText('1.42')
  await expect(
    page.getByRole('row').filter({ hasText: '2026-04-e2e-quarterly' }),
  ).toBeVisible()
})

test('RV-02 kind tab filter：URL 同步 + forced 空狀態回到全部', async ({
  page,
}) => {
  await page.goto('/reviews', { waitUntil: 'domcontentloaded' })

  await page.getByRole('tab', { name: 'quarterly' }).click()
  await expect(page).toHaveURL(/\?kind=quarterly/)
  await expect(page.getByText('2026-04-e2e-quarterly')).toBeVisible()
  await expect(page.getByText('2026-05-e2e-monthly')).toHaveCount(0)

  await page.getByRole('tab', { name: 'forced' }).click()
  await expect(page.getByText(/目前\s*forced\s*沒有 review/)).toBeVisible()
  await page.getByRole('button', { name: '回到全部' }).click()
  await expect(page).not.toHaveURL(/kind=/)
  await expect(page.getByText('2026-05-e2e-monthly')).toBeVisible()
})

test('RV-03 monthly 詳情：KPI、6 檔已產出、report 內文、提案表跨頁', async ({
  page,
}) => {
  await page.goto('/reviews', { waitUntil: 'domcontentloaded' })
  await page
    .getByRole('row')
    .filter({ hasText: '2026-05-e2e-monthly' })
    .click()
  await expect(page).toHaveURL(/\/reviews\/2026-05-e2e-monthly/)

  // KPI tiles（summary 來自 _index.json）。
  // exact:true — report <pre> 全文也含 58.3% / 1.42，避免撞 KPI span。
  await expect(page.getByText('期間交易筆數')).toBeVisible()
  await expect(page.getByText('12', { exact: true })).toBeVisible()
  await expect(page.getByText('58.3%', { exact: true })).toBeVisible()
  await expect(page.getByText('1.42', { exact: true })).toBeVisible()

  // 6 檔全部已產出、無 partial banner。
  await expect(page.getByLabel('已產出')).toHaveCount(6)
  await expect(page.getByText('部分節點未完成')).toHaveCount(0)

  // report.md 全文以 <pre> 呈現。
  await expect(page.getByText('e2e 五月復盤報告')).toBeVisible()

  // 提案表 1 列 → 點 slug 跨到 proposal 詳情。
  await page
    .getByRole('link', { name: '2026-01-06-e2e-pr05m' })
    .click()
  await expect(page).toHaveURL(/\/proposals\/2026-01-06-e2e-pr05m/)
})

test('RV-04 partial 詳情：banner + 缺漏 checklist + 本期無提案', async ({
  page,
}) => {
  await page.goto('/reviews/2026-04-e2e-quarterly', {
    waitUntil: 'domcontentloaded',
  })
  await expect(page.getByText('部分節點未完成')).toBeVisible()
  await expect(page.getByLabel('已產出')).toHaveCount(1) // 只有 report.md
  await expect(page.getByLabel('缺漏')).toHaveCount(5)
  await expect(page.getByText('本期無提案')).toBeVisible()
})

test('RV-05 不存在的 review：not found 卡 + 回列表連結', async ({ page }) => {
  await page.goto('/reviews/does-not-exist-9999', {
    waitUntil: 'domcontentloaded',
  })
  await expect(page.getByText(/Review not found:/)).toBeVisible()
  await page.getByRole('link', { name: '回到 Reviews 列表' }).click()
  await expect(page).toHaveURL(/\/reviews$/)
})
