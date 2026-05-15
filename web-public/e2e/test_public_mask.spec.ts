import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

/**
 * Mask penetration test.
 *
 * Mirrors docs/auth-and-mask.md §6.1: capture SSE traffic from the public
 * channel for 30 s and assert NO real symbol / company name / DENYLIST field
 * leaks. Failure here is a SITC-compliance incident (see §4 of the same
 * doc) — fix the serializer, do not relax this test.
 *
 * Run manually:
 *   uv run uvicorn ohmystock.api.app:create_app --factory --port 8000   (terminal 1)
 *   npm run dev                                                          (terminal 2)
 *   npx playwright test                                                  (terminal 3)
 *
 * If no events are emitted while the test is open, the assertions still
 * pass trivially (empty payload = no leaks). To exercise positively, emit a
 * synthetic event from a Python REPL: see the smoke procedure in
 * openspec/changes/web-public-shell-and-mask/tasks.md §8.2.
 */

const HERE = dirname(fileURLToPath(import.meta.url))

const DENYLIST_KEY_TOKENS = [
  '"symbol"',
  '"company_name"',
  '"price"',
  '"expected_price"',
  '"quantity"',
  '"pnl_twd"',
  '"account_id"',
  '"api_key"',
  '"broker_order_id"',
  '"reasoning"',
  '"query"',
  '"symbols"',
  '"failure_reason"',
]

const FOURDIGIT_IN_STRING_RE = /"[^"]*\b\d{4}\b[^"]*"/g

test('public SSE channel never leaks real symbol or DENYLIST fields', async ({ page }) => {
  await page.goto('/')

  // Capture SSE frame bodies via a JS-side EventSource for 30 s. This is more
  // reliable than waiting for the network-response body, which the EventSource
  // never closes until the page unloads.
  const captured: string[] = await page.evaluate(async () => {
    return await new Promise<string[]>((resolveFn) => {
      const acc: string[] = []
      const es = new EventSource('/api/public/events')
      es.onmessage = (msg) => acc.push(msg.data)
      window.setTimeout(() => {
        es.close()
        resolveFn(acc)
      }, 30_000)
    })
  })

  const allText = captured.join('\n')

  // 1. No DENYLIST key appears anywhere.
  for (const banned of DENYLIST_KEY_TOKENS) {
    expect(allText, `Found DENYLIST key ${banned} in public stream`).not.toContain(banned)
  }

  // 2. No raw 4-digit TWSE code appears in a JSON string value, except inside
  //    ISO-8601-shaped substrings (whitelist-allowed timestamps + review_id).
  const codeMatches = allText.match(FOURDIGIT_IN_STRING_RE) ?? []
  const offenders = codeMatches.filter((m) => !/\d{4}-\d{2}/.test(m))
  expect(offenders, `Found 4-digit code in public stream: ${offenders.join(', ')}`).toHaveLength(0)

  // 3. No top-50 company name appears.
  const blacklistPath = resolve(HERE, 'fixtures/twse_top50_names.json')
  const blacklist: string[] = JSON.parse(await readFile(blacklistPath, 'utf-8'))
  for (const name of blacklist) {
    expect(allText, `Found company name ${name} in public stream`).not.toContain(name)
  }
})
