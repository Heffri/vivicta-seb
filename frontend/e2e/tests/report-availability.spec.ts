import { expect, test } from '@playwright/test'

for (const outcome of ['success', 'cancelled', 'wrong-company']) {
  test(`Desktop report download ${outcome} preserves the batch and only extracts verified PDFs`, async ({ page }) => {
    const company = 'The Grand Group AB'
    const report = { report_id: 'lib-grand-browser', company, fiscal_year: 2025, pages: 12, stem: 'grand-browser', filename: 'grand.pdf' }
    await page.addInitScript(({ report, outcome }) => {
      Object.defineProperty(window, 'arp', { value: {
        downloadReport: async (listing: { company: string; fiscal_year: number }) => {
          if (listing.company !== report.company || listing.fiscal_year !== report.fiscal_year) throw new Error('Wrong selection sent to desktop')
          if (outcome === 'success') return { ok: true, report }
          return outcome === 'cancelled' ? { ok: false, cancelled: true } : { ok: false, error: 'issuer mismatch' }
        },
      } })
    }, { report, outcome })
    let extracts = 0
    let fetches = 0
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/reports/fetch') {
        fetches++
        return route.fulfill({ status: 409, json: { code: 'report_listed', detail: 'Report listed online.', listings: [
          { company, fiscal_year: 2025, title: 'Annual report 2025', url: 'https://registry.example/company/123', evidence: 'Annual report 2025 Download', access: 'manual_download' },
        ] } })
      }
      if (path.endsWith('/extract')) {
        extracts++
        expect(path).toBe('/api/reports/lib-grand-browser/extract')
        expect(route.request().postDataJSON().section).toBe('debt_maturity')
        return route.fulfill({ json: { ...report, section: 'debt_maturity', fields: [], checks: [], warnings: [] } })
      }
      return route.fulfill({ json: path === '/api/companies' ? [{ name: company, ticker: '', sector: null, cached_years: [] }]
        : path === '/api/config' ? { provider: 'codex', model: 'test' }
        : path === '/api/schemas' ? [{ name: 'debt_maturity', title: 'Debt maturity structure' }] : [] })
    })
    await page.goto('/')
    await page.getByRole('button', { name: company, exact: true }).click()
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()
    const row = page.getByRole('list', { name: 'Batch progress' })
    const download = row.getByRole('button', { name: 'Download and continue — Annual report 2025' })
    await expect(download).toBeVisible()
    await download.click()
    if (outcome === 'success') {
      await expect(row.getByText('Done', { exact: true })).toBeVisible()
      await expect(row.getByRole('list', { name: 'Report listings' })).toHaveCount(0)
      expect(extracts).toBe(1)
    } else {
      await expect(download).toBeEnabled()
      if (outcome === 'wrong-company') await expect(row.getByRole('alert')).toHaveText('issuer mismatch')
      else await expect(row.getByRole('alert')).toHaveCount(0)
      expect(extracts).toBe(0)
    }
    expect(fetches).toBe(1)
  })
}

for (const sample of [
  { company: 'Atlas Antibodies AB', code: 'report_unavailable', status: 404, stage: 'Report not found automatically', detail: 'No verified public annual-report PDF was found for Atlas Antibodies AB 2025.', reason: 'issuer mismatch: the PDF is the owner’s report', next: /Upload this company’s annual-report PDF/ },
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

for (const company of ['The Grand Group AB', 'Example Manufacturing Ltd']) {
  test(`Registry listing offers a manual source for ${company} and clears stale links on retry`, async ({ page }) => {
    let fetches = 0
    let extracts = 0
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/extract')) extracts++
      if (path === '/api/reports/fetch') {
        fetches++
        return route.fulfill({ status: fetches === 1 ? 409 : 404, json: fetches === 1 ? {
          code: 'report_listed', detail: `An annual report for ${company} 2025 is listed online, but its PDF could not be downloaded and verified automatically.`,
          listings: [{ company, fiscal_year: 2025, title: 'Annual report 2025', url: 'https://registry.example/company/123', evidence: 'Annual report 2025 Download report', access: 'manual_download' }],
        } : { code: 'report_unavailable', detail: 'Automatic lookup did not find a verified report.' } })
      }
      await route.fulfill({ json: path === '/api/companies' ? [{ name: company, ticker: '', sector: null, cached_years: [] }]
        : path === '/api/config' ? { provider: 'codex', model: 'test' }
        : path === '/api/schemas' ? [{ name: 'debt_maturity', title: 'Debt maturity structure' }] : [] })
    })
    await page.goto('/')
    await page.getByRole('button', { name: company, exact: true }).click()
    await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()
    const row = page.getByRole('list', { name: 'Batch progress' })
    await expect(row.getByText('Report listed — manual download needed', { exact: true })).toBeVisible()
    await expect(row.getByRole('link', { name: 'Open report listing — Annual report 2025' })).toHaveAttribute('href', 'https://registry.example/company/123')
    await expect(row.getByText(/then upload it above/)).toBeVisible()
    await expect(row.getByText(/Some companies do not publish/)).toHaveCount(0)
    await expect(row.getByRole('button', { name: 'Open Settings' })).toHaveCount(0)
    await row.getByRole('button', { name: 'Retry this one' }).click()
    await expect(row.getByText('Report not found automatically', { exact: true })).toBeVisible()
    await expect(row.getByRole('list', { name: 'Report listings' })).toHaveCount(0)
    expect(extracts).toBe(0)
  })
}
