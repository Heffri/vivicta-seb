import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// The wait says which pages are being read, and a nothing-found result explains itself.
// The candidates endpoint (GET /candidates) is real here — keyword scoring on the uploaded PDF's
// text; only the model call itself is shaped: held open to make the waiting state observable
// (fixture answers instantly), or fulfilled with every field nulled to reproduce a report the
// model finds nothing in. The note text sits on 3 of 70 pages — the locator strips lines that
// repeat across too many pages as boilerplate, so the debt note must stay rare to be scorable.
const DEBT_PAGES: (string | undefined)[] = Array.from({ length: 70 }, (_, i) =>
  i >= 29 && i <= 31 ? `Note 20 Borrowings Maturity profile of the loans note page ${i + 1} total 1 234` : undefined,
)

for (const tone of TONES) {
  test(`extract: the wait names the candidate pages it is reading [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
    await page.setInputFiles('#pdf', [{ name: 'candidates-report.pdf', mimeType: 'application/pdf', buffer: makePdf(70, DEBT_PAGES) }])
    await expect(page.getByText('1 file selected')).toBeVisible()

    // Hold /extract open (fixture would answer instantly) so the waiting line is observable.
    await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000))
      await route.continue()
    })
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

    const wait = page.getByText(/Reading pages [\d,–]+ of 70 ·/)
    await expect(wait).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/· \d+ s$/)).toBeVisible() // the stopwatch ticks alongside

    // A finished batch never forces a tab switch (BatchProgress's own "View results" does).
    await page.getByRole('main').getByRole('button', { name: /^View results/ }).click({ timeout: 30000 })
    await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()
    expect(errors).toEqual([])
  })

  test(`upload: the saved real-debt sample opens with no model call [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    const extractCalls: string[] = []
    await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
      extractCalls.push(route.request().url())
      await route.continue()
    })
    await gotoWithTone(page, tone)

    // The first-screen shortcut opens the stored karnell_2025 debt extraction straight from the
    // knowledge base — real figures on Results without a single /extract, fixture mode or not.
    await page.getByRole('button', { name: /Open a real debt sample/ }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Karnell/, { timeout: 15000 })
    await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()
    expect(extractCalls).toEqual([])
    expect(errors).toEqual([])
  })

  test(`results: a banner names the searched pages when nothing was found [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
    await page.setInputFiles('#pdf', [{ name: 'not-found-report.pdf', mimeType: 'application/pdf', buffer: makePdf(70, DEBT_PAGES) }])
    await expect(page.getByText('1 file selected')).toBeVisible()

    // Same bytes, same locator — but the model "finds nothing": every field comes back null.
    await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
      const response = await route.fetch()
      const json = await response.json()
      json.fields = json.fields.map((f: { value: unknown }) => ({ ...f, value: null, source: null }))
      await route.fulfill({ response, json })
    })
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

    // A finished batch never forces a tab switch (BatchProgress's own "View results" does).
    await page.getByRole('main').getByRole('button', { name: /^View results/ }).click({ timeout: 20000 })
    const banner = page.getByRole('region', { name: 'Figures the model did not find' })
    await expect(banner).toBeVisible()
    await expect(banner.getByText(/Candidates were pages 30–32 of this report/)).toBeVisible()

    // The banner's entry lands on the manual review form of the first not-found figure.
    await banner.getByRole('button', { name: 'Fill in below' }).click()
    await page.locator('summary').filter({ hasText: /^Review / }).click()
    await expect(page.getByRole('form', { name: /^Review / })).toBeVisible()
    expect(errors).toEqual([])
  })
}
