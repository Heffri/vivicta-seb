import { expect, test } from '@playwright/test'

test('human confirmation, correction, reopening and failed save', async ({ page }) => {
  const entry = { stem: 'review_test', report_id: 'lib-review_test', company: 'Review Test', fiscal_year: 2025, pages: 1, sections: ['income_statement'], indexed: false, pdf_available: false }
  let extraction: any = { ...entry, section: 'income_statement', currency: 'MSEK', fields: [{ key: 'revenue', label: 'Revenue', value: 100, unit: 'MSEK', period: '2025', raw_label: 'Revenue', source: { page: 1, quote: 'Revenue 100' }, evidence: [], confidence: 0 }], checks: [{ name: 'net_profit_arith', passed: true, detail: 'old check' }], warnings: [] }
  let fail = false
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/review')) {
      if (fail) return route.fulfill({ status: 409, json: { detail: 'This figure changed. Reopen the report before reviewing it.' } })
      const body = route.request().postDataJSON()
      expect(body.expected).toEqual(extraction.fields[0])
      const previous = structuredClone(extraction.fields[0])
      const review = { decision: body.decision, reviewer: body.reviewer, note: body.note, at: new Date().toISOString() }
      extraction = { ...extraction, fields: [{ ...previous, ...(body.decision === 'corrected' ? { value: body.value, unit: body.unit, period: body.period } : {}), human_review: review, review_history: [...(previous.review_history ?? []), { ...review, previous }] }], checks: extraction.checks.map((c: any) => ({ ...c, stale: body.decision === 'corrected' })) }
      return route.fulfill({ json: extraction })
    }
    return route.fulfill({ json: path === '/api/kb' ? [entry] : path === '/api/config' ? { provider: 'codex', model: 'test' } : path.includes('/pages/') ? { text: 'Revenue 100', page: 1 } : path === '/api/kb/review_test/income_statement' ? extraction : [] })
  })
  await page.goto('/')
  const open = async () => { await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click(); await page.getByRole('button', { name: 'Open', exact: true }).click(); await page.locator('summary').filter({ hasText: /^Review Revenue$/ }).click() }
  await open()
  const form = page.getByRole('form', { name: 'Review Revenue' })
  await form.getByLabel('Your name').fill('Sebastian')
  await form.getByLabel('Review note').fill('Checked page 1 and the year column')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(page.locator('details').getByText('Human confirmed', { exact: true })).toBeVisible()
  await form.getByLabel('Decision').selectOption('corrected')
  await form.getByLabel('Value', { exact: true }).fill('120')
  await form.getByLabel('Review note').fill('Corrected using page 1')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(page.locator('details').getByText('Human corrected', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '120', exact: true })).toBeVisible()
  await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: /Checks & review/ }).click()
  await expect(page.getByText('Net profit: Needs recalculation', { exact: true })).toBeVisible()
  await page.reload(); await open()
  await expect(page.locator('details').getByText('Human corrected', { exact: true })).toBeVisible()
  await form.getByText('Review history (2)', { exact: true }).click()
  await expect(form).toContainText('Previous: 100 MSEK (2025)')
  fail = true
  await form.getByLabel('Decision').selectOption('unresolved')
  await form.getByLabel('Review note').fill('Needs another look')
  await form.getByRole('button', { name: 'Save review' }).click()
  await expect(form.getByRole('alert')).toContainText('This figure changed')
  await expect(page.locator('details').getByText('Human corrected', { exact: true })).toBeVisible()
})
