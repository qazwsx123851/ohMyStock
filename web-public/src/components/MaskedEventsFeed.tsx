import { useEffect, useRef, useState } from 'react'

/**
 * Live feed of masked events from /api/public/events.
 *
 * Holds at most 50 events in memory, oldest evicted on overflow, deduped by
 * `event_id` so SSE auto-reconnect with `Last-Event-ID` does not duplicate
 * rows. Renders each event as a <li> with timestamp (TPE local time),
 * event_type, agent, and a <code> dump of the masked payload.
 *
 * Defence-in-depth: even if the server somehow ships a DENYLIST field, the
 * frontend strips it from `payload` before rendering. The server is already
 * supposed to strip, but a regression there would be a compliance incident,
 * so we keep an independent layer here.
 *
 * Spec: openspec/changes/web-public-shell-and-mask/specs/web-public-shell/spec.md
 */

interface MaskedEvent {
  event_id: string
  timestamp: string
  event_type: string
  agent: string
  payload: Record<string, unknown>
}

const MAX_ITEMS = 50

// Mirror of backend ohmystock.eventbus.serializers.DENYLIST_FIELDS.
const PAYLOAD_DENYLIST: ReadonlySet<string> = new Set([
  'symbol',
  'company_name',
  'price',
  'expected_price',
  'quantity',
  'pnl_twd',
  'account_id',
  'api_key',
  'broker_order_id',
  'reasoning',
  'query',
  'symbols',
  'failure_reason',
])

const TPE_TIME_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Taipei',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function stripDenylist(payload: Record<string, unknown>): Record<string, unknown> {
  const clean: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(payload)) {
    if (!PAYLOAD_DENYLIST.has(k)) {
      clean[k] = v
    }
  }
  return clean
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return TPE_TIME_FMT.format(d)
  } catch {
    return iso
  }
}

// Exported so unit tests can swap a fake EventSource in.
export interface MaskedEventsFeedProps {
  url?: string
  eventSourceFactory?: (url: string) => EventSource
}

export function MaskedEventsFeed({
  url = '/api/public/events',
  eventSourceFactory,
}: MaskedEventsFeedProps) {
  const [events, setEvents] = useState<MaskedEvent[]>([])
  const seenIds = useRef<Set<string>>(new Set())

  useEffect(() => {
    const factory = eventSourceFactory ?? ((u: string) => new EventSource(u))
    const es = factory(url)
    const onMessage = (msg: MessageEvent) => {
      let parsed: MaskedEvent
      try {
        parsed = JSON.parse(msg.data)
      } catch {
        return
      }
      if (!parsed?.event_id || seenIds.current.has(parsed.event_id)) {
        return
      }
      seenIds.current.add(parsed.event_id)
      const clean: MaskedEvent = {
        ...parsed,
        payload: stripDenylist(parsed.payload ?? {}),
      }
      setEvents((prev) => {
        const next = [clean, ...prev]
        if (next.length > MAX_ITEMS) {
          // Drop oldest from BOTH the rendered list and the dedupe set so the
          // set doesn't grow unbounded over a long session.
          const dropped = next.slice(MAX_ITEMS)
          for (const d of dropped) {
            seenIds.current.delete(d.event_id)
          }
          return next.slice(0, MAX_ITEMS)
        }
        return next
      })
    }
    es.addEventListener('message', onMessage)
    return () => {
      es.removeEventListener('message', onMessage)
      es.close()
    }
  }, [url, eventSourceFactory])

  return (
    <section aria-label="Masked events feed">
      <h2 className="text-base font-semibold mb-3">
        AI 助手即時動態
        <span className="ml-2 text-xs font-normal text-[color:var(--muted-foreground)]">
          (最近 {events.length} 筆，最多 {MAX_ITEMS})
        </span>
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-[color:var(--muted-foreground)]">
          目前 idle，等待事件…
        </p>
      ) : (
        <ul data-testid="masked-events-list" className="space-y-2">
          {events.map((e) => (
            <li
              key={e.event_id}
              data-testid="masked-event-row"
              className="rounded border border-zinc-200 px-3 py-2 text-sm"
            >
              <div className="flex items-baseline gap-2">
                <time className="font-mono text-xs text-[color:var(--muted-foreground)]">
                  {formatTimestamp(e.timestamp)}
                </time>
                <span className="font-medium">{e.event_type}</span>
                <span className="text-xs text-[color:var(--muted-foreground)]">
                  · {e.agent}
                </span>
              </div>
              <code className="block mt-1 text-xs font-mono text-[color:var(--muted-foreground)] break-all">
                {JSON.stringify(e.payload)}
              </code>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
