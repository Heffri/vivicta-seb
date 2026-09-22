import { expect, test } from '@playwright/test'

test('older years reach discovery and audited alternative sources are labeled', async ({ page }) => {
  const company = 'Example Industries Inc.'
  const notice = 'FY2020 audited accounts from a registration statement/prospectus, not a standalone annual report. Original PDF page numbers are preserved.'
  const queries: number[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      queries.push(route.request().postDataJSON().year)
      return route.fulfill({ json: { candidates: [{ legal_name: company, ticker: 'EXM', document_type: 'registration statement', document_title: 'IPO filing with audited 2020 accounts', url: 'https://example.com/s1.pdf', reason: 'Historical audited accounts', saved: false }], note: null } })
    }
    if (path === '/api/reports/fetch') {
      expect(route.request().postDataJSON().year).toBe(2020)
      return route.fulfill({ json: { report_id: 'lib-example_2020', company, fiscal_year: 2020, pages: 300, document_type: 'registration_statement', statement_pages: [200, 201], source_notice: notice } })
    }
    if (path.endsWith('/extract')) return route.fulfill({ json: { report_id: 'lib-example_2020', company, fiscal_year: 2020, section: 'income_statement', fields: [], checks: [], warnings: [notice] } })
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : [] })
  })
  await page.goto('/')
  await page.getByRole('combobox', { name: 'Fiscal year' }).click()
  await page.getByRole('option', { name: '2020', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('EXM')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('button', { name: 'Use this company', exact: true }).click()
  await expect(page.getByRole('list', { name: 'Batch progress' }).getByText(notice, { exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Batch progress' }).getByText('Done', { exact: true })).toBeVisible()
  expect(queries).toEqual([2020])
})
