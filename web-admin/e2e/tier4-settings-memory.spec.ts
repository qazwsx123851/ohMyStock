/**
 * Tier 4 — 設定與記憶 GWT 情境（docs/web-admin-user-testing-spec.md）。
 *
 * ST-01 Settings 唯讀載入 / ST-02 API key badge / ST-03 Safety 視覺分化 /
 * ST-04 Breaker 格式化 / ST-B1 連線測試 / ST-B2 額度與模型分布 /
 * ME-01 瀏覽+filter / ME-02 FTS5 搜尋 / ME-03 語法錯誤 / ME-04 展開+空結果 /
 * ME-B1 寫入偏好。
 *
 * Fixtures: web-admin/e2e/seed_db.py（memory_rows 4 筆，kind 各一）。
 */
import { test, expect } from '@playwright/test'
import { injectAuth } from './helpers'

test.beforeEach(async ({ context }) => {
  await injectAuth(context)
})

// ---------------------------------------------------------------------------
// ST — Settings
// ---------------------------------------------------------------------------

test.describe('ST Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings', { waitUntil: 'domcontentloaded' })
    await expect(
      page.getByRole('heading', { level: 2, name: 'API keys' }),
    ).toBeVisible()
  })

  test('ST-01 唯讀載入：四大區塊渲染、控制項 disabled', async ({ page }) => {
    for (const name of ['API keys', '主題', 'Safety', 'Breakers']) {
      await expect(page.getByRole('heading', { level: 2, name })).toBeVisible()
    }
    // Theme select 與 Breakers inputs 全部 disabled（唯讀檢視）。
    await expect(page.getByLabel('主題模式')).toBeDisabled()
    await expect(page.getByLabel('信心下限')).toBeDisabled()
    await expect(page.getByText('編輯 .env 並重啟以變更').first()).toBeVisible()
  })

  test('ST-02 API key badge：只顯示 已設定/未設定，不洩漏明文', async ({
    page,
  }) => {
    const apiCard = page
      .getByRole('heading', { level: 2, name: 'API keys' })
      .locator('..')
    for (const label of ['Anthropic', 'FinMind', 'Shioaji']) {
      const row = apiCard.locator('div', { hasText: label }).last()
      const badge = row.locator('[data-state="set"], [data-state="unset"]')
      await expect(badge).toHaveText(/^(已設定|未設定)$/)
    }
    // 頁面不得出現任何 key 樣式明文（sk- 開頭等）。
    await expect(page.locator('body')).not.toContainText('sk-ant')
  })

  test('ST-03 Safety 視覺分化：auto_execute 兩態對應文案', async ({
    page,
  }) => {
    const card = page.locator('[data-auto-execute]')
    await expect(card).toBeVisible()
    const state = await card.getAttribute('data-auto-execute')
    if (state === 'on') {
      await expect(card).toContainText('AUTO_EXECUTE 已啟用')
    } else {
      expect(state).toBe('off')
      await expect(card).toContainText('AUTO_EXECUTE 關閉（人工 Confirm Gate）')
    }
    await expect(card).toContainText('Broker：')
  })

  test('ST-04 Breaker 格式化：7 欄位以正確格式呈現', async ({ page }) => {
    const labels = [
      '信心下限',
      '單日上限',
      '配額（單筆 Notional）',
      '偏離上限',
      '虧損鎖定（小時）',
      '虧損鎖定觸發',
      '帳戶權益',
    ]
    for (const label of labels) {
      await expect(page.getByLabel(label)).toBeVisible()
    }
    // 信心下限固定兩位小數；帳戶權益千分位整數。
    await expect(page.getByLabel('信心下限')).toHaveValue(/^\d+\.\d{2}$/)
    await expect(page.getByLabel('帳戶權益')).toHaveValue(/^[\d,]+$/)
  })

  test('ST-B1 連線測試：點按後顯示成功或失敗結果', async ({ page }) => {
    const finmindRow = page.locator('[data-provider="finmind"]')
    await finmindRow.getByRole('button', { name: '測試連線' }).click()
    // 真實 probe：成功（連線成功 + latency）或失敗（失敗：…）皆為合法終態。
    await expect(
      finmindRow.locator('[data-testid="result-finmind"]'),
    ).toContainText(/連線成功|失敗：/, { timeout: 30_000 })
  })

  test('ST-B2 額度/模型分布：唯讀 budget 卡片', async ({ page }) => {
    await expect(
      page.getByRole('heading', { level: 2, name: '本月額度與模型分布' }),
    ).toBeVisible()
    for (const key of ['opus', 'sonnet', 'haiku']) {
      await expect(page.locator(`[data-model="${key}"]`)).toContainText('%')
    }
    await expect(page.getByText('USD · 本月累計（唯讀）')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// ME — Memory
// ---------------------------------------------------------------------------

test.describe('ME Memory', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'domcontentloaded' })
    await expect(
      page.getByRole('heading', { level: 1, name: '長期記憶' }).first(),
    ).toBeVisible()
  })

  test('ME-01 瀏覽 + kind/tag filter', async ({ page }) => {
    // 全部：4 筆 fixture 都在。
    await expect(page.getByText('台積電 法說會 重點觀察', { exact: false })).toBeVisible()
    await expect(page.getByText('停損紀律', { exact: false })).toBeVisible()

    // kind filter = 經驗（lesson）→ 只剩 lesson 列。
    await page.getByLabel('按 kind 過濾').selectOption('lesson')
    await expect(page.getByText('停損紀律', { exact: false })).toBeVisible()
    await expect(
      page.getByText('台積電 法說會 重點觀察', { exact: false }),
    ).toBeHidden()

    // 還原 + tag filter = 2330 → 只剩 note 列。
    await page.getByLabel('按 kind 過濾').selectOption('all')
    await page.getByLabel('按 tag 過濾').fill('2330')
    await page.getByLabel('按 tag 過濾').press('Enter')
    await expect(page.getByText('台積電 法說會 重點觀察', { exact: false })).toBeVisible()
    await expect(page.getByText('停損紀律', { exact: false })).toBeHidden()

    // 移除 tag chip 還原。
    await page.getByLabel('移除 tag 2330').click()
    await expect(page.getByText('停損紀律', { exact: false })).toBeVisible()
  })

  test('ME-02 FTS5 搜尋（BM25）', async ({ page }) => {
    await page.getByRole('tab', { name: '搜尋' }).click()
    await page.getByLabel('FTS5 查詢').fill('法說會')
    await page.getByRole('button', { name: '搜尋' }).click()
    await expect(page.getByText('台積電 法說會 重點觀察', { exact: false })).toBeVisible()

    // 無結果查詢顯示空狀態。
    await page.getByLabel('FTS5 查詢').fill('不存在的詞彙xyz')
    await page.getByLabel('FTS5 查詢').press('Enter')
    await expect(
      page.getByText('找不到符合「不存在的詞彙xyz」的 memory'),
    ).toBeVisible()
  })

  test('ME-03 搜尋語法錯誤 → 查詢語法錯誤 alert', async ({ page }) => {
    await page.getByRole('tab', { name: '搜尋' }).click()
    await page.getByLabel('FTS5 查詢').fill('AND')
    await page.getByRole('button', { name: '搜尋' }).click()
    await expect(page.getByText('查詢語法錯誤')).toBeVisible()
  })

  test('ME-04 展開列 + filter 空結果 + 清除 filter', async ({ page }) => {
    // 點列展開完整內容。
    await page.getByText('停損紀律', { exact: false }).click()
    await expect(page.getByText(/\d+ 字元/)).toBeVisible()
    await expect(
      page.locator('pre', { hasText: '停損紀律：跌破 ATR 停損價不凹單' }),
    ).toBeVisible()

    // kind=復盤 + tag=nonexistent → 空結果 + 清除 filter。
    await page.getByLabel('按 kind 過濾').selectOption('review_summary')
    await page.getByLabel('按 tag 過濾').fill('nonexistent-tag')
    await page.getByLabel('按 tag 過濾').press('Enter')
    await expect(page.getByText('無符合條件的 memory')).toBeVisible()
    await page.getByRole('button', { name: '清除 filter' }).click()
    await expect(page.getByText('台積電 法說會 重點觀察', { exact: false })).toBeVisible()
  })

  test('ME-B1 寫入個人偏好 → 立即出現在列表', async ({ page }) => {
    await page.getByRole('button', { name: '+ 新增 memory' }).click()
    await page.getByLabel('新增 memory kind').selectOption('note')
    await page.getByLabel('新增 memory tags').fill('e2e-pref')
    await page.getByLabel('新增 memory 內容').fill('E2E 寫入偏好：盤前只看 P0 通知')
    await page.getByRole('button', { name: '儲存' }).click()
    // 表單收合 + 新列出現（invalidate 後 refetch）。
    await expect(page.getByRole('button', { name: '+ 新增 memory' })).toBeVisible()
    await expect(
      page.getByText('E2E 寫入偏好：盤前只看 P0 通知', { exact: false }),
    ).toBeVisible()
  })
})
