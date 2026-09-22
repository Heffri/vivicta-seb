import { expect, test } from '@playwright/test'

test('human correction carries a checked citation and component evidence', async ({ page }) => {
  const entry = { stem: 'review_test', report_id: 'lib-review_test', company: 'Review Test', fiscal_year: 2025, pages: 2, sections: ['income_statement'], indexed: false, pdf_available: false }
  const quotes: Record<number, string> = { 1: 'Revenue 125', 2: 'Revenue 120' }
  let extraction: any = { ...entry, section: 'income_statement', currency: 'MSEK', fields: [{ key: 'revenue', label: 'Revenue', value: null, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: null, evidence: [], confidence: 0 }], checks: [{ name: 'net_profit_arith', passed: true, detail: 'old check' }], warnings: [] }
  let fail = false
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/review')) {
      if (fail) return route.fulfill({ status: 409, json: { detail: 'This figure changed. Reopen the report before reviewing it.' } })
      const body = route.request().postDataJSON()
      expect(body.expected).toEqual(extraction.fields[0])
      const previous = structuredClone(extraction.fields[0])
      const cited = body.components?.[0] ?? (body.source_page ? { page: body.source_page, quote: body.source_quote } : null)
      if (cited && quotes[cited.page] !== cited.quote) return route.fulfill({ status: 400, json: { detail: `Citation is not on page ${cited.page}` } })
      if (body.components?.some((component: any) => quotes[component.page] !== component.quote)) return route.fulfill({ status: 400, json: { detail: 'Citation is not on its page' } })
      const review = { decision: body.decision, reviewer: body.reviewer, note: body.note, at: new Date().toISOString(), ...(cited ? { source_verified: true } : {}) }
      const components = body.components
      extraction = { ...extraction, fields: [{ ...previous, ...(body.decision === 'corrected' ? { value: components ? components.reduce((sum: number, component: any) => sum + component.value, 0) : body.value, unit: body.unit, period: body.period, evidence: components ? ['human_reviewed', 'components_sum'] : ['human_reviewed'] } : {}), ...(cited ? { source: { page: cited.page, quote: cited.quote } } : {}), ...(components ? { components } : {}), human_review: review, review_history: [...(previous.review_history ?? []), { ...review, previous }] }], checks: extraction.checks.map((c: any) => ({ ...c, stale: body.decision === 'corrected' })) }
      return route.fulfill({ json: extraction })
    }
    const match = path.match(/\/pages\/(\d+)$/)
    return route.fulfill({ json: path === '/api/kb' ? [entry] : path === '/api/config' ? { provider: 'codex', model: 'test' } : match ? { text: quotes[Number(match[1])], page: Number(match[1]) } : path === '/api/kb/review_test/income_statement' ? extraction : [] })
  })
  await page.goto('/')
  const open = async () => { await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click(); await page.getByRole('button', { name: 'Open', exact: true }).click(); await page.getByRole('cell', { name: 'Revenue', exact: true }).click(); await page.locator('summary').filter({ hasText: /^Review Revenue$/ }).click() }
  await open()
  const form = page.getByRole('form', { name: 'Review Revenue' })
  await form.getByLabel('Your name').fill('Sebastian')
  await form.getByLabel('Decision').selectOption('corrected')
  await form.getByLabel('Value', { exact: true }).fill('120')
  await form.getByLabel('Citation page').fill('2')
  await form.getByLabel('Citation quote').fill('Revenue 120')
  await form.getByLabel('Review note').fill('Filled the missing value from page 2')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(page.getByText('Human corrected', { exact: true }).last()).toBeVisible()
  await expect(page.getByRole('cell', { name: '120', exact: true })).toBeVisible()
  await expect(page.getByText(/Reviewed source · p\.2/)).toBeVisible()
  await page.reload(); await open()
  await expect(page.getByText('Human corrected', { exact: true }).last()).toBeVisible()
  await expect(page.locator('#report-source')).toContainText('Revenue 120')
  await form.getByLabel('Decision').selectOption('corrected')
  await page.getByRole('button', { name: 'Use this line as citation' }).click()
  await expect(form.getByLabel('Citation page')).toHaveValue('2')
  await form.getByLabel('Value', { exact: true }).fill('125')
  await form.getByLabel('Citation page').fill('1')
  await form.getByLabel('Citation quote').fill('Revenue 125')
  await form.getByLabel('Review note').fill('Moved the evidence to the corrected page')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(page.getByText(/Reviewed source · p\.1/)).toBeVisible()
  await form.getByLabel('Decision').selectOption('corrected')
  await form.getByLabel('Sum printed components instead of entering one total').check()
  await form.getByRole('button', { name: 'Add component' }).click()
  await form.getByRole('button', { name: 'Add component' }).click()
  await form.getByLabel('Component 1 value').fill('50')
  await form.getByLabel('Component 1 page').fill('1')
  await form.getByLabel('Component 1 quote').fill('Revenue 125')
  await form.getByLabel('Component 2 value').fill('75')
  await form.getByLabel('Component 2 page').fill('2')
  await form.getByLabel('Component 2 quote').fill('Revenue 120')
  await expect(form.getByText('Component sum: 125', { exact: true })).toBeVisible()
  await form.getByLabel('Review note').fill('Summed two printed components')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(page.getByText(/2 components/)).toBeVisible()
  await form.getByLabel('Decision').selectOption('corrected')
  await form.getByLabel('Citation page').fill('1')
  await form.getByLabel('Citation quote').fill('Not printed')
  await form.getByLabel('Review note').fill('This must fail')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(form.getByRole('alert')).toContainText('Citation is not on page 1')
  fail = true
  await form.getByLabel('Decision').selectOption('unresolved')
  await form.getByLabel('Review note').fill('Needs another look')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(form.getByRole('alert')).toContainText('This figure changed')
  await expect(page.getByText('Human corrected', { exact: true }).last()).toBeVisible()
})
