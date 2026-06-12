/**
 * Tier 0 — Confirm Gate GWT 情境（docs/web-admin-user-testing-spec.md）。
 *
 * CG-01 confirm / CG-02 reject / CG-03 sweep / CG-04 鍵盤 y/n /
 * CG-B1 二次輸入張數（409 + clamp）/ CG-B2 自訂拒絕原因 /
 * CG-06 SSE 即時刷新 / CG-05 佇列倒數與清空（最後跑，清空佇列）。
 *
 * Fixtures（seed_db.py）：7 筆 pending_confirm，每測試消耗自己的
 * decision_id，宣告順序即執行順序（workers=1），重跑整檔會重新 seed。
 */
import { test, expect, type Page } from '@playwright/test'
import { AUTH_HEADERS, injectAuth } from './helpers'

test.beforeEach(async ({ context, page }) => {
  await injectAuth(context)
  await page.goto('/paper', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('heading', { level: 2, name: '待確認列表' }),
  ).toBeVisible()
})

function card(page: Page, decisionId: string) {
  return page.locator(`[data-pending-card][data-decision-id="${decisionId}"]`)
}

test('CG-01 confirm 進場決策：dialog 確認 → 卡片消失、持倉+1、journal 更新', async ({
  page,
}) => {
  await expect(card(page, 'e2e-cg-01')).toBeVisible()

  // 點 ✓ 確認 → 開啟「確認進場」dialog，建議張數預填 1（1M*10%/200 → 1 張）。
  await card(page, 'e2e-cg-01').getByRole('button', { name: '確認 3034' }).click()
  await expect(page.getByRole('heading', { name: '確認進場' })).toBeVisible()
  await expect(page.getByLabel('下單張數')).toHaveValue('1')

  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/api/admin/confirm-gate/confirm'),
  )
  await page.getByRole('button', { name: '確認下單' }).click()
  const resp = await respPromise
  expect(resp.status()).toBe(200)
  const body = await resp.json()
  expect(body.ok).toBe(true)
  expect(body.data.decision_id).toBe('e2e-cg-01')
  expect(body.data.qty).toBe(1000)

  // 卡片從佇列消失；開倉摘要出現 2330 新倉。
  await expect(card(page, 'e2e-cg-01')).toHaveCount(0)

  // DB 斷言（經 journal API）：entry 列已 confirmed + 寫入成交欄位。
  const rows = await page.request.get(
    '/api/admin/journal/rows?kind=entry&limit=50',
    { headers: AUTH_HEADERS },
  )
  const rowsBody = await rows.json()
  const entry = rowsBody.data.items.find(
    (i: { decision_id: string }) => i.decision_id === 'e2e-cg-01',
  )
  expect(entry.payload.decision_status).toBe('confirmed')
  expect(entry.payload.actual_entry_price).toBeGreaterThan(0)
  expect(entry.payload.actual_qty).toBe(1000)
  expect(entry.payload.stop_loss_price).toBeGreaterThan(0)
  expect(entry.payload.human_confirmed_by).toBe('mark')
  expect(entry.payload.auto_executed).toBe(false)
})

test('CG-02 reject 決策：填原因送出 → 卡片消失', async ({ page }) => {
  await expect(card(page, 'e2e-cg-02')).toBeVisible()
  await card(page, 'e2e-cg-02').getByRole('button', { name: '拒絕 2317' }).click()
  await expect(page.getByRole('heading', { name: '拒絕決策' })).toBeVisible()

  // 原因必填：空白時送出鈕 disabled。
  await expect(page.getByRole('button', { name: '確認拒絕' })).toBeDisabled()
  await page.getByLabel('拒絕原因').fill('e2e：訊號不夠強，先觀望')

  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/api/admin/confirm-gate/reject'),
  )
  await page.getByRole('button', { name: '確認拒絕' }).click()
  expect((await respPromise).status()).toBe(200)
  await expect(card(page, 'e2e-cg-02')).toHaveCount(0)
})

test('CG-03 sweep 過期決策：window.confirm 後過期卡消失、未過期保留', async ({
  page,
}) => {
  // 過期 fixture（2h 前建立，TTL 30min）顯示剩餘 0s。
  await expect(card(page, 'e2e-cg-03')).toBeVisible()
  await expect(card(page, 'e2e-cg-03')).toContainText('剩餘 0s')

  page.once('dialog', (d) => d.accept())
  const respPromise = page.waitForResponse((r) =>
    r.url().includes('/api/admin/confirm-gate/sweep-expired'),
  )
  await page.getByRole('button', { name: '全部 sweep 過期' }).click()
  expect((await respPromise).status()).toBe(200)

  await expect(card(page, 'e2e-cg-03')).toHaveCount(0)
  // 未過期的卡片仍在。
  await expect(card(page, 'e2e-cg-04a')).toBeVisible()

  // journal 寫入 kind=expire 列。
  const rows = await page.request.get(
    '/api/admin/journal/rows?kind=expire&limit=50',
    { headers: AUTH_HEADERS },
  )
  const items = (await rows.json()).data.items
  expect(
    items.some(
      (i: { decision_id: string }) => i.decision_id === 'e2e-cg-03',
    ),
  ).toBe(true)
})

test('CG-04 鍵盤快捷：focus 卡片後 y 開確認 dialog、n 開拒絕 dialog', async ({
  page,
}) => {
  const target = card(page, 'e2e-cg-04a')
  await expect(target).toBeVisible()

  await target.focus()
  await page.keyboard.press('y')
  await expect(page.getByRole('heading', { name: '確認進場' })).toBeVisible()
  await page.getByRole('button', { name: '取消' }).click()
  await expect(page.getByRole('heading', { name: '確認進場' })).toBeHidden()

  await target.focus()
  await page.keyboard.press('n')
  await expect(page.getByRole('heading', { name: '拒絕決策' })).toBeVisible()
  await page.getByRole('button', { name: '取消' }).click()

  // 取消不消耗決策。
  await expect(target).toBeVisible()
})

test('CG-B1 confirm 二次輸入張數：超額 409、偏離 clamp 後下單', async ({
  page,
}) => {
  // fixture：price 100 / sizing 10% / 資本 1M → 系統 1 張；上限 25% 名目 = 2.5 張。
  await card(page, 'e2e-cg-b1').getByRole('button', { name: '確認 1216' }).click()
  await expect(page.getByLabel('下單張數')).toHaveValue('1')

  // 3 張 = 300k 名目 > 250k 上限 → 409，dialog 留在原地。
  await page.getByLabel('下單張數').fill('3')
  const resp409 = page.waitForResponse((r) =>
    r.url().includes('/confirm-gate/confirm'),
  )
  await page.getByRole('button', { name: '確認下單' }).click()
  const r409 = await resp409
  expect(r409.status()).toBe(409)
  expect((await r409.json()).error.code).toBe('qty_exceeds_notional_limit')
  await expect(page.getByRole('heading', { name: '確認進場' })).toBeVisible()

  // 2 張 ≤ 上限但偏離系統值 100% > 30% → clamp 回 1 張 + 警示 banner。
  await page.getByLabel('下單張數').fill('2')
  const resp200 = page.waitForResponse((r) =>
    r.url().includes('/confirm-gate/confirm'),
  )
  await page.getByRole('button', { name: '確認下單' }).click()
  const r200 = await resp200
  expect(r200.status()).toBe(200)
  const data = (await r200.json()).data
  expect(data.clamped).toBe(true)
  expect(data.qty).toBe(1000)

  await expect(
    page.getByText('已依風控調整為 1 張下單', { exact: false }),
  ).toBeVisible()
  await expect(card(page, 'e2e-cg-b1')).toHaveCount(0)
})

test('CG-B2 reject 自訂原因：寫入 journal reject 列', async ({ page }) => {
  await card(page, 'e2e-cg-b2').getByRole('button', { name: '拒絕 2882' }).click()
  const reason = 'e2e：這檔前年被套過，先觀望'
  await page.getByLabel('拒絕原因').fill(reason)
  await page.getByRole('button', { name: '確認拒絕' }).click()
  await expect(card(page, 'e2e-cg-b2')).toHaveCount(0)

  const rows = await page.request.get(
    '/api/admin/journal/rows?kind=reject&limit=50',
    { headers: AUTH_HEADERS },
  )
  const items = (await rows.json()).data.items
  const row = items.find(
    (i: { decision_id: string }) => i.decision_id === 'e2e-cg-b2',
  )
  expect(row.payload.reject_reason).toBe(reason)
  expect(row.payload.reject_layer).toBe('human')
  expect(row.payload.rejected_by).toBe('mark')
})

test('CG-06 SSE 即時刷新：後端 confirm 後卡片自動消失、事件進 LiveFeed', async ({
  page,
}) => {
  await expect(card(page, 'e2e-cg-04b')).toBeVisible()

  // 不操作 UI，直接打 API（模擬另一端動作）→ SSE order_sent → 頁面自動刷新。
  const resp = await page.request.post('/api/admin/confirm-gate/confirm', {
    headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
    data: { decision_id: 'e2e-cg-04b', user: 'mark' },
  })
  expect(resp.status()).toBe(200)

  await expect(card(page, 'e2e-cg-04b')).toHaveCount(0, { timeout: 20_000 })
  await expect(
    page.locator('li', { hasText: 'order_sent' }).first(),
  ).toBeVisible({ timeout: 20_000 })
})

test('CG-05 佇列載入/倒數/清空：倒數條 + 消耗最後一筆 → 空狀態', async ({
  page,
}) => {
  // 只剩 e2e-cg-04a；倒數 progressbar + 剩餘秒數格式正確。
  const target = card(page, 'e2e-cg-04a')
  await expect(target).toBeVisible()
  await expect(
    target.getByRole('progressbar', { name: '待確認剩餘時間' }),
  ).toBeVisible()
  await expect(target).toContainText(/剩餘 \d+s \/ \d+s/)

  // 消耗最後一筆 → SSE 刷新 → 空狀態。
  const resp = await page.request.post('/api/admin/confirm-gate/confirm', {
    headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
    data: { decision_id: 'e2e-cg-04a', user: 'mark' },
  })
  expect(resp.status()).toBe(200)
  await expect(page.getByText('目前無待確認')).toBeVisible({ timeout: 20_000 })
})
