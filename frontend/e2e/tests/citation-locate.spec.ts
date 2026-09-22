import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// v179 (consult item 12): "there is a citation" -> "you can see the line in one glance". Image mode
// frames the cited quote on the page image (real /locate call against a real uploaded PDF); the
// no-PDF saved-text view scrolls to and highlights it instead. Both degrade silently — a request
// that 500s, or a quote that never repeats, or one that never printed verbatim, all just fall back
// to the plain page with no console noise.

// p.30 (index 29): a citation exactly as it would come off a two-line page (get_text joins lines
// with \n) — proves a wrapped citation still gets framed, whichever tier the backend matched on.
// p.31 (index 30): the same line printed twice (a group/parent pair) — proves every occurrence
// frames, with a count, rather than guessing one.
const LOCATE_PAGES: (string | undefined)[] = Array.from({ length: 35 }, (_, i) =>
  i === 29 ? 'Note 20 Borrowings\nTotal debt is 1 234 MSEK due within one year, filed with the group'
    : i === 30 ? 'Total debt 1 234 MSEK\nTotal debt 1 234 MSEK'
      : undefined,
)

for (const tone of TONES) {
  test(`source: Image mode frames a citation, counts repeats, and a failed lookup leaves the page unframed [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
      const response = await route.fetch()
      const json = await response.json()
      json.fields = [
        { key: 'total_debt', label: 'Total debt', value: 1234, unit: 'MSEK', period: '2025', raw_label: 'Total debt',
          source: { page: 30, quote: 'Note 20 Borrowings\nTotal debt is 1 234 MSEK due within one year, filed with the group' },
          evidence: ['quote_on_page', 'value_in_quote'], confidence: 0.9 },
        { key: 'due_within_1_year', label: 'Due within 1 year', value: 1234, unit: 'MSEK', period: '2025', raw_label: 'Due within 1 year',
          source: { page: 31, quote: 'Total debt 1 234 MSEK' },
          evidence: ['quote_on_page', 'value_in_quote'], confidence: 0.9 },
      ]
      json.checks = []
      json.warnings = []
      await route.fulfill({ response, json })
    })

    await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
    await page.setInputFiles('#pdf', [{ name: 'locate-report.pdf', mimeType: 'application/pdf', buffer: makePdf(35, LOCATE_PAGES) }])
    await expect(page.getByText('1 file selected')).toBeVisible()
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()
    await page.getByRole('main').getByRole('button', { name: /^View results/ }).click({ timeout: 20000 })

    // Total debt (p.30): a citation spanning what were two printed lines draws a box per line
    // (2 rects) but is still ONE occurrence -- no "N matches" badge for an ordinary wrapped quote.
    await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Total debt', exact: true }) }).click()
    await page.getByRole('group', { name: 'Provenance viewer' }).getByRole('button', { name: 'Image', exact: true }).click()
    const page30 = page.getByAltText('Page 30 of the report')
    await expect(page30).toBeVisible()
    const overlay30 = page.locator('img[alt="Page 30 of the report"] + div')
    await expect(overlay30.locator('> div')).toHaveCount(2)
    await expect(overlay30.getByText(/matches$/)).toHaveCount(0) // one wrapped citation carries no count badge

    // Due within 1 year (p.31): the (single-line) quote is printed twice -- a real second occurrence,
    // reported and framed as such.
    await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Due within 1 year', exact: true }) }).click()
    await expect(page.getByAltText('Page 31 of the report')).toBeVisible()
    const overlay31 = page.locator('img[alt="Page 31 of the report"] + div')
    await expect(overlay31.locator('> div')).toHaveCount(2)
    await expect(overlay31.getByText('2 matches')).toBeVisible()

    // Back to Total debt, but /locate now fails -- the page still renders, just unframed, no console noise.
    await page.route(/\/pages\/\d+\/locate\?/, (route) => route.fulfill({ status: 500, json: { detail: 'boom' } }))
    await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Total debt', exact: true }) }).click()
    await expect(page30).toBeVisible()
    await expect(page.locator('img[alt="Page 30 of the report"] + div')).toHaveCount(0)

    expect(errors).toEqual([])
  })
}

const SAVED_TEXT = [
  'Total debt',
  'Total debt 1 234 MSEK due within one year',
  'Some unrelated maturity row here',
  'Total debt 1 234 MSEK due within one year',
  'Total credit facility undrawn 500 MSEK',
].join('\n')

const entry = { stem: 'locate_2025', report_id: 'lib-locate_2025', company: 'Locate Test AB', fiscal_year: 2025, pages: 12, sections: ['debt_maturity'], indexed: false, sector: 'Industrials', pdf_available: false }
const evidence = ['quote_on_page', 'value_in_quote', 'arith_ok', 'label_known', 'page_is_statement']

for (const tone of TONES) {
  test(`source: saved-text view scrolls to and cycles a repeated quote, flags a missing one, and marks OCR evidence [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await page.addInitScript((t) => window.localStorage.setItem('acrylic-tone', t), tone)
    await page.route('**/api/**', (route) => {
      const path = new URL(route.request().url()).pathname
      const data = path === '/api/kb' ? [entry]
        : path === '/api/config' ? { provider: 'codex', model: 'test', retrieval: 'bm25' }
        : path === '/api/schemas' ? [{ name: 'debt_maturity', title: 'Debt maturity' }]
        : path.includes('/pages/') ? { page: 12, text: SAVED_TEXT }
        : path.startsWith('/api/kb/locate_2025/')
          ? { report_id: entry.report_id, stem: entry.stem, company: entry.company, fiscal_year: 2025, pdf_available: false, currency: 'MSEK', section: 'debt_maturity',
              fields: [
                { key: 'total_debt', label: 'Total debt', value: 1234, unit: 'MSEK', period: '2025', raw_label: 'Total debt', source: { page: 12, quote: 'Total debt 1 234 MSEK due within one year' }, evidence, confidence: 0.8 },
                { key: 'due_within_1_year', label: 'Due within 1 year', value: 999, unit: 'MSEK', period: '2025', raw_label: 'Due within 1 year', source: { page: 12, quote: 'This exact phrase never appears in the saved text' }, evidence, confidence: 0.8 },
                { key: 'due_after_5_years', label: 'Due after 5 years', value: 500, unit: 'MSEK', period: '2025', raw_label: 'Due after 5 years', source: { page: 12, quote: 'Total credit facility undrawn 500 MSEK' }, evidence: [...evidence, 'ocr_text'], confidence: 0.7 },
              ], checks: [], warnings: [] }
          : []
      return route.fulfill({ json: data })
    })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Open', exact: true })).toHaveCount(1)
    await page.getByRole('button', { name: 'Open', exact: true }).click()

    // Total debt: its line is printed twice -- scrolls to and highlights one, offers "1/2 <>" to cycle.
    await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Total debt', exact: true }) }).click()
    // .overflow-y-auto is StoredPageText's own pre; #report-source also holds a second, unrelated
    // <pre> (the existing verbatim-quote highlight box) whenever a field with a source is selected.
    const pre = page.locator('#report-source pre.overflow-y-auto')
    await expect(pre).toContainText('Total debt 1 234 MSEK due within one year')
    const active = pre.locator('div[class*="ring-ring/45"]')
    await expect(active).toHaveCount(1)
    await expect(active).toHaveText('Total debt 1 234 MSEK due within one year')
    const cycler = page.getByRole('button', { name: '1/2 ▸' })
    await expect(cycler).toBeVisible()
    await cycler.click()
    await expect(page.getByRole('button', { name: '2/2 ▸' })).toBeVisible()

    // Due within 1 year: the cited quote never printed verbatim -- the full page still shows, with a note.
    await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Due within 1 year', exact: true }) }).click()
    await expect(page.getByText('Quote not found verbatim in saved text.')).toBeVisible()
    await expect(pre).toContainText('Total credit facility undrawn 500 MSEK') // the whole page still renders

    // Due after 5 years: OCR evidence is flagged both in the table and at the top of Source.
    await page.getByRole('row').filter({ has: page.getByText('Due after 5 years', { exact: true }) }).click()
    await expect(page.getByText('From OCR — check the scanned image', { exact: false })).toHaveCount(2)

    expect(errors).toEqual([])
  })
}
