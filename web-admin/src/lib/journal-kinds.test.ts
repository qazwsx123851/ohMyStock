import { describe, it, expect } from 'vitest'
import {
  JOURNAL_KIND_ALL,
  JOURNAL_KIND_ENTRY_LIKE,
  type JournalKind,
} from './journal-kinds'

describe('journal-kinds', () => {
  it('JOURNAL_KIND_ENTRY_LIKE equals [entry, fill, exit, reject] (order-sensitive)', () => {
    expect([...JOURNAL_KIND_ENTRY_LIKE]).toEqual([
      'entry',
      'fill',
      'exit',
      'reject',
    ])
  })

  it('JOURNAL_KIND_ENTRY_LIKE is a subset of JOURNAL_KIND_ALL', () => {
    const all = JOURNAL_KIND_ALL as readonly string[]
    expect(JOURNAL_KIND_ENTRY_LIKE.every((k) => all.includes(k))).toBe(true)
  })

  it('JOURNAL_KIND_ALL has 11 entries (4 entry-like + 7 lifecycle/risk)', () => {
    expect(JOURNAL_KIND_ALL.length).toBe(11)
  })

  it('JournalKind type is the union of JOURNAL_KIND_ALL members', () => {
    const k: JournalKind = 'risk_off_triggered'
    expect(JOURNAL_KIND_ALL).toContain(k)
  })
})
