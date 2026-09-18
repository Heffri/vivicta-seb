import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { railTab } from '../support/nav'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// The first test opens Atlas Copco, which needs its PDF cached on disk (data/reports/ is gitignored).
// The second is v092's whole point: a row whose PDF is NOT cached opens its stored extraction anyway —
// only the page images wait, and the placeholder says where to fetch the PDF from.
const ATLAS_PDF = path.resolve(import.meta.dirname, '../../../data/reports/atlas_copco_2025.pdf')
const REASON = 'data/reports/atlas_copco_2025.pdf not present — copy the shared report in first (see common.md)'

for (const tone of TONES) {
  test(`kb: filter "atlas" -> Open -> Results [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ATLAS_PDF), REASON)
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

  test(`kb: a row with no cached PDF opens its stored extraction [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    // ABB's KB entry exists on every clone; its PDF is gitignored like all of data/reports/.
    await page.getByLabel('Filter reports').fill('abb_2025')
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('no PDF')
    const open = rows.first().getByRole('button', { name: 'Open' })
    await expect(open).toBeEnabled() // v092: the badge says pages wait, the open itself does not

    await open.click()
    await expect(page.getByRole('heading', { name: 'ABB', exact: false })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()
    await expect(page.getByText('Revenue', { exact: true })).toBeVisible() // the table carries real stored data

    // Page images are the one thing still waiting on the PDF — the placeholder says where to get it.
    await page.getByRole('button', { name: 'Image', exact: true }).click()
    await expect(page.getByText('Page preview unavailable')).toBeVisible()
    await expect(page.getByText('Fetch the PDF from Extract (directory search) to see the pages.')).toBeVisible()

    expect(errors).toEqual([])
  })
}
