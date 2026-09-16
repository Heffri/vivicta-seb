import { FOCUS_RING } from './focusRing'

// Page's first focusable element: visually hidden until Tab reaches it, then shown as a
// floating glass chip (the SelectContent treatment — a popover sitting outside the one
// shell pane, docs/acrylic/DESIGN.md's "one material" exception). The onClick focus() is a
// belt-and-suspenders fix for browsers that skip the native fragment-focus step when the
// hash is already #content (e.g. a second activation without a reload in between).
export function SkipLink() {
  return (
    <a
      href="#content"
      onClick={() => document.getElementById('content')?.focus()}
      className={`sr-only glass rounded-lg px-4 py-2 text-sm font-medium text-foreground ring-1 ring-foreground/10 focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 ${FOCUS_RING}`}
    >
      Skip to content
    </a>
  )
}
