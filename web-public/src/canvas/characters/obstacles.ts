/**
 * Static obstacle grid for the office scene. Includes the wall band and
 * furniture footprints so BFS pathfind avoids walking through them.
 *
 * render.ts draws the same furniture geometry, so any change here MUST be
 * mirrored in render.ts drawStaticFurniture().
 */

import { GRID_COLS, type GridKey, type GridPos, gridKey } from '@/types/public-event'

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
  ...rect(0, 0, GRID_COLS, 3), // top wall band (cream wall + trim)
  ...rect(0, 3, 1, 2), // vending cabinet, left wall
  ...rect(2, 6, 2, 1), // workstation desk 1
  ...rect(5, 6, 2, 1), // workstation desk 2
  ...rect(13, 8, 9, 1), // reception counter, horizontal arm
  ...rect(21, 9, 1, 3), // reception counter, vertical arm
  ...rect(22, 4, 2, 2), // printer, right wall
  ...rect(22, 6, 2, 2), // drawer unit, right wall
  ...rect(21, 12, 1, 2), // water cooler
  ...rect(22, 14, 1, 1), // waste bin
  ...rect(13, 12, 2, 1), // review desk 1
  ...rect(16, 12, 2, 1), // review desk 2
  ...rect(3, 11, 3, 2), // library table
  ...rect(1, 12, 1, 2), // floor plant, bottom-left
]

export const OBSTACLES: ReadonlySet<GridKey> = new Set(
  OBSTACLE_CELLS.map(gridKey),
)
