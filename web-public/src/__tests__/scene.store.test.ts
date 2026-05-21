import { beforeEach, describe, expect, it } from 'vitest'
import { QUEUE_CAP, TIMELINE_CAP, useSceneStore } from '@/stores/scene'
import type { CharacterAction, PublicEvent } from '@/types/public-event'

function mkAction(seq: number): CharacterAction {
  return {
    targetCharId: 'decider',
    action: `a${seq}`,
    durationMs: 1000,
    bubble: `b${seq}`,
  }
}

function mkEvent(id: string): PublicEvent {
  return {
    event_id: id,
    timestamp: new Date().toISOString(),
    event_type: 'decision_made',
    agent: 'decider',
    payload: {},
  }
}

describe('useSceneStore', () => {
  beforeEach(() => {
    useSceneStore.getState().reset()
  })

  it('enqueueAction adds to the targeted character queue', () => {
    useSceneStore.getState().enqueueAction(mkAction(1))
    expect(useSceneStore.getState().actionQueues.decider).toHaveLength(1)
  })

  it('drops oldest when queue exceeds cap', () => {
    for (let i = 0; i < QUEUE_CAP + 3; i++) {
      useSceneStore.getState().enqueueAction(mkAction(i))
    }
    const queue = useSceneStore.getState().actionQueues.decider
    expect(queue).toHaveLength(QUEUE_CAP)
    expect(queue[0]!.action).toBe('a3')
    expect(queue[QUEUE_CAP - 1]!.action).toBe(`a${QUEUE_CAP + 2}`)
  })

  it('pushTimeline prepends newest', () => {
    useSceneStore.getState().pushTimeline(mkEvent('e1'))
    useSceneStore.getState().pushTimeline(mkEvent('e2'))
    expect(useSceneStore.getState().timeline.map((e) => e.event_id)).toEqual([
      'e2',
      'e1',
    ])
  })

  it('timeline caps at TIMELINE_CAP', () => {
    for (let i = 0; i < TIMELINE_CAP + 50; i++) {
      useSceneStore.getState().pushTimeline(mkEvent(`e${i}`))
    }
    expect(useSceneStore.getState().timeline).toHaveLength(TIMELINE_CAP)
    expect(
      useSceneStore.getState().timeline[TIMELINE_CAP - 1]!.event_id,
    ).toBe('e50')
  })

  it('dequeueAction pops in FIFO order', () => {
    useSceneStore.getState().enqueueAction(mkAction(1))
    useSceneStore.getState().enqueueAction(mkAction(2))
    expect(useSceneStore.getState().dequeueAction('decider')?.action).toBe('a1')
    expect(useSceneStore.getState().dequeueAction('decider')?.action).toBe('a2')
    expect(useSceneStore.getState().dequeueAction('decider')).toBeUndefined()
  })

  it('setTickHz updates state', () => {
    useSceneStore.getState().setTickHz(15)
    expect(useSceneStore.getState().tickHz).toBe(15)
  })
})
