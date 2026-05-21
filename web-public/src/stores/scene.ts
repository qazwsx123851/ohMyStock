/**
 * Scene store — Zustand store for characters, per-character action queues,
 * timeline, and tick rate.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirements: Action Queue Backpressure, Activity Timeline,
 *        Idle Fallback Display, Game Loop Cadence)
 */

import { create } from 'zustand'
import {
  ALL_CHARACTER_IDS,
  type Character,
  type CharacterAction,
  type CharacterId,
  type PublicEvent,
} from '@/types/public-event'
import { DEFAULT_SEATS } from '@/canvas/characters/seats'
import { generatePlaceholderSheet } from '@/canvas/spritePlaceholder'

export const QUEUE_CAP = 5
export const TIMELINE_CAP = 100

function makeInitialCharacters(): Character[] {
  return ALL_CHARACTER_IDS.map((id) => ({
    id,
    pos: { ...DEFAULT_SEATS[id] },
    seat: { ...DEFAULT_SEATS[id] },
    facing: 'down',
    state: { kind: 'idle' as const },
  }))
}

function makeInitialQueues(): Record<CharacterId, CharacterAction[]> {
  const q = {} as Record<CharacterId, CharacterAction[]>
  for (const id of ALL_CHARACTER_IDS) q[id] = []
  return q
}

function makeInitialSprites(): Map<CharacterId, HTMLCanvasElement> | null {
  if (typeof document === 'undefined') return null
  try {
    const m = new Map<CharacterId, HTMLCanvasElement>()
    for (const id of ALL_CHARACTER_IDS) {
      m.set(id, generatePlaceholderSheet(id))
    }
    return m
  } catch {
    // jsdom (test env) lacks a 2D canvas context — render is a no-op there.
    return null
  }
}

export interface SceneState {
  characters: Character[]
  actionQueues: Record<CharacterId, CharacterAction[]>
  timeline: PublicEvent[]
  lastEventAt: number | null
  tickHz: 30 | 15
  sprites: Map<CharacterId, HTMLCanvasElement> | null
  enqueueAction: (action: CharacterAction) => void
  pushTimeline: (event: PublicEvent) => void
  dequeueAction: (id: CharacterId) => CharacterAction | undefined
  peekAction: (id: CharacterId) => CharacterAction | undefined
  setTickHz: (hz: 30 | 15) => void
  reset: () => void
}

export const useSceneStore = create<SceneState>((set, get) => ({
  characters: makeInitialCharacters(),
  actionQueues: makeInitialQueues(),
  timeline: [],
  lastEventAt: null,
  tickHz: 30,
  sprites: makeInitialSprites(),

  enqueueAction(action) {
    const { characters, actionQueues } = get()
    const char = characters.find((c) => c.id === action.targetCharId)
    if (!char) return
    const queue = actionQueues[action.targetCharId]
    queue.push(action)
    if (queue.length > QUEUE_CAP) {
      queue.shift()
    }
    set({ actionQueues: { ...actionQueues } })
  },

  pushTimeline(event) {
    const { timeline } = get()
    const next = [event, ...timeline]
    if (next.length > TIMELINE_CAP) {
      next.length = TIMELINE_CAP
    }
    set({ timeline: next, lastEventAt: Date.now() })
  },

  dequeueAction(id) {
    const { actionQueues } = get()
    const queue = actionQueues[id]
    const a = queue.shift()
    if (a) set({ actionQueues: { ...actionQueues } })
    return a
  },

  peekAction(id) {
    return get().actionQueues[id][0]
  },

  setTickHz(hz) {
    set({ tickHz: hz })
  },

  reset() {
    set({
      characters: makeInitialCharacters(),
      actionQueues: makeInitialQueues(),
      timeline: [],
      lastEventAt: null,
      tickHz: 30,
    })
  },
}))
