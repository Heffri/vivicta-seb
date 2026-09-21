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

    // v171: a finished batch never forces a tab switch (BatchProgress's own "View results" does);
    // it also appears as soon as the first of the two is done, so wait for the count to say both
    // finished before clicking through, or this can land on the single Results view instead.
    const viewResults = page.getByRole('main').getByRole('button', { name: 'View results (2)' })
    await expect(viewResults).toBeVisible({ timeout: 20000 })
    await viewResults.click()
    await expect(page.getByRole('heading', { name: 'Comparison' })).toBeVisible()
    await expect(page.getByText('2 of 2 reports extracted')).toBeVisible()
    await expect(page.locator('table thead th')).toHaveCount(3) // Field + 2 report columns

    expect(errors).toEqual([])
  })
}
