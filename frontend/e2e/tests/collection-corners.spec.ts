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
