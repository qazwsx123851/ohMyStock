/**
 * Subscribes to /api/public/events (masked SSE) and feeds the scene store.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: SSE Connection)
 */

import { useEffect } from 'react'
import { routeEvent } from '@/lib/eventToAction'
import { useSceneStore } from '@/stores/scene'
import type { PublicEvent } from '@/types/public-event'

export interface UsePublicSSEOptions {
  url?: string
  eventSourceFactory?: (url: string) => EventSource
}

export function usePublicSSE(opts: UsePublicSSEOptions = {}): void {
  const { url = '/api/public/events', eventSourceFactory } = opts
  useEffect(() => {
    const factory =
      eventSourceFactory ?? ((u: string) => new EventSource(u))
    const es = factory(url)

    const onMessage = (msg: MessageEvent): void => {
      let parsed: PublicEvent
      try {
        parsed = JSON.parse(msg.data) as PublicEvent
      } catch {
        return
      }
      if (!parsed?.event_id) return
      useSceneStore.getState().pushTimeline(parsed)
      const action = routeEvent(parsed)
      if (action) {
        useSceneStore.getState().enqueueAction(action)
      }
    }

    es.addEventListener('message', onMessage)
    return () => {
      es.removeEventListener('message', onMessage)
      es.close()
    }
  }, [url, eventSourceFactory])
}
