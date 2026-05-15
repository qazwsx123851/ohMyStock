import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DisclaimerBanner } from '@/components/DisclaimerBanner'

describe('DisclaimerBanner', () => {
  it('renders the verbatim zh-TW disclaimer substrings from auth-and-mask.md §4.3', () => {
    render(<DisclaimerBanner />)
    const banner = screen.getByTestId('disclaimer-banner')
    expect(banner.textContent).toContain(
      '本網站為 AI 系統運作展示，非投資建議',
    )
    expect(banner.textContent).toContain(
      '所有股票代號（STK-A、STK-B 等）為虛構代換',
    )
  })

  it('has no dismiss / close control inside the banner subtree', () => {
    render(<DisclaimerBanner />)
    const banner = screen.getByTestId('disclaimer-banner')
    expect(banner.querySelector('button')).toBeNull()
    expect(banner.querySelector('[role="button"]')).toBeNull()
    const aria = banner.querySelector('[aria-label]')?.getAttribute('aria-label') ?? ''
    expect(aria).not.toMatch(/關閉|close|dismiss/i)
  })

  it('mounts with role=alert so assistive tech exposes it', () => {
    render(<DisclaimerBanner />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
