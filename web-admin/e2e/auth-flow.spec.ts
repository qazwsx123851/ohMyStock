/**
 * 登入/登出實際操作流程（補 testing-spec GATE-01 之外的缺口）。
 *
 * 不注入 localStorage — 真的在登入頁打字、按「登入」、按「登出」，
 * 驗證 token 長度防呆、成功進入 Dashboard、登出清除、錯誤 token 被
 * 401 自動踢回 /login（apiFetch 401 → logout()）。
 */
import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN } from './constants'

test('登入：短 token 防呆 → 正確 token 進入 Dashboard → 登出清除', async ({
  page,
}) => {
  await page.goto('/login', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('heading', { name: 'ohMyStock 後台登入' }),
  ).toBeVisible()

  // 短 token（<32 字元）→ 行內錯誤、不離開登入頁。
  await page.getByLabel('OHMYSTOCK_ADMIN_TOKEN').fill('too-short')
  await page.getByRole('button', { name: '登入' }).click()
  await expect(
    page.getByText('Token 長度不足；OHMYSTOCK_ADMIN_TOKEN 應 ≥ 32 字元'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/login/)

  // 正確 token → 進入 Dashboard（TopBar 顯示登出）。
  await page.getByLabel('OHMYSTOCK_ADMIN_TOKEN').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '登入' }).click()
  await expect(page).not.toHaveURL(/\/login/)
  await expect(page.getByRole('button', { name: '登出' })).toBeVisible()
  await expect(
    page.getByRole('banner').getByRole('heading', { level: 1 }),
  ).toHaveText('Dashboard')

  // 登出 → 回 /login，且重訪受保護頁仍被擋。
  await page.getByRole('button', { name: '登出' }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/paper', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/login/)
})

test('登入：長度合法但錯誤的 token → 首個 API 401 自動登出踢回 /login', async ({
  page,
}) => {
  await page.goto('/login', { waitUntil: 'domcontentloaded' })
  await page
    .getByLabel('OHMYSTOCK_ADMIN_TOKEN')
    .fill('wrong-token-but-long-enough-0000000000')
  await page.getByRole('button', { name: '登入' }).click()

  // 前端長度檢查過 → 先導向 Dashboard，隨後 API 401 → logout() → 踢回。
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 })
})
