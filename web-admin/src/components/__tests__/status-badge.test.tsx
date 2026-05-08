import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { StatusBadge, type Status } from '../status-badge'

const ALL_STATUSES: Status[] = [
  'pending',
  'approved',
  'rejected',
  'executed',
  'expired',
  'canceled',
  'errored',
]

describe('StatusBadge', () => {
  it.each(ALL_STATUSES)(
    'renders status=%s with a Lucide SVG icon (color is never the only signal)',
    (status) => {
      const { container } = render(<StatusBadge status={status} />)
      const svg = container.querySelector('svg')
      expect(svg, `status=${status} must render an SVG icon`).not.toBeNull()
      // Decorative icons should be hidden from assistive tech
      expect(svg).toHaveAttribute('aria-hidden')
    },
  )

  it('errored status maps to the --destructive token (via shadcn destructive variant)', () => {
    const { container } = render(<StatusBadge status="errored" />)
    const badge = container.querySelector('[data-status="errored"]')
    expect(badge).not.toBeNull()
    // shadcn destructive variant applies `bg-destructive` (which is wired to
    // the --destructive CSS custom property in index.css)
    expect(badge!.className).toMatch(/destructive/)
  })

  it('rejected and errored share destructive bg but use distinct icons', () => {
    // Spec: "no two statuses SHALL share both the same icon AND the same
    // computed background color" — verified here for the two destructive-bg
    // statuses by confirming their SVG markup differs.
    const rejectedSvg = render(<StatusBadge status="rejected" />)
      .container.querySelector('svg')!.outerHTML
    const erroredSvg = render(<StatusBadge status="errored" />)
      .container.querySelector('svg')!.outerHTML
    expect(rejectedSvg).not.toBe(erroredSvg)
  })

  it('renders the default zh-TW label, overridable via prop', () => {
    const { rerender, container } = render(<StatusBadge status="pending" />)
    expect(container.textContent).toContain('待處理')
    rerender(<StatusBadge status="pending" label="排隊中" />)
    expect(container.textContent).toContain('排隊中')
  })
})
