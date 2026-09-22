import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
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
// The maturity wall card needs a saved debt_maturity extraction in the default collection.
const ERICSSON_DEBT = path.resolve(import.meta.dirname, '../../../data/kb/ericsson_2025/extractions/debt_maturity.json')
const WALL_REASON = 'Ericsson saved debt maturity extraction is not present'

for (const tone of TONES) {
  test(`kb: filter "atlas" -> Open -> Results [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ATLAS_EXTRACTION), REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    await page.getByLabel('Filter reports').fill('atlas')
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Atlas Copco')

    await rows.first().getByRole('button', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { name: 'Atlas Copco', exact: false })).toBeVisible({ timeout: 20000 })
    await page.getByRole('navigation', { name: 'Report workspace' }).getByRole('button', { name: 'Export', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Export JSON' })).toBeVisible()

    expect(errors).toEqual([])
  })

  test(`kb: every saved report is listed, and a reload still lists them [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()
    // The whole of data/kb, never a subset — the count keeps growing as other tests upload, so
    // this is a floor, not an exact number.
    const rows = page.locator('tbody tr')
    await expect.poll(async () => rows.count(), { timeout: 20000 }).toBeGreaterThanOrEqual(190)

    // Nothing is persisted that could narrow the list on the next visit; the reload lands on the
    // default Extract tab, so go back to Knowledge base before counting again.
    await page.reload()
    await railTab(page, 'Knowledge base').click()
    await expect.poll(async () => rows.count(), { timeout: 20000 }).toBeGreaterThanOrEqual(190)

    expect(errors).toEqual([])
  })

  test(`kb: a saved extraction without its PDF can still open [${tone}]`, async ({ page }) => {
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible()

    const noPdfRow = page.locator('tbody tr', { has: page.getByText('no PDF', { exact: true }) }).first()
    await expect(noPdfRow).toBeVisible()
    await expect(noPdfRow.getByRole('button', { name: 'Open' })).toBeEnabled()
    await noPdfRow.getByRole('button', { name: 'Open' }).click()
    await expect(page.getByText('Saved page text. The original PDF is not available on this device.')).toBeVisible()

    expect(errors).toEqual([])
  })

  // The KB page's "Maturity wall" card — one bar per company grouped by sector. On the seed
  // KB the default collection's single debt report (Ericsson) has buckets that do not reconcile,
  // so the card must show one group, its count line, and the honest grey "buckets incomplete" mark.
  test(`kb: maturity wall card groups the collection by sector [${tone}]`, async ({ page }) => {
    test.skip(!existsSync(ERICSSON_DEBT), WALL_REASON)
    const errors = trackPageErrors(page)
    await gotoWithTone(page, tone)

    await railTab(page, 'Knowledge base').click()
    // The toolbar (and with it the Maturity wall button) only renders once GET /api/kb lands, which
    // takes seconds cold for 206 stems — ride it out here rather than repeating the pre-existing
    // 5 s-budget smoke failures (see docs/acrylic/evidence/v165.md).
    await expect(page.getByRole('heading', { name: /reports/ })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'Maturity wall' })).toBeVisible({ timeout: 20000 })

    await page.getByRole('button', { name: 'Maturity wall' }).click()
    const card = page.getByRole('region', { name: 'Maturity wall' })
    await expect(card).toBeVisible()
    await expect(card.getByText(/share of debt due within 1 year · 0 of 1 companies with complete buckets/)).toBeVisible()

    const sectors = card.getByRole('heading', { name: /^Sector / })
    await expect(sectors).toHaveCount(1)
    await expect(sectors.first()).toContainText('Telecommunications')
    // svg text, not getByText: the row's hidden <title> tooltip carries the same words
    await expect(card.locator('svg text').filter({ hasText: 'buckets incomplete' }).first()).toBeVisible()

    // A company row opens that company through the KB view's existing Open action.
    await card.getByRole('button', { name: /^Ericsson/ }).click()
    await expect(page.getByRole('heading', { name: 'Ericsson', exact: false })).toBeVisible({ timeout: 20000 })

    expect(errors).toEqual([])
  })
}
