import { expect, test } from '@playwright/test'

for (const width of [1440, 900]) test(`review issue scroll stays inside the app [${width}px]`, async ({ page }) => {
  await page.setViewportSize({ width, height: 738 })
  const entry = { stem: 'aak_2025', report_id: 'lib-aak_2025', company: 'AAK', fiscal_year: 2025, sections: ['debt_maturity'], pages: 190, pdf_available: false, indexed: false }
  const extraction = { ...entry, section: 'debt_maturity', currency: 'SEK million', fields: ['total_debt', 'due_within_1_year', 'due_1_to_5_years', 'due_after_5_years'].map((key, i) => ({ key, label: ['Total borrowings', 'Due within 1 year', 'Due 1–5 years', 'Due after 5 years'][i], value: [4478, 4088, 0, 390][i], unit: 'SEK million', period: '2025', source: { page: 169, quote: 'Borrowings note' }, confidence: 0, evidence: [] })), checks: [{ name: 'maturity_sums_to_total', passed: false, detail: 'Check debt repayment figures' }], warnings: [], issues: [{ kind: 'check', key: 'maturity_sums_to_total', detail: 'Check debt repayment figures' }], ready: false }
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const json = path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path === '/api/review-queue' ? [{ ...extraction.issues[0], report: entry, section: 'debt_maturity' }]
      : path === '/api/kb/aak_2025/debt_maturity' ? extraction
      : path.includes('/pages/') ? { page: 169, text: 'Borrowings note' } : []
    return route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Review', exact: true }).click()
  await page.getByText('Show outstanding checks', { exact: true }).click()
  await page.getByRole('button', { name: 'Review Check debt repayment figures', exact: true }).click()
  await expect(page.locator('#calculation-checks')).toBeInViewport()
  const geometry = await page.evaluate(() => {
    const content = document.getElementById('content')!
    const shell = document.querySelector('#root > div')!.getBoundingClientRect()
    return { windowY: window.scrollY, contentY: content.scrollTop, top: shell.top, bottom: shell.bottom, height: innerHeight, bodyHeight: document.body.scrollHeight }
  })
  expect(geometry.windowY).toBe(0)
  // Checks now open directly in their subpage and may already fit without scrolling.
  expect(geometry.contentY).toBeGreaterThanOrEqual(0)
  await expect(page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: /Checks & review/ })).toHaveAttribute('aria-current', 'page')
  expect(geometry.top).toBe(0)
  expect(geometry.bottom).toBe(geometry.height)
  expect(geometry.bodyHeight).toBe(geometry.height)
  await page.screenshot({ path: `e2e/test-results/review-scroll-${width}.png` })
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Question', exact: true })).toBeVisible()
})

test('one statement card keeps independent basis prefill, source hints, reviewer and filter', async ({ page }) => {
  const entry = { stem: 'atlas_2025', report_id: 'lib-atlas_2025', company: 'Atlas Copco', fiscal_year: 2025, sections: ['debt_maturity'], pages: 7, pdf_available: false, indexed: false }
  const source = { page: 7, quote: 'Maturity profile: due within 1 year, due 1 to 5 years and due after 5 years (carrying amount)' }
  const fields = [
    { key: 'total_debt', label: 'Total borrowings', value: 100, unit: 'MSEK', period: '2025', raw_label: 'Total borrowings', source, confidence: 0, evidence: [] },
    { key: 'due_within_1_year', label: 'Due within 1 year', value: null, unit: null, period: null, raw_label: 'Due within 1 year', source: null, confidence: 0, evidence: [] },
    { key: 'due_1_to_5_years', label: 'Due 1–5 years', value: 50, unit: 'MSEK', period: '2025', raw_label: 'Due 1–5 years', source, confidence: 0, evidence: [] },
    { key: 'due_after_5_years', label: 'Due after 5 years', value: 30, unit: 'MSEK', period: '2025', raw_label: 'Due after 5 years', source, confidence: 0, evidence: [] },
  ]
  const issues: any[] = [
    { kind: 'field', key: 'total_debt', detail: 'Total borrowings: verify value, unit, period and source' },
    { kind: 'field', key: 'due_within_1_year', detail: 'Due within 1 year: missing value (not zero)' },
    { kind: 'check', key: 'maturity_sums_to_total', detail: 'maturity_sums_to_total: 100 != 80' },
    { kind: 'check', key: 'periods', detail: 'periods: Cannot reconcile missing or incompatible units/periods.' },
  ]
  const extraction: any = {
    ...entry, section: 'debt_maturity', currency: 'MSEK', fields, checks: [], warnings: [], issues, ready: false,
    // Confirmed basis choices do not block the figure/check queue. The backend pre-fills
    // its safe defaults in this dictionary, while the older source-backed hints remain available
    // for a reviewer to inspect or explicitly re-apply.
    basis_issues: [{ kind: 'basis', key: 'period', detail: 'Confirm period' }],
    basis_suggested: {
      entity: 'Atlas Copco', consolidation: 'Group', period: '2025', currency: 'SEK', scale: 'Millions',
      source: 'Annual report', restatement: 'As reported', debt_basis: 'Carrying amounts',
      bucket_mapping: 'Under 1, 1 to 5, over 5',
    },
    basis_suggestions: [
      { key: 'debt_basis', value: 'Carrying amounts', source },
      { key: 'bucket_mapping', value: 'Under 1, 1 to 5, over 5', source },
    ],
  }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/review')) return route.fulfill({ status: 409, json: { detail: 'The field changed. Reopen before saving.' } })
    const json = path === '/api/config' ? { provider: 'fixture', model: 'test' }
      : path === '/api/review-queue' ? issues.map(issue => ({ ...issue, report: entry, section: 'debt_maturity' }))
      : path === '/api/kb/atlas_2025/debt_maturity' ? extraction
      : path.includes('/pages/') ? { page: 7, text: source.quote }
      : path.endsWith('/comparison') ? { candidates: [], reasons: [], rows: [] } : []
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Review', exact: true }).click()
  await expect(page.getByRole('article')).toHaveCount(1)
  const statement = page.getByRole('article', { name: 'Atlas Copco 2025 debt maturity' })
  await statement.getByText('Show outstanding checks', { exact: true }).click()
  for (const heading of ['Numeric conflicts', 'Missing evidence', 'Cannot calculate']) await expect(statement.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  await expect(statement.getByRole('heading', { name: 'Basis to confirm', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Figures', exact: true }).click()
  await statement.getByRole('button', { name: 'Review statement', exact: true }).click()
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: /Checks & review/ }).click()
  const basis = page.locator('#basis-review')
  await basis.locator('summary').click()
  await expect(basis).toHaveAttribute('open', '')
  await expect(basis.getByLabel('Reporting entity', { exact: true })).toHaveValue('Atlas Copco')
  await expect(basis.getByLabel('Group or parent', { exact: true })).toHaveValue('Group')
  await expect(basis.getByLabel('Source references (page and supporting text)', { exact: true })).toHaveValue('Annual report')
  await expect(basis.getByLabel('Restatement status', { exact: true })).toHaveValue('As reported')
  await expect(basis).toContainText('Prefilled from the report; nothing is confirmed until you save.')
  await expect(basis.getByText('Suggested from p. 7', { exact: true }).first()).toBeVisible()
  await expect(basis).toContainText('Basis of figures · Basis not confirmed')
  await expect(basis.getByRole('button', { name: 'Use suggestion for Debt measurement', exact: true })).toBeVisible()
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Figures & sources', exact: true }).click()
  const totalReview = page.getByRole('form', { name: 'Review Total borrowings', exact: true })
  await totalReview.getByLabel('Your name', { exact: true }).fill('Alex Analyst')
  await totalReview.getByRole('button', { name: 'Save review', exact: true }).click()
  await expect(totalReview.getByRole('alert')).toContainText('The field changed')
  await expect(totalReview.getByLabel('Your name', { exact: true })).toHaveValue('Alex Analyst')
  await page.getByRole('button', { name: 'Next unresolved field', exact: true }).click()
  await page.locator('summary').filter({ hasText: /^Review Due within 1 year$/ }).click()
  const nextReview = page.getByRole('form', { name: 'Review Due within 1 year', exact: true })
  await expect(nextReview.getByLabel('Your name', { exact: true })).toHaveValue('Alex Analyst')
  await page.getByRole('button', { name: 'Back to reports', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Figures', exact: true })).toHaveAttribute('aria-current', 'page')
})

for (const tone of ['light', 'dark']) test(`review queue, basis and saved comparison [${tone}]`, async ({ page }) => {
  const entry = { stem: 'atlas_2025', report_id: 'lib-atlas_2025', company: 'Atlas Copco', fiscal_year: 2025, sections: ['income_statement'], pages: 1, pdf_available: false, indexed: false }
  const previous = { ...entry, stem: 'atlas_2024', fiscal_year: 2024 }
  // The queue lists the unverified revenue row; the unconfirmed basis sits beside it (basis_issues) with a prefill and never queues.
  const suggested = { entity: 'Atlas Copco', consolidation: 'Group', period: '2025', currency: 'SEK', scale: 'Millions', source: 'Annual report', restatement: 'As reported' }
  let extraction: any = { ...entry, section: 'income_statement', currency: 'MSEK', fields: [{ key: 'revenue', label: 'Revenue', value: 120, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: { page: 1, quote: 'Revenue 120' }, confidence: 0, evidence: [] }], checks: [], warnings: [], issues: [{ kind: 'field', key: 'revenue', detail: 'Revenue: verify value, unit, period and source' }], basis_issues: [{ kind: 'basis', key: 'entity', detail: 'Confirm entity' }], basis_suggested: suggested, not_reported: [], ready: false }
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
      expect(body.values).toEqual({ ...suggested, entity: 'Atlas Copco AB', source: 'Page 1, group statement' })
      extraction = { ...extraction, basis: { values: body.values, reviewer: body.reviewer, note: body.note, at: '2026-09-18T12:00:00Z' }, basis_issues: [] }
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
  await expect(page.getByText('Wallenberg collection · 1 statement · 1 outstanding check', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Review statement' }).click()
  await expect(page.getByText('1 need a human', { exact: true })).toBeVisible()
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: /Checks & review/ }).click()
  const basis = page.locator('#basis-review')
  await expect(basis).toContainText('Basis not confirmed')
  await basis.locator('summary').click()
  await expect(basis).toHaveAttribute('open', '')
  // prefilled from the extraction: only the entity's legal form and the source reference are the analyst's to add
  await expect(basis.getByLabel('Reporting entity', { exact: true })).toHaveValue('Atlas Copco')
  await expect(basis.getByLabel('Scale', { exact: true })).toHaveValue('Millions')
  await basis.getByLabel('Reporting entity', { exact: true }).fill('Atlas Copco AB')
  await basis.getByLabel('Source references').fill('Page 1, group statement')
  await basis.getByLabel('Basis reviewer').fill('Sebastian')
  await basis.getByLabel('Basis review note').fill('Checked the statement heading and units')
  await basis.getByRole('button', { name: 'Save basis review' }).click()
  await expect(basis).toContainText('Basis confirmed')
  await expect(page.getByText('1 need a human', { exact: true })).toBeVisible() // a confirmed basis resolves no figure
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Prior year', exact: true }).click()
  const comparison = page.getByRole('region', { name: 'Prior-year comparison' })
  await expect(comparison).toContainText('2024 → 2025')
  await expect(comparison.getByRole('cell', { name: '20', exact: true })).toHaveCount(2)
  await comparison.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `e2e/test-results/workbench-${tone}.png` })
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Export CSV' })).toHaveAttribute('href', /section=income_statement&previous_stem=atlas_2024/)
  await page.getByRole('button', { name: 'Back to reports' }).click()
  // basis confirmation never touched `issues`, so the revenue field issue is still outstanding on remount
  await expect(page.getByText('Wallenberg collection · 1 statement · 1 outstanding check', { exact: true })).toBeVisible()
  expect(downloads).toBe(0)
  expect(errors).toEqual([])
})
