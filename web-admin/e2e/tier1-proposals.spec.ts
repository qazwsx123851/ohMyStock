/**
 * Tier 1 — 提案狀態機 GWT 情境（docs/web-admin-user-testing-spec.md）。
 *
 * PR-01 pending→validating / PR-02 validate（dry-run、pass、fail、422、409、
 * 欄位持久化=PR-B1）/ PR-03 approve→merged / PR-04 reject / PR-05 終態守恆 /
 * PR-06 非法轉移與 slug 防護。
 *
 * Fixtures（seed_db.py seed_proposals）：8 個 slug，每測試操作自己的提案；
 * 宣告順序即執行順序（workers=1）。PR-02 pass 後接 Approve 驗證 D7 人工
 * 模式（報告產出 → 停在 validating → 人工核可 + 路徑預填）。
 */
import { test, expect, type Page } from '@playwright/test'
import { AUTH_HEADERS, injectAuth } from './helpers'

const SLUG = {
  pr01: '2026-01-01-e2e-pr01',
  pr02: '2026-01-02-e2e-pr02',
  pr02f: '2026-01-03-e2e-pr02f',
  pr03: '2026-01-04-e2e-pr03',
  pr04: '2026-01-05-e2e-pr04',
  pr05m: '2026-01-06-e2e-pr05m',
  pr05r: '2026-01-07-e2e-pr05r',
  pr06: '2026-01-08-e2e-pr06',
} as const

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

async function gotoDetail(page: Page, slug: string) {
  await page.goto(`/proposals/${slug}`, { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('Target section:')).toBeVisible()
}

/** 狀態 badge（限 header 範圍，避開 changelog 內同字樣）。 */
function statusBadge(page: Page, status: string) {
  return page.locator('header').getByText(status, { exact: true })
}

/** 填 ValidationDialog 並送出；回傳 /validate response。 */
async function runValidation(
  page: Page,
  opts: {
    universe: string
    overrides?: string
    dryRun?: boolean
    wfa?: number
    ratio?: number
    capital?: number
  },
) {
  await page.getByRole('button', { name: 'Run Validation…' }).click()
  await expect(
    page.getByRole('heading', { name: 'Run Validation' }),
  ).toBeVisible()

  await page.getByLabel('Strategy').selectOption('sma_cross')
  await page.getByLabel('Period from').fill('2025-01-02')
  await page.getByLabel('Period to').fill('2025-12-30')
  await page.getByLabel('Universe (comma-separated)').fill(opts.universe)
  if (opts.overrides) {
    await page
      .getByLabel('Parameter overrides (one key=value per line)')
      .fill(opts.overrides)
  }
  if (opts.wfa != null)
    await page.getByLabel('WFA windows').fill(String(opts.wfa))
  if (opts.ratio != null)
    await page.getByLabel('IS ratio').fill(String(opts.ratio))
  if (opts.capital != null)
    await page.getByLabel('Initial capital').fill(String(opts.capital))
  if (opts.dryRun) await page.getByRole('checkbox').check()

  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/validate'),
  )
  await page.getByRole('button', { name: 'Run Validation', exact: true }).click()
  return respPromise
}

test('PR-01 pending → validating：單一按鈕 + changelog 記錄', async ({
  page,
}) => {
  await gotoDetail(page, SLUG.pr01)
  await expect(statusBadge(page, 'pending')).toBeVisible()

  // pending 只有一顆 action。
  await expect(page.getByRole('button', { name: 'Mark Validating' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve…' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Mark Validating' }).click()
  await expect(
    page.getByRole('heading', { name: 'Mark as validating' }),
  ).toBeVisible()
  await page.getByPlaceholder('你的名字').fill('mark')

  const respPromise = page.waitForResponse((r) => r.url().includes('/transition'))
  await page.getByRole('button', { name: 'Confirm' }).click()
  const resp = await respPromise
  expect(resp.status()).toBe(200)
  expect((await resp.json()).data.new_status).toBe('validating')

  // 刷新後狀態 badge + changelog + 三顆 action。
  await expect(statusBadge(page, 'validating')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run Validation…' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve…' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reject…' })).toBeVisible()
  // changelog 追加 pending → validating by mark。
  await expect(
    page.locator('li', { hasText: 'by mark' }).first(),
  ).toContainText('validating')
})

test('PR-02 dry-run：不轉狀態不搬檔 + 欄位持久化（PR-B1）', async ({
  page,
}) => {
  await gotoDetail(page, SLUG.pr02)

  const resp = await runValidation(page, {
    universe: '2330',
    overrides: 'fast=10',
    dryRun: true,
    wfa: 6,
    ratio: 0.6,
    capital: 2000000,
  })
  expect(resp.status()).toBe(200)
  const data = (await resp.json()).data
  expect(data.verdict).toBe('pass')
  expect(data.new_status).toBe('validating')
  expect(data.report_path).toBeNull()

  await expect(page.getByRole('status').first()).toContainText(
    'Dry run: verdict=pass — no state change',
  )
  await expect(statusBadge(page, 'validating')).toBeVisible()

  // PR-B1 欄位持久化：重開 dialog 帶回上次參數（period/overrides/dry-run 重置）。
  await page.getByRole('button', { name: 'Run Validation…' }).click()
  await expect(page.getByLabel('Universe (comma-separated)')).toHaveValue('2330')
  await expect(page.getByLabel('WFA windows')).toHaveValue('6')
  await expect(page.getByLabel('IS ratio')).toHaveValue('0.6')
  await expect(page.getByLabel('Initial capital')).toHaveValue('2000000')
  await expect(page.getByLabel('Period from')).toHaveValue('')
  await expect(
    page.getByLabel('Parameter overrides (one key=value per line)'),
  ).toHaveValue('')
})

test('PR-02 pass（D7 人工模式）：報告產出停在 validating → 人工 Approve 預填路徑', async ({
  page,
}) => {
  await gotoDetail(page, SLUG.pr02)

  const resp = await runValidation(page, {
    universe: '2330',
    overrides: 'fast=10',
  })
  expect(resp.status()).toBe(200)
  const data = (await resp.json()).data
  expect(data.verdict).toBe('pass')
  expect(data.new_status).toBe('validating')
  expect(data.new_path).toBeNull()
  expect(data.report_path).toBe(`${SLUG.pr02}.validation.json`)

  await expect(page.getByRole('status').first()).toContainText(
    'Validated: verdict=pass — 報告已產出，請審閱後 Approve/Reject',
  )
  // 不自動轉：狀態仍 validating、action 仍三顆。
  await expect(statusBadge(page, 'validating')).toBeVisible()

  // 人工 Approve：Validation report path 預填 <slug>.validation.json。
  await page.getByRole('button', { name: 'Approve…' }).click()
  await expect(
    page.getByRole('heading', { name: 'Approve proposal' }),
  ).toBeVisible()
  await expect(page.getByLabel('Validation report path')).toHaveValue(
    `${SLUG.pr02}.validation.json`,
  )
  await page.getByPlaceholder('你的名字（會寫進 changelog）').fill('mark')

  const tResp = page.waitForResponse((r) => r.url().includes('/transition'))
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  expect((await tResp).status()).toBe(200)

  await expect(statusBadge(page, 'approved')).toBeVisible()
  await expect(page.getByText('validation_report_path')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mark Merged…' })).toBeVisible()
})

test('PR-02 fail（D7 人工模式）：fail 也只寫報告、不搬 rejected/', async ({
  page,
}) => {
  await gotoDetail(page, SLUG.pr02f)

  const resp = await runValidation(page, { universe: '1101' })
  expect(resp.status()).toBe(200)
  const data = (await resp.json()).data
  expect(data.verdict).toBe('fail')
  expect(data.failures.length).toBeGreaterThan(0)
  expect(data.new_status).toBe('validating')

  await expect(page.getByRole('status').first()).toContainText(
    /Validated: verdict=fail — 報告已產出（\d+ failure\(s\)），請審閱後 Approve\/Reject/,
  )
  await expect(statusBadge(page, 'validating')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reject…' })).toBeVisible()
})

test('PR-02 錯誤路徑：UI 422 wfa_validation_failed + API 409/400 防護', async ({
  page,
}) => {
  // UI：缺 bars 的 symbol → 422，inline error，dialog 不關。
  await gotoDetail(page, SLUG.pr04)
  const resp = await runValidation(page, { universe: '9999' })
  expect(resp.status()).toBe(422)
  await expect(page.locator('[data-testid="validation-error"]')).toContainText(
    'wfa_validation_failed',
  )
  await expect(
    page.getByRole('heading', { name: 'Run Validation' }),
  ).toBeVisible()

  // API：對 pending 提案 validate → 409 illegal_transition。
  const v409 = await page.request.post(
    `/api/admin/proposals/${SLUG.pr06}/validate`,
    {
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      data: {
        strategy: 'sma_cross',
        period: { from: '2025-01-02', to: '2025-12-30' },
        param_overrides: [],
        universe: ['2330'],
        wfa_windows: 5,
        in_sample_ratio: 0.7,
        initial_capital: 1000000,
        dry_run: false,
      },
    },
  )
  expect(v409.status()).toBe(409)
  expect((await v409.json()).error.code).toBe('illegal_transition')

  // API：merged 缺 merged_to_version → 400 invalid_input（design D10：
  // missing_* 一律映射 invalid_input，細節在 message）。
  const t400 = await page.request.post(
    `/api/admin/proposals/${SLUG.pr03}/transition`,
    {
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      data: { new_status: 'merged', actor: 'e2e' },
    },
  )
  expect(t400.status()).toBe(400)
  const t400Body = await t400.json()
  expect(t400Body.error.code).toBe('invalid_input')
  expect(t400Body.error.message).toContain('missing_merged_to_version')

  // API：rejected 缺 reason → 400 invalid_input。
  const r400 = await page.request.post(
    `/api/admin/proposals/${SLUG.pr04}/transition`,
    {
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      data: { new_status: 'rejected', actor: 'e2e' },
    },
  )
  expect(r400.status()).toBe(400)
  const r400Body = await r400.json()
  expect(r400Body.error.code).toBe('invalid_input')
  expect(r400Body.error.message).toContain('missing_rejection_reason')
})

test('PR-03 approve → merged：必填版本 + 終局', async ({ page }) => {
  await gotoDetail(page, SLUG.pr03)
  await expect(statusBadge(page, 'approved')).toBeVisible()

  await page.getByRole('button', { name: 'Mark Merged…' }).click()
  await expect(
    page.getByRole('heading', { name: 'Mark as merged' }),
  ).toBeVisible()

  // 未填版本時送出鈕 disabled。
  await page.getByPlaceholder('你的名字（會寫進 changelog）').fill('mark')
  await expect(
    page.getByRole('button', { name: 'Mark merged', exact: true }),
  ).toBeDisabled()

  await page.getByPlaceholder('v3.1').fill('v9.9')
  const tResp = page.waitForResponse((r) => r.url().includes('/transition'))
  await page.getByRole('button', { name: 'Mark merged', exact: true }).click()
  expect((await tResp).status()).toBe(200)

  await expect(statusBadge(page, 'merged')).toBeVisible()
  await expect(page.getByText('merged_to_version')).toBeVisible()
  await expect(page.getByText('終局狀態')).toBeVisible()
})

test('PR-04 reject：reason 必填 + frontmatter.rejected_reason', async ({
  page,
}) => {
  await gotoDetail(page, SLUG.pr04)
  await page.getByRole('button', { name: 'Reject…' }).click()
  await expect(
    page.getByRole('heading', { name: 'Reject proposal' }),
  ).toBeVisible()

  await page.getByPlaceholder('你的名字（會寫進 changelog）').fill('mark')
  await expect(
    page.getByRole('button', { name: 'Reject', exact: true }),
  ).toBeDisabled()

  await page
    .getByPlaceholder('說明拒絕原因（會寫進 changelog 與 frontmatter.rejected_reason）')
    .fill('e2e：WFA 不過，放棄此提案')
  const tResp = page.waitForResponse((r) => r.url().includes('/transition'))
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  expect((await tResp).status()).toBe(200)

  await expect(statusBadge(page, 'rejected')).toBeVisible()
  await expect(page.getByText('rejected_reason')).toBeVisible()
  await expect(page.getByText('終局狀態')).toBeVisible()
})

test('PR-05 終態守恆：merged / rejected 無任何 action', async ({ page }) => {
  for (const slug of [SLUG.pr05m, SLUG.pr05r]) {
    await gotoDetail(page, slug)
    await expect(page.getByText('終局狀態')).toBeVisible()
    for (const name of [
      'Mark Validating',
      'Run Validation…',
      'Approve…',
      'Reject…',
      'Mark Merged…',
    ]) {
      await expect(page.getByRole('button', { name })).toHaveCount(0)
    }
    // header/body/changelog 正常渲染。
    await expect(page.getByText('## 1. 改動描述')).toBeVisible()
    await expect(page.getByText('變更紀錄')).toBeVisible()
  }
})

test('PR-06 非法轉移 / slug 防護（API 層）', async ({ page }) => {
  // pending 直跳 approved → 409。
  const t409 = await page.request.post(
    `/api/admin/proposals/${SLUG.pr06}/transition`,
    {
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      data: {
        new_status: 'approved',
        actor: 'e2e',
        validation_report_path: 'x.json',
      },
    },
  )
  expect(t409.status()).toBe(409)
  expect((await t409.json()).error.code).toBe('illegal_transition')

  // slug 含 `..` → 400 invalid_input。
  const bad = await page.request.post(
    '/api/admin/proposals/a..b/transition',
    {
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      data: { new_status: 'validating', actor: 'e2e' },
    },
  )
  expect(bad.status()).toBe(400)
  expect((await bad.json()).error.code).toBe('invalid_input')
})
