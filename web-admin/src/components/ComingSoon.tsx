type Props = { name: string; description?: string }

export function ComingSoon({ name, description }: Props) {
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <div className="rounded-lg border bg-card p-10 text-center shadow-sm">
        <h1 className="text-2xl font-semibold text-foreground">{name}</h1>
        {description ? (
          <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
        ) : null}
        <p className="mt-6 text-xs uppercase tracking-wider text-muted-foreground">
          Coming soon - tracked in a future change
        </p>
      </div>
    </div>
  )
}