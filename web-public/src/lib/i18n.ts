/**
 * i18next setup. Locale selection: ?lang= → <html lang> → 'zh-TW'.
 * Never reads or writes browser storage.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Internationalization)
 */

import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhTW from '@/locales/zh-TW.json'
import en from '@/locales/en.json'

export type SupportedLang = 'zh-TW' | 'en'

export function resolveLang(
  search?: string,
  htmlLang?: string,
): SupportedLang {
  const params = new URLSearchParams(
    search ?? (typeof window !== 'undefined' ? window.location.search : ''),
  )
  const raw = params.get('lang')?.toLowerCase()
  if (raw === 'en' || raw === 'en-us') return 'en'
  if (raw === 'zh-tw' || raw === 'zh' || raw === 'zh-hant' || raw === 'zh-hant-tw') {
    return 'zh-TW'
  }
  const html =
    htmlLang ?? (typeof document !== 'undefined' ? document.documentElement.lang : '')
  if (html.toLowerCase().startsWith('en')) return 'en'
  return 'zh-TW'
}

let initialised = false

export function initI18n(opts: { lng?: SupportedLang } = {}): typeof i18next {
  if (initialised) return i18next
  const lng = opts.lng ?? resolveLang()
  void i18next.use(initReactI18next).init({
    resources: {
      'zh-TW': { translation: zhTW },
      en: { translation: en },
    },
    lng,
    fallbackLng: 'zh-TW',
    interpolation: { escapeValue: false },
  })
  initialised = true
  return i18next
}

export { i18next }
