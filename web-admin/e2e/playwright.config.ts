import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import {
  ADMIN_TOKEN,
  BACKEND_HEALTH_URL,
  BACKEND_PORT,
  DB_PATH,
  PATH_WITH_UV,
  PREVIEW_URL,
  PROPOSALS_DIR,
  REVIEWS_DIR,
} from './constants'

// Self-contained E2E harness: Playwright boots the backend (uvicorn --factory)
// and the built web-admin (vite preview) itself, so `npm run e2e` needs no
// manually started servers. The backend runs against a temp SQLite DB seeded by
// global-setup; the real journal.db is never touched.
// `npm run e2e` runs from web-admin/e2e (cwd).
const repoRoot = path.resolve(process.cwd(), '..', '..')
const webAdminRoot = path.resolve(process.cwd(), '..')

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [['list']],
  outputDir: './.playwright/results',
  globalSetup: './global-setup.ts',

  use: {
    baseURL: PREVIEW_URL,
    trace: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      // Backend: uvicorn factory mode, no reload, temp DB + test token.
      command: `uv run ohmystock api --no-reload --host 127.0.0.1 --port ${BACKEND_PORT}`,
      url: BACKEND_HEALTH_URL,
      cwd: repoRoot,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        OHMYSTOCK_ADMIN_TOKEN: ADMIN_TOKEN,
        OHMYSTOCK_DB_PATH: DB_PATH,
        PROPOSALS_DIR,
        REVIEWS_DIR,
        // Single space (strips to empty server-side): env beats the repo's
        // .env in pydantic-settings, so chat send deterministically 422s with
        // missing_api_key instead of calling the real Anthropic API. A space
        // (not '') avoids Windows dropping empty env vars on spawn.
        ANTHROPIC_API_KEY: ' ',
        PATH: PATH_WITH_UV,
      },
    },
    {
      // Frontend: build then serve via vite preview (proxy /api -> backend).
      command: 'npm run build && npm run preview',
      url: PREVIEW_URL,
      cwd: webAdminRoot,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
})
