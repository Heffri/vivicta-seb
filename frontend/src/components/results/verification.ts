import type { Field } from '@/types'

type Verification = {
  label: 'Not found' | 'Not checked' | 'Needs review' | 'Calculated from report' | 'Checks passed'
  variant: 'secondary' | 'warning' | 'success'
  detail: string
}

export function fieldVerification(field: Field): Verification {
  if (field.value === null) return { label: 'Not found', variant: 'secondary', detail: 'No figure was extracted. This does not mean zero.' }
  const evidence = field.evidence ?? []
  if (!evidence.length) return { label: 'Not checked', variant: 'secondary', detail: `No automated checks were recorded. Check ${field.value} against the report row, its ${field.period || 'year'} column and ${field.unit || 'currency/unit'}, then compare the related totals.` }
  const actions: Record<string, string> = {
    arith_ok: 'Arithmetic is not verified. Compare this figure with the related totals in the calculation checks.',
    quote_on_page: `Check the quoted text against ${field.source ? `page ${field.source.page}` : 'the original report'}. It has not been matched to that page.`,
    label_known: `Confirm that “${field.raw_label || field.label}” represents ${field.label.toLowerCase()}, not a different measure.`,
    period_ok: `Confirm the figure is in the ${field.period || 'intended year'} column, not the comparative year.`,
    page_is_statement: 'Confirm the figure comes from the required statement, not a note or a parent-company table.',
    unit_ok: `Confirm the table uses ${field.unit || 'the intended currency and scale'} (for example, thousands versus millions).`,
  }
  const missing = Object.entries(actions).filter(([code]) => !evidence.includes(code)).map(([, text]) => text)
  if (!field.source?.quote || !Number.isInteger(field.source.page) || field.source.page < 1) missing.unshift('No usable source reference is available.')
  if (!evidence.includes('value_in_quote') && !evidence.includes('value_derived')) {
    missing.push(evidence.includes('printed_nil') ? 'A dash was interpreted as zero. Confirm this in the report.'
      : evidence.includes('stated_zero') ? 'Zero was inferred from the report text. Confirm the interpretation.'
      : `Find ${field.value} in the quoted row and confirm the sign and decimal scale. The number has not been matched to the text.`)
  }
  if (missing.length) return { label: 'Needs review', variant: 'warning', detail: missing.join(' ') }
  if (evidence.includes('value_derived')) return { label: 'Calculated from report', variant: 'secondary', detail: 'Calculated from source rows, rather than copied from a printed total. Review those rows in the report.' }
  return { label: 'Checks passed', variant: 'success', detail: 'The figure matches its source text, label, year and unit. No related arithmetic check failed. This is an automated cross-check, not confirmation that the report itself is correct.' }
}
