/**
 * The Canvas 2D pixel office page.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirements: Office Scene Layout, Integer-Scale Pixel Rendering,
 *        Idle Fallback Display, Agent Info Sheet)
 */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { startLoop } from '@/canvas/gameLoop'
import { usePublicSSE } from '@/hooks/usePublicSSE'
import { useSceneStore } from '@/stores/scene'
import { AgentInfoSheet } from '@/components/AgentInfoSheet'
import {
  CANVAS_LOGICAL_H,
  CANVAS_LOGICAL_W,
  CSS_SCALE,
  type Character,
} from '@/types/public-event'
import {
  BLUE,
  BLUE_DARK,
  CYAN,
  GREEN_LEAF,
  INK,
  INK_SOFT,
  ORANGE,
  RED,
  TEAL,
  UNIFORM_NAVY,
} from '@/styles/palette'
import { hitTestCharacters } from '@/canvas/assets'
import { isDemoMode, startDemo } from '@/lib/demoScenario'

const LEGEND: ReadonlyArray<readonly [string, string]> = [
  ['Scanner', BLUE],
  ['PatternAnalyst', BLUE_DARK],
  ['Decider', RED],
  ['Trader', GREEN_LEAF],
  ['Librarian', ORANGE],
  ['Validator', TEAL],
  ['Reviewer', CYAN],
  ['Proposer', UNIFORM_NAVY],
  ['Guard', INK_SOFT],
]

const IDLE_TIMEOUT_MS = 60_000

export function OfficeScene() {
  const { t } = useTranslation()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [selected, setSelected] = useState<Character | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [pageOpenedAt] = useState(() => Date.now())
  const lastEventAt = useSceneStore((s) => s.lastEventAt)
  const characters = useSceneStore((s) => s.characters)
  const timeline = useSceneStore((s) => s.timeline)

  usePublicSSE()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const handle = startLoop({ canvas })
    return () => handle.stop()
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (!isDemoMode()) return
    return startDemo()
  }, [])

  const idle =
    lastEventAt === null
      ? now - pageOpenedAt > IDLE_TIMEOUT_MS
      : now - lastEventAt > IDLE_TIMEOUT_MS

  function onCanvasClick(ev: React.MouseEvent<HTMLCanvasElement>): void {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const xLogical = ((ev.clientX - rect.left) * CANVAS_LOGICAL_W) / rect.width
    const yLogical = ((ev.clientY - rect.top) * CANVAS_LOGICAL_H) / rect.height
    setSelected(hitTestCharacters(characters, xLogical, yLogical))
  }

  return (
    <section className="relative flex flex-col items-center">
      <div
        style={{
          width: CANVAS_LOGICAL_W * CSS_SCALE,
          height: CANVAS_LOGICAL_H * CSS_SCALE,
        }}
        className="relative"
      >
        <canvas
          ref={canvasRef}
          width={CANVAS_LOGICAL_W}
          height={CANVAS_LOGICAL_H}
          onClick={onCanvasClick}
          data-testid="office-canvas"
          style={{
            imageRendering: 'pixelated',
            transform: `scale(${CSS_SCALE})`,
            transformOrigin: 'top left',
            cursor: 'pointer',
          }}
        />
        {idle && (
          <div
            data-testid="idle-overlay"
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
            // INK with ~35% alpha (0x59 = 89/255). Palette-derived.
            style={{ background: `${INK}59` }}
          >
            <p className="px-3 py-1 rounded bg-white text-sm font-mono">
              {t('idle.overlay')}
            </p>
          </div>
        )}
      </div>
      <div
        data-testid="role-legend"
        className="mt-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-1"
      >
        {LEGEND.map(([label, colour]) => (
          <span key={label} className="flex items-center gap-1 text-xs text-[color:var(--muted-foreground)]">
            <span
              className="inline-block h-2.5 w-2.5 rounded-[2px]"
              style={{ background: colour }}
            />
            {label}
          </span>
        ))}
      </div>
      <AgentInfoSheet
        open={selected !== null}
        character={selected}
        timeline={timeline}
        onClose={() => setSelected(null)}
      />
    </section>
  )
}
