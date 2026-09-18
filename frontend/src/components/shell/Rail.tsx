import { useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Moon, Sun } from 'lucide-react'
import { FOCUS_RING } from './focusRing'
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

// Full rail above 900px; folds to an icon column at or below it (no router/state lib — see
// docs/acrylic/DESIGN.md). WAI-ARIA Tabs pattern (vertical, manual activation): the tablist
// keeps a roving tabindex over the *enabled* tabs — Up/Down and Left/Right move DOM focus
// among them (disabled tabs are skipped, not just visually dimmed), Home/End jump to the
// first/last enabled tab, and Enter/Space activate natively since these stay real <button>s.
// Disabled tabs use aria-disabled instead of the native attribute so they stay in the
// tablist's accessibility tree (a screen reader can still discover "Results, dimmed") —
// see docs/acrylic/evidence/v027.md.
export function Rail({ active, enabled, compareCount, onSelect, tone, onToneChange }: RailProps) {
  const activeIndex = TABS.findIndex((t) => t.id === active)
  const [focusIndex, setFocusIndex] = useState(activeIndex)
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Resyncs whenever the active tab changes for any reason (click, keyboard activation, or a
  // programmatic switch elsewhere in the app) — adjusted during render (React's documented
  // alternative to an effect for this), not after, so it can't cause an extra paint. Arrow-key
  // roving between those changes is untouched, since `active` itself doesn't change while the
  // user is just moving focus.
  const [prevActive, setPrevActive] = useState(active)
  if (active !== prevActive) {
    setPrevActive(active)
    setFocusIndex(activeIndex)
  }

  // Guards against the roving pointer ever landing on a tab that became disabled out from
  // under it (App.tsx keeps `active` always enabled, so this should be a no-op in practice).
  const safeFocusIndex = enabled[TABS[focusIndex]?.id] ? focusIndex : activeIndex

  const moveFocus = (nextIndex: number) => {
    setFocusIndex(nextIndex)
    buttonRefs.current[nextIndex]?.focus()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const enabledIndices = TABS.map((_, i) => i).filter((i) => enabled[TABS[i].id])
    const pos = enabledIndices.indexOf(index)
    let nextPos: number
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        nextPos = (pos + 1) % enabledIndices.length
        break
      case 'ArrowUp':
      case 'ArrowLeft':
        nextPos = (pos - 1 + enabledIndices.length) % enabledIndices.length
        break
      case 'Home':
        nextPos = 0
        break
      case 'End':
        nextPos = enabledIndices.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    moveFocus(enabledIndices[nextPos])
  }

  return (
    <nav className="flex w-16 shrink-0 flex-col border-r border-border min-[901px]:w-56">
      <ul
        role="tablist"
        aria-label="Sections"
        aria-orientation="vertical"
        className="flex-1 space-y-1 overflow-y-auto p-2"
      >
        {TABS.map((t, i) => {
          const Icon = t.icon
          const isActive = t.id === active
          const isDisabled = !enabled[t.id]
          return (
            <li key={t.id} role="presentation">
              <button
                ref={(el) => {
                  buttonRefs.current[i] = el
                }}
                type="button"
                role="tab"
                id={`rail-tab-${t.id}`}
                aria-selected={isActive}
                aria-disabled={isDisabled || undefined}
                aria-controls="content"
                tabIndex={i === safeFocusIndex ? 0 : -1}
                onClick={() => !isDisabled && onSelect(t.id)}
                onKeyDown={(e) => handleKeyDown(e, i)}
                title={t.label}
                className={`flex w-full items-center justify-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors min-[901px]:justify-start ${FOCUS_RING} ${
                  isDisabled
                    ? 'pointer-events-none text-muted-foreground opacity-40'
                    : isActive
                      ? 'bg-accent text-foreground'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
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
          className={`flex w-full items-center justify-center gap-2 rounded-lg border border-border py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground min-[901px]:justify-start min-[901px]:px-3 ${FOCUS_RING}`}
        >
          {tone === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span className="max-[900px]:hidden">{tone === 'dark' ? 'Light' : 'Dark'}</span>
        </button>
      </div>
    </nav>
  )
}
