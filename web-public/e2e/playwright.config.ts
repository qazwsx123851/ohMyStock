import { defineConfig } from '@playwright/test'

/**
 * Playwright config for the mask-penetration E2E test.
 *
 * Run prerequisites (manual, not in CI yet):
 *   1. Backend up:  uv run uvicorn ohmystock.api.app:create_app --factory --port 8000
 *   2. Dev server:  cd web-public && npm run dev   (serves http://localhost:5173)
 *   3. E2E:         cd web-public && npx playwright test
 *
 * Production-deploy CORS + rate-limit are deferred to the deploy change.
 */
export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  reporter: 'list',
})
