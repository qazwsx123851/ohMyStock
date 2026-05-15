/**
 * Sticky, non-dismissable disclaimer banner.
 *
 * The exact zh-TW text comes from docs/auth-and-mask.md §4.3. Two substrings
 * are asserted by the spec — they must remain verbatim:
 *   - 本網站為 AI 系統運作展示，非投資建議
 *   - 所有股票代號（STK-A、STK-B 等）為虛構代換
 *
 * Intentionally has no close button, no dismiss control, and no aria-label
 * that would allow assistive technologies to "skip" it.
 *
 * Spec: openspec/changes/web-public-shell-and-mask/specs/web-public-shell/spec.md
 */
export function DisclaimerBanner() {
  return (
    <div
      role="alert"
      data-testid="disclaimer-banner"
      className="sticky top-0 z-50 w-full bg-[color:var(--warning)] text-[color:var(--warning-foreground)] px-4 py-2 text-sm leading-relaxed"
    >
      <span aria-hidden="true">⚠️ </span>
      本網站為 AI 系統運作展示，非投資建議。
      所有股票代號（STK-A、STK-B 等）為虛構代換，不對應任何真實標的。
      過往任何績效數字皆不代表未來表現。
    </div>
  )
}
