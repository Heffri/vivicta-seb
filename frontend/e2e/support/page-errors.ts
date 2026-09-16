import type { Page } from '@playwright/test'

// Call right after the page/context is created, before goto(); read the array at the end of the
// test and assert it's empty. Uncaught exceptions in the app (not console.error, not network
// failures) land here — that's the "each tab, each tone, no pageerror" smoke check.
export function trackPageErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  return errors
}
