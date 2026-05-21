import { describe, expect, it } from 'vitest'
import { resolveLang } from '@/lib/i18n'

describe('resolveLang', () => {
  it('defaults to zh-TW when no query param and no html lang', () => {
    expect(resolveLang('', '')).toBe('zh-TW')
  })

  it('honours ?lang=en', () => {
    expect(resolveLang('?lang=en', '')).toBe('en')
  })

  it('honours ?lang=zh-TW', () => {
    expect(resolveLang('?lang=zh-TW', '')).toBe('zh-TW')
  })

  it('falls back to html lang when no query param', () => {
    expect(resolveLang('', 'en-US')).toBe('en')
    expect(resolveLang('', 'zh-Hant-TW')).toBe('zh-TW')
  })

  it('falls back to zh-TW for unknown html lang', () => {
    expect(resolveLang('', 'ja-JP')).toBe('zh-TW')
  })
})
