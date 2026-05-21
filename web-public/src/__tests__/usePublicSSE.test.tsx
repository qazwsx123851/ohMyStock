import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePublicSSE } from '@/hooks/usePublicSSE'
import { useSceneStore } from '@/stores/scene'

class FakeEventSource {
  url: string
  listeners: Record<string, ((ev: MessageEvent) => void)[]> = {}
  closed = false
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void): void {
    ;(this.listeners[type] ??= []).push(fn)
  }
  removeEventListener(type: string, fn: (ev: MessageEvent) => void): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn)
  }
  close(): void {
    this.closed = true
  }
  emit(data: unknown): void {
    const msg = { data: JSON.stringify(data) } as MessageEvent
    for (const fn of this.listeners.message ?? []) fn(msg)
  }
  static instances: FakeEventSource[] = []
  static reset(): void {
    FakeEventSource.instances = []
  }
}

describe('usePublicSSE', () => {
  beforeEach(() => {
    FakeEventSource.reset()
    useSceneStore.getState().reset()
  })

  it('opens an EventSource against /api/public/events on mount', () => {
    const factory = vi.fn((url: string) => new FakeEventSource(url) as unknown as EventSource)
    renderHook(() => usePublicSSE({ eventSourceFactory: factory }))
    expect(factory).toHaveBeenCalledWith('/api/public/events')
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('closes the EventSource on unmount', () => {
    const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource
    const { unmount } = renderHook(() => usePublicSSE({ eventSourceFactory: factory }))
    unmount()
    expect(FakeEventSource.instances[0]!.closed).toBe(true)
  })

  it('dispatches a known event into store timeline and queue', () => {
    const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource
    renderHook(() => usePublicSSE({ eventSourceFactory: factory }))
    const es = FakeEventSource.instances[0]!
    es.emit({
      event_id: 'e1',
      timestamp: new Date().toISOString(),
      event_type: 'decision_made',
      agent: 'decider',
      payload: { masked_symbol: 'STK-A', confidence: 0.7, action: 'entry' },
    })
    const state = useSceneStore.getState()
    expect(state.timeline).toHaveLength(1)
    expect(state.actionQueues.decider).toHaveLength(1)
  })

  it('ignores unknown event_type without throwing', () => {
    const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource
    renderHook(() => usePublicSSE({ eventSourceFactory: factory }))
    const es = FakeEventSource.instances[0]!
    expect(() =>
      es.emit({
        event_id: 'e1',
        timestamp: new Date().toISOString(),
        event_type: 'future_unknown_v2',
        agent: 'whatever',
        payload: {},
      }),
    ).not.toThrow()
    const state = useSceneStore.getState()
    expect(state.timeline).toHaveLength(1)
    expect(state.actionQueues.decider).toHaveLength(0)
  })
})
