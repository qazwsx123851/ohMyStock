import { describe, expect, it } from 'vitest'
import { pathfind } from '@/canvas/pathfind'
import { gridKey, type GridKey } from '@/types/public-event'

const NO_OBSTACLES: ReadonlySet<GridKey> = new Set()

describe('pathfind', () => {
  it('returns empty path when from === to', () => {
    const p = pathfind({ x: 4, y: 4 }, { x: 4, y: 4 }, NO_OBSTACLES)
    expect(p).toEqual([])
  })

  it('finds a straight 4-step path with no obstacles', () => {
    const p = pathfind({ x: 0, y: 0 }, { x: 4, y: 0 }, NO_OBSTACLES)
    expect(p).not.toBeNull()
    expect(p!.length).toBe(4)
    expect(p![p!.length - 1]).toEqual({ x: 4, y: 0 })
  })

  it('routes around a wall of obstacles', () => {
    const obstacles = new Set<GridKey>([
      gridKey({ x: 2, y: 0 }),
      gridKey({ x: 2, y: 1 }),
      gridKey({ x: 2, y: 2 }),
    ])
    const p = pathfind({ x: 0, y: 0 }, { x: 4, y: 0 }, obstacles)
    expect(p).not.toBeNull()
    expect(p!.length).toBeGreaterThan(4)
    for (const step of p!) {
      expect(obstacles.has(gridKey(step))).toBe(false)
    }
  })

  it('returns null when target is fully enclosed', () => {
    const obstacles = new Set<GridKey>([
      gridKey({ x: 4, y: 5 }),
      gridKey({ x: 6, y: 5 }),
      gridKey({ x: 5, y: 4 }),
      gridKey({ x: 5, y: 6 }),
    ])
    const p = pathfind({ x: 0, y: 0 }, { x: 5, y: 5 }, obstacles)
    expect(p).toBeNull()
  })

  it('returns null when from is out of bounds', () => {
    const p = pathfind({ x: -1, y: 0 }, { x: 4, y: 0 }, NO_OBSTACLES)
    expect(p).toBeNull()
  })
})
