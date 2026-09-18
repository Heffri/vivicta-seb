import type { Field } from '@/types'

const REQUIRED = {
  quote_on_page: 'The quoted text has not been matched to the report page.',
  arith_ok: 'A related arithmetic check did not pass.',
  label_known: 'The report label has not been matched to this financial measure.',
  period_ok: 'The year has not been confirmed.',
  page_is_statement: 'The source page has not been confirmed as the relevant statement.',
  unit_ok: 'The currency or unit has not been confirmed.',
}

type Verification = {
  label: 'Not found' | 'Not checked' | 'Needs review' | 'Calculated from report' | 'Checks passed'
  variant: 'secondary' | 'warning' | 'success'
  detail: string
}

export function fieldVerification(field: Field): Verification {
  if (field.value === null) return { label: 'Not found', variant: 'secondary', detail: 'No figure was extracted. This does not mean zero.' }
  const evidence = field.evidence ?? []
  if (!evidence.length) return { label: 'Not checked', variant: 'secondary', detail: 'This result has no recorded verification evidence. Check the figure in the report.' }
  const missing = Object.entries(REQUIRED).filter(([code]) => !evidence.includes(code)).map(([, text]) => text)
  if (!field.source?.quote || !Number.isInteger(field.source.page) || field.source.page < 1) missing.unshift('No usable source reference is available.')
  if (!evidence.includes('value_in_quote') && !evidence.includes('value_derived')) {
    missing.push(evidence.includes('printed_nil') ? 'A dash was interpreted as zero. Confirm this in the report.'
      : evidence.includes('stated_zero') ? 'Zero was inferred from the report text. Confirm the interpretation.'
      : 'The number has not been matched to the quoted text.')
  }
  if (missing.length) return { label: 'Needs review', variant: 'warning', detail: missing.join(' ') }
  if (evidence.includes('value_derived')) return { label: 'Calculated from report', variant: 'secondary', detail: 'Calculated from source rows, rather than copied from a printed total. Review those rows in the report.' }
  return { label: 'Checks passed', variant: 'success', detail: 'The figure matches its source text, label, year and unit. No related arithmetic check failed. This is an automated cross-check, not confirmation that the report itself is correct.' }
}
