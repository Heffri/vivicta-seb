import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { railTab } from '../support/nav'
import { trackPageErrors } from '../support/page-errors'
import { gotoWithTone, TONES } from '../support/tone'

// Fully mocked: proves the KB page's building-poll stops on its own instead of re-fetching
// the whole KB every 2 s for as long as any row says building. Two building
// listings, then a ready one — the third scheduled poll must never fire.
const kbEntry = (status: string) => ({
  stem: 'acme_2025', report_id: 'lib-acme_2025', company: 'Acme', fiscal_year: 2025, pages: 3,
  sections: ['income_statement'], indexed: status === 'ready', status,
  reason: status === 'building' ? 'Report update in progress' : 'No embeddings built',
  embed_model: status === 'ready' ? 'bge-m3' : null, dimensions: status === 'ready' ? 1024 : null,
  chunks: status === 'ready' ? 12 : 0, page_chunks: status === 'ready' ? 10 : 0, fact_chunks: status === 'ready' ? 2 : 0,
  built_at: status === 'ready' ? '2026-09-22T00:00:00Z' : null, sector: null,
  pdf_available: false, text_available: true, figures_available: true,
})

test('kb: building poll backs off, then stops for good once a listing has no building row', async ({ page }) => {
  const errors = trackPageErrors(page)
  const kbCalls: number[] = []
  let kbResponses = 0
  await page.route('**/api/**', async (route) => {
    const reqPath = new URL(route.request().url()).pathname
    if (reqPath === '/api/kb') {
      kbCalls.push(Date.now())
      kbResponses += 1
      return route.fulfill({ json: [kbEntry(kbResponses <= 3 ? 'building' : 'ready')] })
    }
    if (reqPath === '/api/config') {
      return route.fulfill({ json: { provider: 'codex', model: 'test', embed_model: 'bge-m3', base_url: null, llm: true, retrieval: 'hybrid' } })
    }
    if (reqPath === '/api/schemas') {
      return route.fulfill({ json: [{ name: 'income_statement', title: 'Income statement' }] })
    }
    return route.fulfill({ json: [] })
  })

  await page.goto('/')
  await railTab(page, 'Knowledge base').click()
  await page.getByRole('button', { name: 'Search index', exact: true }).click()
  const row = page.locator('tbody tr').first()
  await expect(row).toBeVisible()
  await expect(row.getByText('building', { exact: true })).toBeVisible()

  // first poll (2 s) still building, second poll lands ready — dev StrictMode's double mount
  // consumes two of the three building responses either way
  await expect(row.getByText('ready', { exact: true })).toBeVisible({ timeout: 20000 })
  const callsAtReady = kbCalls.length
  expect(callsAtReady).toBeGreaterThanOrEqual(4)

  // and then silence: no further /api/kb request may fire now that nothing says building
  await page.waitForTimeout(3000)
  expect(kbCalls.length).toBe(callsAtReady)
  expect(errors).toEqual([])
})

// The real-library smoke case requires the Atlas saved extraction.
const ATLAS_EXTRACTION = path.resolve(import.meta.dirname, '../../../data/kb/atlas_copco_2025/extractions/income_statement.json')
const REASON = 'Atlas Copco saved income statement is not present'

// Self-built fixtures, kept from the collection-scoping tests these replaced: asserting against
// the live data/kb company count is not stable, because it only ever grows as other tests and
// lanes save reports into it.
const savedEntry = (stem: string, company: string, sections: string[] = ['income_statement']) => ({
  stem, report_id: `lib-${stem}`, company, fiscal_year: 2025, pages: 4, sections,
  indexed: false, status: 'missing', reason: 'No embeddings built', embed_model: null, dimensions: null,
  chunks: 0, page_chunks: 0, fact_chunks: 0, built_at: null, sector: null,
  pdf_available: false, text_available: true, figures_available: true,
})
const SAVED_REPORTS = [
  savedEntry('alpha_2025', 'Alpha Industri'), savedEntry('beta_2025', 'Beta Verkstad'),
  savedEntry('gamma_2025', 'Gamma Kraft'), savedEntry('delta_2025', 'Delta Logistik'), savedEntry('epsilon_2025', 'Epsilon Bygg'),
]

async function mockKb(page: Page) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    // Deliberately ignores every query parameter: nothing narrows this list any more.
    if (url.pathname === '/api/kb') return route.fulfill({ json: SAVED_REPORTS })
    if (url.pathname === '/api/config') {
      return route.fulfill({ json: { provider: 'codex', model: 'test', embed_model: 'bge-m3', base_url: null, llm: true, retrieval: 'hybrid' } })
    }
    if (url.pathname === '/api/schemas') {
      return route.fulfill({ json: [{ name: 'income_statement', title: 'Income statement' }] })
    }
    return route.fulfill({ json: [] })
  })
}

for (const tone of TONES) {
  test(`kb: filter "atlas" -> Open -> Results [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ATLAS_EXTRACTION), REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    await page.getByLabel('Filter reports').fill('atlas')
    const rows = page.locator('tbody tr')
    // The real library is ~212 entries here and the list renders "Loading…" until /api/kb answers;
    // the same 20 s allowance the Open assertion below uses, not a weaker assertion.
    await expect(rows).toHaveCount(1, { timeout: 20000 })
    await expect(rows.first()).toContainText('Atlas Copco')

    await rows.first().getByRole('button', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { name: 'Atlas Copco', exact: false })).toBeVisible({ timeout: 20000 })
    await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()

    expect(errors).toEqual([])
  })

  // What the collection-switch case used to guard, inverted: there is no switch, so the whole
  // list must be there on load, still be there after a reload, and no request may narrow it.
  test(`kb: every saved report is listed, and a reload still lists them [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    const scoped: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.searchParams.has('collection_name') || url.searchParams.has('collection')) scoped.push(url.pathname)
    })
    await mockKb(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(SAVED_REPORTS.length)
    for (const entry of SAVED_REPORTS) await expect(rows.filter({ hasText: entry.company })).toHaveCount(1)

    // No preference survives a reload because there is none to save. The reload lands on the
    // default Extract tab, so go back to Knowledge base before reading the list.
    await page.reload()
    await railTab(page, 'Knowledge base').click()
    await expect(rows).toHaveCount(SAVED_REPORTS.length, { timeout: 20000 })
    await expect(page.getByRole('group', { name: 'Collection' })).toHaveCount(0)

    expect(scoped).toEqual([])
    expect(errors).toEqual([])
  })

  test(`kb: a saved extraction without its PDF can still open [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    const noPdfRow = page.locator('tbody tr', { has: page.getByText('no PDF', { exact: true }) }).first()
    await expect(noPdfRow).toBeVisible({ timeout: 20000 })
    await expect(noPdfRow.getByRole('button', { name: 'Open' })).toBeEnabled()
    await noPdfRow.getByRole('button', { name: 'Open' }).click()
    await expect(page.getByText('Saved page text. The original PDF is not available on this device.')).toBeVisible()

    expect(errors).toEqual([])
  })

  // The KB page's "Maturity wall" card — one bar per company grouped by sector, honest about
  // buckets that do not reconcile. Self-built: one fictional debt_maturity report is enough to
  // prove the grouping/labelling logic without depending on which real companies currently have a
  // saved debt_maturity extraction in data/kb.
  test(`kb: maturity wall card groups every saved debt report by sector [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    const wallEntry = savedEntry('fjord_metals_2025', 'Fjord Metals', ['debt_maturity'])
    const wallRow = {
      stem: wallEntry.stem, report_id: wallEntry.report_id, company: wallEntry.company, fiscal_year: 2025,
      total: { value: 32703, unit: 'MSEK' }, due_within_1_year: { value: 3538, unit: 'MSEK' }, share: 0.1082,
      basis_confirmed: false, consolidation: null, debt_basis: null, leases: null, review_status: 'unreviewed',
      comparable: false, reason: 'Basis not confirmed: entity level, period, debt basis and lease scope must be reviewed first.',
      sector: 'Materials', complete: false,
    }
    const extraction = { report_id: wallEntry.report_id, company: wallEntry.company, fiscal_year: 2025, currency: 'MSEK', section: 'debt_maturity', fields: [], checks: [], warnings: [] }
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/kb') return route.fulfill({ json: [wallEntry] })
      if (url.pathname === '/api/kb/maturity-wall') {
        return route.fulfill({ json: { rows: [wallRow], coverage: { total: 1, comparable: 0, missing_total: 0, missing_w1y: 0, basis_unconfirmed: 1 }, sectors: [{ sector: 'Materials', companies: 1, complete: 0, median_share: null, min: null, max: null }] } })
      }
      if (url.pathname === `/api/kb/${wallEntry.stem}/debt_maturity`) return route.fulfill({ json: extraction })
      if (url.pathname === '/api/config') return route.fulfill({ json: { provider: 'codex', model: 'test', embed_model: 'bge-m3', base_url: null, llm: true, retrieval: 'hybrid' } })
      if (url.pathname === '/api/schemas') return route.fulfill({ json: [{ name: 'income_statement', title: 'Income statement' }, { name: 'debt_maturity', title: 'Debt maturity' }] })
      return route.fulfill({ json: [] })
    })
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Maturity wall' })).toBeVisible()

    await page.getByRole('button', { name: 'Maturity wall' }).click()
    const card = page.getByRole('region', { name: 'Maturity wall' })
    await expect(card).toBeVisible()
    await expect(card.getByText(/share of debt due within 1 year · 0 of 1 companies with complete buckets/)).toBeVisible()

    const sectors = card.getByRole('heading', { name: /^Sector / })
    await expect(sectors).toHaveCount(1)
    await expect(sectors.first()).toContainText('Materials')
    // svg text, not getByText: the row's hidden <title> tooltip carries the same words
    await expect(card.locator('svg text').filter({ hasText: 'buckets incomplete' }).first()).toBeVisible()

    // A company row opens that company through the KB view's existing Open action.
    await card.getByRole('button', { name: /^Fjord Metals/ }).click()
    await expect(page.getByRole('heading', { name: 'Fjord Metals', exact: false })).toBeVisible()

    expect(errors).toEqual([])
  })
}
