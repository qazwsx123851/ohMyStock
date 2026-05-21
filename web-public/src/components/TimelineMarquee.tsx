/**
 * Horizontal-scroll marquee at the bottom of the page. Click to expand into
 * the existing <MaskedEventsFeed /> full list view (which preserves the
 * web-public-shell spec's MaskedEventsFeed requirement).
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Activity Timeline)
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSceneStore } from '@/stores/scene'
import { stripFourDigit } from '@/lib/maskBubble'
import { MaskedEventsFeed } from './MaskedEventsFeed'

const MARQUEE_LIMIT = 8

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

export function TimelineMarquee() {
  const { t } = useTranslation()
  const timeline = useSceneStore((s) => s.timeline)
  const [expanded, setExpanded] = useState(false)
  const head = timeline.slice(0, MARQUEE_LIMIT)
  return (
    <section
      data-testid="timeline-marquee"
      className="border-t border-zinc-200 bg-zinc-50"
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-2 text-xs"
      >
        <span className="font-semibold">{t('timeline.title')}</span>
        <span className="text-[color:var(--muted-foreground)]">
          ({timeline.length})
        </span>
        <span className="ml-auto underline">
          {expanded ? t('timeline.collapse') : t('timeline.expand')}
        </span>
      </button>
      {!expanded && (
        <div className="overflow-x-auto whitespace-nowrap px-4 pb-2 text-xs font-mono">
          {head.length === 0 ? (
            <span className="text-[color:var(--muted-foreground)]">
              {t('timeline.empty')}
            </span>
          ) : (
            head.map((e) => (
              <span
                key={e.event_id}
                data-testid="timeline-marquee-item"
                className="mr-4 inline-block"
              >
                <time className="text-[color:var(--muted-foreground)]">
                  [{formatTime(e.timestamp)}]
                </time>{' '}
                {stripFourDigit(e.event_type)} · {stripFourDigit(e.agent)}
              </span>
            ))
          )}
        </div>
      )}
      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-zinc-200">
          <MaskedEventsFeed />
        </div>
      )}
    </section>
  )
}
