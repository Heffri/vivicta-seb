import type { Page } from '@playwright/test'

// Scope tab clicks to the Rail: the embedded AskPanel (inside Results/Compare) has its own
// submit button also named "Ask", which otherwise resolves ambiguously — `nav` is the <nav> the
// Rail renders. Rail items are role="tab" inside a role="tablist" (the WAI-ARIA Tabs pattern, see
// src/components/shell/Rail.tsx), not role="button".
export const railTab = (page: Page, name: string) => page.getByRole('navigation').getByRole('tab', { name, exact: true })
