import { expect, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// Two runtime-generated PDFs (different page counts so their bytes/sizes differ, same as v021's
// evidence did with its PyMuPDF-built fixtures) — no atlas dependency, no fixture binaries to commit.
for (const tone of TONES) {
  test(`extract: two uploaded PDFs -> Compare with two columns [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await page.setInputFiles('#pdf', [
      { name: 'sample-report-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
      { name: 'sample-report-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
    ])
    await expect(page.getByText('2 files selected')).toBeVisible()
    await expect(page.getByText('sample-report-a.pdf')).toBeVisible()
    await expect(page.getByText('sample-report-b.pdf')).toBeVisible()

    const extractButton = page.getByRole('main').getByRole('button', { name: /^Extract/ })
    await expect(extractButton).toHaveText('Extract 2 reports')
    await extractButton.click()

    // v171: a finished batch never forces a tab switch (BatchProgress's own "View results" does);
    // it also appears as soon as the first of the two is done, so wait for the count to say both
    // finished before clicking through, or this can land on the single Results view instead.
    const viewResults = page.getByRole('main').getByRole('button', { name: 'View results (2)' })
    await expect(viewResults).toBeVisible({ timeout: 20000 })
    await viewResults.click()
    await expect(page.getByRole('heading', { name: 'Comparison' })).toBeVisible()
    await expect(page.getByText('2 of 2 reports extracted')).toBeVisible()
    await expect(page.locator('table thead th')).toHaveCount(3) // Field + 2 report columns

    // v174: the "Upcoming maturities" section is collection-wide (data/kb), independent of the two
    // uploaded fixture reports above it. Wallenberg has only one saved debt_maturity extraction, so
    // switch to All for a pool wide enough to prove the threshold filter actually removes rows.
    await expect(page.getByRole('heading', { name: 'Upcoming maturities', exact: false })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText(/comparable$|comparable ·/)).toBeVisible()
    await page.getByRole('group', { name: 'Collection' }).getByRole('button', { name: 'All', exact: true }).click()
    const wallRows = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Share' }) }).locator('tbody tr')
    await expect.poll(async () => wallRows.count(), { timeout: 20000 }).toBeGreaterThan(5)
    const beforeFilter = await wallRows.count()

    const threshold = page.getByLabel('Minimum share due within 1 year, percent')
    await threshold.fill('90')
    await expect.poll(async () => wallRows.count(), { timeout: 20000 }).toBeLessThan(beforeFilter)

    expect(errors).toEqual([])
  })
}

// Extraction runs three at a time (the backend's hosted-model semaphore is 3): with five queued files the
// fourth /extract must wait for one of the first three to finish, and results keep the queue order.
test('extract: five uploads run three at a time', async ({ page }) => {
  let inFlight = 0, peak = 0
  const started: string[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports' && route.request().method() === 'POST') {
      const name = /filename="([^"]+)"/.exec(route.request().postDataBuffer()?.toString('latin1') ?? '')?.[1] ?? 'unknown.pdf'
      return route.fulfill({ json: { report_id: `up-${name}`, filename: name, pages: 2, company: name.replace('.pdf', ''), fiscal_year: 2025 } })
    }
    if (path.endsWith('/extract')) {
      const id = path.split('/')[3]
      started.push(id); inFlight++; peak = Math.max(peak, inFlight)
      await new Promise(r => setTimeout(r, 400))
      inFlight--
      return route.fulfill({ json: { report_id: id, company: id.replace('up-', '').replace('.pdf', ''), fiscal_year: 2025, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    }
    return route.fulfill({ json: path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : path === '/api/config' ? { provider: 'codex', model: 'test' } : [] })
  })
  await page.goto('/')
  await page.setInputFiles('#pdf', [1, 2, 3, 4, 5].map(i => ({ name: `report-${i}.pdf`, mimeType: 'application/pdf', buffer: makePdf(i) })))
  await page.getByRole('main').getByRole('button', { name: 'Extract 5 reports', exact: true }).click()
  await expect.poll(() => started.length).toBe(3) // the first three start together…
  expect(inFlight).toBe(3)
  await expect.poll(() => started.length).toBe(5) // …the rest only as slots free up
  await expect(page.getByText('5 of 5 reports extracted')).toBeVisible()
  expect(peak).toBe(3)
  await expect(page.locator('table thead th')).toHaveCount(6) // Field + 5 report columns, queue order
  await expect(page.locator('table thead th').nth(1)).toHaveText(/report-1/)
  await expect(page.locator('table thead th').nth(5)).toHaveText(/report-5/)
})
