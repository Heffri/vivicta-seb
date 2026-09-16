import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { railTab } from '../support/nav'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// Self-contained (no atlas dependency): a single generated 70-page upload lands straight on
// Results (fixture mode's canned sample_extraction.json, citations on page 64/65 — common.md) and
// 70 pages is enough that GET /api/reports/{id}/pages/64.png doesn't 404.
for (const tone of TONES) {
  test(`ask (embedded in Results): question -> inline citation chip -> Source shows Page 64 [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.setInputFiles('#pdf', [{ name: 'sample-report.pdf', mimeType: 'application/pdf', buffer: makePdf(70) }])
    const extractButton = page.getByRole('main').getByRole('button', { name: /^Extract/ })
    await expect(extractButton).toHaveText('Extract') // single file: no "N reports" suffix, lands on Results not Compare
    await extractButton.click()

    await expect(page.getByRole('heading', { name: 'Nordic Industrials', exact: false })).toBeVisible({ timeout: 20000 })

    const askBox = page.getByPlaceholder(/Ask about these reports/)
    await askBox.fill('Which page is the income statement on?')
    await askBox.press('Enter')

    const chip = page.getByRole('button', { name: /Nordic Industrials.*p\.\s?64/ }).first()
    await chip.waitFor({ timeout: 20000 })
    await chip.click()

    await expect(page.getByText('Page 64, cited in an answer below', { exact: false })).toBeVisible()

    // Touch the standalone Ask tab too (this test's flow otherwise only visits the embedded
    // AskPanel inside Results) so every rail tab gets a pageerror check somewhere in the suite.
    await railTab(page, 'Ask').click()
    await expect(page.getByText('Ask the reports')).toBeVisible()

    expect(errors).toEqual([])
  })
}
