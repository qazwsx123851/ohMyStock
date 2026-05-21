/**
 * Side panel shown when a character sprite is clicked.
 * Renders only allowlisted public fields — never reasoning_full / payload internals.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Agent Info Sheet)
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { stripFourDigit } from '@/lib/maskBubble'
import type { Character, CharacterId, PublicEvent } from '@/types/public-event'

export interface AgentInfoSheetProps {
  open: boolean
  character: Character | null
  timeline: PublicEvent[]
  onClose: () => void
}

const AGENT_LABEL: Record<CharacterId, string> = {
  scanner: 'Scanner',
  pattern_analyst: 'Pattern Analyst',
  decider: 'Decider',
  trader: 'Trader',
  librarian: 'Librarian',
  reviewer_1: 'Reviewer 1',
  reviewer_2: 'Reviewer 2',
  reviewer_3: 'Reviewer 3',
  reviewer_4: 'Reviewer 4',
  reviewer_5: 'Reviewer 5',
  proposer: 'Proposer',
  validator: 'Validator',
  guard: 'Guard',
}

const AGENT_TO_CHAR: Record<string, CharacterId | undefined> = {
  scanner: 'scanner',
  screener: 'scanner',
  pattern_analyst: 'pattern_analyst',
  decider: 'decider',
  trader: 'trader',
  librarian: 'librarian',
  journal: 'librarian',
  proposer: 'proposer',
  validator: 'validator',
  risk_gate: 'guard',
  guard: 'guard',
}

function eventsForCharacter(
  charId: CharacterId,
  timeline: ReadonlyArray<PublicEvent>,
): PublicEvent[] {
  return timeline
    .filter((e) => {
      const mapped = AGENT_TO_CHAR[e.agent]
      if (mapped === charId) return true
      if (charId.startsWith('reviewer_') && e.agent === 'reviewer') {
        const idx = (e.payload as { node_index?: number }).node_index
        return `reviewer_${idx}` === charId
      }
      return false
    })
    .slice(0, 5)
}

function summariseEvent(e: PublicEvent): string {
  const ALLOW = [
    'masked_symbol',
    'pattern',
    'score',
    'confidence',
    'action',
    'priority',
    'target_section',
    'severity',
  ]
  const parts: string[] = [e.event_type]
  for (const k of ALLOW) {
    const v = (e.payload as Record<string, unknown>)[k]
    if (v !== undefined) parts.push(`${k}=${String(v)}`)
  }
  return stripFourDigit(parts.join(' · '))
}

export function AgentInfoSheet({
  open,
  character,
  timeline,
  onClose,
}: AgentInfoSheetProps) {
  const { t } = useTranslation()
  const recent = useMemo(
    () => (character ? eventsForCharacter(character.id, timeline) : []),
    [character, timeline],
  )

  if (!open || !character) return null

  const total = recent.length
  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-label={t('agent_sheet.title')}
      data-testid="agent-info-sheet"
      className="fixed top-16 right-4 z-40 w-72 rounded border border-zinc-200 bg-white shadow-lg p-4 text-sm"
    >
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-base font-semibold">
          {AGENT_LABEL[character.id]}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-xs underline text-[color:var(--muted-foreground)]"
        >
          {t('agent_sheet.close')}
        </button>
      </div>
      <p className="text-xs text-[color:var(--muted-foreground)]">
        {t('agent_sheet.state')}:{' '}
        <span className="font-mono">{character.state.kind}</span>
      </p>
      <p className="text-xs text-[color:var(--muted-foreground)] mb-2">
        {t('agent_sheet.total_today')}: {total}
      </p>
      <h3 className="text-xs font-semibold mt-2 mb-1">
        {t('agent_sheet.recent')}
      </h3>
      {recent.length === 0 ? (
        <p className="text-xs text-[color:var(--muted-foreground)]">
          {t('agent_sheet.no_events')}
        </p>
      ) : (
        <ul data-testid="agent-recent-events" className="space-y-1">
          {recent.map((e) => (
            <li
              key={e.event_id}
              className="text-xs font-mono break-all border-l-2 border-zinc-200 pl-2"
            >
              {summariseEvent(e)}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
