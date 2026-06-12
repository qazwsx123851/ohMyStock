/**
 * Tier 7 — Skills（/skills, /skills/:name）。
 *
 * 零 fixture：registry 是 in-repo 檔案系統（src/ohmystock/skills/registry/
 * 10 個 .md 隨 package），import 時解析。斷言指名 version-controlled 的
 * skill（rs-percentile=indicator、screener=signal），總數用 N>=10 regex
 * 避免 registry 成長時測試壞掉。
 */
import { test, expect } from '@playwright/test'
import { injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

test('SK-01 grid：指名卡片可見 + 共 N/N 筆（N>=10）', async ({ page }) => {
  await page.goto('/skills', { waitUntil: 'domcontentloaded' })
  // TopBar h1 與頁面 h1 同名 — scope main 避開 strict violation。
  await expect(
    page.getByRole('main').getByRole('heading', { name: 'Skills' }),
  ).toBeVisible()

  await expect(
    page.getByRole('button', { name: /^rs-percentile：/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /^sepa-trend-template：/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /^screener：/ }),
  ).toBeVisible()

  const counter = page.getByText(/共 (\d+)\/(\d+) 筆/)
  await expect(counter).toBeVisible()
  const text = (await counter.textContent()) ?? ''
  const m = text.match(/共 (\d+)\/(\d+) 筆/)
  expect(Number(m?.[2])).toBeGreaterThanOrEqual(10)
})

test('SK-02 client-side 搜尋：過濾 + 清除 + 空狀態', async ({ page }) => {
  await page.goto('/skills', { waitUntil: 'domcontentloaded' })

  await page.getByLabel('搜尋 skills').fill('rs-percentile')
  await expect(
    page.getByRole('button', { name: /^rs-percentile：/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /^screener：/ }),
  ).toHaveCount(0)
  await expect(page.getByText(/共 1\/\d+ 筆/)).toBeVisible()

  await page.getByRole('button', { name: '清除' }).click()
  await expect(
    page.getByRole('button', { name: /^screener：/ }),
  ).toBeVisible()

  await page.getByLabel('搜尋 skills').fill('zzz-不存在的skill')
  await expect(page.getByText('無符合條件的 skill')).toBeVisible()
  await page.getByRole('button', { name: '清除 filter' }).click()
  await expect(
    page.getByRole('button', { name: /^rs-percentile：/ }),
  ).toBeVisible()
})

test('SK-03 類別 select：indicator 只剩 indicator 卡片', async ({ page }) => {
  await page.goto('/skills', { waitUntil: 'domcontentloaded' })
  await page.getByLabel('類別過濾').selectOption('indicator')

  // registry frontmatter：indicator = rs-percentile + technical-indicators。
  await expect(
    page.getByRole('button', { name: /^rs-percentile：/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /^technical-indicators：/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /^screener：/ }),
  ).toHaveCount(0)
  await expect(page.getByText(/共 2\/\d+ 筆/)).toBeVisible()
})

test('SK-04 詳情：header/body/chars/cited-specs + 404 空狀態', async ({
  page,
}) => {
  await page.goto('/skills', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /^rs-percentile：/ }).click()
  await expect(page).toHaveURL(/\/skills\/rs-percentile/)

  await expect(
    page.getByRole('heading', { name: 'rs-percentile' }),
  ).toBeVisible()
  await expect(page.getByText(/\d+ chars/)).toBeVisible()
  await expect(page.getByText('Cited specs')).toBeVisible()
  // body <pre> 含 registry md 的固定段落。
  await expect(page.locator('pre')).toContainText('Purpose')

  await page.goto('/skills/zzz-not-a-skill', {
    waitUntil: 'domcontentloaded',
  })
  await expect(page.getByText(/找不到 skill:/)).toBeVisible()
  await page.getByRole('link', { name: '返回 Skills' }).click()
  await expect(page).toHaveURL(/\/skills$/)
})
