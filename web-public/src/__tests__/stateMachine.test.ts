import { describe, expect, it } from 'vitest'
import { tick, type TickContext } from '@/canvas/characterStateMachine'
import type { Character, CharacterAction, GridKey } from '@/types/public-event'

function mkChar(): Character {
  return {
    id: 'decider',
    pos: { x: 4, y: 8 },
    facing: 'down',
    state: { kind: 'idle' },
    seat: { x: 4, y: 8 },
  }
}

function mkCtx(queue: CharacterAction[]): TickContext {
  return {
    obstacles: new Set<GridKey>(),
    peekNext: () => queue[0],
    dequeueNext: () => queue.shift(),
  }
}

describe('character state machine', () => {
  it('stays idle when no actions queued', () => {
    const c = mkChar()
    tick(c, 0, mkCtx([]))
    expect(c.state.kind).toBe('idle')
  })

  it('idle → acting when target equals current pos', () => {
    const c = mkChar()
    const ctx = mkCtx([
      {
        targetCharId: 'decider',
        action: 'thinking',
        durationMs: 1000,
        bubble: 'scoring',
        targetPos: { x: 4, y: 8 },
      },
    ])
    tick(c, 1000, ctx)
    expect(c.state.kind).toBe('acting')
    if (c.state.kind === 'acting') {
      expect(c.state.action).toBe('thinking')
      expect(c.state.durationMs).toBe(1000)
    }
  })

  it('idle → walking → acting (multi-step)', () => {
    const c = mkChar()
    const ctx = mkCtx([
      {
        targetCharId: 'decider',
        action: 'reporting',
        durationMs: 5000,
        bubble: 'done',
        targetPos: { x: 6, y: 8 },
      },
    ])
    let t = 0
    tick(c, t, ctx)
    expect(c.state.kind).toBe('walking')
    // Path from (4,8) → (6,8) is 2 steps at TICK_MS=200; advance 3 ticks to
    // ensure arrival.
    for (let step = 0; step < 3; step++) {
      t += 250
      tick(c, t, ctx)
    }
    expect(c.state.kind).toBe('acting')
    expect(c.pos).toEqual({ x: 6, y: 8 })
  })

  it('acting → idle after durationMs', () => {
    const c = mkChar()
    c.state = { kind: 'acting', action: 'x', startedAt: 1000, durationMs: 500 }
    tick(c, 1499, mkCtx([]))
    expect(c.state.kind).toBe('acting')
    tick(c, 1500, mkCtx([]))
    expect(c.state.kind).toBe('idle')
  })

  it('dequeues next action on transition to idle', () => {
    const c = mkChar()
    c.state = { kind: 'acting', action: 'x', startedAt: 0, durationMs: 100 }
    const queue: CharacterAction[] = [
      {
        targetCharId: 'decider',
        action: 'next',
        durationMs: 200,
        bubble: 'next',
        targetPos: { x: 4, y: 8 },
      },
    ]
    const ctx = mkCtx(queue)
    tick(c, 100, ctx)
    tick(c, 101, ctx)
    expect(c.state.kind).toBe('acting')
    if (c.state.kind === 'acting') {
      expect(c.state.action).toBe('next')
    }
  })
})
