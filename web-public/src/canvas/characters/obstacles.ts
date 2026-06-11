/**
 * Static obstacle grid for the office scene, derived from pixel rectangles
 * measured on the design-mockup background (office-bg.png). Only the three
 * movable characters consult this via BFS pathfind.
 */

import { TILE_PX, type GridKey, type GridPos, gridKey } from '@/types/public-event'

/** Pixel rects (x, y, w, h) of impassable furniture on the background. */
const OBSTACLE_RECTS_PX: ReadonlyArray<readonly [number, number, number, number]> = [
  [0, 0, 564, 118], // top wall band incl. wall furniture
  [0, 110, 33, 58], // left fridge cabinet
  [22, 118, 36, 55], // top-left floor plant
  [500, 115, 40, 55], // top-right floor plant
  [70, 150, 145, 140], // mid-left desk pair + chairs + workers
  [366, 183, 40, 30], // back counter (plant)
  [366, 210, 198, 40], // reception counter, horizontal arm
  [515, 250, 49, 105], // reception counter, vertical arm
  [520, 90, 44, 120], // right-wall printer + drawer unit
  [295, 290, 185, 115], // bottom desk pair + workers
  [40, 320, 140, 90], // library table
  [25, 355, 35, 65], // bottom-left floor plant
  [520, 355, 44, 100], // water cooler + waste bin
]

function tilesCovering(rect: readonly [number, number, number, number]): GridPos[] {
  const [x, y, w, h] = rect
  const out: GridPos[] = []
  const x0 = Math.floor(x / TILE_PX)
  const y0 = Math.floor(y / TILE_PX)
  const x1 = Math.floor((x + w - 1) / TILE_PX)
  const y1 = Math.floor((y + h - 1) / TILE_PX)
  for (let gx = x0; gx <= x1; gx++) {
    for (let gy = y0; gy <= y1; gy++) {
      out.push({ x: gx, y: gy })
    }
  }
  return out
}

export const OBSTACLES: ReadonlySet<GridKey> = new Set(
  OBSTACLE_RECTS_PX.flatMap(tilesCovering).map(gridKey),
)
