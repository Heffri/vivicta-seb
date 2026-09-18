import { expect, test } from '@playwright/test'

for (const tone of ['light', 'dark']) test(`review queue, basis and saved comparison [${tone}]`, async ({ page }) => {
  const entry = { stem: 'atlas_2025', report_id: 'lib-atlas_2025', company: 'Atlas Copco', fiscal_year: 2025, sections: ['income_statement'], pages: 1, pdf_available: false, indexed: false }
  const previous = { ...entry, stem: 'atlas_2024', fiscal_year: 2024 }
  let extraction: any = { ...entry, section: 'income_statement', currency: 'MSEK', fields: [{ key: 'revenue', label: 'Revenue', value: 120, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: { page: 1, quote: 'Revenue 120' }, confidence: 0, evidence: [] }], checks: [], warnings: [], issues: [{ kind: 'basis', key: 'entity', detail: 'Confirm reporting entity' }], ready: false }
  let downloads = 0
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path.endsWith('/pdf') || path.endsWith('/fetch')) downloads++
    if (path.endsWith('/basis')) {
      const body = route.request().postDataJSON()
      expect(body.expected).toEqual(extraction.basis ?? {})
      extraction = { ...extraction, basis: { values: body.values, reviewer: body.reviewer, note: body.note, at: '2026-09-18T12:00:00Z' }, issues: [], ready: true }
      return route.fulfill({ json: extraction })
    }
    const json = path === '/api/review-queue' ? extraction.issues.map((i: any) => ({ ...i, report: entry, section: 'income_statement' }))
      : path.endsWith('/comparison') ? { candidates: [previous], previous_stem: previous.stem, current_year: 2025, previous_year: 2024, reasons: extraction.basis ? [] : ['Confirm the basis of figures first.'], rows: [{ key: 'revenue', label: 'Revenue', current: 120, previous: 100, delta: extraction.basis ? 20 : null, percent: extraction.basis ? 20 : null, sign_change: false, reason: '' }] }
      : path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path.includes('/pages/') ? { page: 1, text: 'Revenue 120' }
      : path === '/api/kb/atlas_2025/income_statement' ? extraction : []
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Review', exact: true }).click()
  await expect(page.getByText('1 unresolved items', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Review item' }).click()
  const basis = page.locator('#basis-review')
  await expect(basis).toHaveAttribute('open', '')
  await basis.getByLabel('Reporting entity', { exact: true }).fill('Atlas Copco AB')
  await basis.getByLabel('Group or parent').selectOption('Group')
  await basis.getByLabel('Fiscal period').fill('2025')
  await basis.getByLabel('Currency', { exact: true }).fill('SEK')
  await basis.getByLabel('Scale', { exact: true }).selectOption('Millions')
  await basis.getByLabel('Source references').fill('Page 1, group statement')
  await basis.getByLabel('Restatement status').selectOption('As reported')
  await basis.getByLabel('Basis reviewer').fill('Sebastian')
  await basis.getByLabel('Basis review note').fill('Checked the statement heading and units')
  await basis.getByRole('button', { name: 'Save basis review' }).click()
  await expect(basis).toContainText('Ready for analyst use')
  const comparison = page.getByRole('region', { name: 'Prior-year comparison' })
  await expect(comparison).toContainText('2024 → 2025')
  await expect(comparison.getByRole('cell', { name: '20', exact: true })).toHaveCount(2)
  await expect(page.getByRole('link', { name: 'Export CSV' })).toHaveAttribute('href', /section=income_statement&previous_stem=atlas_2024/)
  await comparison.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `e2e/test-results/workbench-${tone}.png` })
  await page.getByRole('button', { name: 'Back to reports' }).click()
  await expect(page.getByText('0 unresolved items', { exact: true })).toBeVisible()
  expect(downloads).toBe(0)
  expect(errors).toEqual([])
})
