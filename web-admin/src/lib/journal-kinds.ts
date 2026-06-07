// Single source of truth for journal kind enums used by /paper/orders + /audit
// filter UIs. These MUST match the backend's accepted kinds
// (ohmystock.api.routes.journal._VALID_KINDS) — any other value 400s. The
// canonical taxonomy is docs/llm-decision-schema.md §4 (only these 5 kinds are
// ever written as journal rows; live-event types are NOT journal kinds).

export const JOURNAL_KIND_ENTRY_LIKE = ['entry', 'exit', 'reject'] as const

export const JOURNAL_KIND_ALL = [
  'entry',
  'exit',
  'reject',
  'expire',
  'auto_execute_audit',
] as const

export type JournalKind = (typeof JOURNAL_KIND_ALL)[number]
