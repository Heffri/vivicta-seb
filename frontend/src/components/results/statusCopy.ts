import type { Check, Field } from '../../types.ts'

const CHECKS: Record<string, { title: string; explanation: string }> = {
  gross_profit_arith: { title: 'Gross profit', explanation: 'Compares revenue minus cost of sales with gross profit.' },
  net_profit_arith: { title: 'Net profit', explanation: 'Compares profit before tax, adjusted for tax and discontinued operations, with net profit.' },
  maturity_sums_to_total: { title: 'Debt repayments', explanation: 'Compares debt due in each time period with total debt.' },
  margin_sanity: { title: 'Operating profit scale', explanation: 'Checks for a large unit mismatch between operating profit and revenue. This does not verify either value.' },
}

export function explainCheck(check: Check) {
  if (check.status === 'unavailable') return { title: CHECKS[check.name]?.title ?? check.name.replaceAll('_', ' '), status: 'Cannot check', explanation: check.detail, unavailable: true }
  if (check.stale) return { title: CHECKS[check.name]?.title ?? check.name.replaceAll('_', ' '), status: 'Needs recalculation', explanation: 'A figure was corrected by a person. The calculation below predates that correction and is no longer valid.', unavailable: true }
  const known = CHECKS[check.name]
  const missing = check.detail.startsWith('missing:')
  const error = /^[A-Za-z]+Error:/.test(check.detail)
  const scale = check.name === 'margin_sanity'
  const margin = scale ? check.detail.match(/operating margin\s+(-?\d+(?:\.\d+)?)%/i)?.[1] : undefined
  return {
    title: known?.title ?? check.name.replaceAll('_', ' '),
    status: missing || error ? 'Not checked' : check.passed ? (scale ? 'Scale check passed' : known ? 'Adds up' : 'Check passed') : 'Needs review',
    explanation: missing ? 'A required figure is missing. Open the report to find it before checking this total.'
      : error ? 'The calculation could not be completed. Review the figures in the report.'
      : known ? `${margin === undefined ? '' : `Operating margin: ${margin}%. `}${known.explanation}${scale ? '' : ' Allows for rounding of up to 2 in the reported unit.'}${check.passed ? '' : ' Compare the extracted figures with the report.'}`
      : 'See the calculation details and compare the figures with the report.',
    unavailable: missing || error,
  }
}

export function explainWarning(warning: string, fields: Field[]) {
  const key = warning.split(':', 1)[0]
  const field = fields.find((f) => f.key === key)
  const ambiguous = /column ambiguous/i.test(warning)
  const epsColumn = field?.key === 'eps_basic' || /basic vs diluted/i.test(warning)
  return {
    field,
    title: field?.label ?? 'Report note',
    explanation: ambiguous
      ? epsColumn
        ? 'The extraction noted an unclear column. Check whether this figure is basic or diluted earnings per share before using it.'
        : 'The extraction noted an unclear column. Check the column heading and figure in the report before using it.'
      : field
        ? 'An extraction note records an issue or adjustment for this figure. See the details and source below.'
        : 'See the extraction details below for issues or adjustments recorded while reading the report.',
  }
}
