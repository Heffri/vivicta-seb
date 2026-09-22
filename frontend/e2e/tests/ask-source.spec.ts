import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const savedPage = readFileSync('../data/kb/abb_2025/pages.jsonl', 'utf8').trim().split('\n').map(line => JSON.parse(line)).find(p => p.page === 55).text as string
const quote = 'Interest and dividend income 203 206'
const entry = { stem: 'abb_2025', report_id: 'lib-abb_2025', company: 'ABB', fiscal_year: 2025, pages: 142, sections: [], text_available: true, pdf_available: false }

async function setup(page: Page, { pdf = false, fail = false, slow = false, record = entry, pageText = savedPage, passage = quote, pageNumber = 55, image = false } = {}) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === `/api/kb/${record.stem}/pages/${pageNumber}`) {
      if (slow) await new Promise(resolve => setTimeout(resolve, 500))
      await route.fulfill(fail ? { status: 500, json: { detail: 'Page unavailable' } } : { json: { page: pageNumber, text: pageText } })
      return
    }
    if (path.endsWith('.png')) { await route.fulfill(image ? { contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800"><rect width="600" height="800" fill="white"/><text x="50" y="100">Interest and dividend income 203 206</text></svg>' } : { status: 404 }); return }
    const json = path === '/api/kb' ? [{ ...record, pdf_available: pdf }]
      : path === '/api/config' ? { provider: 'fixture', model: 'test', retrieval: 'bm25' }
      : path === '/api/schemas' ? [{ name: 'debt_maturity', title: 'Debt maturity' }]
      : path === '/api/ask' ? { answer: 'ABB reported interest and dividend income of $203 million in 2025 (2024: $206 million).', citations: [
        { ...record, page: pageNumber, quote: passage, score: 1 },
        { ...record, page: pageNumber + 1, quote: 'Cash generated 999', score: 1 },
      ], warnings: [], model: 'test' }
      : path.endsWith(`/pages/${pageNumber + 1}`) ? { page: pageNumber + 1, text: 'Cash generated 999' }
      : path.endsWith('/evidence') ? { page: pageNumber, width: 600, height: 800, keywords: [[50, 80, 250, 100]], numbers: [[260, 80, 300, 100]], matched_quotes: 1, total_quotes: 1 }
      : []
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await page.getByRole('combobox', { name: 'Question', exact: true }).fill(`@${record.company} What were the reported figures?`)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByRole('button', { name: `${record.company} FY2025 · p.${pageNumber}`, exact: true }).click()
}

for (const tone of ['dark', 'light']) {
  test(`Ask source restores ABB's table and highlights only its supporting figures [${tone}]`, async ({ page }, testInfo) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
    await setup(page)
    const source = page.getByRole('region', { name: 'Source evidence', exact: true })
    await expect(source).toBeVisible()
    const table = source.getByRole('table')
    await expect(table.getByRole('columnheader')).toHaveText(['Reported item', '2025', '2024'])
    const row = table.getByRole('row', { name: 'Interest and dividend income 203 206', exact: true })
    await expect(row.locator('mark')).toHaveText(['203', '206'])
    await expect(row).toBeInViewport()
    await expect(table.getByRole('row', { name: 'Sales of products 27,669 25,531', exact: true }).locator('mark')).toHaveCount(0)
    await expect(source.getByText(/Original PDF not downloaded/)).toBeVisible()
    await source.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`ask-source-${tone}.png`) })
    await source.getByRole('button', { name: 'Close source' }).click()
    await expect(source).toHaveCount(0)
    expect(errors).toEqual([])
  })
}

test('Ask retains the supporting passage when loading the page fails', async ({ page }) => {
  await setup(page, { fail: true })
  const source = page.getByRole('region', { name: 'Source evidence', exact: true })
  await expect(source.getByRole('alert')).toContainText('Could not load the full saved page')
  await expect(source.locator('blockquote')).toContainText('Interest and dividend income 203 206')
  await expect(source.locator('blockquote mark')).not.toHaveCount(0)
})

test('downloaded PDFs open inline with a citation overlay and can switch to readable text', async ({ page }) => {
  await setup(page, { pdf: true, image: true })
  const source = page.getByRole('region', { name: 'Source evidence', exact: true })
  await expect(source.getByAltText('Original report, page 55')).toBeVisible()
  await expect(source.locator('[data-evidence="keywords"]')).toHaveCount(1)
  await expect(source.locator('[data-evidence="numbers"]')).toHaveCount(1)
  const pdfLink = source.getByRole('link', { name: 'Download highlighted PDF' })
  await expect(pdfLink).toHaveAttribute('href', /\/pdf\?page=55&quote=Interest.*#page=55$/)
  await source.getByRole('button', { name: 'Highlighted PDF', exact: true }).click()
  await expect(source.getByTitle('Highlighted PDF, page 55')).toHaveAttribute('src', /page=55&quote=Interest.*#page=55$/)
  await source.getByRole('button', { name: 'Readable text' }).click()
  await expect(source.getByRole('table')).toBeVisible()
  await source.getByRole('button', { name: 'Original page' }).click()
  await expect(source.getByAltText('Original report, page 55')).toBeVisible()
})

for (const sample of [
  { stem: 'karnell_2025', company: 'Karnell Group', pageNumber: 106, passage: 'Liabilities to credit institutions 43.5 353.7 - 397.2', headers: ['Reported item', '<1 year', '1-3 years', '>3 years', 'Total'], highlights: ['43.5', '353.7', '397.2'] },
  { stem: 'saab_2025_sv', company: 'Saab', pageNumber: 151, passage: 'Försäljningsintäkter 4 79 146 63 751', headers: ['Reported item', 'Not', '2025', '2024'], highlights: ['79 146', '63 751'] },
]) {
  test(`Ask uses report-derived columns and evidence for ${sample.company}`, async ({ page }) => {
    const text = readFileSync(`../data/kb/${sample.stem}/pages.jsonl`, 'utf8').trim().split('\n').map(line => JSON.parse(line)).find(p => p.page === sample.pageNumber).text
    await setup(page, { record: { ...entry, stem: sample.stem, company: sample.company, report_id: `lib-${sample.stem}` }, pageText: text, passage: sample.passage, pageNumber: sample.pageNumber })
    const source = page.getByRole('region', { name: 'Source evidence', exact: true })
    const table = source.getByRole('table').first()
    await expect(table.getByRole('columnheader')).toHaveText(sample.headers)
    await expect(table.locator('tr[data-cited="true"] mark')).toHaveText(sample.highlights)
  })
}

test('Ask falls back to formatted text if a downloaded PDF preview fails', async ({ page }) => {
  await setup(page, { pdf: true })
  const source = page.getByRole('region', { name: 'Source evidence', exact: true })
  await expect(source.getByRole('table')).toBeVisible()
  await expect(source.getByText(/Page preview unavailable/)).toBeVisible()
  await expect(source.getByRole('link', { name: 'Open original PDF' })).toHaveAttribute('href', '/api/reports/lib-abb_2025/pdf#page=55')
})

test('Ask downloads the matching original from its source panel and enables highlighted download', async ({ page }) => {
  await setup(page, { image: true })
  let attempts = 0
  await page.route('**/api/kb/abb_2025/pdf', async route => {
    expect(route.request().method()).toBe('POST')
    attempts++
    await route.fulfill(attempts === 1
      ? { status: 502, json: { detail: 'Original PDF temporarily unavailable' } }
      : { json: { report_id: entry.report_id, pages: 142 } })
  })
  const source = page.getByRole('region', { name: 'Source evidence', exact: true })
  await source.getByRole('button', { name: 'Download original PDF', exact: true }).click()
  await expect(source.getByText('Original PDF temporarily unavailable')).toBeVisible()
  await expect(source.getByRole('table')).toBeVisible()
  await source.getByRole('button', { name: 'Download original PDF', exact: true }).click()
  await expect(source.getByAltText('Original report, page 55')).toBeVisible()
  await expect(source.getByRole('link', { name: 'Download highlighted PDF' })).toHaveAttribute('href', /quote=Interest.*#page=55$/)
  await expect(source.locator('[data-evidence="numbers"]')).toHaveCount(1)
  await expect(source.getByText('Original PDF temporarily unavailable')).toHaveCount(0)
})

test('readable source keeps current-parser inline statement rows in columns', async ({ page }) => {
  await setup(page, { pageText: 'Year ended December 31 ($ in millions) 2025 2024\nSales of products 27,669 25,531\nInterest and dividend income 203 206' })
  const table = page.getByRole('region', { name: 'Source evidence', exact: true }).getByRole('table')
  await expect(table.getByRole('columnheader')).toHaveText(['Reported item', '2025', '2024'])
  await expect(table.locator('tr[data-cited="true"] mark')).toHaveText(['203', '206'])
})

test('switching citations prevents a slow previous page from replacing the current evidence', async ({ page }) => {
  await setup(page, { slow: true })
  await page.getByRole('button', { name: 'ABB FY2025 · p.56', exact: true }).click()
  const source = page.getByRole('region', { name: 'Source evidence', exact: true })
  await expect(source.getByRole('heading')).toContainText('page 56')
  await expect(source.getByLabel('Formatted source page')).toHaveText('Cash generated 999')
  await page.waitForTimeout(700)
  await expect(source.getByLabel('Formatted source page')).toHaveText('Cash generated 999')
})
