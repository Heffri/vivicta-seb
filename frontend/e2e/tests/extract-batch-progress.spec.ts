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

  // Let the batch finish while we stay on Extract this time (both reports run sequentially, so B
  // only starts once A is done). We DID navigate away during the run, so per the work order it
  // must not force a navigation once it ends — it offers a button instead, and we're still
  // looking at the Extract screen once both reports are done.
  await expect(rowA.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowB.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  const viewResults = page.getByRole('button', { name: /^View results/ })
  await expect(viewResults).toBeVisible()
  await expect(page.getByText('Pick reports, get source-linked numbers')).toBeVisible()

  await viewResults.click()
  await expect(page.getByRole('heading', { name: 'Comparison' })).toBeVisible()

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

  await page.setInputFiles('#pdf', [
    { name: 'retry-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
    { name: 'retry-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
  ])
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const rowA = batchRow(page, 'retry-a.pdf')
  const rowB = batchRow(page, 'retry-b.pdf')
  await expect(rowA.getByText('Failed', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowA.getByText(/model provider failed/)).toBeVisible()
  await expect(rowB.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect.poll(() => extractCalls).toBe(2)

  await rowA.getByRole('button', { name: 'Retry this one' }).click()
  await expect(rowA.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  expect(extractCalls).toBe(3) // only A's retry — B was never re-called
  await expect(rowB.getByText('Done', { exact: true })).toBeVisible() // untouched throughout

  await expect(page.getByRole('button', { name: /^View results/ })).toHaveText('View results (2)')

  expect(errors).toEqual([])
})

test('extract: Stop after current finishes the running report but leaves the rest untouched', async ({ page }) => {
  const errors = trackPageErrors(page)
  await page.goto('/')

  let extractCalls = 0
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    extractCalls++
    if (extractCalls === 1) await new Promise((resolve) => setTimeout(resolve, 3000))
    await route.continue()
  })

  await page.setInputFiles('#pdf', [
    { name: 'stop-a.pdf', mimeType: 'application/pdf', buffer: makePdf(2) },
    { name: 'stop-b.pdf', mimeType: 'application/pdf', buffer: makePdf(3) },
    { name: 'stop-c.pdf', mimeType: 'application/pdf', buffer: makePdf(4) },
  ])
  await page.getByRole('main').getByRole('button', { name: /^Extract/ }).click()

  const rowA = batchRow(page, 'stop-a.pdf')
  const rowB = batchRow(page, 'stop-b.pdf')
  const rowC = batchRow(page, 'stop-c.pdf')

  // A is mid-flight (its /extract is the delayed one); stop now, before B or C ever start.
  await expect(rowA.getByText(/Extracting|Reading/)).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Stop after current' }).click()
  await expect(page.getByRole('button', { name: 'Stopping after this one…' })).toBeVisible()

  await expect(rowA.getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(rowB.getByText('Stopped after current')).toBeVisible()
  await expect(rowC.getByText('Stopped after current')).toBeVisible()
  await expect(page.getByRole('button', { name: /Stop after current|Stopping after/ })).toHaveCount(0)
  expect(extractCalls).toBe(1) // B and C never reached /extract

  expect(errors).toEqual([])
})
