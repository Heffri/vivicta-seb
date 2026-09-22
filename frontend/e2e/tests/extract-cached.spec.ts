import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// Cached Reports only lists PDFs that are actually on disk (GET /api/library joins
// data/reports/index.json against data/reports/*.pdf); the repo ships the curated index entry
// but the PDF itself is gitignored. common.md has teammates copy the shared real report in at
// data/reports/atlas_copco_2025.pdf — skip with a reason instead of failing red when it's absent.
const ATLAS_PDF = path.resolve(import.meta.dirname, '../../../data/reports/atlas_copco_2025.pdf')
const REASON = 'data/reports/atlas_copco_2025.pdf not present — copy the shared report in first (see common.md)'

for (const tone of TONES) {
  test(`extract: first cached report -> Extract -> Results shows Export JSON [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ATLAS_PDF), REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.getByRole('button', { name: 'Saved reports', exact: true }).click()
    const checkbox = page.getByRole('checkbox', { name: /Atlas Copco/ })
    await checkbox.waitFor()
    await checkbox.check()

    const extractButton = page.getByRole('main').getByRole('button', { name: /^Extract/ })
    await expect(extractButton).toBeEnabled()
    await extractButton.click()

    // v171: a finished batch never forces a tab switch (BatchProgress's own "View results" does).
    await page.getByRole('main').getByRole('button', { name: /^View results/ }).click({ timeout: 20000 })
    await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()

    expect(errors).toEqual([])
  })
}
