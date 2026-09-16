import type { ReactNode } from 'react'
import { cn } from 'cn'
import type { Provider } from '@/main'

type ProviderCardProps = {
  value: Provider
  title: string
  description: string
  selected: boolean
  disabled?: boolean
  onSelect: () => void
  children?: ReactNode // fields shown only while this card is selected
}

// A native <input type="radio">, not a styled <button role="radio"> — free keyboard nav (arrow keys
// move the selection within the group, Space/click picks it) and screen-reader semantics, no
// roving-tabindex code to write or get wrong (contrast Rail.tsx's tablist, which needs that because
// its items are buttons, not form controls).
export function ProviderCard({ value, title, description, selected, disabled, onSelect, children }: ProviderCardProps) {
  return (
    <label
      className={cn(
        'block rounded-xl border px-4 py-3 shadow-[inset_0_1px_0_var(--glass-hi)] transition-colors',
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
        selected ? 'border-ring bg-accent/60' : 'border-border bg-card hover:bg-accent/30',
      )}
    >
      <span className="flex items-start gap-3">
        <input
          type="radio"
          name="arp-provider"
          value={value}
          checked={selected}
          disabled={disabled}
          onChange={onSelect}
          // Without this, the implicit label association names the radio after *everything* inside
          // the wrapping <label> — including the field captions rendered below once selected (found
          // live: a screen reader would announce "Base URL (optional), API key (optional)..." as part
          // of the Claude radio's own name). An explicit aria-label overrides name-from-content outright.
          aria-label={title}
          className="mt-0.5 size-4 accent-ring"
        />
        <span className="flex-1 space-y-0.5">
          <span className="block text-sm font-medium">{title}</span>
          <span className="block text-xs text-muted-foreground">{description}</span>
        </span>
      </span>
      {selected && children && <div className="mt-3 space-y-2 border-t border-border pt-3">{children}</div>}
    </label>
  )
}
