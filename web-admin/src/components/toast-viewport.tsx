/**
 * <ToastViewport> — fixed bottom-right list of in-flight toasts.
 *
 * Subscribes to lib/toast.ts; each Toast gets a 4s timer then disappears.
 * role="status" + aria-live="polite" so screen readers announce without
 * interrupting. Cap at 5 visible; older ones fall off.
 *
 * Mounted once in main.tsx alongside <RouterProvider />.
 */
import * as React from 'react'
import { subscribeToToasts, type Toast } from '@/lib/toast'

const VISIBLE_MS = 4000
const MAX_VISIBLE = 5

export function ToastViewport() {
  const [items, setItems] = React.useState<Toast[]>([])

  React.useEffect(() => {
    return subscribeToToasts((t) => {
      setItems((prev) => [...prev, t].slice(-MAX_VISIBLE))
      window.setTimeout(() => {
        setItems((prev) => prev.filter((x) => x.id !== t.id))
      }, VISIBLE_MS)
    })
  }, [])

  if (items.length === 0) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
    >
      {items.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto max-w-sm rounded-md border bg-background px-4 py-2 text-sm shadow-lg"
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
