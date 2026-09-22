import { expect, test, type Page } from '@playwright/test'

const abb = { stem: 'abb_2025', report_id: 'lib-abb_2025', company: 'ABB', fiscal_year: 2025, pages: 2, sections: ['income_statement'], indexed: false, pdf_available: false }
const acast = { ...abb, stem: 'acast_2025', report_id: 'lib-acast_2025', company: 'Acast' }

function entriesFor(collection: string | null) {
  return collection === 'midcap' ? [acast] : collection === 'all' ? [abb, acast] : [abb]
}

async function mockCollections(page: Page, companyRequests: { collection: string | null; query: string | null }[], kbRequests: (string | null)[], asked: unknown[]) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const collection = url.searchParams.get('collection_name')
    const entries = entriesFor(collection)
    if (url.pathname === '/api/companies') companyRequests.push({ collection, query: url.searchParams.get('q') })
    if (url.pathname === '/api/kb') kbRequests.push(collection)
    if (url.pathname === '/api/ask') {
      asked.push(route.request().postDataJSON())
      return route.fulfill({ json: { answer: 'Acast report evidence.', citations: [], warnings: [], model: 'test' } })
    }
    const json = url.pathname === '/api/config' ? { provider: 'codex', model: 'test', retrieval: 'bm25' }
      : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : url.pathname === '/api/companies' ? entries.map(entry => ({ name: entry.company, ticker: entry.company.toUpperCase(), sector: 'Industrials', cached_years: [] }))
      : url.pathname === '/api/kb' ? entries
      : url.pathname === '/api/library' ? []
      : []
    await route.fulfill({ json })
  })
}

test('Extract company search stays within the selected SEB Mid Cap directory', async ({ page }) => {
  const companyRequests: { collection: string | null; query: string | null }[] = []
  await mockCollections(page, companyRequests, [], [])

  await page.goto('/')
  await expect(page.getByRole('button', { name: /ABB ABB/ })).toBeVisible()
  await page.getByRole('group', { name: 'Collection' }).getByRole('button', { name: 'SEB Mid Cap (132)', exact: true }).click()
  await expect(page.getByRole('button', { name: /Acast ACAST/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /ABB ABB/ })).toHaveCount(0)

  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('ac')
  await expect.poll(() => companyRequests.some(request => request.collection === 'midcap' && request.query === 'ac')).toBe(true)
  await expect(page.getByRole('button', { name: /Acast ACAST/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /ABB ABB/ })).toHaveCount(0)
})

test('global Ask sends only SEB Mid Cap stems after the collection changes', async ({ page }) => {
  const kbRequests: (string | null)[] = []
  const asked: unknown[] = []
  await mockCollections(page, [], kbRequests, asked)

  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await page.getByRole('group', { name: 'Collection' }).getByRole('button', { name: 'SEB Mid Cap (132)', exact: true }).click()
  await expect(page.getByText('1 reports with saved text · 1 with extracted figures · 0 PDFs downloaded', { exact: true })).toBeVisible()

  const question = page.getByRole('combobox', { name: 'Question', exact: true })
  await question.fill('@Aca')
  await expect(page.getByRole('option', { name: 'Acast', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: 'ABB', exact: true })).toHaveCount(0)
  await question.fill('Summarise the saved report')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()

  await expect.poll(() => asked.length).toBe(1)
  expect(asked).toEqual([expect.objectContaining({ question: 'Summarise the saved report', report_stems: ['acast_2025'] })])
  expect(kbRequests).toContain('midcap')
})

test('a private Patricia holding opens its saved Investor section without AI discovery or PDF fetch', async ({ page }) => {
  const discovered: unknown[] = [], fetched: unknown[] = [], extracted: unknown[] = []
  const sarnova = {
    name: 'Sarnova', ticker: '', sector: null, isin: null, cached_years: [],
    no_standalone_report: true, reports_in: 'Investor AB', collection_group: 'Patricia Industries',
    report_stem: 'investor_2025', report_page: 41,
  }
  const investorExtraction = {
    report_id: 'lib-investor_2025', stem: 'investor_2025', company: 'Investor AB', fiscal_year: 2025,
    section: 'income_statement', fields: [], checks: [], warnings: [], pdf_available: false,
  }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/discover') discovered.push(route.request().postDataJSON())
    if (path === '/api/reports/fetch') fetched.push(route.request().postDataJSON())
    if (path.endsWith('/extract')) extracted.push(route.request().postDataJSON())
    const json = path === '/api/config' ? { provider: 'fixture', model: 'test' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Consolidated income statement' }]
      : path === '/api/companies' ? [sarnova]
      : path === '/api/kb/investor_2025/income_statement' ? investorExtraction
      : path === '/api/kb/investor_2025/pages/41' ? { page: 41, text: 'Patricia Industries includes Sarnova.' }
      : []
    await route.fulfill({ json })
  })

  await page.goto('/')
  await expect(page.getByText("Private company — reported inside Investor AB's annual report (Patricia Industries)", { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Open Investor AB report for Sarnova', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Investor AB', exact: true })).toBeVisible()
  await expect(page.getByText('Page 41', { exact: true })).toBeVisible()
  expect(discovered).toEqual([])
  expect(fetched).toEqual([])
  expect(extracted).toEqual([])
})
