import { expect, test, type Page } from '@playwright/test'

const company = 'New Horizon Industries'
const stem = 'new_horizon_industries_2025'
const report = { report_id: `lib-${stem}`, company, fiscal_year: 2025, pages: 120 }
const entry = { ...report, stem, sections: [] as string[], indexed: false, status: 'missing', pdf_available: true, text_available: true, page_chunks: 0, fact_chunks: 0 }

async function mockCatalog(page: Page, state: { saved: boolean; extracted: boolean }, extraction?: Promise<void>) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path === '/api/kb') return route.fulfill({ json: state.saved && url.searchParams.get('collection_name') === 'all'
      ? [{ ...entry, sections: state.extracted ? ['income_statement'] : [] }] : [] })
    if (path === '/api/reports/discover') return route.fulfill({ json: { candidates: [{ legal_name: company, ticker: 'NHI', country: 'US', exchange: 'NASDAQ', document_title: 'Annual report 2025', document_type: 'annual report', url: 'https://example.com/report.pdf', reason: 'Matching company', saved: false }], note: null } })
    if (path === '/api/reports/fetch') {
      state.saved = true
      return route.fulfill({ json: report })
    }
    if (path.endsWith('/extract')) {
      await extraction
      state.extracted = true
      return route.fulfill({ json: { ...report, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test', retrieval: 'bm25' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : path === '/api/library' && state.saved ? [{ ...report, file: `${stem}.pdf`, tags: [], language: 'en', source_url: null }] : [] })
  })
}

test('Knowledge base defaults to all reports independently of the Extract collection', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('arp-kb-collection', 'wallenberg'))
  await mockCatalog(page, { saved: true, extracted: true })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: company })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('arp-kb-collection'))).toBe('wallenberg')
})

test('a discovered report and its completed extraction appear while Knowledge base stays open', async ({ page }) => {
  const state = { saved: false, extracted: false }
  let finishExtraction!: () => void
  const extraction = new Promise<void>(resolve => { finishExtraction = resolve })
  await mockCatalog(page, state, extraction)
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill(company)
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.locator('[data-slot="card"]', { hasText: company }).getByRole('button', { name: 'Use this company', exact: true }).click()
  await expect.poll(() => state.saved).toBe(true)
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: company })
  await expect(row.getByText('none yet', { exact: true })).toBeVisible()
  finishExtraction()
  await expect(row.getByText('Income statement', { exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Knowledge base', exact: true })).toHaveAttribute('aria-selected', 'true')
})

test('empty collection keeps an escape to all reports and Refresh picks up newly saved reports', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('arp-kb-view-collection', 'wallenberg'))
  const state = { saved: false, extracted: true }
  await mockCatalog(page, state)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await expect(page.getByText('No saved reports in this collection.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show all saved reports', exact: true }).click()
  await expect(page.getByText('No saved reports yet. Fetch or upload a report in Extract.', { exact: true })).toBeVisible()
  state.saved = true
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: company })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('arp-kb-view-collection'))).toBe('all')
})
