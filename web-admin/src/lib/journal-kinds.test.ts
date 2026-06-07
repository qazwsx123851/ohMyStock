import { describe, it, expect } from 'vitest'
import {
  JOURNAL_KIND_ALL,
  JOURNAL_KIND_ENTRY_LIKE,
  type JournalKind,
} from './journal-kinds'

describe('journal-kinds', () => {
  it('JOURNAL_KIND_ENTRY_LIKE equals [entry, exit, reject] (order-sensitive)', () => {
    expect([...JOURNAL_KIND_ENTRY_LIKE]).toEqual(['entry', 'exit', 'reject'])
  })

  it('JOURNAL_KIND_ENTRY_LIKE is a subset of JOURNAL_KIND_ALL', () => {
    const all = JOURNAL_KIND_ALL as readonly string[]
    expect(JOURNAL_KIND_ENTRY_LIKE.every((k) => all.includes(k))).toBe(true)
  })

  it('JOURNAL_KIND_ALL equals the 5 backend _VALID_KINDS (SSOT §4)', () => {
    expect([...JOURNAL_KIND_ALL]).toEqual([
      'entry',
      'exit',
      'reject',
      'expire',
      'auto_execute_audit',
    ])
  })

  it('JournalKind type is the union of JOURNAL_KIND_ALL members', () => {
    const k: JournalKind = 'auto_execute_audit'
    expect(JOURNAL_KIND_ALL).toContain(k)
  })
})
