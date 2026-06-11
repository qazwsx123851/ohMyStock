/**
 * Pixel-office palette — sampled from the reference design mockup
 * (Pokémon Gen 4 interior style: sage checkered floor, cream walls,
 * warm wood furniture, near-black outlines).
 *
 * Every visual surface (Canvas fill/stroke, sprite generation, tile draw
 * helpers, UI overlay colours) MUST import from this module.
 *
 * Spec: openspec/specs/web-public-pixel-office/spec.md
 */

export const PALETTE = {
  // Outlines / shadows
  INK: '#17181a',
  INK_SOFT: '#3a3c38',

  // Floor (checkered sage)
  FLOOR_A: '#aebd9d',
  FLOOR_B: '#8ca795',
  FLOOR_A_DITHER: '#b9c6a8',
  FLOOR_B_DITHER: '#97b09e',
  FLOOR_SHADOW: '#6e8879',

  // Walls
  WALL_CREAM: '#e3d8b4',
  WALL_CREAM_SHADOW: '#cfc49e',
  WALL_TRIM: '#8a8062',
  WALL_TRIM_DARK: '#5f5844',

  // Wood furniture
  WOOD_LIGHT: '#d6b271',
  WOOD: '#b98c4a',
  WOOD_DARK: '#8a6228',
  WOOD_DEEP: '#5c401c',

  // Neutral surfaces (printer, vending, clock faces, paper)
  WHITE: '#f2f2ee',
  GRAY_LIGHT: '#c9cdd1',
  GRAY: '#8e9499',
  GRAY_DARK: '#5a5f66',

  // Screens
  SCREEN_BEZEL: '#22262e',
  SCREEN_BLUE: '#7fc4e8',
  SCREEN_BLUE_DARK: '#3a78c2',
  SCREEN_GLOW: '#d8f0fa',

  // Accents
  RED: '#c83232',
  RED_DARK: '#8e2020',
  ORANGE: '#d2691e',
  YELLOW: '#e0c050',
  GREEN_LEAF: '#4e9a4e',
  GREEN_LIGHT: '#6fbf6f',
  GREEN_DARK: '#2f6e38',
  BLUE: '#3868c8',
  BLUE_DARK: '#2f4878',
  WATER_BLUE: '#7fb4d8',
  POT_CLAY: '#b06038',
  POT_CLAY_DARK: '#7c3f22',

  // Characters
  SKIN: '#efc89e',
  SKIN_SHADOW: '#c89868',
  HAIR_BLACK: '#2a2a33',
  HAIR_BROWN: '#7a4f2b',
  HAIR_BLOND: '#c8a04e',
  PANTS: '#3a4254',
  PANTS_BROWN: '#6b5436',
  SHOES: '#23232b',
  TEAL: '#2e9688',
  CYAN: '#38a8c0',
  UNIFORM_NAVY: '#26365e',
} as const

export type PaletteToken = keyof typeof PALETTE
export type PaletteHex = (typeof PALETTE)[PaletteToken]

export const PALETTE_HEXES: readonly PaletteHex[] = Object.values(PALETTE)

export const {
  INK,
  INK_SOFT,
  FLOOR_A,
  FLOOR_B,
  FLOOR_A_DITHER,
  FLOOR_B_DITHER,
  FLOOR_SHADOW,
  WALL_CREAM,
  WALL_CREAM_SHADOW,
  WALL_TRIM,
  WALL_TRIM_DARK,
  WOOD_LIGHT,
  WOOD,
  WOOD_DARK,
  WOOD_DEEP,
  WHITE,
  GRAY_LIGHT,
  GRAY,
  GRAY_DARK,
  SCREEN_BEZEL,
  SCREEN_BLUE,
  SCREEN_BLUE_DARK,
  SCREEN_GLOW,
  RED,
  RED_DARK,
  ORANGE,
  YELLOW,
  GREEN_LEAF,
  GREEN_LIGHT,
  GREEN_DARK,
  BLUE,
  BLUE_DARK,
  WATER_BLUE,
  POT_CLAY,
  POT_CLAY_DARK,
  SKIN,
  SKIN_SHADOW,
  HAIR_BLACK,
  HAIR_BROWN,
  HAIR_BLOND,
  PANTS,
  PANTS_BROWN,
  SHOES,
  TEAL,
  CYAN,
  UNIFORM_NAVY,
} = PALETTE
