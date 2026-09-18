// Run: node --experimental-strip-types --test src/components/results/statusCopy.test.ts
/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { explainCheck, explainWarning } from './statusCopy.ts'
import type { Field } from '../../types.ts'

test('calculation results distinguish matching, missing and failed figures', () => {
  const check = { name: 'gross_profit_arith', passed: true, detail: '1 + 2 == 3' }
  assert.equal(explainCheck(check).status, 'Adds up')
  assert.equal(explainCheck({ ...check, passed: false }).status, 'Needs review')
  assert.equal(explainCheck({ ...check, passed: false, detail: 'missing: revenue' }).status, 'Not checked')
  assert.equal(explainCheck({ ...check, passed: false, detail: 'ZeroDivisionError: division by zero' }).status, 'Not checked')
  assert.match(explainCheck({ ...check, name: 'margin_sanity' }).explanation, /does not verify/)
  assert.match(explainCheck({ ...check, name: 'margin_sanity', detail: 'operating margin 20.9%' }).explanation, /Operating margin: 20\.9%/)
  assert.equal(explainCheck({ ...check, name: 'future_check' }).status, 'Check passed')
})

test('ambiguous EPS columns get an actionable note and preserve the source field', () => {
  const field: Field = { key: 'eps_basic', label: 'Basic earnings per share', value: 3, unit: 'SEK', period: '2025', raw_label: null, confidence: 0.5, evidence: [], source: { page: 65, quote: 'EPS 3' } }
  const note = explainWarning('eps_basic: quote found on page 65 but value column ambiguous (basic vs diluted) — confidence lowered', [field])
  assert.equal(note.title, field.label)
  assert.equal(note.field, field)
  assert.match(note.explanation, /basic or diluted/)
  assert.doesNotMatch(note.explanation, /confidence/)
  assert.equal(explainWarning('new unknown warning', []).title, 'Report note')
  assert.doesNotMatch(explainWarning('revenue: value column ambiguous', []).explanation, /earnings per share/)
})
