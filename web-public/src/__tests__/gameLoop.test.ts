import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { startLoop } from '@/canvas/gameLoop'
import { useSceneStore } from '@/stores/scene'

function mkFakeCtx(): CanvasRenderingContext2D {
  // jsdom doesn't ship a real 2D context. Build a fake that supports every
  // call our render code makes — all no-ops.
  const noop = () => {}
  return {
    imageSmoothingEnabled: false,
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    font: '',
    textBaseline: 'top',
    fillRect: noop,
    strokeRect: noop,
    fillText: noop,
    drawImage: noop,
    measureText: () => ({ width: 0 }) as TextMetrics,
  } as unknown as CanvasRenderingContext2D
}

function mkCanvas(): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = 384
  c.height = 256
  const fake = mkFakeCtx()
  Object.defineProperty(c, 'getContext', {
    value: () => fake,
    writable: true,
  })
  return c
}

describe('startLoop', () => {
  let activeFrames: Map<number, FrameRequestCallback>
  let nextId: number
  let rafCalls: number
  let cafCalls: number

  beforeEach(() => {
    useSceneStore.getState().reset()
    activeFrames = new Map()
    nextId = 1
    rafCalls = 0
    cafCalls = 0
  })

  afterEach(() => {
    activeFrames.clear()
  })

  function controlledRaf(cb: FrameRequestCallback): number {
    const id = nextId++
    activeFrames.set(id, cb)
    rafCalls++
    return id
  }
  function controlledCaf(id: number): void {
    activeFrames.delete(id)
    cafCalls++
  }
  function pumpFrame(now: number): void {
    const ids = Array.from(activeFrames.keys())
    for (const id of ids) {
      const cb = activeFrames.get(id)
      activeFrames.delete(id)
      cb?.(now)
    }
  }

  it('keeps scheduling frames while not stopped', () => {
    const canvas = mkCanvas()
    const handle = startLoop({
      canvas,
      raf: controlledRaf,
      caf: controlledCaf,
      getHidden: () => false,
    })
    for (let f = 0; f < 60; f++) {
      pumpFrame((f + 1) * (1000 / 60))
    }
    handle.stop()
    expect(rafCalls).toBeGreaterThanOrEqual(60)
    expect(useSceneStore.getState().tickHz).toBe(30)
  })

  it('drops to 15 Hz when document hidden', () => {
    const canvas = mkCanvas()
    let hidden = false
    const handle = startLoop({
      canvas,
      raf: controlledRaf,
      caf: controlledCaf,
      getHidden: () => hidden,
    })
    hidden = true
    pumpFrame(16)
    expect(useSceneStore.getState().tickHz).toBe(15)
    handle.stop()
  })

  it('stops scheduling further frames after stop()', () => {
    const canvas = mkCanvas()
    const handle = startLoop({
      canvas,
      raf: controlledRaf,
      caf: controlledCaf,
      getHidden: () => false,
    })
    expect(activeFrames.size).toBe(1)
    handle.stop()
    expect(cafCalls).toBe(1)
    const beforePump = rafCalls
    pumpFrame(16)
    expect(rafCalls).toBe(beforePump)
  })
})
