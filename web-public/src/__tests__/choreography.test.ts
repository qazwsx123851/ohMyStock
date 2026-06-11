import { describe, expect, it } from 'vitest'
import { pathfind } from '@/canvas/pathfind'
import { OBSTACLES } from '@/canvas/characters/obstacles'
import { DEFAULT_SEATS } from '@/canvas/characters/seats'

/**
 * The walk choreography in eventToAction.ts only works if its target tiles
 * are reachable from the movable characters' seats on the obstacle grid.
 */
describe('walk choreography reachability', () => {
  it('decider can reach the counter front and walk home', () => {
    const counterFront = { x: 24, y: 16 }
    expect(pathfind(DEFAULT_SEATS.decider, counterFront, OBSTACLES)).not.toBeNull()
    expect(pathfind(counterFront, DEFAULT_SEATS.decider, OBSTACLES)).not.toBeNull()
  })

  it('proposer can reach the centre floor and walk home', () => {
    const centreFloor = { x: 15, y: 14 }
    expect(pathfind(DEFAULT_SEATS.proposer, centreFloor, OBSTACLES)).not.toBeNull()
    expect(pathfind(centreFloor, DEFAULT_SEATS.proposer, OBSTACLES)).not.toBeNull()
  })

  it('no movable seat or choreography target sits on an obstacle', () => {
    for (const id of ['proposer', 'decider', 'trader'] as const) {
      const s = DEFAULT_SEATS[id]
      expect(OBSTACLES.has(`${s.x},${s.y}`)).toBe(false)
    }
    expect(OBSTACLES.has('24,16')).toBe(false)
    expect(OBSTACLES.has('15,14')).toBe(false)
  })
})
