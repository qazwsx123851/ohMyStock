/**
 * Minimal controlled <Dialog> primitive.
 *
 * Built inline (no @radix-ui/react-dialog dep) because the only consumer
 * today is <TransitionDialog>. Provides:
 *
 *   - role="dialog" + aria-modal + aria-labelledby
 *   - escape-to-close
 *   - click-on-overlay-to-close
 *   - body scroll lock while open
 *   - focuses the first focusable element on open
 *
 * Shadcn-style API surface: `<Dialog open onOpenChange>`,
 * `<DialogContent>`, `<DialogHeader>`, `<DialogTitle>`,
 * `<DialogDescription>`, `<DialogFooter>`. Compose-only — no portal,
 * no animation; sufficient for a modal that the user explicitly opens
 * by clicking a button.
 */
import * as React from 'react'
import { cn } from '@/lib/utils'

type DialogContextValue = {
  open: boolean
  onOpenChange: (next: boolean) => void
  titleId: string
  descriptionId: string
}

const DialogContext = React.createContext<DialogContextValue | null>(null)

function useDialogContext() {
  const ctx = React.useContext(DialogContext)
  if (!ctx) throw new Error('Dialog primitives must be used inside <Dialog>')
  return ctx
}

export interface DialogProps {
  open: boolean
  onOpenChange: (next: boolean) => void
  children: React.ReactNode
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  const titleId = React.useId()
  const descriptionId = React.useId()

  React.useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onOpenChange(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onOpenChange])

  return (
    <DialogContext.Provider
      value={{ open, onOpenChange, titleId, descriptionId }}
    >
      {children}
    </DialogContext.Provider>
  )
}

export interface DialogContentProps
  extends React.HTMLAttributes<HTMLDivElement> {
  className?: string
}

export const DialogContent = React.forwardRef<
  HTMLDivElement,
  DialogContentProps
>(function DialogContent({ className, children, ...rest }, ref) {
  const { open, onOpenChange, titleId, descriptionId } = useDialogContext()
  const internalRef = React.useRef<HTMLDivElement>(null)
  React.useImperativeHandle(ref, () => internalRef.current as HTMLDivElement)

  React.useEffect(() => {
    if (!open) return
    const root = internalRef.current
    if (!root) return
    const focusable = root.querySelector<HTMLElement>(
      'input, textarea, select, button, [href], [tabindex]:not([tabindex="-1"])',
    )
    focusable?.focus()
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:items-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false)
      }}
    >
      <div
        ref={internalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className={cn(
          'relative w-full max-w-md rounded-lg border bg-background p-6 shadow-lg',
          className,
        )}
        {...rest}
      >
        {children}
      </div>
    </div>
  )
})

export function DialogHeader({
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mb-4 space-y-1.5 text-left', className)} {...rest} />
  )
}

export function DialogTitle({
  className,
  ...rest
}: React.HTMLAttributes<HTMLHeadingElement>) {
  const { titleId } = useDialogContext()
  return (
    <h2
      id={titleId}
      className={cn(
        'text-lg font-semibold leading-none tracking-tight',
        className,
      )}
      {...rest}
    />
  )
}

export function DialogDescription({
  className,
  ...rest
}: React.HTMLAttributes<HTMLParagraphElement>) {
  const { descriptionId } = useDialogContext()
  return (
    <p
      id={descriptionId}
      className={cn('text-sm text-muted-foreground', className)}
      {...rest}
    />
  )
}

export function DialogFooter({
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end',
        className,
      )}
      {...rest}
    />
  )
}
