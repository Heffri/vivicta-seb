import { expect, test } from '@playwright/test'

// v194: the search/fetch progress trail — jobs.py's job table, GET /api/jobs/{job_id} polled every
// 1.5 s by useReportSearch — fixes the P0 this ticket is about: a company search used to look
// identically "stuck" whether it was working or dead, and switching to another tab and back silently
// dropped the reply. These three specs mock GET /api/jobs/{job_id} directly (something ai-discovery.spec.ts
// never needed to) to prove the trace actually appears, survives a tab switch, and offers a working
// Retry on failure.

const intel = { legal_name: 'Intel Corporation', ticker: 'INTC', exchange: 'NASDAQ', country: 'US', org_number_or_lei: null, fiscal_year_end: 'Dec', document_title: null, document_type: 'annual report', url: null, reason: 'US chipmaker', saved: false, stem: null }
const card = (page: any, name: string) => page.locator('[data-slot="card"]', { hasText: name })
const jobIdOf = (url: string) => new URL(url).pathname.slice('/api/jobs/'.length)
const baseRoutes = (path: string) =>
  path === '/api/config' ? { provider: 'codex', model: 'test' } : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }] : []

test('the trace panel shows the search actually doing something while it runs', async ({ page }) => {
  const discovered: any[] = []
  let jobPolls = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      discovered.push(route.request().postDataJSON())
      await new Promise((r) => setTimeout(r, 3500)) // long enough for two 1.5 s poll ticks to land first
      return route.fulfill({ json: { candidates: [intel], note: null } })
    }
    if (path.startsWith('/api/jobs/')) {
      jobPolls++
      const events = [{ t: Date.now() / 1000, stage: 'directory', text: 'checking saved reports for intel (2025)' }]
      if (jobPolls > 1) events.push({ t: Date.now() / 1000, stage: 'model_search', text: 'model searched: intel annual report 2025' })
      return route.fulfill({
        json: { job_id: jobIdOf(route.request().url()), stage: jobPolls > 1 ? 'model_search' : 'directory', started: Date.now() / 1000, updated: Date.now() / 1000, done: false, error: null, events },
      })
    }
    return route.fulfill({ json: baseRoutes(path) })
  })
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('intel')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).press('Enter')
  await expect(page.getByText('Resolving which company you mean', { exact: true })).toBeVisible()
  await expect(page.getByText('checking saved reports for intel (2025)', { exact: true })).toBeVisible()
  // a second poll tick landed with a new event while the request was still in flight — proves the
  // trail is live, not a one-shot snapshot taken once and never updated
  await expect(page.getByText('model searched: intel annual report 2025', { exact: true })).toBeVisible()
  await expect.poll(() => discovered.length).toBe(1)
  await expect(card(page, 'Intel Corporation')).toBeVisible() // and the search itself still completes normally
})

test('switching to Settings and back does not interrupt a running search', async ({ page }) => {
  const discovered: any[] = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      discovered.push(route.request().postDataJSON())
      await new Promise((r) => setTimeout(r, 4000)) // outlives the tab-switch-and-back below
      return route.fulfill({ json: { candidates: [intel], note: null } })
    }
    if (path.startsWith('/api/jobs/')) {
      return route.fulfill({
        json: {
          job_id: jobIdOf(route.request().url()), stage: 'model_search', started: Date.now() / 1000, updated: Date.now() / 1000, done: false, error: null,
          events: [{ t: Date.now() / 1000, stage: 'model_search', text: 'asking the connected model to search the web' }],
        },
      })
    }
    return route.fulfill({ json: baseRoutes(path) })
  })
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('intel')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).press('Enter')
  await expect(page.getByText('asking the connected model to search the web', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Settings', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Settings', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: 'Extract', exact: true }).click()
  // still the same search, still visibly running — not reset to an empty box, not re-requested
  await expect(page.getByRole('searchbox', { name: 'Search companies', exact: true })).toHaveValue('intel')
  await expect(page.getByText('asking the connected model to search the web', { exact: true })).toBeVisible()
  await expect.poll(() => discovered.length).toBe(1) // exactly one request the whole time
  await expect(card(page, 'Intel Corporation')).toBeVisible() // and it still completes once the mocked call resolves
})

test('a failed search keeps its trail, shows why, and Retry recovers', async ({ page }) => {
  const discovered: any[] = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') {
      discovered.push(route.request().postDataJSON())
      if (discovered.length === 1) return route.fulfill({ status: 502, json: { detail: 'search backend unavailable' } })
      return route.fulfill({ json: { candidates: [intel], note: null } })
    }
    if (path.startsWith('/api/jobs/')) {
      return route.fulfill({
        json: {
          job_id: jobIdOf(route.request().url()), stage: 'directory', started: Date.now() / 1000, updated: Date.now() / 1000, done: false, error: null,
          events: [{ t: Date.now() / 1000, stage: 'directory', text: 'checking saved reports for intel (2025)' }],
        },
      })
    }
    return route.fulfill({ json: baseRoutes(path) })
  })
  await page.goto('/')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('intel')
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).press('Enter')
  await expect(page.getByText('search backend unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('checking saved reports for intel (2025)', { exact: true })).toBeVisible() // the trail up to the failure stays, not cleared
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect.poll(() => discovered.length).toBe(2)
  await expect(card(page, 'Intel Corporation')).toBeVisible() // Retry actually re-ran the same query and recovered
})
