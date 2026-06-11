/**
 * Character state machine — three states (idle / walking / acting).
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Character State Machine)
 */

import { pathfind } from './pathfind'
import { DEFAULT_FACINGS } from './characters/seats'
import {
  type Character,
  type CharacterAction,
  type Facing,
  type GridKey,
  type GridPos,
} from '@/types/public-event'

const TICK_MS = 200

function facingFor(from: GridPos, to: GridPos): Facing {
  if (to.x > from.x) return 'right'
  if (to.x < from.x) return 'left'
  if (to.y > from.y) return 'down'
  return 'up'
}

function startAction(
  char: Character,
  action: CharacterAction,
  now: number,
): void {
  char.state = {
    kind: 'acting',
    action: action.action,
    startedAt: now,
    durationMs: action.durationMs,
    bubble: action.bubble,
  }
}

function startMovement(
  char: Character,
  target: GridPos,
  obstacles: ReadonlySet<GridKey>,
  pendingAction: CharacterAction | undefined,
  now: number,
): void {
  const path = pathfind(char.pos, target, obstacles)
  if (path === null || path.length === 0) {
    if (pendingAction) {
      startAction(char, pendingAction, now)
    }
    return
  }
  char.state = { kind: 'walking', path, pathIdx: 0, lastStepAt: now }
}

function settleAtRest(char: Character): void {
  if (char.pos.x === char.seat.x && char.pos.y === char.seat.y) {
    // back home — restore the mockup rest pose
    char.facing = DEFAULT_FACINGS[char.id]
  }
}

export interface TickContext {
  obstacles: ReadonlySet<GridKey>
  peekNext: () => CharacterAction | undefined
  dequeueNext: () => CharacterAction | undefined
}

export function tick(char: Character, now: number, ctx: TickContext): void {
  switch (char.state.kind) {
    case 'idle': {
      const action = ctx.peekNext()
      if (!action) return
      const target = action.targetPos ?? char.seat
      if (target.x === char.pos.x && target.y === char.pos.y) {
        ctx.dequeueNext()
        startAction(char, action, now)
      } else {
        ctx.dequeueNext()
        char.pendingAction = action
        startMovement(char, target, ctx.obstacles, action, now)
      }
      return
    }
    case 'walking': {
      if (now - char.state.lastStepAt < TICK_MS) return
      const next = char.state.path[char.state.pathIdx]
      if (!next) {
        const pending = char.pendingAction
        char.pendingAction = undefined
        if (pending) {
          startAction(char, pending, now)
        } else {
          char.state = { kind: 'idle' }
          settleAtRest(char)
        }
        return
      }
      char.facing = facingFor(char.pos, next)
      char.pos = next
      const newIdx = char.state.pathIdx + 1
      char.state = {
        kind: 'walking',
        path: char.state.path,
        pathIdx: newIdx,
        lastStepAt: now,
      }
      if (newIdx >= char.state.path.length) {
        const pending = char.pendingAction
        char.pendingAction = undefined
        if (pending) {
          startAction(char, pending, now)
        } else {
          char.state = { kind: 'idle' }
          settleAtRest(char)
        }
      }
      return
    }
    case 'acting': {
      if (now - char.state.startedAt < char.state.durationMs) return
      char.state = { kind: 'idle' }
      // Done performing away from home with nothing queued — walk back.
      if (
        !ctx.peekNext() &&
        (char.pos.x !== char.seat.x || char.pos.y !== char.seat.y)
      ) {
        startMovement(char, char.seat, ctx.obstacles, undefined, now)
      }
      return
    }
  }
}

declare module '@/types/public-event' {
  interface Character {
    pendingAction?: CharacterAction
  }
}
