import { expect, test } from '@playwright/test'

// A directory pick never needs an opt-in: saved text/PDF are reused first (download_pdf:false), and the
// backend's 409 "nothing saved" answer retries once with the download allowed behind a progress line.
test('directory picks reuse saved reports first and download the PDF on 409', async ({ page }) => {
  const fetched: any[] = []
  const scopes: string[] = []
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (['/api/companies', '/api/library', '/api/kb'].includes(url.pathname)) scopes.push(url.searchParams.get('collection_name') ?? '')
    if (url.pathname === '/api/reports/fetch') {
      const body = route.request().postDataJSON(); fetched.push(body)
      if (!body.download_pdf) return route.fulfill({ status: 409, json: { detail: 'No saved report. PDF download is off.' } })
      await new Promise(r => setTimeout(r, 300)) // keep the download line visible long enough to assert on it
      return route.fulfill({ json: { report_id: 'lib-atlas_copco_2025', company: 'Atlas Copco', fiscal_year: 2025, pages: 150 } })
    }
    if (url.pathname.endsWith('/extract')) return route.fulfill({ json: { report_id: 'lib-atlas_copco_2025', company: 'Atlas Copco', fiscal_year: 2025, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    return route.fulfill({ json: url.pathname === '/api/companies' ? [{ name: 'Atlas Copco', ticker: 'ATCO', sector: 'Industrials', isin: null, cached_years: [] }] : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : url.pathname === '/api/config' ? { provider: 'codex', model: 'test' } : [] })
  })
  await page.goto('/')
  await expect(page.getByRole('checkbox', { name: /Allow PDF download/ })).toHaveCount(0)
  await page.getByRole('button', { name: /Atlas Copco ATCO/ }).click()
  expect(fetched).toEqual([]) // picking queues, nothing is fetched yet
  await page.getByRole('button', { name: 'Extract', exact: true }).click()
  await expect(page.getByText(/Downloading PDF/)).toBeVisible()
  await expect.poll(() => fetched.length).toBe(2)
  expect(fetched.map(request => [request.company, request.download_pdf])).toEqual([['Atlas Copco', false], ['Atlas Copco', true]])
  await expect(page.getByText(/No saved report/)).toHaveCount(0) // the 409 is handled, never shown as a failure
  await expect(page.getByRole('heading', { name: 'Atlas Copco', exact: true })).toBeVisible() // results view: the fetch + extract went through
  expect(scopes.every(scope => scope === 'wallenberg')).toBe(true)
})

test('a fetch error other than 409 is shown, not retried', async ({ page }) => {
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
  await expect(page.getByText('Atlas Copco: tried 1 URL', { exact: true })).toBeVisible()
  expect(fetched.map(request => request.download_pdf)).toEqual([false])
})
