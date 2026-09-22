import type { Field } from '@/types'

type Verification = {
  label: 'Human confirmed' | 'Human corrected' | 'Not found' | 'Not printed in this report' | 'Not reported' | 'Not checked' | 'Needs review' | 'Calculated from report' | 'Reported as zero' | 'Checks passed'
  variant: 'secondary' | 'warning' | 'success'
  detail: string
}

/** Labels that are a human's task (the backend's field issues, mirrored). */
export const NEEDS_HUMAN: Verification['label'][] = ['Needs review', 'Not checked', 'Not found']

/** `notReported`: the backend listed this optional field in `not_reported` — the report prints no such row. */
export function fieldVerification(field: Field, notReported = false): Verification {
  if (field.human_review) {
    const r = field.human_review
    return { label: r.decision === 'unresolved' ? 'Needs review' : r.decision === 'corrected' ? 'Human corrected' : 'Human confirmed', variant: r.decision === 'unresolved' ? 'warning' : 'success', detail: `${r.reviewer} · ${r.at}: ${r.note || 'Confirmed against the source.'} Human review is separate from automated checks.` }
  }
  if (field.value === null) {
    // The report's maturity table prints no column for this window — the header row quoted in
    // the source is the proof. An explicit absence, not a missed figure and not zero.
    if ((field.evidence ?? []).includes('absent_in_table'))
      return { label: 'Not printed in this report', variant: 'secondary', detail: `The maturity table on ${field.source ? `page ${field.source.page}` : 'this report'} prints no column for this window — its own header row is the source quoted here. This is an explicit absence, not a missed figure and not zero.` }
    return notReported ? { label: 'Not reported', variant: 'secondary', detail: 'The report has no such row. This is not zero and needs no review; mark it unresolved below if the report does print one.' }
      : { label: 'Not found', variant: 'secondary', detail: 'No figure was extracted. This does not mean zero.' }
  }
  const evidence = field.evidence ?? []
  if (!evidence.length) return { label: 'Not checked', variant: 'secondary', detail: `No automated checks were recorded. Check ${field.value} against the report row, its ${field.period || 'year'} column and ${field.unit || 'currency/unit'}, then compare the related totals.` }
  const actions: Record<string, string> = {
    quote_on_page: `Check the quoted text against ${field.source ? `page ${field.source.page}` : 'the original report'}. It has not been matched to that page.`,
    label_known: `Confirm that “${field.raw_label || field.label}” represents ${field.label.toLowerCase()}, not a different measure.`,
    period_ok: `Confirm the figure is in the ${field.period || 'intended year'} column, not the comparative year.`,
    page_is_statement: 'Confirm the figure comes from the required statement, not a note or a parent-company table.',
    unit_ok: `Confirm the table uses ${field.unit || 'the intended currency and scale'} (for example, thousands versus millions).`,
  }
  const missing = Object.entries(actions).filter(([code]) => !evidence.includes(code)).map(([, text]) => text)
  if (!field.source?.quote || !Number.isInteger(field.source.page) || field.source.page < 1) missing.unshift('No usable source reference is available.')
  // value_in_quote, or exactly one stand-in for it (docs/CONFIDENCE.md): two at once prove nothing
  const standIns = ['value_derived', 'stated_zero', 'printed_nil'].filter((code) => evidence.includes(code))
  if (!evidence.includes('value_in_quote') && standIns.length !== 1) {
    missing.push(standIns.length > 1 ? 'Two different readings claim this value. Confirm which one the report supports.'
      : `Find ${field.value} in the quoted row and confirm the sign and decimal scale. The number has not been matched to the text.`)
  }
  if (missing.length) return { label: 'Needs review', variant: 'warning', detail: missing.join(' ') }
  if (evidence.includes('value_derived')) return { label: 'Calculated from report', variant: 'secondary', detail: 'Calculated from source rows, rather than copied from a printed total. Review those rows in the report.' }
  if (evidence.includes('printed_nil')) return { label: 'Reported as zero', variant: 'secondary', detail: 'The row prints a dash in this column: the report says nothing is due in that window. Read as 0, with the row shown as the source.' }
  if (evidence.includes('stated_zero')) return { label: 'Reported as zero', variant: 'secondary', detail: 'The report states in words that there is none. Read as 0, with that text shown as the source.' }
  return { label: 'Checks passed', variant: 'success', detail: 'The figure matches its source text, label, year and unit. See the separate calculation checks for arithmetic. This is an automated cross-check, not confirmation that the report itself is correct.' }
}
