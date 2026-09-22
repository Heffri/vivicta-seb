import { expect, test } from '@playwright/test'

// The PDF is always wanted: every directory pick fetches once with download_pdf:true (the backend reuses a
// cached PDF, downloads when only text is saved, and falls back to saved text if the download fails).
test('directory picks fetch once with the PDF download on', async ({ page }) => {
  const fetched: any[] = []
  const scoped: string[] = []
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    // Nothing narrows the catalogue any more: no surface may send a collection_name.
    if (url.searchParams.has('collection_name')) scoped.push(url.pathname)
    if (url.pathname === '/api/reports/fetch') {
      fetched.push(route.request().postDataJSON())
      await new Promise(r => setTimeout(r, 300)) // keep the progress line visible long enough to assert on it
      return route.fulfill({ json: { report_id: 'lib-atlas_copco_2025', company: 'Atlas Copco', fiscal_year: 2025, pages: 150 } })
    }
    if (url.pathname.endsWith('/extract')) return route.fulfill({ json: { report_id: 'lib-atlas_copco_2025', company: 'Atlas Copco', fiscal_year: 2025, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    return route.fulfill({ json: url.pathname === '/api/companies' ? [{ name: 'Atlas Copco', ticker: 'ATCO', sector: 'Industrials', isin: null, cached_years: [] }] : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : url.pathname === '/api/config' ? { provider: 'codex', model: 'test' } : [] })
  })
  await page.goto('/')
  await expect(page.getByRole('checkbox', { name: /Allow PDF download/ })).toHaveCount(0) // no opt-in anywhere
  await page.getByRole('button', { name: /Atlas Copco ATCO/ }).click()
  expect(fetched).toEqual([]) // picking queues, nothing is fetched yet
  await page.getByRole('button', { name: 'Extract', exact: true }).click()
  await expect(page.getByText(/Opening Atlas Copco annual report 2025/)).toBeVisible()
  // The completed batch stays on Extract so its per-report outcome remains inspectable.
  // Opening Results is explicit, rather than an implicit navigation at the moment it settles.
  await page.getByRole('button', { name: 'View results (1)', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Atlas Copco', exact: true })).toBeVisible() // results view: the fetch + extract went through
  expect(fetched.map(request => [request.company, request.year, request.download_pdf])).toEqual([['Atlas Copco', 2025, true]])
  expect(scoped).toEqual([])
})

test('a fetch error is shown with the URLs tried, never retried', async ({ page }) => {
  const fetched: any[] = []
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/reports/fetch') { fetched.push(route.request().postDataJSON()); return route.fulfill({ status: 404, json: { detail: 'No annual report found', tried: ['https://example.com/a.pdf'] } }) }
    return route.fulfill({ json: url.pathname === '/api/companies' ? [{ name: 'Atlas Copco', ticker: 'ATCO', sector: 'Industrials', isin: null, cached_years: [] }] : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : url.pathname === '/api/config' ? { provider: 'codex', model: 'test' } : [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /Atlas Copco ATCO/ }).click()
  await page.getByRole('button', { name: 'Extract', exact: true }).click()
  await expect(page.getByText(/No annual report found/)).toBeVisible()
  // The batch row keeps the attempted URLs beside the failed item; expand it to prove the
  // backend's diagnostic survives without an automatic retry or a forced tab switch.
  await page.getByText('tried 1 URL', { exact: true }).click()
  await expect(page.getByText('https://example.com/a.pdf', { exact: true })).toBeVisible()
  expect(fetched.map(request => request.download_pdf)).toEqual([true])
})
