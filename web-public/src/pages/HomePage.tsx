import { MaskedEventsFeed } from '@/components/MaskedEventsFeed'

export function HomePage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">ohMyStock — AI 助手即時動態</h1>
        <p className="text-sm text-[color:var(--muted-foreground)] mt-1">
          這個畫面 mirror 後台 LLM agents 在做什麼 — 所有股票代號皆已 mask。
        </p>
      </header>
      <MaskedEventsFeed />
    </div>
  )
}
