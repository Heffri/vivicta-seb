import { expect, test } from '@playwright/test'

for (const sample of [
  { company: 'Atlas Antibodies AB', code: 'report_unavailable', status: 404, stage: 'Report not available', detail: 'No verified public annual-report PDF was found for Atlas Antibodies AB 2025.', reason: 'issuer mismatch: the PDF is the owner’s report', next: /Upload this company’s annual-report PDF/ },
  { company: 'Nasdaq', code: 'download_failed', status: 502, stage: 'Download could not complete', detail: 'Some source sites failed or blocked access.', reason: 'HTTP Error 403: Forbidden', next: /A source site could not be reached/ },
]) {
  test(`Extract explains ${sample.code} without treating it as an extraction failure`, async ({ page }) => {
    const requests: string[] = []
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      requests.push(path)
      if (path === '/api/reports/fetch') return route.fulfill({ status: sample.status, json: {
        code: sample.code, detail: sample.detail, tried: ['https://example.com/report.pdf'],
        attempts: [{ url: 'https://example.com/report.pdf', reason: sample.reason, kind: sample.code === 'download_failed' ? 'download' : 'rejected' }],
      } })
      await route.fulfill({ json: path === '/api/companies' ? [{ name: sample.company, ticker: '', sector: null, cached_years: [] }]
        : path === '/api/config' ? { provider: 'codex', model: 'test' }
        : path === '/api/schemas' ? [{ name: 'debt_maturity', title: 'Debt maturity structure' }] : [] })
    })
    await page.goto('/')
    await expect(page.getByText(/Includes private companies/)).toBeVisible()
    await page.getByRole('button', { name: sample.company, exact: true }).click()
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()
    const row = page.getByRole('list', { name: 'Batch progress' })
    await expect(row.getByText(sample.stage, { exact: true })).toBeVisible()
    await expect(row.getByText(sample.next)).toBeVisible()
    await row.getByText('Source checks (1)').click()
    await expect(row.getByText(sample.reason)).toBeVisible()
    await expect(row.getByRole('button', { name: 'Open Settings' })).toHaveCount(0)
    expect(requests.some(path => path.endsWith('/extract'))).toBe(false)
    await row.getByRole('button', { name: 'Retry this one' }).click()
    await expect.poll(() => requests.filter(path => path === '/api/reports/fetch').length).toBe(2)
  })
}
