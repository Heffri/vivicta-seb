import type { Page } from '@playwright/test'

export type Tone = 'dark' | 'light'
export const TONES: readonly Tone[] = ['dark', 'light']

const STORAGE_KEY = 'acrylic-tone' // src/components/shell/useTone.ts

// useTone() reads this key once on mount, so it has to be in place before the app's first paint —
// set it via an init script, then navigate (matches the shared shot.mjs's --tonekey/--tone).
export async function gotoWithTone(page: Page, tone: Tone) {
  await page.addInitScript((v) => window.localStorage.setItem(v.key, v.tone), { key: STORAGE_KEY, tone })
  await page.goto('/')
}
