import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from 'cn'

// Shared status states (v010): loading = spinner + one sentence; error = the danger block
// (the recipe v005 introduced on the KB view) with optional collapsible details. Empty states
// stay plain — a muted sentence plus the next step needs no component.

/** Busy line: spinner + one sentence, the same shape the KB loading and Ask thinking lines used. */
export function LoadingLine({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('flex items-center gap-2 text-sm text-muted-foreground', className)}>
      <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
      {children}
    </p>
  )
}

type ErrorBlockProps = {
  children: ReactNode // the message; \n renders as a line break
  details?: ReactNode // rendered under the message: collapsible extras (tried URLs, next step)
  className?: string // size overrides for compact contexts (form rows, pane faces)
}

/** Failure block: danger tokens (data status, not destructive action — DESIGN.md), a
 *  hairline border on the muted danger tint, announced via role="alert". */
export function ErrorBlock({ children, details, className }: ErrorBlockProps) {
  return (
    <div
      role="alert"
      className={cn('rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger', className)}
    >
      <p className="whitespace-pre-wrap">{children}</p>
      {details}
    </div>
  )
}
