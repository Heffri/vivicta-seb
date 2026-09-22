import { expect, test, type Page } from '@playwright/test'

const abb = { stem: 'abb_2025', report_id: 'lib-abb_2025', company: 'ABB', fiscal_year: 2025, pages: 2, sections: ['income_statement'], pdf_available: false, indexed: false }
const acast = { ...abb, stem: 'acast_2025', report_id: 'lib-acast_2025', company: 'Acast' }
const answer = { answer: 'Revenue was 100 [ABB FY2025 p.1].', citations: [{ report_id: abb.report_id, stem: abb.stem, company: 'ABB', fiscal_year: 2025, page: 1, quote: 'Revenue 100', score: 1 }], warnings: [], model: 'test' }

async function mockLibrary(page: Page) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const all = url.searchParams.get('collection_name') === 'all'
    const json = url.pathname === '/api/config' ? { provider: 'codex', model: 'test', retrieval: 'bm25' }
      : url.pathname === '/api/companies' ? (all ? [abb, acast] : [abb]).map(entry => ({ name: entry.company, ticker: entry.company.toUpperCase(), sector: 'Industrials', cached_years: [] }))
      : url.pathname === '/api/kb' ? all ? [abb, acast] : [abb]
      : url.pathname === '/api/schemas' ? [{ name: 'income_statement', title: 'Income statement' }]
      : url.pathname.endsWith('/pages/1') ? { page: 1, text: 'Revenue 100. Saved page evidence.' }
      : []
    await route.fulfill({ json })
  })
}

test('Extract and Ask can use all companies, and the choice follows navigation', async ({ page }) => {
  await mockLibrary(page)
  const scopes: string[] = []
  page.on('request', request => { if (request.url().includes('/api/companies?')) scopes.push(new URL(request.url()).searchParams.get('collection_name')!) })
  await page.goto('/')
  await expect(page.getByRole('button', { name: /ABB ABB/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Acast ACAST/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'All companies', exact: true }).click()
  await expect(page.getByRole('button', { name: /Acast ACAST/ })).toBeVisible()
  await page.getByRole('button', { name: 'All companies', exact: true }).click()
  await expect(page.getByRole('button', { name: /Acast ACAST/ })).toBeVisible()
  expect(scopes).toContain('all')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Scope: Saved text from 2 reports', { exact: true })).toBeVisible()
  await page.getByRole('group', { name: 'Collection' }).getByRole('button', { name: 'All', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Question', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Question', exact: true }).fill('@Aca')
  await expect(page.getByRole('option', { name: 'Acast' })).toBeVisible()
  await page.getByRole('tab', { name: 'Knowledge base', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Saved reports', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open', exact: true })).toHaveCount(2)
})

test('Review groups checks by exact report and statement, retaining filters and details', async ({ page }) => {
  await mockLibrary(page)
  await page.route('**/api/review-queue', route => route.fulfill({ json: [
    ...['entity', 'period', 'currency'].map(key => ({ report: abb, section: 'income_statement', kind: 'basis', key, detail: `Confirm ${key}` })),
    { report: abb, section: 'debt_maturity', kind: 'check', key: 'maturity', detail: 'Check debt maturity sum' },
    { report: acast, section: 'income_statement', kind: 'field', key: 'revenue', detail: 'Review revenue' },
  ] }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Review', exact: true }).click()
  await expect(page.getByText('3 statements · 5 outstanding checks', { exact: true })).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(3)
  const statement = page.getByRole('article', { name: 'ABB 2025 income statement' })
  await statement.getByText('Show outstanding checks', { exact: true }).click()
  for (const key of ['entity', 'period', 'currency']) await expect(statement.getByText(`Confirm ${key}`, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Reporting basis', exact: true }).click()
  await expect(page.getByRole('article')).toHaveCount(1)
  await expect(page.getByText('1 statement · 3 outstanding checks', { exact: true })).toBeVisible()
  await page.getByLabel('Company', { exact: true }).click()
  await page.getByRole('option', { name: 'Acast', exact: true }).click()
  await expect(page.getByText('No checks match these filters.')).toBeVisible()
})

for (const tone of ['light', 'dark']) test(`Ask orb, stop, retry and saved citations [${tone}]`, async ({ page }) => {
  await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
  await mockLibrary(page)
  const errors: string[] = [], external: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) external.push(request.url()) })
  let release = () => {}, requests = 0
  await page.route('**/api/ask', async route => {
    requests++
    if (requests === 1) await new Promise<void>(resolve => { release = resolve })
    await route.fulfill({ json: answer }).catch(() => {})
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  await page.getByRole('button', { name: /Understand the figures/ }).click()
  const question = page.getByRole('combobox', { name: 'Question', exact: true })
  await expect(question).toHaveValue('Explain the key figures in plain language')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Finding a source-backed answer…')).toBeVisible()
  await expect(page.locator('[data-orb-state="thinking"]')).toBeVisible()
  await expect(page.locator('[data-orb-theme]').first()).toHaveAttribute('data-orb-theme', tone)
  await page.evaluate(t => { document.documentElement.dataset.tone = t }, tone === 'dark' ? 'light' : 'dark')
  await expect(page.locator('[data-orb-theme]').first()).toHaveAttribute('data-orb-theme', tone === 'dark' ? 'light' : 'dark')
  await page.evaluate(t => { document.documentElement.dataset.tone = t }, tone)
  await expect(page.getByRole('list', { name: 'Questions and answers' })).toContainText('Explain the key figures in plain language')
  await page.screenshot({ path: `e2e/test-results/ask-thinking-${tone}.png`, fullPage: true })
  await page.getByRole('button', { name: 'Stop waiting' }).click()
  await expect(page.getByText(/Stopped waiting/)).toBeVisible()
  release()
  await question.fill('@UnknownCompany unfinished draft')
  await page.getByRole('button', { name: 'Retry question' }).click()
  await expect(page.getByText('Revenue was 100', { exact: false }).first()).toBeVisible()
  await page.getByRole('button', { name: /ABB.*2025.*p\.1/ }).first().click()
  await expect(page.getByRole('region', { name: 'Saved source text' })).toContainText('Saved page evidence.')
  await expect(page.getByRole('button', { name: 'Copy answer' })).toBeEnabled()
  await page.screenshot({ path: `e2e/test-results/ask-answer-${tone}.png`, fullPage: true })
  await page.getByRole('button', { name: 'New conversation' }).click()
  await expect(page.getByRole('list', { name: 'Questions and answers' })).toHaveCount(0)
  expect(external).toEqual([])
  expect(errors).toEqual([])
})

test('Ask keeps working with reduced motion and unavailable WebGL', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (...args: Parameters<typeof original>) {
      if (String(args[0]).startsWith('webgl')) return null
      return original.apply(this, args)
    } as typeof original
  })
  await mockLibrary(page)
  await page.route('**/api/ask', route => route.fulfill({ json: answer }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask', exact: true }).click()
  await page.getByRole('combobox', { name: 'Question', exact: true }).fill('What was revenue?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Revenue was 100', { exact: false }).first()).toBeVisible()
})
