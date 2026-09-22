import { expect, test } from '@playwright/test'

const entry = { stem: 'atlas_2025', report_id: 'lib-atlas_2025', company: 'Atlas Copco', fiscal_year: 2025, pages: 80, sections: ['income_statement', 'debt_maturity'], indexed: false, sector: 'Industrials', pdf_available: false }
const evidence = ['quote_on_page', 'value_in_quote', 'arith_ok', 'label_known', 'page_is_statement']

for (const tone of ['light', 'dark']) test(`review guidance, one Open, statement switch and graph interactions [${tone}]`, async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const section = path.endsWith('/debt_maturity') ? 'debt_maturity' : 'income_statement'
    const data = path === '/api/kb' ? [entry]
      : path === '/api/config' ? { provider: 'codex', model: 'test', retrieval: 'bm25' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }, { name: 'debt_maturity', title: 'Debt maturity' }]
      : path.includes('/pages/') ? { page: 3, text: 'Revenue 100 MSEK. Total debt 200 MSEK.' }
      : path.startsWith('/api/kb/atlas_2025/') ? { report_id: entry.report_id, stem: entry.stem, company: entry.company, fiscal_year: 2025, pdf_available: false, currency: 'MSEK', section,
          fields: [{ key: section === 'debt_maturity' ? 'total_debt' : 'revenue', label: section === 'debt_maturity' ? 'Total debt' : 'Revenue', value: section === 'debt_maturity' ? 200 : 100, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: { page: 3, quote: 'Revenue 100 MSEK' }, evidence, confidence: 0.8 }], checks: [], warnings: [] }
      : []
    return route.fulfill({ json: data })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Open', exact: true })).toHaveCount(1)
  await page.getByRole('button', { name: 'Open', exact: true }).click()
  await expect(page.getByLabel('Statement', { exact: true })).toContainText('Consolidated income statement')
  const revenue = page.getByRole('row').filter({ has: page.getByText('Revenue', { exact: true }) })
  await expect(revenue).toContainText('Needs review')
  await page.locator('summary').filter({ hasText: /^Review Revenue$/ }).click()
  const guidance = page.locator('details').filter({ has: page.getByRole('form', { name: 'Review Revenue' }) })
  await expect(guidance).toContainText('Confirm the figure is in the 2025 column')
  await expect(guidance).toContainText('Confirm the table uses MSEK')
  await page.getByLabel('Statement', { exact: true }).click()
  await page.getByRole('option', { name: 'Debt maturity', exact: true }).click()
  await expect(page.getByText('Total debt', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Back to reports', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Open', exact: true })).toHaveCount(1)
  await page.getByRole('tab', { name: 'Company map', exact: true }).click()
  const graph = page.getByRole('region', { name: 'Interactive company graph' })
  await expect(graph.locator('line')).toHaveCount(3)
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click()
  await expect(graph).toContainText('125%')
  await page.getByRole('button', { name: 'Reset graph view', exact: true }).click()
  const node = graph.locator('[data-node-id="company:atlas copco"]')
  const before = await node.getAttribute('transform')
  const box = await node.locator('circle').last().boundingBox()
  if (!box) throw new Error('Company node missing')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 50, box.y + box.height / 2 + 30, { steps: 5 })
  await page.mouse.up()
  await expect(node).not.toHaveAttribute('transform', before!)
  await page.getByRole('button', { name: 'Reset graph view', exact: true }).click()
  await expect(node).toHaveAttribute('transform', before!)
  const canvas = graph.locator('svg[role="group"]')
  const canvasBox = await canvas.boundingBox()
  if (!canvasBox) throw new Error('Graph canvas missing')
  const transform = canvas.locator(':scope > g')
  const origin = await transform.getAttribute('transform')
  await page.mouse.move(canvasBox.x + 20, canvasBox.y + 130)
  await page.mouse.down()
  await page.mouse.move(canvasBox.x + 60, canvasBox.y + 160, { steps: 4 })
  await page.mouse.up()
  await expect(transform).not.toHaveAttribute('transform', origin!)
  await page.getByRole('button', { name: 'Reset graph view', exact: true }).click()
  await page.getByLabel('Search companies or reports').fill('missing company')
  await expect(graph.getByRole('status')).toContainText('No matching companies')
  await page.getByLabel('Search companies or reports').fill('')
  await page.screenshot({ path: `e2e/test-results/graph-${tone}.png`, fullPage: true })
  await graph.getByRole('button', { name: 'Open Atlas Copco 2025 report', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Statement', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
