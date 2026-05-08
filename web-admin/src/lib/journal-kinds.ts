// Single source of truth for journal kind enums used by /paper/orders + /audit
// filter UIs. Keep in sync with openspec/specs/admin-read-endpoints/spec.md.

export const JOURNAL_KIND_ENTRY_LIKE = [
  'entry',
  'fill',
  'exit',
  'reject',
] as const

export const JOURNAL_KIND_ALL = [
  'entry',
  'fill',
  'exit',
  'reject',
  'decision_made',
  'awaiting_confirm',
  'decider_thinking',
  'risk_off_triggered',
  'breaker_tripped',
  'confirm_received',
  'confirm_rejected',
] as const

export type JournalKind = (typeof JOURNAL_KIND_ALL)[number]
