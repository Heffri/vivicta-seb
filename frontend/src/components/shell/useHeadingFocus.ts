import { useEffect, useRef } from 'react'
import { FOCUS_RING } from './focusRing'

const HEADING_FOCUS_CLASSES = `${FOCUS_RING} rounded-sm`.split(' ')

// Moves focus to the active view's h1 after a rail navigation, so a screen reader announces
// the new view's name (views live under #content, mounted with id/tabIndex in App.tsx).
// Skipped on the first run (mount) so page load doesn't steal focus from the skip link —
// compares against the previous tab rather than a "have I run yet" flag, since that flag
// flips under StrictMode's dev-mode double-invoke of a fresh mount's effect (mount -> cleanup
// -> mount again, same tab both times) and fires the focus on load instead of skipping it.
export function useHeadingFocus(tab: string) {
  const prevTab = useRef(tab)

  useEffect(() => {
    if (prevTab.current === tab) return
    prevTab.current = tab
    const heading = document.getElementById('content')?.querySelector<HTMLElement>('h1')
    if (!heading) return
    if (!heading.hasAttribute('tabindex')) heading.tabIndex = -1
    heading.classList.add(...HEADING_FOCUS_CLASSES)
    heading.focus({ preventScroll: true })
  }, [tab])
}
