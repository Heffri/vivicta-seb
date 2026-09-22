import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { fieldVerification } from '../../src/components/results/verification'
import type { Extraction, Field } from '../../src/types'

const fixture: Extraction = JSON.parse(readFileSync(new URL('../../../backend/fixtures/sample_extraction.json', import.meta.url), 'utf8'))
const evidence = ['quote_on_page', 'value_in_quote', 'arith_ok', 'label_known', 'period_ok', 'page_is_statement', 'unit_ok']

test('verification reports evidence rather than a probability of truth', () => {
  const field: Field = { ...fixture.fields[0], confidence: 1, evidence }
  expect(fieldVerification({ ...field, evidence: [] }).label).toBe('Not checked')
  expect(fieldVerification({ ...field, value: null }).label).toBe('Not found')
  // v165: a bucket the maturity table prints no column for — the header row in the source proves it.
  expect(fieldVerification({ ...field, value: null, evidence: ['absent_in_table'] }).label).toBe('Not printed in this report')
  expect(fieldVerification({ ...field, value: null, evidence: ['absent_in_table'] }).variant).toBe('secondary')
  expect(fieldVerification({ ...field, confidence: 0 }).label).toBe('Checks passed')
  expect(fieldVerification({ ...field, evidence: evidence.map(e => e === 'value_in_quote' ? 'value_derived' : e) }).label).toBe('Calculated from report')
  expect(fieldVerification({ ...field, evidence: evidence.filter(e => e !== 'period_ok') }).label).toBe('Needs review')
  expect(fieldVerification({ ...field, source: null }).label).toBe('Needs review')
  // exactly one stand-in for value_in_quote resolves the row (docs/CONFIDENCE.md); two at once, or none, is a review
  for (const zero of ['printed_nil', 'stated_zero']) {
    expect(fieldVerification({ ...field, value: 0, evidence: evidence.map(e => e === 'value_in_quote' ? zero : e) }).label).toBe('Reported as zero')
    expect(fieldVerification({ ...field, value: 0, evidence: evidence.map(e => e === 'value_in_quote' ? zero : e).filter(e => e !== 'label_known') }).label).toBe('Needs review')
  }
  expect(fieldVerification({ ...field, value: 0, evidence: [...evidence.filter(e => e !== 'value_in_quote'), 'value_derived', 'stated_zero'] }).label).toBe('Needs review')
  expect(fieldVerification({ ...field, evidence: evidence.filter(e => e !== 'value_in_quote') }).label).toBe('Needs review')
  // a schema-optional row the report does not print: not found is not a task, and not a zero
  expect(fieldVerification({ ...field, value: null }, true).label).toBe('Not reported')
  expect(fieldVerification({ ...field, value: null, human_review: { decision: 'unresolved', reviewer: 'A', note: 'The row exists', at: 'now' } }, true).label).toBe('Needs review')
})

for (const tone of ['dark', 'light']) {
  test(`readable results and source review [${tone}]`, async ({ page }) => {
    await page.addInitScript(t => localStorage.setItem('acrylic-tone', t), tone)
    await page.route('**/api/**', route => {
      const url = new URL(route.request().url())
      const data = url.pathname === '/api/schemas' ? [{name:'income_statement', title:'Income statement'}]
        : url.pathname === '/api/library' ? [{file:'test.pdf', company:'Example company', fiscal_year:2025, language:'en', pages:65, source_url:null, tags:[]}]
        : url.pathname === '/api/reports/from-library' ? {report_id:'fixture', filename:'test.pdf', pages:65}
        : url.pathname.endsWith('/extract') ? fixture
        : url.pathname === '/api/config' ? {provider:'fixture', model:'fixture'}
        : []
      return route.fulfill({json:data})
    })
    await page.goto('/')
    await page.getByRole('button', {name:'Saved reports', exact:true}).click()
    await page.getByRole('checkbox', {name:/Example company/}).check()
    await page.getByRole('main').getByRole('button', {name:/^Extract/}).click()
    // v171: a finished batch never forces a tab switch (BatchProgress's own "View results" does).
    await page.getByRole('main').getByRole('button', {name:/^View results/}).click({timeout: 20000})
    await expect(page.getByRole('columnheader', {name:'Verification'})).toBeVisible()
    await expect(page.getByRole('columnheader', {name:'Confidence'})).toHaveCount(0)
    await expect(page.getByRole('cell').filter({has: page.getByText('Not checked', {exact:true})})).toHaveCount(8)
    await page.getByRole('row').filter({has:page.getByRole('cell',{name:'EPS, basic',exact:true})}).click()
    await expect(page.getByText('EPS, basic: Not checked', {exact:true})).toBeVisible()
    await expect(page.getByRole('button', {name:'Which page is the income statement on?'})).toHaveCount(0)
    await page.getByRole('navigation', {name:'Report workspace'}).getByRole('button', {name:/Checks & review/}).click()
    await page.getByText('Do the numbers add up?', {exact:true}).scrollIntoViewIfNeeded()
    await expect(page.getByText('Gross profit: Adds up', {exact:true})).toBeVisible()
    await expect(page.getByText(/Check whether this figure is basic or diluted/)).toBeVisible()
    await page.screenshot({path:`e2e/test-results/readable-results-${tone}.png`, fullPage:true})
    await page.getByRole('button', {name:'Open source, page 65'}).click()
    await expect(page.locator('#report-source')).toBeFocused()
  })
}

for (const [passed, detail, expected, visibleStatus] of [
  [true, '100 = 100', 'Repayments add up to total debt (within rounding)', 'Debt repayments: Adds up'],
  [false, '100 != 110', 'Repayments do not add up to total debt', 'Debt repayments: Needs review'],
  [false, 'missing: total_debt', 'Not enough data to check the total', 'Debt repayments: Not checked'],
] as const) {
  test(`maturity check: ${expected}`, async ({page}) => {
    const extraction = { ...fixture, section:'debt_maturity', warnings:[],
      fields: ['total_debt','due_within_1_year','due_1_to_5_years','due_after_5_years'].map((key, i) => ({...fixture.fields[0], key, label:key, value:i ? 30 : 90, evidence})),
      checks:[{name:'maturity_sums_to_total', passed, detail}] }
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      return route.fulfill({json:path === '/api/schemas' ? [{name:'debt_maturity', title:'Debt maturity'}]
        : path === '/api/library' ? [{file:'test.pdf', company:'Example company', fiscal_year:2025, language:'en', pages:65, source_url:null, tags:[]}]
        : path === '/api/reports/from-library' ? {report_id:'fixture', filename:'test.pdf', pages:65}
        : path.endsWith('/extract') ? extraction
        : path === '/api/config' ? {provider:'fixture', model:'fixture'} : []})
    })
    await page.goto('/')
    await page.getByRole('button', {name:'Saved reports', exact:true}).click()
    await page.getByRole('checkbox', {name:/Example company/}).check()
    await page.getByRole('main').getByRole('button', {name:/^Extract/}).click()
    // v171: a finished batch never forces a tab switch (BatchProgress's own "View results" does).
    await page.getByRole('main').getByRole('button', {name:/^View results/}).click({timeout: 20000})
    await page.getByRole('navigation', {name:'Report workspace'}).getByRole('button', {name:/Checks & review/}).click()
    await expect(page.getByText(visibleStatus, {exact:true})).toBeVisible()
  })
}
