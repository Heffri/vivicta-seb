import { expect, type Page, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'

// v171 (consult item 6): the batch's progress used to live inside UploadView, so switching tabs
// mid-batch unmounted it, and the still-running promise chain called the old onDone regardless of
// which tab was open when it finished — yanking the user back to Results/Compare even if they'd
// since navigated elsewhere. These three specs cover the fix: state survives a tab switch, a
// partial failure only retries the failed report, and "Stop after current" leaves the rest queued
// but untouched. Logic tests, not visual ones (like ai-discovery.spec.ts / pdf-opt-in.spec.ts) —
// no tone loop.

// Scoped to BatchProgress's own labeled list — Dropzone stages its picked files as <li> rows too
// (name + size + a remove button), and a plain `page.locator('li', { hasText })` matches both.
const batchRow = (page: Page, filename: string) => page.getByRole('list', { name: 'Batch progress' }).getByRole('listitem').filter({ hasText: filename })

test('extract: switching tabs mid-batch and back keeps progress, and the finish does not force a navigation', async ({ page }) => {
  const errors = trackPageErrors(page)
  await page.goto('/')

  // Hold every /extract open briefly so both reports are still in flight when we tab away.
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    await route.continue()
  })

  await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
  await page.setInputFiles('#pdf', [
    { name: 'switch-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
    { name: 'switch-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
  ])
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const rowA = batchRow(page, 'switch-a.pdf')
  const rowB = batchRow(page, 'switch-b.pdf')
  await expect(rowA).toBeVisible()

  // Switch away while the batch is still running — this used to unmount the progress state.
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Ask', exact: true })).toHaveAttribute('aria-selected', 'true')

  // ...come back; the same rows must still be there, further along or finished.
  await page.getByRole('tab', { name: 'Extract', exact: true }).click()
  await expect(rowA).toBeVisible()
  await expect(rowB).toBeVisible()

  // Let the active reports finish while we stay on Extract. We DID navigate away during the run,
  // so per the work order it must not force a navigation once it ends — it offers a button
  // instead, and we're still looking at the Extract screen once both reports are done.
  await expect(rowA.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowB.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  const viewResults = page.getByRole('button', { name: /^View results/ })
  await expect(viewResults).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Extract report data', exact: true })).toBeVisible()

  await viewResults.click()
  await expect(page.getByRole('heading', { name: 'Compare reports', exact: true })).toBeVisible()

  expect(errors).toEqual([])
})

test('extract: one of two reports fails with a provider error, retry only re-runs that one', async ({ page }) => {
  const errors = trackPageErrors(page)
  await page.goto('/')

  let extractCalls = 0
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    extractCalls++
    if (extractCalls === 1) {
      await route.fulfill({ status: 502, json: { detail: 'llm: the provider connection failed' } })
      return
    }
    await route.continue()
  })

  await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
  await page.setInputFiles('#pdf', [
    { name: 'retry-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
    { name: 'retry-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
  ])
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const rowA = batchRow(page, 'retry-a.pdf')
  const rowB = batchRow(page, 'retry-b.pdf')
  // The first request to reach the mocked route may be either concurrent worker, so identify the
  // failed row by its observed outcome rather than relying on upload scheduling.
  await expect.poll(async () => (
    await rowA.getByText('Failed', { exact: true }).isVisible().catch(() => false) ? 'a'
      : await rowB.getByText('Failed', { exact: true }).isVisible().catch(() => false) ? 'b' : ''
  )).not.toBe('')
  const failedRow = await rowA.getByText('Failed', { exact: true }).isVisible() ? rowA : rowB
  const doneRow = failedRow === rowA ? rowB : rowA
  await expect(failedRow.getByText(/model provider failed/)).toBeVisible()
  await expect(doneRow.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect.poll(() => extractCalls).toBe(2)

  await failedRow.getByRole('button', { name: 'Retry this one' }).click()
  await expect(failedRow.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  expect(extractCalls).toBe(3) // only the failed row's retry — the successful row was never re-called
  await expect(doneRow.getByText('Done', { exact: true })).toBeVisible() // untouched throughout

  await expect(page.getByRole('button', { name: /^View results/ })).toHaveText('View results (2)')

  expect(errors).toEqual([])
})

test('extract: Stop after current lets the active three finish and leaves later reports untouched', async ({ page }) => {
  const errors = trackPageErrors(page)
  await page.goto('/')

  let extractCalls = 0
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    extractCalls++
    // Hold the active three so the two later reports remain queued while Stop is requested.
    if (extractCalls <= 3) await new Promise((resolve) => setTimeout(resolve, 3000))
    await route.continue()
  })

  await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
  await page.setInputFiles('#pdf', [
    { name: 'stop-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
    { name: 'stop-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
    { name: 'stop-c.pdf', mimeType: 'application/pdf', buffer: makePdf(4) },
    { name: 'stop-d.pdf', mimeType: 'application/pdf', buffer: makePdf(5) },
    { name: 'stop-e.pdf', mimeType: 'application/pdf', buffer: makePdf(6) },
  ])
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const rowA = batchRow(page, 'stop-a.pdf')
  const rowB = batchRow(page, 'stop-b.pdf')
  const rowC = batchRow(page, 'stop-c.pdf')
  const rowD = batchRow(page, 'stop-d.pdf')
  const rowE = batchRow(page, 'stop-e.pdf')

  // A/B/C are the three active slots; stop now before D or E can claim one.
  await expect(rowA.getByText(/Extracting|Reading/)).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Stop after current' }).click()
  await expect(page.getByRole('button', { name: 'Stopping after this one…' })).toBeVisible()

  await expect(rowA.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowB.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowC.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowD.getByText('Stopped after current')).toBeVisible()
  await expect(rowE.getByText('Stopped after current')).toBeVisible()
  await expect(page.getByRole('button', { name: /Stop after current|Stopping after/ })).toHaveCount(0)
  expect(extractCalls).toBe(3) // D and E never reached /extract

  expect(errors).toEqual([])
})

test('extract: a scanned PDF over the OCR page budget offers "Run OCR anyway", which resends with ocr=full', async ({ page }) => {
  // v191(c): registration 422s with {detail, ocr_pages_needed} when a scanned PDF's bounded OCR
  // pass alone is over budget; the batch row surfaces a "Run OCR anyway (~N min)" button that
  // resends the same upload with ocr=full. Mocked end to end (work order's own instruction) — the
  // real bounded-OCR mechanics are covered by the backend's pipeline.test_maturity_ocr/test_runtime.
  const errors = trackPageErrors(page)
  await page.goto('/')

  let uploadCalls = 0
  await page.route(/\/api\/reports(\?.*)?$/, async (route) => {
    uploadCalls++
    const ocr = new URL(route.request().url()).searchParams.get('ocr')
    if (ocr !== 'full') {
      await route.fulfill({ status: 422, json: { detail: 'scanned PDF: OCR would take ~2 min for 55 pages', ocr_pages_needed: 55 } })
      return
    }
    await route.fulfill({ status: 200, json: { report_id: 'up-mock191', filename: 'scan-191.pdf', pages: 60, company: null, fiscal_year: null, ocr_pages: [3, 4, 5] } })
  })
  await page.route(/\/api\/reports\/up-mock191\/candidates/, (route) => route.fulfill({ status: 200, json: [] }))
  await page.route(/\/api\/reports\/up-mock191\/extract$/, (route) =>
    route.fulfill({ status: 200, json: { report_id: 'up-mock191', section: 'debt_maturity', company: null, fiscal_year: null, currency: null, fields: [], checks: [], warnings: [] } }),
  )

  await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
  await page.setInputFiles('#pdf', { name: 'scan-191.pdf', mimeType: 'application/pdf', buffer: makePdf(2) })
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const row = batchRow(page, 'scan-191.pdf')
  await expect(row.getByText('scanned PDF: OCR would take ~2 min for 55 pages')).toBeVisible()
  const runAnyway = row.getByRole('button', { name: /Run OCR anyway/ })
  await expect(runAnyway).toHaveText('Run OCR anyway (~2 min)')

  await runAnyway.click()
  await expect(row.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(row.getByText('OCR: 3 pages')).toBeVisible()
  await expect.poll(() => uploadCalls).toBe(2)

  expect(errors).toEqual([])
})
