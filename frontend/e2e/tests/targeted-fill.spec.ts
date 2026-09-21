import { expect, test } from '@playwright/test'

test('an analyst-directed page candidate only populates the ordinary correction form', async ({ page }) => {
  const entry = { stem: 'fill_test', report_id: 'lib-fill_test', company: 'Fill Test', fiscal_year: 2025, pages: 2, sections: ['income_statement'], indexed: false, pdf_available: false }
  const extraction: any = { ...entry, section: 'income_statement', currency: 'MSEK', fields: [
    { key: 'revenue', label: 'Revenue', value: null, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: null, evidence: [], confidence: 0 },
    { key: 'cost_of_sales', label: 'Cost of sales', value: -80, unit: 'MSEK', period: '2025', raw_label: 'Cost of sales', source: { page: 1, quote: 'Cost of sales -80' }, evidence: ['quote_on_page'], confidence: .8 },
  ], checks: [], warnings: [] }
  const fills: any[] = []
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/fill')) {
      fills.push(route.request().postDataJSON())
      return route.fulfill({ json: { candidate: { ...extraction.fields[0], value: 125, source: { page: 1, quote: 'Revenue 125' }, evidence: ['quote_on_page'], confidence: .8 }, warnings: ['Candidate is unreviewed; check the evidence before saving.'] } })
    }
    const pageMatch = path.match(/\/pages\/(\d+)$/)
    return route.fulfill({ json: path === '/api/kb' ? [entry]
      : path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path === '/api/kb/fill_test/income_statement' ? extraction
      : pageMatch ? { page: Number(pageMatch[1]), text: Number(pageMatch[1]) === 1 ? 'Revenue 125\nCost of sales -80' : '' }
      : [] })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await page.getByRole('button', { name: 'Open', exact: true }).click()
  await page.getByRole('cell', { name: 'Revenue', exact: true }).click()
  const form = page.getByRole('form', { name: 'Review Revenue' })
  const fill = page.getByRole('button', { name: 'Fill Revenue from this page', exact: true })
  await expect(fill).toBeVisible()
  await fill.click()
  const candidate = form.getByRole('region', { name: 'Candidate for Revenue' })
  await expect(candidate).toContainText('Revenue 125')
  expect(fills).toEqual([{ field: 'revenue', pages: [1] }])
  // Write evidence only after the candidate and request assertions have passed; this avoids a
  // superficially plausible screenshot from a failed state becoming the delivery artifact.
  await candidate.scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../docs/acrylic/evidence/v177/targeted-fill-candidate.png', fullPage: true })
  await form.getByRole('button', { name: 'Accept as correction', exact: true }).click()
  await expect(form.getByLabel('Decision')).toHaveValue('corrected')
  await expect(form.getByLabel('Value', { exact: true })).toHaveValue('125')
  await expect(form.getByLabel('Citation page')).toHaveValue('1')
  await expect(form.getByLabel('Citation quote')).toHaveValue('Revenue 125')

  await fill.click()
  await expect(form.getByRole('region', { name: 'Candidate for Revenue' })).toBeVisible()
  await form.getByRole('button', { name: 'Discard', exact: true }).click()
  await expect(form.getByRole('region', { name: 'Candidate for Revenue' })).toBeHidden()
})
