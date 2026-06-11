/**
 * Single requestAnimationFrame loop driving fixed-timestep ticks (30 Hz)
 * and per-frame renders (~60 Hz on a 60 Hz display).
 *
 * Drops to 15 Hz when document.hidden becomes true; restores to 30 Hz
 * when the tab becomes visible again.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirements: Game Loop Cadence, Performance Budget)
 */

import { drawScene, type SceneSnapshot } from './render'
import { tick, type TickContext } from './characterStateMachine'
import { OBSTACLES } from './characters/obstacles'
import { useSceneStore } from '@/stores/scene'

export interface LoopHandle {
  stop: () => void
}

export interface StartLoopOptions {
  canvas: HTMLCanvasElement
  /** Test seam: override animation frame scheduler. */
  raf?: (cb: FrameRequestCallback) => number
  caf?: (handle: number) => void
  /** Test seam: override visibility source. */
  getHidden?: () => boolean
}

export function startLoop(opts: StartLoopOptions): LoopHandle {
  const { canvas } = opts
  const maybeCtx = canvas.getContext('2d')
  if (!maybeCtx) throw new Error('startLoop: 2D context unavailable')
  const ctx: CanvasRenderingContext2D = maybeCtx

  const raf = opts.raf ?? ((cb) => requestAnimationFrame(cb))
  const caf = opts.caf ?? ((h) => cancelAnimationFrame(h))
  const getHidden =
    opts.getHidden ?? (() => (typeof document !== 'undefined' ? document.hidden : false))

  let rafId = 0
  let stopped = false
  let lastTickAt = 0

  function tickCharacters(now: number): void {
    const store = useSceneStore.getState()
    for (const char of store.characters) {
      const ctxTick: TickContext = {
        obstacles: OBSTACLES,
        peekNext: () => store.peekAction(char.id),
        dequeueNext: () => store.dequeueAction(char.id),
      }
      tick(char, now, ctxTick)
    }
  }

  function frame(now: number): void {
    if (stopped) return
    const tickHz = getHidden() ? 15 : 30
    if (useSceneStore.getState().tickHz !== tickHz) {
      useSceneStore.getState().setTickHz(tickHz)
    }
    const msPerTick = 1000 / tickHz
    if (now - lastTickAt >= msPerTick) {
      tickCharacters(now)
      lastTickAt = now
    }
    const store = useSceneStore.getState()
    const snap: SceneSnapshot = {
      characters: store.characters,
      sprites: (store.sprites ?? new Map()) as ReadonlyMap<string, CanvasImageSource>,
      bg: store.bg,
    }
    drawScene(ctx, snap, now)
    rafId = raf(frame)
  }

  rafId = raf(frame)

  const onVisibility = () => {
    // No-op — frame() reads getHidden() each frame.
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility)
  }

  return {
    stop() {
      stopped = true
      caf(rafId)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility)
      }
    },
  }
}
