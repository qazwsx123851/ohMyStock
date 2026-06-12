import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import {
  DB_PATH,
  E2E_TMP_DIR,
  PATH_WITH_UV,
  PROPOSALS_DIR,
  REVIEWS_DIR,
} from './constants'

// Runs once before the suite: wipe the throwaway temp dir and (re)create the
// SQLite schema so smoke pages query real tables instead of 500-ing on
// "no such table". Backend opens a fresh connection per request, so seeding
// before the first test is sufficient regardless of webServer start order.
//
// Invoked from web-admin (cwd) via `npm run e2e`; repo root is one level up so
// `uv run` resolves the project pyproject.toml.
export default function globalSetup() {
  fs.rmSync(E2E_TMP_DIR, { recursive: true, force: true })
  fs.mkdirSync(E2E_TMP_DIR, { recursive: true })

  // `npm run e2e` runs from web-admin/e2e (cwd), so repo root is two levels up.
  const repoRoot = path.resolve(process.cwd(), '..', '..')
  const seeder = path.join(process.cwd(), 'seed_db.py')

  execSync(`uv run python "${seeder}"`, {
    cwd: repoRoot,
    stdio: 'inherit',
    env: {
      ...process.env,
      OHMYSTOCK_DB_PATH: DB_PATH,
      PROPOSALS_DIR,
      REVIEWS_DIR,
      PATH: PATH_WITH_UV,
    },
  })
}
