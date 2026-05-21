/**
 * Static obstacle grid for the office scene. Includes furniture footprints
 * so BFS pathfind avoids walking over the counter / shelves / tables.
 *
 * Kept tiny (under 30 cells) — render.ts draws the same furniture geometry,
 * so any change here MUST be mirrored in render.ts drawStaticFurniture().
 */

import { type GridKey, type GridPos, gridKey } from '@/types/public-event'

function rect(x: number, y: number, w: number, h: number): GridPos[] {
  const out: GridPos[] = []
  for (let dx = 0; dx < w; dx++) {
    for (let dy = 0; dy < h; dy++) {
      out.push({ x: x + dx, y: y + dy })
    }
  }
  return out
}

const OBSTACLE_CELLS: GridPos[] = [
  ...rect(1, 1, 3, 2),
  ...rect(16, 1, 3, 2),
  ...rect(3, 6, 7, 2),
  ...rect(20, 5, 3, 6),
  ...rect(14, 5, 3, 6),
  ...rect(3, 13, 5, 2),
  ...rect(15, 13, 7, 2),
]

export const OBSTACLES: ReadonlySet<GridKey> = new Set(
  OBSTACLE_CELLS.map(gridKey),
)
