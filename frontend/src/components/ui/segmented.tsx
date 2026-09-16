import { cn } from 'cn'

// Promoted from results/Segmented.tsx in v010 (verbatim) — the second consumer didn't
// appear, but views may now treat it as a primitive per the v010 work order.

type SegmentedProps<T extends string> = {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  className?: string
  'aria-label': string
}

/** Compact two-or-more-way toggle: a flat raised well (one hairline + the specular top
 *  edge) with the pressed option as a filled step inside it — a control, not two buttons. */
export function Segmented<T extends string>({ options, value, onChange, className, ...rest }: SegmentedProps<T>) {
  return (
    <div
      role="group"
      className={cn(
        'inline-flex items-center gap-0.5 rounded-[10px] border border-border bg-background/60 p-0.5 shadow-[inset_0_1px_0_var(--glass-hi)]',
        className,
      )}
      {...rest}
    >
      {options.map((o) => {
        const pressed = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={pressed}
            onClick={() => onChange(o.value)}
            className={`h-6 rounded-md px-2 text-xs font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${
              pressed
                ? 'bg-muted text-foreground shadow-[inset_0_1px_0_var(--glass-hi)]'
                : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
