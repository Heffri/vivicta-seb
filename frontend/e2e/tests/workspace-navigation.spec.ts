import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'

const report = { stem: 'atlas_2025', report_id: 'lib-atlas_2025', company: 'Atlas Copco', fiscal_year: 2025, pages: 1, sections: ['income_statement'], indexed: false, status: 'missing', sector: 'Industrials', pdf_available: true, text_available: true }
const extraction = { ...report, section: 'income_statement', currency: 'MSEK', fields: [{ key: 'revenue', label: 'Revenue', value: 100, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: { page: 1, quote: 'Revenue 100 MSEK' }, evidence: [], confidence: 0 }], checks: [], warnings: [] }

for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }]) test(`all income figures fit without scrolling at ${viewport.width}×${viewport.height}`, async ({ page }) => {
  await page.setViewportSize(viewport)
  const labels = ['Revenue', 'Cost of sales', 'Gross profit', 'Operating profit', 'Profit before tax', 'Income tax', 'Profit from discontinued operations', 'Profit for the year', 'EPS, basic']
  const figures = labels.map((label, i) => ({ ...extraction.fields[0], key: `figure_${i}`, label, value: i === 6 ? null : i === 8 ? 5.43 : 168343 - i * 1000, unit: i === 6 ? null : i === 8 ? 'SEK' : 'MSEK', period: i === 6 ? null : '2025' }))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/pdf')) return route.fulfill({ contentType: 'application/pdf', body: makePdf(1) })
    return route.fulfill({ json: path === '/api/kb' ? [report] : path === '/api/config' ? { provider: 'fixture', model: 'test' } : path === '/api/kb/atlas_2025/income_statement' ? { ...extraction, stale: true, fields: figures } : [] })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await page.getByRole('button', { name: 'Open', exact: true }).click()
  const table = page.getByRole('table', { name: 'Statement figures' })
  await expect(table.locator('tbody tr')).toHaveCount(9)
  const content = await page.locator('#content').boundingBox()
  const bounds = await table.boundingBox()
  expect(bounds!.y).toBeGreaterThanOrEqual(content!.y)
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(content!.y + content!.height)
  expect(await page.locator('#content').evaluate(el => el.scrollTop)).toBe(0)
  expect(await table.evaluate(el => el.parentElement!.scrollWidth <= el.parentElement!.clientWidth)).toBe(true)
  await expect(table.getByRole('cell', { name: '5.43 SEK', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: '—', exact: true })).toBeVisible()
  await table.getByRole('row').filter({ hasText: 'EPS, basic' }).press('Enter')
  await expect(table.getByRole('row').filter({ hasText: 'EPS, basic' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#report-source')).toContainText('EPS, basic')
})

for (const tone of ['dark', 'light']) test(`workspaces preserve drafts and provide a readable source pane [${tone}]`, async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/pdf')) return route.fulfill({ contentType: 'application/pdf', body: makePdf(1) })
    return route.fulfill({ json: path === '/api/kb' ? [report]
      : path === '/api/config' ? { provider: 'fixture', model: 'test', retrieval: 'bm25' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : path === '/api/kb/atlas_2025/income_statement' ? extraction
      : path.endsWith('/comparison') ? { candidates: [], rows: [], reasons: [] }
      : path === '/api/companies' ? [{ name: 'Atlas Copco', ticker: 'ATCO', sector: 'Industrials', cached_years: [] }]
      : path === '/api/review-queue' ? [{ kind: 'basis', key: 'entity', detail: 'Confirm entity', section: 'income_statement', report }]
      : [] })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Rebuild', exact: true })).not.toBeVisible()
  await page.getByRole('button', { name: 'Search index', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Rebuild', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Reports', exact: true }).click()
  await page.getByRole('button', { name: 'Open', exact: true }).click()
  const source = page.locator('#report-source')
  const pdf = source.locator('iframe')
  await expect(pdf).toHaveAttribute('src', /page=1&navpanes=0&zoom=100/)
  const sideWidth = (await source.boundingBox())!.width
  expect(sideWidth).toBeGreaterThan(550)
  await source.getByRole('button', { name: 'Zoom in source', exact: true }).click()
  await expect(pdf).toHaveAttribute('src', /zoom=125/)
  await source.getByRole('button', { name: 'Fit width', exact: true }).click()
  await expect(pdf).toHaveAttribute('src', /view=FitH/)
  await source.getByRole('button', { name: 'Expand reader', exact: true }).click()
  expect((await source.boundingBox())!.width).toBeGreaterThan(sideWidth * 1.5)
  await expect(page.locator('tbody').getByText('Revenue', { exact: true })).not.toBeVisible()
  await source.getByRole('button', { name: 'Back to figures', exact: true }).click()
  await page.locator('summary').filter({ hasText: /^Review Revenue$/ }).click()
  await page.getByRole('form', { name: 'Review Revenue' }).getByLabel('Your name').fill('Draft reviewer')
  const nav = page.getByRole('navigation', { name: 'Report workspace' })
  await nav.getByRole('button', { name: 'Ask report', exact: true }).click()
  await page.getByLabel('Question', { exact: true }).fill('Explain this figure')
  await nav.getByRole('button', { name: 'Figures & sources', exact: true }).click()
  await expect(page.getByRole('form', { name: 'Review Revenue' }).getByLabel('Your name')).toHaveValue('Draft reviewer')
  await nav.getByRole('button', { name: 'Ask report', exact: true }).click()
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('Explain this figure')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await page.getByLabel('Question', { exact: true }).fill('My draft question')
  await page.getByRole('button', { name: /Available reports/ }).click()
  await expect(page.getByRole('cell', { name: 'Atlas Copco', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Conversation', exact: true }).click()
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('My draft question')
  await page.screenshot({ path: `e2e/test-results/workspace-ask-${tone}.png` })
  await page.getByRole('tab', { name: 'Review', exact: true }).click()
  await page.getByRole('button', { name: 'Figures', exact: true }).click()
  await expect(page.getByText('No checks match these filters.')).toBeVisible()
  await page.getByRole('button', { name: 'Reporting basis', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Review statement', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Company map', exact: true }).click()
  await page.getByRole('navigation', { name: 'Company workspace' }).getByRole('button', { name: /Company reports/ }).click()
  await expect(page.getByRole('button', { name: 'Open report', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Settings', exact: true }).click()
  await expect(page.getByText('Running now', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Appearance', exact: true }).click()
  await expect(page.getByText('Theme', { exact: true })).toBeVisible()
  await expect(page.getByText('Running now', { exact: true })).not.toBeVisible()
  expect(errors).toEqual([])
})
