import { type BrowserContext, type Page } from '@playwright/test'
import { ADMIN_TOKEN, TOKEN_STORAGE_KEY } from './constants'

/** Inject the Bearer token before any app script runs (skips /login). */
export async function injectAuth(context: BrowserContext): Promise<void> {
  await context.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [TOKEN_STORAGE_KEY, ADMIN_TOKEN] as const,
  )
}

/** Authorization header for page.request API calls (GWT API-level asserts). */
export const AUTH_HEADERS = { Authorization: `Bearer ${ADMIN_TOKEN}` }

/** Collect non-whitelisted console errors + pageerrors for a page. */
const CONSOLE_WHITELIST: RegExp[] = [
  /favicon/i,
  /EventSource/i,
  /ResizeObserver/i,
  /React DevTools/i,
  /Failed to load resource.*\b404\b/i,
  /net::ERR_/i,
]

export function trackErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(`PAGEERROR: ${e.message}`))
  return errors
}

export function unexpectedErrors(errors: string[]): string[] {
  return errors.filter((e) => !CONSOLE_WHITELIST.some((re) => re.test(e)))
}
