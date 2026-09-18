import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { railTab } from '../support/nav'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// The real-library smoke case requires the Atlas saved extraction.
const ATLAS_EXTRACTION = path.resolve(import.meta.dirname, '../../../data/kb/atlas_copco_2025/extractions/income_statement.json')
const REASON = 'Atlas Copco saved income statement is not present'

for (const tone of TONES) {
  test(`kb: filter "atlas" -> Open -> Results [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ATLAS_EXTRACTION), REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    await page.getByLabel('Filter reports').fill('atlas')
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Atlas Copco')

    await rows.first().getByRole('button', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { name: 'Atlas Copco', exact: false })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()

    expect(errors).toEqual([])
  })

  test(`kb: a saved extraction without its PDF can still open [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    const noPdfRow = page.locator('tbody tr', { has: page.getByText('no PDF', { exact: true }) }).first()
    await expect(noPdfRow).toBeVisible()
    await expect(noPdfRow.getByRole('button', { name: 'Open' })).toBeEnabled()
    await noPdfRow.getByRole('button', { name: 'Open' }).click()
    await expect(page.getByText('Saved page text. The original PDF is not available on this device.')).toBeVisible()

    expect(errors).toEqual([])
  })
}
