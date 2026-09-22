import { expect, type Page, test } from '@playwright/test'
import { makePdf } from '../fixtures/make-pdf'
import { trackPageErrors } from '../support/page-errors'

const batchRow = (page: Page, filename: string) => page.getByRole('list', { name: 'Batch progress' }).getByRole('listitem').filter({ hasText: filename })

async function chooseSection(page: Page, title: string) {
  await page.locator('#section').click()
  await page.getByRole('option', { name: title, exact: true }).click()
}

async function uploadOne(page: Page, filename: string) {
  await page.getByRole('button', { name: 'Upload PDF', exact: true }).click()
  await page.setInputFiles('#pdf', { name: filename, mimeType: 'application/pdf', buffer: makePdf(2) })
}

test('extract: a failed debt run can switch to income and start a fresh batch', async ({ page }) => {
  const errors = trackPageErrors(page)
  const sections: string[] = []
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    const { section } = route.request().postDataJSON() as { section: string }
    sections.push(section)
    if (section === 'debt_maturity') {
      await route.fulfill({ status: 422, json: { detail: 'Debt note has no candidate pages' } })
      return
    }
    await route.fulfill({ json: { report_id: 'up-switch', section, company: 'Switch fixture', fiscal_year: 2025, currency: 'SEK', fields: [], checks: [], warnings: [] } })
  })

  await page.goto('/')
  await uploadOne(page, 'switch-section.pdf')
  await page.getByRole('main').getByRole('button', { name: /^Extract$/ }).click()

  const row = batchRow(page, 'switch-section.pdf')
  await expect(row.getByText('Failed', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(row.getByText('Debt note has no candidate pages')).toBeVisible()
  // The failure stays visible with an explicit restart action; it must not trap the batch in a
  // terminal state where only Retry can run the old section.
  await expect(page.getByRole('button', { name: 'Extract again', exact: true })).toBeVisible()

  await chooseSection(page, 'Consolidated income statement')
  await expect(page.getByRole('list', { name: 'Batch progress' })).toHaveCount(0)
  await page.getByRole('main').getByRole('button', { name: /^Extract$/ }).click()
  await expect(batchRow(page, 'switch-section.pdf').getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })
  expect(sections).toEqual(['debt_maturity', 'income_statement'])
  expect(errors).toEqual([])
})

test('extract: one report can complete debt then income without sharing the section result', async ({ page }) => {
  const errors = trackPageErrors(page)
  const runs: { reportId: string; section: string }[] = []
  await page.route(/\/api\/reports\/.+\/extract$/, async (route) => {
    const { section } = route.request().postDataJSON() as { section: string }
    const reportId = new URL(route.request().url()).pathname.split('/')[3]
    runs.push({ reportId, section })
    await route.fulfill({ json: { report_id: reportId, section, company: 'Two sections fixture', fiscal_year: 2025, currency: 'SEK', fields: [], checks: [], warnings: [] } })
  })

  await page.goto('/')
  await uploadOne(page, 'two-sections.pdf')
  await page.getByRole('main').getByRole('button', { name: /^Extract$/ }).click()
  await expect(batchRow(page, 'two-sections.pdf').getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })

  await chooseSection(page, 'Consolidated income statement')
  await page.getByRole('main').getByRole('button', { name: /^Extract$/ }).click()
  await expect(batchRow(page, 'two-sections.pdf').getByText('Done', { exact: true })).toBeVisible({ timeout: 20000 })

  expect(runs).toHaveLength(2)
  expect(runs[0].reportId).toBe(runs[1].reportId)
  expect(runs.map((run) => run.section)).toEqual(['debt_maturity', 'income_statement'])
  expect(errors).toEqual([])
})
