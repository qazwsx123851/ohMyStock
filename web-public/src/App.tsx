import { Outlet, Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { DisclaimerBanner } from '@/components/DisclaimerBanner'
import { TimelineMarquee } from '@/components/TimelineMarquee'

export function App() {
  const { t } = useTranslation()
  return (
    <div className="min-h-screen flex flex-col">
      <DisclaimerBanner />
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
      <TimelineMarquee />
      <footer className="border-t border-zinc-200 py-3 px-4 flex items-center justify-between text-xs text-[color:var(--muted-foreground)]">
        <span>{t('footer.demo')}</span>
        <Link to="/about" className="underline">
          {t('footer.about')}
        </Link>
      </footer>
    </div>
  )
}
