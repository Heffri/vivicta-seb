import type { Page } from '@playwright/test'

// Scope tab clicks to the Rail: the embedded AskPanel (inside Results/Compare) has its own
// submit button also named "Ask", which otherwise resolves ambiguously (v025's evidence hit the
// same thing) — `nav` is the <nav> the Rail renders (src/components/shell/Rail.tsx).
export const railTab = (page: Page, name: string) => page.getByRole('navigation').getByRole('button', { name, exact: true })
