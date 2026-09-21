import { useEffect, useState } from 'react'
import { getComparison, getReviewQueue, saveBasis } from '@/api'
import type { Comparison, Extraction, KbEntry, QueueIssue } from '@/types'
import { Button } from '@/components/ui/button'

const input = 'w-full rounded-lg border border-input bg-background p-2 text-foreground'
const labels: Record<string, string> = { entity: 'Reporting entity', consolidation: 'Group or parent', period: 'Fiscal period (exact field period)', currency: 'Currency', scale: 'Scale', source: 'Source references (page and supporting text)', restatement: 'Restatement status', debt_basis: 'Debt measurement', leases: 'Lease treatment', bucket_mapping: 'Native intervals mapped to <1 / 1–5 / >5 years' }
const choices: Record<string, string[]> = { consolidation: ['Group', 'Parent'], scale: ['Units', 'Thousands', 'Millions', 'Billions'], restatement: ['As reported', 'Restated (explain in note)'], debt_basis: ['Carrying amounts', 'Contractual undiscounted cash flows'], leases: ['Included', 'Excluded'] }

export function BasisPanel({ extraction: x, onUpdated }: { extraction: Extraction; onUpdated: (x: Extraction) => void }) {
  const keys = ['entity', 'consolidation', 'period', 'currency', 'scale', 'source', 'restatement', ...(x.section === 'debt_maturity' ? ['debt_basis', 'leases', 'bucket_mapping'] : [])]
  const [values, setValues] = useState<Record<string, string>>(x.basis?.values ?? {})
  const [reviewer, setReviewer] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return <details className="rounded-xl border bg-card p-4" id="basis-review">
    <summary className="cursor-pointer font-semibold">Basis of figures · {x.ready ? 'Ready for analyst use' : `${x.issues?.filter(issue => issue.kind === 'basis').length ?? 'Unresolved'} definitions to confirm`}</summary>
    <p className="my-3 text-sm text-muted-foreground">Unknown definitions remain unresolved. Enter definitions from the source and explain assumptions in your note. Human confirmation is separate from automated evidence.</p>
    {x.basis && <p className="mb-3 text-sm">Last confirmed by {x.basis.reviewer} · {x.basis.at} · {x.basis.note}</p>}
    <form className="space-y-3" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { onUpdated(await saveBasis(x.report_id, { section: x.section, expected: x.basis ?? {}, values, reviewer, note })) } catch (err) { setError((err as Error).message) } finally { setBusy(false) } }}>
      <div className="grid gap-3 md:grid-cols-2">{keys.map(k => <label key={k} className="text-sm">{labels[k]}{choices[k] ? <select aria-label={labels[k]} className={input} value={values[k] ?? ''} onChange={e => setValues({ ...values, [k]: e.target.value })}><option value="">Unknown / not confirmed</option>{choices[k].map(v => <option key={v}>{v}</option>)}</select> : <input aria-label={labels[k]} className={input} maxLength={2000} value={values[k] ?? ''} placeholder="Unknown / not confirmed" onChange={e => setValues({ ...values, [k]: e.target.value })} />}</label>)}</div>
      <label className="block text-sm">Basis reviewer<input required maxLength={120} className={input} value={reviewer} onChange={e => setReviewer(e.target.value)} /></label>
      <label className="block text-sm">Basis review note<textarea required maxLength={2000} className={input} value={note} onChange={e => setNote(e.target.value)} /></label>
      {error && <p role="alert">{error}</p>}<Button type="submit" disabled={busy || !x.stem}>{busy ? 'Saving…' : 'Save basis review'}</Button>
    </form>
    {!!x.check_history?.length && <details className="mt-3"><summary>Previous calculation results ({x.check_history.length})</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{JSON.stringify(x.check_history, null, 2)}</pre></details>}
    {!!x.basis_history?.length && <details className="mt-3"><summary>Basis history ({x.basis_history.length})</summary>{x.basis_history.map((b, i) => <pre key={i} className="mt-2 whitespace-pre-wrap break-words text-xs">{JSON.stringify(b, null, 2)}</pre>)}</details>}
  </details>
}

const number = (v: number | string | null) => v === null ? 'N/A' : typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : v
export function YearComparison({ extraction: x, onChange }: { extraction: Extraction; onChange: (value: Comparison | null) => void }) {
  const [previous, setPrevious] = useState('')
  const [result, setResult] = useState<Comparison | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let stale = false
    setResult(null); onChange(null); setError('')
    if (x.stem) getComparison(x.stem, x.section, previous || undefined).then(r => { if (!stale && Array.isArray(r.rows)) { setResult(r); onChange(r) } }).catch(e => { if (!stale) setError(e.message) })
    return () => { stale = true }
  }, [x, previous, onChange])
  if (!x.stem) return null
  return <section className="space-y-3 rounded-xl border bg-card p-4" aria-label="Prior-year comparison">
    <h2 className="font-semibold">Prior-year comparison {result?.previous_year && `· ${result.previous_year} → ${result.current_year}`}</h2>
    <p className="text-sm text-muted-foreground">Saved statements only. No currency conversion or inferred restatement. Percentage change uses the absolute previous value.</p>
    <label className="block text-sm">Comparison source<select aria-label="Comparison source" className={input} value={previous || result?.previous_stem || ''} onChange={e => setPrevious(e.target.value)}><option value="">Immediately preceding year (if unique)</option>{result?.candidates.map(c => <option key={c.stem} value={c.stem}>{c.fiscal_year} · {c.company} · {c.stem}</option>)}</select></label>
    {error && <p role="alert">{error}</p>}{result?.reasons.map(r => <p key={r} className="text-sm text-amber-700 dark:text-amber-300">{r}</p>)}
    {result?.restatement && <p className="text-xs">Current: {result.restatement.current} · Previous: {result.restatement.previous}</p>}
    {!!result?.rows.length && <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Figure', 'Previous', 'Current', 'Change', '%', 'Notes'].map(h => <th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{result.rows.map(r => <tr key={r.key} className="border-t"><th className="p-2 font-normal">{r.label}</th><td className="p-2">{number(r.previous)}</td><td className="p-2">{number(r.current)}</td><td className="p-2">{number(r.delta)}</td><td className="p-2">{number(r.percent)}</td><td className="p-2">{r.sign_change && 'Sign change. '}{r.reason}</td></tr>)}</tbody></table></div>}
  </section>
}

export function ReviewQueue({ onOpen }: { onOpen: (report: KbEntry, section: string, key?: string) => void }) {
  const [issues, setIssues] = useState<QueueIssue[] | null>(null)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ company: '', year: '', section: '', kind: '' })
  useEffect(() => { let stale = false; getReviewQueue().then(r => { if (!stale) setIssues(r) }).catch(e => { if (!stale) setError(e.message) }); return () => { stale = true } }, [])
  const value = (i: QueueIssue, k: string) => k === 'company' ? i.report.company ?? i.report.stem : k === 'year' ? String(i.report.fiscal_year ?? '') : k === 'section' ? i.section : i.kind
  const visible = issues?.filter(i => Object.entries(filters).every(([k, v]) => !v || value(i, k) === v))
  const groups = new Map<string, { report: KbEntry; section: string; issues: QueueIssue[] }>()
  for (const issue of visible ?? []) {
    const key = `${issue.report.stem}:${issue.section}`
    if (!groups.has(key)) groups.set(key, { report: issue.report, section: issue.section, issues: [] })
    groups.get(key)!.issues.push(issue)
  }
  const target = (issue: QueueIssue) => issue.kind === 'field' ? issue.key : issue.kind === 'basis' ? '@basis' : '@checks'
  return <section className="space-y-5"><h1 className="text-2xl font-semibold">Review</h1><p className="text-muted-foreground">Outstanding checks in the saved Wallenberg collection, grouped by statement. Open a statement to review its figures and sources.</p>
    <div className="grid gap-3 sm:grid-cols-4">{Object.entries(filters).map(([k, v]) => <label key={k} className="text-sm capitalize">{k}<select aria-label={k} className={input} value={v} onChange={e => setFilters({ ...filters, [k]: e.target.value })}><option value="">All</option>{[...new Set(issues?.map(i => value(i, k)))].sort().map(v => <option key={v} value={v}>{v.replaceAll('_', ' ')}</option>)}</select></label>)}</div>
    {error && <p role="alert">{error}</p>}{!issues && !error && <p>Loading review queue…</p>}
    {issues && <p role="status">{groups.size} {groups.size === 1 ? 'statement' : 'statements'} · {visible?.length} outstanding {visible?.length === 1 ? 'check' : 'checks'}</p>}
    {issues && !visible?.length && <p className="text-sm text-muted-foreground">{issues.length ? 'No checks match these filters.' : 'No outstanding checks in this collection.'}</p>}
    <div className="space-y-3">{[...groups].map(([key, group]) => <article key={key} aria-label={`${group.report.company ?? group.report.stem} ${group.report.fiscal_year ?? ''} ${group.section.replaceAll('_', ' ')}`} className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="font-medium">{group.report.company ?? group.report.stem} · {group.report.fiscal_year ?? 'Year unknown'}</h2><p className="mt-1 text-sm text-muted-foreground">{group.section.replaceAll('_', ' ')} · {group.issues.length} outstanding {group.issues.length === 1 ? 'check' : 'checks'}</p></div>
        <Button variant="outline" onClick={() => onOpen(group.report, group.section, target(group.issues[0]))}>Review statement</Button>
      </div>
      <details className="mt-3 border-t pt-3"><summary className="cursor-pointer text-sm text-muted-foreground">Show outstanding checks</summary>
        <ul className="mt-2 divide-y">{group.issues.map((issue, n) => <li key={`${issue.kind}:${issue.key}:${n}`} className="flex items-start justify-between gap-3 py-2 text-sm"><span>{issue.detail}</span><button type="button" className="shrink-0 rounded px-2 text-primary underline underline-offset-4 focus-visible:outline-2" aria-label={`Review ${issue.detail}`} onClick={() => onOpen(group.report, group.section, target(issue))}>Review</button></li>)}</ul>
      </details>
    </article>)}</div>
  </section>
}
