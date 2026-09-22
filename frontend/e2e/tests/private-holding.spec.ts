import { expect, test } from '@playwright/test'

// A private holding has no annual report of its own, so it exists in the company directory only
// because the curated roster is merged into it. The row must stay reachable — and opening it must
// go straight to the saved parent section, with no discovery, download or model call.
test('a private Patricia holding opens its saved Investor section without AI discovery or PDF fetch', async ({ page }) => {
  const discovered: unknown[] = [], fetched: unknown[] = [], extracted: unknown[] = []
  const sarnova = {
    name: 'Sarnova', ticker: '', sector: null, isin: null, cached_years: [],
    no_standalone_report: true, reports_in: 'Investor AB', collection_group: 'Patricia Industries',
    report_stem: 'investor_2025', report_page: 41,
  }
  const investorExtraction = {
    report_id: 'lib-investor_2025', stem: 'investor_2025', company: 'Investor AB', fiscal_year: 2025,
    section: 'income_statement', fields: [], checks: [], warnings: [], pdf_available: false,
  }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') discovered.push(route.request().postDataJSON())
    if (path === '/api/reports/fetch') fetched.push(route.request().postDataJSON())
    if (path.endsWith('/extract')) extracted.push(route.request().postDataJSON())
    const json = path === '/api/config' ? { provider: 'fixture', model: 'test' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Consolidated income statement' }]
      : path === '/api/companies' ? [sarnova]
      : path === '/api/kb/investor_2025/income_statement' ? investorExtraction
      : path === '/api/kb/investor_2025/pages/41' ? { page: 41, text: 'Patricia Industries includes Sarnova.' }
      : []
    await route.fulfill({ json })
  })

  await page.goto('/')
  await expect(page.getByText("Private company — reported inside Investor AB's annual report (Patricia Industries)", { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Open Investor AB report for Sarnova', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Investor AB', exact: true })).toBeVisible()
  await expect(page.getByText('Page 41', { exact: true })).toBeVisible()
  expect(discovered).toEqual([])
  expect(fetched).toEqual([])
  expect(extracted).toEqual([])
})
