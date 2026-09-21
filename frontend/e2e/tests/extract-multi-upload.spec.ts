import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// Two runtime-generated PDFs (different page counts so their bytes/sizes differ, same as v021's
// evidence did with its PyMuPDF-built fixtures) — no atlas dependency, no fixture binaries to commit.
for (const tone of TONES) {
  test(`extract: two uploaded PDFs -> Compare with two columns [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.setInputFiles('#pdf', [
      { name: 'sample-report-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
      { name: 'sample-report-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
    ])
    await expect(page.getByText('2 files selected')).toBeVisible()
    await expect(page.getByText('sample-report-a.pdf')).toBeVisible()
    await expect(page.getByText('sample-report-b.pdf')).toBeVisible()

    const extractButton = page.getByRole('main').getByRole('button', { name: /^Extract/ })
    await expect(extractButton).toHaveText('Extract 2 reports')
    await extractButton.click()

    await expect(page.getByRole('heading', { name: 'Comparison' })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('2 of 2 reports extracted')).toBeVisible()
    await expect(page.locator('table thead th')).toHaveCount(3) // Field + 2 report columns

    // v174: the "Upcoming maturities" section is collection-wide (data/kb), independent of the two
    // uploaded fixture reports above it. Wallenberg has only one saved debt_maturity extraction, so
    // switch to All for a pool wide enough to prove the threshold filter actually removes rows.
    await expect(page.getByRole('heading', { name: 'Upcoming maturities', exact: false })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText(/comparable$|comparable ·/)).toBeVisible()
    await page.getByRole('group', { name: 'Collection' }).getByRole('button', { name: 'All', exact: true }).click()
    const wallRows = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Share' }) }).locator('tbody tr')
    await expect.poll(async () => wallRows.count(), { timeout: 20000 }).toBeGreaterThan(5)
    const beforeFilter = await wallRows.count()

    const threshold = page.getByLabel('Minimum share due within 1 year, percent')
    await threshold.fill('90')
    await expect.poll(async () => wallRows.count(), { timeout: 20000 }).toBeLessThan(beforeFilter)

    expect(errors).toEqual([])
  })
}
