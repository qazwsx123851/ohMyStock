/**
 * Frozen Pokémon Gen 2 (Game Boy Color) palette.
 *
 * Every visual surface (Canvas fill/stroke, sprite placeholder generation,
 * tile draw helpers, region backgrounds, UI overlay text colour) MUST import
 * from this module. Off-palette hex literals are guarded by task 12.7.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Frozen Gen 2 Palette)
 */

export const PALETTE = {
  GB_WALL: '#2b2b2b',
  GB_FLOOR_DARK: '#a0a0a0',
  GB_FLOOR_LIGHT: '#d8d8d8',
  GB_FURNITURE: '#e8b840',
  GB_FURNITURE_SHADOW: '#a07820',
  GB_ACCENT: '#e84020',
  GB_HIGHLIGHT: '#80b8e8',
} as const

export type PaletteToken = keyof typeof PALETTE
export type PaletteHex = (typeof PALETTE)[PaletteToken]

export const PALETTE_HEXES: readonly PaletteHex[] = Object.values(PALETTE)

export const {
  GB_WALL,
  GB_FLOOR_DARK,
  GB_FLOOR_LIGHT,
  GB_FURNITURE,
  GB_FURNITURE_SHADOW,
  GB_ACCENT,
  GB_HIGHLIGHT,
} = PALETTE
