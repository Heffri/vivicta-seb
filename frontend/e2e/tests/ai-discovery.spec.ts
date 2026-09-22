import { expect, test } from '@playwright/test'

const intel = { legal_name: 'Intel Corporation', ticker: 'INTC', exchange: 'NASDAQ', country: 'US', org_number_or_lei: null, fiscal_year_end: 'Dec', document_title: 'Intel 2025 Annual Report on Form 10-K', document_type: '10-K', url: 'https://www.intc.com/2025-10k.pdf', reason: 'US chipmaker; the fragment "intel" resolves to it', saved: false, stem: null }
const altera = { ...intel, legal_name: 'Altera Corporation', ticker: null, exchange: null, country: 'US', document_title: null, document_type: 'annual report', url: null, reason: 'former Intel subsidiary', saved: true, stem: 'altera_2025' }
const card = (page: any, name: string) => page.locator('[data-slot="card"]', { hasText: name })

// A typed fragment resolves to concrete legal entities the user confirms; only the confirmed one is fetched
// (its PDF link tried first, download_pdf always true) and extracted.
test('AI discovery proposes companies to confirm before fetching', async ({ page }) => {
  const discovered: any[] = [], fetched: any[] = [], extracted: string[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      const body = route.request().postDataJSON(); discovered.push(body)
      return route.fulfill({ json: { candidates: body.hint ? [altera] : [intel, altera], note: null } })
    }
    if (path === '/api/reports/fetch') {
      fetched.push(route.request().postDataJSON())
      return route.fulfill({ json: { report_id: 'lib-intel_2025', company: 'Intel Corporation', fiscal_year: 2025, pages: 120 } })
    }
    if (path.endsWith('/extract')) {
      extracted.push(path)
      return route.fulfill({ json: { report_id: 'lib-intel_2025', company: 'Intel Corporation', fiscal_year: 2025, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    }
    // Every discover/fetch call carries a job_id; useReportSearch polls this once as soon
    // as the call settles (plus every 1.5 s while it's still running) — a generic "done" reply is all
    // this test needs, since it does not assert on the trace panel's own content.
    if (path.startsWith('/api/jobs/')) {
      return route.fulfill({ json: { job_id: path.slice('/api/jobs/'.length), stage: 'done', started: Date.now() / 1000, updated: Date.now() / 1000, done: true, error: null, events: [] } })
    }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : path === '/api/companies' ? [{ name: 'ABB', ticker: 'ABB', sector: 'Industrials', cached_years: [] }] : [] })
  })
  await page.goto('/')
  await expect(page.getByRole('checkbox', { name: /Allow PDF download/ })).toHaveCount(0) // no opt-in: the PDF is fetched whenever it is needed
  await page.getByRole('button', { name: /ABB ABB/ }).click()
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('intel')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).press('Enter')
  await expect.poll(() => discovered.length).toBe(1)
  expect(discovered[0]).toEqual({ company: 'intel', year: 2025, job_id: expect.any(String) })
  // Cards name the legal entity, never the fragment; identity fields are shown so the user can tell them apart.
  await expect(card(page, 'Intel Corporation').getByText('NASDAQ: INTC · US · FY ends Dec', { exact: true })).toBeVisible()
  await expect(card(page, 'Intel Corporation').getByText('Intel 2025 Annual Report on Form 10-K · 10-K', { exact: true })).toBeVisible()
  await expect(card(page, 'Altera Corporation').getByText('saved', { exact: true })).toBeVisible()
  expect(fetched).toEqual([]) // nothing downloads until a card is confirmed
  await card(page, 'Intel Corporation').getByRole('button', { name: 'Use this company', exact: true }).click()
  await expect.poll(() => extracted.length).toBe(1)
  // The confirmed legal name and its PDF link go to /fetch once; the unrelated directory pick stays out of this run.
  expect(fetched.map(request => [request.company, request.url, request.download_pdf])).toEqual([['Intel Corporation', intel.url, true]])
})

test('a deterministic saved report skips search until Search the web anyway is chosen', async ({ page }) => {
  const discovered: any[] = []
  const saved = { legal_name: 'Sandvik', ticker: 'SAND', exchange: null, country: null, org_number_or_lei: null, fiscal_year_end: null, document_title: null, document_type: 'annual report', url: 'https://example.test/sandvik-2025.pdf', reason: 'saved PDF in the report cache', saved: true, stem: 'sandvik_2025' }
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      const body = route.request().postDataJSON(); discovered.push(body)
      return route.fulfill({ json: body.force_web
        ? { candidates: [intel], note: null, source: 'web', skipped_web_search: false }
        : { candidates: [saved], note: null, source: 'saved', skipped_web_search: true } })
    }
    if (path.startsWith('/api/jobs/')) {
      return route.fulfill({ json: { job_id: path.slice('/api/jobs/'.length), stage: 'done', started: Date.now() / 1000, updated: Date.now() / 1000, done: true, error: null, events: [] } })
    }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' } : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : [] })
  })
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('sandvik')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).press('Enter')
  await expect(page.getByText('Saved report found — using it.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Search the web anyway', exact: true })).toBeVisible()
  await expect.poll(() => discovered.length).toBe(1)
  expect(discovered[0]).toEqual({ company: 'sandvik', year: 2025, job_id: expect.any(String) })
  await page.getByRole('button', { name: 'Search the web anyway', exact: true }).click()
  await expect.poll(() => discovered.length).toBe(2)
  expect(discovered[1]).toEqual({ company: 'sandvik', year: 2025, force_web: true, job_id: expect.any(String) })
  await expect(card(page, 'Intel Corporation')).toBeVisible()
})

test('"None of these" re-runs discovery with a hint', async ({ page }) => {
  const discovered: any[] = []
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      const body = route.request().postDataJSON(); discovered.push(body)
      return route.fulfill({ json: { candidates: body.hint ? [altera] : [intel], note: body.hint ? null : 'model search (codex) failed: timeout' } })
    }
    if (path.startsWith('/api/jobs/')) {
      return route.fulfill({ json: { job_id: path.slice('/api/jobs/'.length), stage: 'done', started: Date.now() / 1000, updated: Date.now() / 1000, done: true, error: null, events: [] } })
    }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' } : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : [] })
  })
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('intel')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(card(page, 'Intel Corporation')).toBeVisible()
  await expect(page.getByText('model search (codex) failed: timeout', { exact: true })).toBeVisible() // the backend note rides along
  await page.getByRole('button', { name: 'None of these', exact: true }).click()
  await page.getByRole('textbox', { name: 'Hint', exact: true }).fill('programmable logic, San Jose')
  await page.getByRole('button', { name: 'Search again', exact: true }).click()
  await expect.poll(() => discovered.length).toBe(2)
  expect(discovered[1]).toEqual({ company: 'intel', year: 2025, hint: 'programmable logic, San Jose', job_id: expect.any(String) })
  await expect(card(page, 'Altera Corporation')).toBeVisible()
  await expect(card(page, 'Intel Corporation')).toHaveCount(0)
})

test('Ask counts actual text, figures and PDFs, excluding empty entries from retrieval', async ({ page }) => {
  const reports = [
    { stem: 'one', company: 'One', text_available: true, figures_available: true, pdf_available: false, sections: ['income_statement'] },
    { stem: 'two', company: 'Two', text_available: true, figures_available: false, pdf_available: true, sections: ['debt_maturity'] },
    { stem: 'empty', company: 'Empty', text_available: false, figures_available: false, pdf_available: false, sections: [] },
  ]
  const asked: any[] = []
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/ask') { asked.push(route.request().postDataJSON()); return route.fulfill({ json: { answer: 'No matching evidence.', citations: [], warnings: [], model: 'test' } }) }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' } : path === '/api/kb' ? reports : [] })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await page.getByRole('button', { name: /Available reports/ }).click()
  await expect(page.getByText('2 reports with saved text · 1 with extracted figures · 1 PDFs downloaded', { exact: true })).toBeVisible()
  await expect(page.getByText(/1 catalog entries have no readable page text/)).toBeVisible()
  await page.getByRole('button', { name: 'Conversation', exact: true }).click()
  await page.getByRole('combobox', { name: 'Question', exact: true }).fill('Summarise revenue')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect.poll(() => asked.length).toBe(1)
  expect(asked[0].report_stems).toEqual(['one', 'two'])
})
