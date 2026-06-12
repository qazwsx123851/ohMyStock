/**
 * Tier 9 — 清單頁 status filter（/proposals）。檔名排最後：tier1 對
 * proposal 狀態的變動已全部結束，這裡只依賴 terminal fixtures
 * （e2e-pr05m=merged、e2e-pr05r=rejected，seed 後不再變）。
 * 列表「主題」欄顯示 topic（非完整 slug）— 斷言用 topic 文字。
 */
import { test, expect } from '@playwright/test'
import { injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

test('PL-01 status tab：merged/rejected 互斥過濾 + URL 同步', async ({
  page,
}) => {
  await page.goto('/proposals', { waitUntil: 'domcontentloaded' })

  await page.getByRole('tab', { name: 'merged' }).click()
  await expect(page).toHaveURL(/\?status=merged/)
  await expect(page.getByText('e2e-pr05m', { exact: true })).toBeVisible()
  await expect(page.getByText('e2e-pr05r', { exact: true })).toHaveCount(0)

  await page.getByRole('tab', { name: 'rejected' }).click()
  await expect(page).toHaveURL(/\?status=rejected/)
  await expect(page.getByText('e2e-pr05r', { exact: true })).toBeVisible()
  await expect(page.getByText('e2e-pr05m', { exact: true })).toHaveCount(0)
})

test('PL-02 URL 直入：?status=rejected 還原 tab 選取與過濾', async ({
  page,
}) => {
  await page.goto('/proposals?status=rejected', {
    waitUntil: 'domcontentloaded',
  })
  await expect(
    page.getByRole('tab', { name: 'rejected' }),
  ).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('e2e-pr05r', { exact: true })).toBeVisible()
  await expect(page.getByText('e2e-pr05m', { exact: true })).toHaveCount(0)
})
