import { Outlet } from 'react-router'
import { DisclaimerBanner } from '@/components/DisclaimerBanner'

export function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <DisclaimerBanner />
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-zinc-200 py-4 px-4 text-center text-xs text-[color:var(--muted-foreground)]">
        ohMyStock — open-source educational demo. Not investment advice.
      </footer>
    </div>
  )
}
