import { expect, test } from '@playwright/test'

for (const cached of [false, true]) test(`AI discovery works beyond directory matches and reuses saved text [cached=${cached}]`, async ({ page }) => {
  const fetched: any[] = [], extracted: string[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reports/fetch') {
      const body = route.request().postDataJSON(); fetched.push(body)
      if (!cached && !body.download_pdf) return route.fulfill({ status: 409, json: { detail: 'No saved report' } })
      return route.fulfill({ json: { report_id: 'lib-siemens_2025', company: 'Siemens', fiscal_year: 2025, pages: 335 } })
    }
    if (path.endsWith('/extract')) {
      extracted.push(path)
      return route.fulfill({ json: { report_id: 'lib-siemens_2025', company: 'Siemens', fiscal_year: 2025, section: 'income_statement', fields: [], checks: [], warnings: [] } })
    }
    return route.fulfill({ json: path === '/api/config' ? { provider: 'codex', model: 'test' }
      : path === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : path === '/api/companies' ? [{ name: 'ABB', ticker: 'ABB', sector: 'Industrials', cached_years: [] }] : [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /ABB ABB/ }).click()
  await page.getByRole('searchbox', { name: 'Search companies', exact: true }).fill('Siemens')
  await expect(page.getByRole('checkbox', { name: /Allow PDF download/ })).not.toBeChecked()
  // Nonempty directory results and an unrelated pick must neither hide nor join this search.
  await page.getByRole('button', { name: 'AI search, download & extract · 2025', exact: true }).click()
  await expect.poll(() => extracted.length).toBe(1)
  expect(fetched.map(request => request.company)).toEqual(cached ? ['Siemens'] : ['Siemens', 'Siemens'])
  expect(fetched.map(request => request.download_pdf)).toEqual(cached ? [false] : [false, true])
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
  await expect(page.getByText('2 reports with saved text · 1 with extracted figures · 1 PDFs downloaded', { exact: true })).toBeVisible()
  await expect(page.getByText(/1 catalog entries have no readable page text/)).toBeVisible()
  await page.getByRole('combobox', { name: 'Question', exact: true }).fill('Summarise revenue')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect.poll(() => asked.length).toBe(1)
  expect(asked[0].report_stems).toEqual(['one', 'two'])
})
