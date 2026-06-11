import { expect, test } from '@playwright/test'

/**
 * Smoke test for the pixel office page.
 *
 * Prereqs (manual):
 *   1. Backend up:    uv run uvicorn ohmystock.api.app:create_app --factory --port 8000
 *   2. Dev server:    cd web-public && npm run dev
 *   3. Run:           cd web-public && npx playwright test office.spec.ts
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 */

test('canvas mounts at the design-mockup resolution with pixelated rendering', async ({ page }) => {
  await page.goto('/')
  const canvas = page.getByTestId('office-canvas')
  await expect(canvas).toBeVisible()
  await expect(canvas).toHaveAttribute('width', '564')
  await expect(canvas).toHaveAttribute('height', '445')

  const rendering = await canvas.evaluate(
    (el) => window.getComputedStyle(el).imageRendering,
  )
  expect(rendering).toBe('pixelated')
})

test('disclaimer banner renders without close button', async ({ page }) => {
  await page.goto('/')
  const banner = page.getByTestId('disclaimer-banner')
  await expect(banner).toBeVisible()
  const buttonCount = await banner.locator('button').count()
  expect(buttonCount).toBe(0)
})

test('timeline marquee is present even with zero events', async ({ page }) => {
  await page.goto('/')
  const marquee = page.getByTestId('timeline-marquee')
  await expect(marquee).toBeVisible()
})

test('about page renders via /about and keeps the banner', async ({ page }) => {
  await page.goto('/about')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByTestId('disclaimer-banner')).toBeVisible()
})

test('no PII writes: cookie / localStorage / sessionStorage empty', async ({ page }) => {
  await page.goto('/')
  await page.waitForTimeout(2000)
  const cookies = await page.context().cookies()
  expect(cookies.length).toBe(0)
  const localCount = await page.evaluate(() => window.localStorage.length)
  const sessionCount = await page.evaluate(() => window.sessionStorage.length)
  expect(localCount).toBe(0)
  expect(sessionCount).toBe(0)
})
