import { useState } from 'react'
import { reviewField } from '@/api'
import { Button } from '@/components/ui/button'
import type { Extraction, Field, HumanReview, ReviewComponent } from '@/types'

type ComponentDraft = { label: string; value: string; page: string; quote: string }

export function HumanReviewForm({ extraction, field, citation, onCitationChange, onSaved }: { extraction: Extraction; field: Field; citation: { page: string; quote: string }; onCitationChange: (citation: { page: string; quote: string }) => void; onSaved: (result: Extraction) => void }) {
  const [decision, setDecision] = useState<HumanReview['decision']>('confirmed')
  const [reviewer, setReviewer] = useState(field.human_review?.reviewer ?? '')
  const [note, setNote] = useState('')
  const [value, setValue] = useState(String(field.value ?? ''))
  const [unit, setUnit] = useState(field.unit ?? '')
  const [period, setPeriod] = useState(field.period ?? '')
  const [useComponents, setUseComponents] = useState(false)
  const [components, setComponents] = useState<ComponentDraft[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputClass = 'w-full rounded-md border bg-background px-3 py-2 text-sm'
  const componentNumbers = components.map((component) => Number(component.value))
  const completeComponents = components.length > 0 && components.every((component, index) => component.label.trim() && component.quote.trim() && Number.isFinite(componentNumbers[index]) && Number.isInteger(Number(component.page)) && Number(component.page) > 0)
  const componentTotal = completeComponents ? componentNumbers.reduce((sum, component) => sum + component, 0) : null
  const updateComponent = (index: number, patch: Partial<ComponentDraft>) => setComponents((current) => current.map((component, i) => i === index ? { ...component, ...patch } : component))
  const addComponent = () => setComponents((current) => [...current, { label: `Component ${current.length + 1}`, value: '', page: '', quote: '' }])
  return <form aria-label={`Review ${field.label}`} className="space-y-3 rounded-xl border bg-card p-4" onSubmit={async e => {
    e.preventDefault(); setError('')
    let componentPayload: ReviewComponent[] | undefined
    if (decision === 'corrected' && useComponents) {
      if (!completeComponents) { setError('Each component needs a label, finite value, page and quoted text.'); return }
      componentPayload = components.map((component, index) => ({ label: component.label.trim(), value: componentNumbers[index], page: Number(component.page), quote: component.quote.trim() }))
    }
    const citationRequested = !useComponents && (citation.page.trim() || citation.quote.trim())
    if (citationRequested && (!Number.isInteger(Number(citation.page)) || Number(citation.page) < 1 || !citation.quote.trim())) { setError('A citation needs a positive page number and quoted text.'); return }
    setBusy(true)
    try {
      const trimmed = value.trim()
      const corrected = trimmed === '' ? null : Number.isFinite(Number(trimmed)) ? Number(trimmed) : trimmed
      onSaved(await reviewField(extraction.report_id, {
        section: extraction.section, key: field.key, expected: field, decision, reviewer, note,
        ...(decision === 'corrected' ? { unit: unit.trim() || null, period: period.trim() || null, ...(componentPayload ? { components: componentPayload } : { value: corrected }) } : {}),
        ...(citationRequested ? { source_page: Number(citation.page), source_quote: citation.quote.trim() } : {}),
      }))
      setNote('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save review') }
    finally { setBusy(false) }
  }}>
    <h3 className="font-semibold">Review {field.label}</h3>
    <p className="text-xs text-muted-foreground">Check the source before confirming. Your name is self-reported. Original values and previous decisions remain in the history.</p>
    {field.human_review && <p className="text-sm">Last review: {field.human_review.reviewer} · {new Date(field.human_review.at).toLocaleString()} · {field.human_review.note || field.human_review.decision}{field.human_review.source_verified ? ' · submitted citation checked on its page' : ''}</p>}
    <fieldset disabled={busy} className="space-y-3">
      <label className="block text-sm">Decision<select className={inputClass} value={decision} onChange={e => setDecision(e.target.value as HumanReview['decision'])}><option value="confirmed">Confirm against source</option><option value="corrected">Correct figure</option><option value="unresolved">Leave unresolved</option></select></label>
      {decision === 'corrected' && <>
        <div className="grid gap-2 sm:grid-cols-3"><label className="text-sm">Value<input disabled={useComponents} className={inputClass} type={typeof field.value === 'string' ? 'text' : 'number'} step="any" value={value} onChange={e => setValue(e.target.value)} placeholder="Blank = not found" /></label><label className="text-sm">Unit<input className={inputClass} maxLength={80} value={unit} onChange={e => setUnit(e.target.value)} /></label><label className="text-sm">Period<input className={inputClass} maxLength={80} value={period} onChange={e => setPeriod(e.target.value)} /></label><p className="text-xs text-muted-foreground sm:col-span-3">Use a decimal point and no thousands separators. Calculations are rerun after saving. Previous results remain in the audit history.</p></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={useComponents} onChange={e => setUseComponents(e.target.checked)} /> Sum printed components instead of entering one total</label>
        {useComponents ? <div className="space-y-2 rounded-lg border p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">Components</p><Button type="button" variant="outline" size="xs" onClick={addComponent}>Add component</Button></div>{components.map((component, index) => <div key={index} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1.1fr_0.8fr_0.65fr_2fr_auto]"><label className="text-xs">Label<input aria-label={`Component ${index + 1} label`} className={inputClass} maxLength={160} value={component.label} onChange={e => updateComponent(index, { label: e.target.value })} /></label><label className="text-xs">Value<input aria-label={`Component ${index + 1} value`} className={inputClass} type="number" step="any" value={component.value} onChange={e => updateComponent(index, { value: e.target.value })} /></label><label className="text-xs">Page<input aria-label={`Component ${index + 1} page`} className={inputClass} type="number" min="1" value={component.page} onChange={e => updateComponent(index, { page: e.target.value })} /></label><label className="text-xs">Quoted text<textarea aria-label={`Component ${index + 1} quote`} className={inputClass} maxLength={8000} value={component.quote} onChange={e => updateComponent(index, { quote: e.target.value })} /></label><Button type="button" variant="ghost" size="xs" className="self-end" onClick={() => setComponents((current) => current.filter((_, i) => i !== index))}>Remove</Button></div>)}<p className="text-xs text-muted-foreground">{componentTotal === null ? 'Add every component to calculate an exact sum.' : `Component sum: ${componentTotal}`}</p></div> : <div className="grid gap-2 sm:grid-cols-[9rem_1fr]"><label className="text-sm">Citation page<input aria-label="Citation page" className={inputClass} type="number" min="1" value={citation.page} onChange={e => onCitationChange({ ...citation, page: e.target.value })} placeholder="PDF page" /></label><label className="text-sm">Citation quote<textarea aria-label="Citation quote" className={inputClass} maxLength={8000} value={citation.quote} onChange={e => onCitationChange({ ...citation, quote: e.target.value })} placeholder="Verbatim row from that page" /></label><p className="text-xs text-muted-foreground sm:col-span-2">A supplied citation is checked against the saved page text before it can replace the current source.</p></div>}
      </>}
      <label className="block text-sm">Your name<input required maxLength={120} className={inputClass} value={reviewer} onChange={e => setReviewer(e.target.value)} /></label>
      <label className="block text-sm">Review note<textarea required={decision !== 'confirmed'} maxLength={2000} className={inputClass} value={note} onChange={e => setNote(e.target.value)} placeholder="What did you check or correct?" /></label>
      <Button type="submit">{busy ? 'Saving…' : 'Save review'}</Button>
    </fieldset>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {!!field.review_history?.length && <details><summary className="cursor-pointer text-sm">Review history ({field.review_history.length})</summary><ol className="mt-2 space-y-2 text-xs">{field.review_history.map((r, i) => <li key={i}>{r.reviewer} · {new Date(r.at).toLocaleString()} · {r.decision}<br />Previous: {String(r.previous.value ?? 'Not found')} {r.previous.unit} ({r.previous.period}){r.previous.source ? ` · p.${r.previous.source.page} “${r.previous.source.quote}”` : ''}{r.previous.components?.length ? ` · ${r.previous.components.length} components` : ''}<br />{r.note}</li>)}</ol></details>}
  </form>
}
