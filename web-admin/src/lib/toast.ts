/**
 * Minimal pub/sub toast — module-level subscriber, no React context.
 *
 * One consumer today (<ValidationDialog>); kept tiny on purpose. If a
 * second use site grows nontrivial requirements, swap for `sonner`.
 *
 * `toast(message)` enqueues a Toast event. `<ToastViewport />` mounted in
 * `main.tsx` subscribes and renders fixed-position notifications with
 * 4s auto-dismiss + role="status" for screen readers.
 */

export interface Toast {
  id: number
  message: string
  ts: number
}

type Listener = (toast: Toast) => void

let nextId = 1
const listeners = new Set<Listener>()

export function toast(message: string): void {
  const t: Toast = { id: nextId++, message, ts: Date.now() }
  for (const l of listeners) l(t)
}

export function subscribeToToasts(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
