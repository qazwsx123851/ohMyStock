/**
 * Tier 5 — Chat sessions（/chat, /chat/:id, /sessions）。
 *
 * 零 LLM 成本：e2e 後端 ANTHROPIC_API_KEY 為空白（playwright.config.ts 覆寫
 * repo .env），送訊息固定 422 missing_api_key（routes/chat.py:380），且 422
 * 發生在 insert_message 之前 — user 訊息不落 DB。
 *
 * fixtures（seed_db.py seed_chat）：
 *   chat_e2e00001 「e2e 固定對話 A」 active、2 則訊息（含 e2etokenalpha）
 *   chat_e2e00002 「e2e 固定對話 B」 active、0 則（CH-07 刪除目標）
 *   chat_e2e00003 「e2e 已刪除對話」 deleted、1 則（含 e2etokenalpha）
 *
 * 順序敏感：CH-01 斷言 B 存在 → CH-07 才刪 B。整檔重跑（global-setup 重 seed）。
 */
import { test, expect } from '@playwright/test'
import { AUTH_HEADERS, injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

test('CH-01 列表：seeded sessions 可見、deleted 隱藏、訊息數正確', async ({
  page,
}) => {
  await page.goto('/chat', { waitUntil: 'domcontentloaded' })
  // TopBar h1 與頁面 h1 同名 — scope main 避開 strict violation。
  await expect(
    page.getByRole('main').getByRole('heading', { name: '對話模式' }),
  ).toBeVisible()

  const rowA = page.getByRole('row').filter({ hasText: 'e2e 固定對話 A' })
  await expect(rowA).toBeVisible()
  await expect(rowA).toContainText('2') // 訊息數
  await expect(
    page.getByRole('row').filter({ hasText: 'e2e 固定對話 B' }),
  ).toBeVisible()
  // 列表只列 active — deleted session 不出現。
  await expect(page.getByText('e2e 已刪除對話')).toHaveCount(0)
})

test('CH-02 新對話：POST 成功 → 導向 /chat/<id> + 空狀態', async ({
  page,
}) => {
  await page.goto('/chat', { waitUntil: 'domcontentloaded' })
  // 按鈕有 aria-label="新增對話 (Cmd/Ctrl+N)"，accessible name 不是可見文字。
  await page.getByRole('button', { name: /新增對話/ }).click()
  await expect(page).toHaveURL(/\/chat\/chat_[0-9a-f]{8}$/)
  await expect(
    page.getByText('這是新對話 — 在下方輸入你的問題'),
  ).toBeVisible()
})

test('CH-03 詳情：標題 + 兩則歷史訊息渲染', async ({ page }) => {
  await page.goto('/chat/chat_e2e00001', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('heading', { name: 'e2e 固定對話 A' }),
  ).toBeVisible()
  await expect(
    page.getByText('請幫我看台積電走勢 e2etokenalpha'),
  ).toBeVisible()
  await expect(page.getByText('e2e fixture 回覆：已收到。')).toBeVisible()
})

test('CH-04 送訊息（無 API key）：alert 顯示 missing_api_key、訊息不落 DB', async ({
  page,
}) => {
  await page.goto('/chat/chat_e2e00001', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('heading', { name: 'e2e 固定對話 A' }),
  ).toBeVisible()

  await page.getByLabel('訊息輸入').fill('這則訊息不該被保存（無 key）')
  await page.getByRole('button', { name: /送出/ }).click()

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('網路或服務異常（missing_api_key）')
  // TODO（已回報 UX bug）：錯誤卡寫「已保留你輸入的內容」，但
  // ChatSessionPage.startStream 在 stream 前就清空 input — 內容實際遺失。
  await expect(page.getByLabel('訊息輸入')).toBeEnabled()

  // 422 在 insert_message 之前 → API 確認 message 數仍為 2。
  const resp = await page.request.get(
    '/api/admin/chat/sessions/chat_e2e00001',
    { headers: AUTH_HEADERS },
  )
  expect(resp.status()).toBe(200)
  const body = await resp.json()
  expect(body.data.messages).toHaveLength(2)
})

test('CH-05 已刪除 session：destructive 卡片、無輸入框', async ({ page }) => {
  await page.goto('/chat/chat_e2e00003', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('此對話已刪除')).toBeVisible()
  await expect(
    page.getByText('訊息保留以供搜尋與復盤，但無法繼續對話。'),
  ).toBeVisible()
  await expect(page.getByLabel('訊息輸入')).toHaveCount(0)
})

test('CH-06 不存在的 session：找不到對話 + 返回連結', async ({ page }) => {
  await page.goto('/chat/chat_ffffffff', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('找不到對話')).toBeVisible()
  await page.getByRole('link', { name: '← 回到對話列表' }).click()
  await expect(page).toHaveURL(/\/chat$/)
})

test('CH-07 UI 刪除：選單 → 確認卡 → 回列表且 B 消失', async ({ page }) => {
  await page.goto('/chat/chat_e2e00002', { waitUntil: 'domcontentloaded' })
  await expect(
    page.getByRole('heading', { name: 'e2e 固定對話 B' }),
  ).toBeVisible()

  await page.getByLabel('對話選單').click()
  await page.getByRole('button', { name: '刪除對話' }).click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toContainText('確定刪除此對話？')
  await dialog.getByRole('button', { name: '確定刪除' }).click()

  await expect(page).toHaveURL(/\/chat$/)
  await expect(
    page.getByRole('main').getByRole('heading', { name: '對話模式' }),
  ).toBeVisible()
  await expect(page.getByText('e2e 固定對話 B')).toHaveCount(0)
})

test('CH-08 搜尋：FTS 命中 2 組、mark 高亮、deleted 組開啟鈕 disabled', async ({
  page,
}) => {
  await page.goto('/sessions', { waitUntil: 'domcontentloaded' })
  await page.getByLabel('搜尋').fill('e2etokenalpha')
  await page.getByLabel('搜尋').press('Enter')

  await expect(page.getByText(/2 個對話、2 段命中/)).toBeVisible()
  await expect(page.locator('mark').first()).toBeVisible()

  await expect(page.getByText('(已刪除)')).toBeVisible()
  // active 組的開啟鈕包在 Link 裡也是 button — 用 disabled 過濾鎖定 deleted 組。
  await expect(
    page.getByRole('button', { name: '開啟 →', disabled: true }),
  ).toBeVisible()

  // active 組的開啟 → 導向詳情。
  await page.getByRole('link', { name: /開啟/ }).click()
  await expect(page).toHaveURL(/\/chat\/chat_e2e00001/)
})

test('CH-09 搜尋日期 filter：縮到 05-02 只剩 1 組；無命中顯示空狀態', async ({
  page,
}) => {
  await page.goto('/sessions', { waitUntil: 'domcontentloaded' })
  await page.getByLabel('搜尋').fill('e2etokenalpha')
  await page.locator('#date-from').fill('2026-05-02')
  await page.getByLabel('到').fill('2026-05-02')
  await page.getByRole('button', { name: /搜尋/ }).click()

  await expect(page.getByText(/1 個對話、1 段命中/)).toBeVisible()
  await expect(page.getByText('(已刪除)')).toBeVisible()
  await expect(page.getByText('e2e 固定對話 A')).toHaveCount(0)

  await page.getByLabel('搜尋').fill('zzzznohit')
  await page.getByLabel('搜尋').press('Enter')
  await expect(page.getByText('無命中 — 試試其他關鍵字')).toBeVisible()
})
