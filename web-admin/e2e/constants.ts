import os from 'node:os'
import path from 'node:path'

// Backend (uvicorn factory) + frontend (vite preview) ports. The vite preview
// proxy in vite.config.ts forwards /api from PREVIEW_PORT to BACKEND_PORT.
export const BACKEND_PORT = 8000
export const PREVIEW_PORT = 4173
export const PREVIEW_URL = `http://localhost:${PREVIEW_PORT}`
export const BACKEND_HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/healthz`

// Test-only admin token (>=32 chars to satisfy both the backend startup check
// in ohmystock.api.auth and the LoginPage length guard). Injected into the
// browser localStorage to skip the login flow; also passed to the backend via
// OHMYSTOCK_ADMIN_TOKEN so Bearer auth matches end-to-end.
export const ADMIN_TOKEN = 'e2e-smoke-admin-token-000000000000'
export const TOKEN_STORAGE_KEY = 'ohmystock.admin.token'

// Throwaway SQLite DB. Deterministic path so config re-imports across workers
// agree; global-setup wipes + reseeds it each run. Never the real journal.db.
export const E2E_TMP_DIR = path.join(os.tmpdir(), 'ohmystock-e2e')
export const DB_PATH = path.join(E2E_TMP_DIR, 'journal.db')

// Throwaway proposals root (markdown state machine fixtures). Passed to the
// backend via PROPOSALS_DIR so e2e never touches the repo's real proposals/.
export const PROPOSALS_DIR = path.join(E2E_TMP_DIR, 'proposals')

// Playwright spawns webServer / globalSetup via cmd.exe, whose PATH lacks the
// uv install dir (~/.local/bin, uv's default Windows location). Prepend it so
// `uv run ...` resolves without relying on the interactive shell's PATH.
export const UV_BIN_DIR = path.join(os.homedir(), '.local', 'bin')
export const PATH_WITH_UV = `${UV_BIN_DIR}${path.delimiter}${process.env.PATH ?? ''}`
