import { useEffect, useRef } from 'react'
import { openSSE, type SseHandle } from '@/lib/api'
import { useLiveFeedStore, useAuthStore, logout } from '@/stores'

const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 30_000] as const

/**
 * Subscribe to /api/admin/events for the lifetime of the component.
 *
 * Reconnect schedule: 1s, 2s, 4s, 8s, then 30s indefinitely.
 * Aborts (no reconnect) on HTTP 401 - also calls logout().
 */
export function useAdminEvents() {
  const pushEvent = useLiveFeedStore((s) => s.pushEvent)
  const token = useAuthStore((s) => s.token)
  const handleRef = useRef<SseHandle | null>(null)

  useEffect(() => {
    if (!token) return
    let attempt = 0
    let cancelled = false
    let reconnectTimer: number | undefined

    const connect = () => {
      if (cancelled) return
      handleRef.current = openSSE('/api/admin/events', {
        onEvent: (e) => {
          attempt = 0 // reset backoff on any successful event
          pushEvent(e)
        },
        onUnauthorized: () => {
          cancelled = true
          logout()
        },
        onError: () => {
          if (cancelled) return
          const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
          attempt += 1
          reconnectTimer = window.setTimeout(connect, delay)
        },
      })
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== undefined) clearTimeout(reconnectTimer)
      handleRef.current?.close()
      handleRef.current = null
    }
  }, [token, pushEvent])
}