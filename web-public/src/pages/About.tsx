import { useTranslation } from 'react-i18next'

export function About() {
  const { t } = useTranslation()
  return (
    <article className="prose prose-sm max-w-2xl py-8">
      <h1 className="text-2xl font-semibold mb-3">{t('about.title')}</h1>
      <p className="mb-3">{t('about.intro')}</p>
      <p className="mb-3 text-sm text-[color:var(--muted-foreground)]">
        {t('about.demo_note')}
      </p>
      <p className="mb-3 text-sm">{t('about.not_advice')}</p>
      <p className="text-sm">
        {t('about.links')}{' '}
        <a
          href="https://github.com/qazwsx123851/ohMyStock"
          className="underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('about.repo_label')}
        </a>
      </p>
    </article>
  )
}
