// Run with Node 24: node --test src/components/ask/sourceDocument.test.ts
// @ts-nocheck -- the app's TypeScript config contains browser types only.
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { evidenceRanges, evidenceRuns, sourceDocument } from './sourceDocument.ts'

test('ABB page 55 restores its real year columns, financial rows, and section labels without changing figures', () => {
  const pages = readFileSync('../data/kb/abb_2025/pages.jsonl', 'utf8').trim().split('\n').map(JSON.parse)
  const text = pages.find(p => p.page === 55).text
  const tables = sourceDocument(text).filter(b => b.type === 'table')
  assert.equal(tables.length, 1)
  const table = tables[0]
  assert.deepEqual(table.headers.map(h => h.text), ['2025', '2024'])
  const row = table.rows.find(r => r.label.map(l => l.text).join(' ') === 'Interest and dividend income')
  assert.deepEqual(row.values.map(v => v.text), ['203', '206'])
  assert.ok(table.rows.some(r => r.label[0].text === 'Amounts attributable to ABB shareholders:' && !r.values.length))
  assert.ok(table.rows.some(r => r.values.some(v => v.text === '(16,581)')))
  for (const block of sourceDocument(text)) {
    const spans = block.type === 'text' ? block.lines : [...block.headers, ...block.rows.flatMap(r => [...r.label, ...r.values])]
    for (const span of spans) assert.equal(text.slice(span.start, span.end), span.text)
  }
  const ranges = evidenceRanges(text, ['Interest and dividend income 203 206'])
  assert.equal(ranges.length, 1)
  assert.deepEqual(row.values.map(v => evidenceRuns(v, ranges).filter(r => r.number).map(r => r.text).join('')), ['203', '206'])
  assert.ok(table.rows.find(r => r.label[0].text === 'Sales of products').values.every(v => evidenceRuns(v, ranges).every(r => !r.cited)))
})

for (const [stem, page, label, values] of [
  ['atlas_copco_2025', 106, 'Revenues', ['3', '168 343', '176 771']],
  ['investor_2025', 121, 'Net sales', ['8', '64,826', '63,196']],
  ['saab_2025_sv', 151, 'Försäljningsintäkter', ['4', '79 146', '63 751']],
  ['skf_2025', 99, 'Gross profit', ['', '24,525', '27,373']],
  ['karnell_2025', 106, 'Liabilities to credit institutions', ['43.5', '353.7', '-', '397.2']],
]) {
  test(`${stem}: restores the actual report columns, including optional notes and maturity buckets`, () => {
    const pages = readFileSync(`../data/kb/${stem}/pages.jsonl`, 'utf8').trim().split('\n').map(JSON.parse)
    const text = pages.find(p => p.page === page).text
    const blocks = sourceDocument(text)
    const displayed = blocks.flatMap(b => b.type === 'text' ? b.lines : [...b.headers, ...b.rows.flatMap(r => [...r.label, ...r.values])]).map(s => s.text).join('')
    assert.equal(displayed.replace(/\s/g, ''), text.replace(/\s/g, ''), 'Every source word and figure must survive formatting')
    const rows = blocks.filter(b => b.type === 'table').flatMap(b => b.rows)
    const row = rows.find(r => r.label.map(l => l.text).join(' ') === label)
    assert.ok(row, `Missing table row for ${label}`)
    assert.deepEqual(row.values.map(v => v.text), values)
    for (const r of rows) for (const span of [...r.label, ...r.values]) assert.equal(text.slice(span.start, span.end), span.text)
  })
}

test('ambiguous columns and narrative year mentions are not guessed into a table', () => {
  for (const text of ['2025\n2024\nDebt\n100\n200\n300\nCash\n50\n60', '2025\n2024\nA year of change\nWe earned 203 million.', '2025\n2023\nDebt\n100\n200\nCash\n50\n60']) {
    assert.ok(sourceDocument(text).every(b => b.type === 'text'))
  }
})

test('wrapped labels and accounting values keep their columns', () => {
  const text = 'Statement\n2025\n2024\nInterest and\ndividend income\n203\n206\nFinance expense\n(86)\n(74)\nFootnote.'
  const table = sourceDocument(text).find(b => b.type === 'table')
  assert.deepEqual(table.rows[0].label.map(l => l.text), ['Interest and', 'dividend income'])
  assert.deepEqual(table.rows[1].values.map(v => v.text), ['(86)', '(74)'])
  assert.equal(sourceDocument(text).at(-1).lines[0].text, 'Footnote.')
})

test('current parser inline year headers retain aligned rows and exact evidence offsets', () => {
  const text = 'Consolidated statement\nYear ended December 31 ($ in millions) 2025 2024\nSales of products 27,669 25,531\nInterest and dividend income 203 206\nFinance expense (86) (74)'
  const blocks = sourceDocument(text)
  const table = blocks.find(b => b.type === 'table')
  assert.deepEqual(table.headers.map(h => h.text), ['2025', '2024'])
  assert.deepEqual(table.rows[1].values.map(v => v.text), ['203', '206'])
  const spans = blocks.flatMap(b => b.type === 'text' ? b.lines : [...b.headers, ...b.rows.flatMap(r => [...r.label, ...r.values])])
  assert.equal(spans.map(s => s.text).join('').replace(/\s/g, ''), text.replace(/\s/g, ''))
  for (const span of spans) assert.equal(text.slice(span.start, span.end), span.text)
  const ranges = evidenceRanges(text, ['Interest and dividend income 203 206'])
  assert.deepEqual(table.rows[1].values.flatMap(v => evidenceRuns(v, ranges)).filter(r => r.number).map(r => r.text), ['203', '206'])
})

test('only whole quoted passages are highlighted, including repeats and CRLF whitespace', () => {
  const text = 'Other income 203\r\nInterest income\r\n203\r\n206\r\nInterest income 203 206'
  const ranges = evidenceRanges(text, ['Interest income 203 206'])
  assert.equal(ranges.length, 2)
  assert.ok(ranges.every(r => r.start > text.indexOf('Other income')))
  assert.equal(evidenceRanges(text, ['Interest income 999']).length, 0)
  const span = { text, start: 0, end: text.length }
  const runs = evidenceRuns(span, ranges)
  assert.equal(runs.map(r => r.text).join(''), text)
  assert.ok(!runs.find(r => r.text.includes('Other income')).cited)
})

test('a partial numeric quote does not turn part of a larger amount into a highlighted figure', () => {
  const text = 'Income 2030'
  assert.ok(evidenceRuns({ text, start: 0, end: text.length }, evidenceRanges(text, ['Income 203'])).every(run => !run.number))
})
