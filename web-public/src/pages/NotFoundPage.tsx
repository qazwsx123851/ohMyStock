/**
 * 404 view — still displays the DisclaimerBanner (mounted at App level) and
 * a single home link. Contains no stock-specific content.
 *
 * Spec: openspec/changes/web-public-shell-and-mask/specs/web-public-shell/spec.md
 */
export function NotFoundPage() {
  return (
    <div className="text-center py-16">
      <h1 className="text-4xl font-semibold mb-4">404</h1>
      <p className="text-sm text-[color:var(--muted-foreground)] mb-6">
        找不到這個頁面。
      </p>
      <a href="/" className="underline text-sm">
        回首頁
      </a>
    </div>
  )
}
