/**
 * 4-neighbour BFS over the 24×16 office grid.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: BFS Pathfinding)
 */

import {
  GRID_COLS,
  GRID_ROWS,
  type GridKey,
  type GridPos,
  gridKey,
} from '@/types/public-event'

const DELTAS: ReadonlyArray<readonly [number, number]> = [
  [0, 1],
  [0, -1],
  [1, 0],
  [-1, 0],
]

function inBounds(p: GridPos): boolean {
  return p.x >= 0 && p.x < GRID_COLS && p.y >= 0 && p.y < GRID_ROWS
}

export function pathfind(
  from: GridPos,
  to: GridPos,
  obstacles: ReadonlySet<GridKey>,
): GridPos[] | null {
  if (from.x === to.x && from.y === to.y) {
    return []
  }
  if (!inBounds(from) || !inBounds(to)) {
    return null
  }
  if (obstacles.has(gridKey(to))) {
    return null
  }

  const visited = new Map<GridKey, GridKey | null>()
  visited.set(gridKey(from), null)
  const queue: GridPos[] = [from]

  while (queue.length > 0) {
    const cur = queue.shift()!
    if (cur.x === to.x && cur.y === to.y) {
      const path: GridPos[] = []
      let k: GridKey | null = gridKey(cur)
      while (k !== null) {
        const [xs, ys] = k.split(',')
        path.push({ x: Number(xs), y: Number(ys) })
        k = visited.get(k) ?? null
      }
      path.reverse()
      // Drop the starting cell — caller already stands there.
      path.shift()
      return path
    }
    for (const [dx, dy] of DELTAS) {
      const next: GridPos = { x: cur.x + dx, y: cur.y + dy }
      const nk = gridKey(next)
      if (!inBounds(next)) continue
      if (visited.has(nk)) continue
      if (obstacles.has(nk)) continue
      visited.set(nk, gridKey(cur))
      queue.push(next)
    }
  }
  return null
}
