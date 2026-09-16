import type { ReactNode } from 'react'

type FaceProps = {
  label: string
  hint?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}

// One of the three paths inside the upload pane. Faces are flat translucent zones of the
// single pane material — separated by hairlines that run top-to-bottom while stacked and
// left-to-right at ≥1280px where the faces sit side by side (no per-face glass: DESIGN.md).
export function Face({ label, hint, actions, className = '', children }: FaceProps) {
  return (
    <section
      className={`flex min-w-0 flex-col gap-3 border-border p-5 max-[1279px]:border-t max-[1279px]:first:border-t-0 min-[1280px]:border-l min-[1280px]:first:border-l-0 ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-baseline gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {label}
          {hint && (
            <span className="text-xs font-normal normal-case tracking-normal text-muted-foreground/80">{hint}</span>
          )}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  )
}
