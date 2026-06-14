import { create } from 'zustand'
import type { LiveEvent } from '@/lib/api'

const TOKEN_KEY = 'ohmystock.admin.token'
const SIDEBAR_KEY = 'ohmystock.admin.sidebar.collapsed'
const THEME_KEY = 'ohmystock.admin.theme'
const LIVE_FEED_CAP = 100

// ---------------------------------------------------------------------------
// auth - Bearer token persisted in localStorage
// ---------------------------------------------------------------------------

type AuthState = {
  token: string | null
  setToken: (t: string) => void
  clearToken: () => void
}

const initialToken = (): string | null => {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  token: initialToken(),
  setToken: (t) => {
    try { localStorage.setItem(TOKEN_KEY, t) } catch { /* ignore */ }
    set({ token: t })
  },
  clearToken: () => {
    try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
    set({ token: null })
  },
}))

/**
 * Logout helper - clears the token and forces a hard reload to /login so
 * in-memory caches (TanStack Query, SSE connections) are torn down.
 */
export function logout(): void {
  useAuthStore.getState().clearToken()
  if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// ---------------------------------------------------------------------------
// ui - sidebar collapse state
// ---------------------------------------------------------------------------

type Theme = 'light' | 'dark'

type UiState = {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  theme: Theme
  toggleTheme: () => void
}

const initialCollapsed = (): boolean => {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

// Mirrors the FOUC guard in index.html: only an explicit 'light' goes light.
const initialTheme = (): Theme => {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: initialCollapsed(),
  toggleSidebar: () =>
    set((s) => {
      const next = !s.sidebarCollapsed
      try { localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0') } catch { /* ignore */ }
      return { sidebarCollapsed: next }
    }),
  theme: initialTheme(),
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'dark' ? 'light' : 'dark'
      try { localStorage.setItem(THEME_KEY, next) } catch { /* ignore */ }
      document.documentElement.classList.toggle('dark', next === 'dark')
      return { theme: next }
    }),
}))

// ---------------------------------------------------------------------------
// liveFeed - capped FIFO of SSE events
// ---------------------------------------------------------------------------

type LiveFeedState = {
  events: LiveEvent[]
  pushEvent: (e: LiveEvent) => void
  clear: () => void
}

export const useLiveFeedStore = create<LiveFeedState>((set) => ({
  events: [],
  pushEvent: (e) =>
    set((s) => {
      const next = [e, ...s.events]
      if (next.length > LIVE_FEED_CAP) next.length = LIVE_FEED_CAP
      return { events: next }
    }),
  clear: () => set({ events: [] }),
}))