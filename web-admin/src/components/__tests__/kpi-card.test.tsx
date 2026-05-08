import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { KpiCard, directionOf } from '../kpi-card'

describe('KpiCard', () => {
  it('direction=up renders text-up class and an ArrowUp svg (aria-hidden)', () => {
    const { container } = render(
      <KpiCard label="今日損益" value="+12,345" direction="up" />,
    )
    const valueRow = container.querySelector('[data-direction="up"]')
    expect(valueRow).not.toBeNull()
    expect(valueRow!.className).toMatch(/text-up/)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg).toHaveAttribute('aria-hidden')
  })

  it('direction=down renders text-down class and an ArrowDown svg', () => {
    const { container } = render(
      <KpiCard label="本週實現損益" value="-3,400" direction="down" />,
    )
    const valueRow = container.querySelector('[data-direction="down"]')
    expect(valueRow).not.toBeNull()
    expect(valueRow!.className).toMatch(/text-down/)
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('direction=neutral renders neither directional color nor a directional glyph', () => {
    const { container } = render(
      <KpiCard label="持倉檔數" value={4} direction="neutral" />,
    )
    const valueRow = container.querySelector('[data-direction="neutral"]')
    expect(valueRow).not.toBeNull()
    expect(valueRow!.className).not.toMatch(/text-up/)
    expect(valueRow!.className).not.toMatch(/text-down/)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('loading=true renders a Skeleton in place of the value', () => {
    const { container } = render(
      <KpiCard label="今日損益" value="+12,345" direction="up" loading />,
    )
    // shadcn Skeleton applies `animate-pulse`; spec scenario "Loading shows skeleton".
    expect(container.querySelector('.animate-pulse')).not.toBeNull()
    expect(container.textContent).not.toContain('+12,345')
    expect(container.querySelector('[data-direction]')).toBeNull()
  })

  it('glyph=null suppresses the directional arrow even when direction=up', () => {
    const { container } = render(
      <KpiCard label="x" value="1" direction="up" glyph={null} />,
    )
    expect(container.querySelector('svg')).toBeNull()
    // colour still applied — color is one of the two channels
    expect(container.querySelector('[data-direction="up"]')!.className).toMatch(
      /text-up/,
    )
  })

  it('renders unit token in muted text when provided', () => {
    const { container } = render(
      <KpiCard label="今日損益" value="12,345" unit="TWD" />,
    )
    expect(container.textContent).toContain('TWD')
  })

  it('directionOf maps positive→up, negative→down, 0/null/undefined→neutral', () => {
    expect(directionOf(1)).toBe('up')
    expect(directionOf(0.0001)).toBe('up')
    expect(directionOf(-1)).toBe('down')
    expect(directionOf(0)).toBe('neutral')
    expect(directionOf(null)).toBe('neutral')
    expect(directionOf(undefined)).toBe('neutral')
  })
})
