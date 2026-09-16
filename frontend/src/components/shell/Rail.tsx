import { Moon, Sun } from 'lucide-react'
import { TABS, type Tab } from './tabs'
import type { Tone } from './useTone'

type RailProps = {
  active: Tab
  enabled: Record<Tab, boolean>
  compareCount: number
  onSelect: (id: Tab) => void
  tone: Tone
  onToneChange: (tone: Tone) => void
}

// Full rail above 900px; folds to an icon column at or below it (no router/state lib — see docs/acrylic/DESIGN.md).
export function Rail({ active, enabled, compareCount, onSelect, tone, onToneChange }: RailProps) {
  return (
    <nav className="flex w-16 shrink-0 flex-col border-r border-border min-[901px]:w-56">
      <ul className="flex-1 space-y-1 overflow-y-auto p-2">
        {TABS.map((t) => {
          const Icon = t.icon
          const isActive = t.id === active
          return (
            <li key={t.id}>
              <button
                type="button"
                disabled={!enabled[t.id]}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onSelect(t.id)}
                title={t.label}
                className={`flex w-full items-center justify-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors disabled:pointer-events-none disabled:opacity-40 min-[901px]:justify-start ${
                  isActive ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                }`}
              >
                <Icon className={`size-4 shrink-0 ${isActive ? 'text-primary' : ''}`} />
                <span className="max-[900px]:hidden">{t.label}</span>
                {t.id === 'compare' && compareCount > 1 && (
                  <span className="ml-auto rounded-full bg-muted px-1.5 text-xs text-muted-foreground max-[900px]:hidden">
                    {compareCount}
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={() => onToneChange(tone === 'dark' ? 'light' : 'dark')}
          title={tone === 'dark' ? 'Switch to light glass' : 'Switch to dark glass'}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-border py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground min-[901px]:justify-start min-[901px]:px-3"
        >
          {tone === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span className="max-[900px]:hidden">{tone === 'dark' ? 'Light' : 'Dark'}</span>
        </button>
      </div>
    </nav>
  )
}
