import { expect, test } from '@playwright/test'

test('PDF download is off by default and requires an explicit request', async ({ page }) => {
  const fetched: any[] = []
  const scopes: string[] = []
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (['/api/companies', '/api/library', '/api/kb'].includes(url.pathname)) scopes.push(url.searchParams.get('collection_name') ?? '')
    if (url.pathname === '/api/reports/fetch') { fetched.push(route.request().postDataJSON()); return route.fulfill({ status: 409, json: { detail: 'No saved report. PDF download is off.' } }) }
    return route.fulfill({ json: url.pathname === '/api/companies' ? [{ name: 'Atlas Copco', ticker: 'ATCO', sector: 'Industrials', isin: null, cached_years: [] }] : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : url.pathname === '/api/config' ? { provider: 'codex', model: 'test' } : [] })
  })
  await page.goto('/')
  const optIn = page.getByRole('checkbox', { name: /Allow PDF download for this request/ })
  await expect(optIn).not.toBeChecked()
  await page.getByRole('button', { name: /Atlas Copco ATCO/ }).click()
  expect(fetched).toEqual([])
  await page.getByRole('button', { name: 'Extract', exact: true }).click()
  await expect.poll(() => fetched.length).toBe(1)
  expect(fetched[0].download_pdf).toBe(false)
  await expect(page.getByText(/No saved report. PDF download is off/)).toBeVisible()
  await optIn.check()
  await page.getByRole('button', { name: 'Download PDF and extract', exact: true }).click()
  await expect.poll(() => fetched.length).toBe(2)
  expect(fetched[1].download_pdf).toBe(true)
  expect(scopes.every(scope => scope === 'wallenberg')).toBe(true)
  await page.reload()
  await expect(optIn).not.toBeChecked()
})
