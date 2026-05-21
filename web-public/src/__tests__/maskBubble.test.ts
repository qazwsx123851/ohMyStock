import { describe, expect, it } from 'vitest'
import { stripFourDigit } from '@/lib/maskBubble'

describe('stripFourDigit', () => {
  it('strips a standalone 4-digit number', () => {
    expect(stripFourDigit('買 2330 100 股')).toBe('買 STK-? 100 股')
  })

  it('leaves 5-digit numbers untouched', () => {
    expect(stripFourDigit('12345')).toBe('12345')
  })

  it('leaves 3-digit numbers untouched', () => {
    expect(stripFourDigit('score 100 of 999')).toBe('score 100 of 999')
  })

  it('leaves short decimals untouched', () => {
    expect(stripFourDigit('confidence 0.72')).toBe('confidence 0.72')
  })

  it('strips multiple 4-digit groups', () => {
    expect(stripFourDigit('2330 vs 2454')).toBe('STK-? vs STK-?')
  })

  it('preserves the empty string', () => {
    expect(stripFourDigit('')).toBe('')
  })
})
