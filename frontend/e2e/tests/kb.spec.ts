import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { railTab } from '../support/nav'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// The real-library smoke case requires the Atlas saved extraction.
const ATLAS_EXTRACTION = path.resolve(import.meta.dirname, '../../../data/kb/atlas_copco_2025/extractions/income_statement.json')
const REASON = 'Atlas Copco saved income statement is not present'
// v180: the maturity wall card needs a saved debt_maturity extraction in the default collection.
const ERICSSON_DEBT = path.resolve(import.meta.dirname, '../../../data/kb/ericsson_2025/extractions/debt_maturity.json')
const WALL_REASON = 'Ericsson saved debt maturity extraction is not present'

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

  test(`kb: collection switch Wallenberg -> All -> back [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(11)

    const collection = page.getByRole('group', { name: 'Collection' })
    await collection.getByRole('button', { name: 'All', exact: true }).click()
    // The heading's collection label flips with state, not with the fetch — wait for the row count
    // to actually change (it keeps growing as other tests upload, so no exact number here).
    await expect.poll(async () => rows.count(), { timeout: 20000 }).toBeGreaterThan(11)
    expect(await rows.count()).toBeGreaterThanOrEqual(190)

    // The choice sticks across a reload (localStorage arp-kb-collection); the reload lands on the
    // default Extract tab, so go back to Knowledge base before reading the header.
    await page.reload()
    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toContainText('all saved reports', { timeout: 20000 })

    await collection.getByRole('button', { name: 'Wallenberg', exact: true }).click()
    await expect(page.getByRole('heading', { name: /reports/ })).toContainText('Wallenberg collection', { timeout: 20000 })
    await expect(rows).toHaveCount(11)

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

  // v180: the KB page's "Maturity wall" card — one bar per company grouped by sector. On the seed
  // KB the default collection's single debt report (Ericsson) has buckets that do not reconcile,
  // so the card must show one group, its count line, and the honest grey "buckets incomplete" mark.
  test(`kb: maturity wall card groups the collection by sector [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ERICSSON_DEBT), WALL_REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    // The toolbar (and with it the Maturity wall button) only renders once GET /api/kb lands, which
    // takes seconds cold for 206 stems — ride it out here rather than repeating the pre-existing
    // 5 s-budget smoke failures (docs/acrylic/evidence/v165.md).
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'Maturity wall' })).toBeVisible({ timeout: 20000 })

    await page.getByRole('button', { name: 'Maturity wall' }).click()
    const card = page.getByRole('region', { name: 'Maturity wall' })
    await expect(card).toBeVisible()
    await expect(card.getByText(/share of debt due within 1 year · 0 of 1 companies with complete buckets/)).toBeVisible()

    const sectors = card.getByRole('heading', { name: /^Sector / })
    await expect(sectors).toHaveCount(1)
    await expect(sectors.first()).toContainText('Telecommunications')
    // svg text, not getByText: the row's hidden <title> tooltip carries the same words
    await expect(card.locator('svg text').filter({ hasText: 'buckets incomplete' }).first()).toBeVisible()

    // A company row opens that company through the KB view's existing Open action.
    await card.getByRole('button', { name: /^Ericsson/ }).click()
    await expect(page.getByRole('heading', { name: 'Ericsson', exact: false })).toBeVisible({ timeout: 20000 })

    expect(errors).toEqual([])
  })
}
