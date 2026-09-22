import { BasisPanel, YearComparison } from '@/components/AnalystWorkbench'
import { ArrowLeft, Download, FileText, ListChecks, Columns3, MessageCircle, ChartColumn } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { csvUrl, pptxUrl, extractSection, fillField } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { HumanReviewForm } from '@/components/results/HumanReviewForm'
import { FieldsTable } from '@/components/results/FieldsTable'
import { isMaturitySection, MaturityChart } from '@/components/results/MaturityChart'
import { NotFoundBanner } from '@/components/results/NotFoundBanner'
import { SourcePanel, type Viewer } from '@/components/results/SourcePanel'
import { StatusCards } from '@/components/results/StatusCards'
import { Badge } from '@/components/ui/badge'
import { scrollContent } from '@/components/shell/scrollContent'
import { fieldVerification, NEEDS_HUMAN } from '@/components/results/verification'
import { Button, buttonVariants } from '@/components/ui/button'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import type { Comparison, Extraction, Field, FieldFill, Source } from '@/types'

type Props = {
  extraction: Extraction
  sectionTitle: string
  onUpdated: (result: Extraction) => void
  onReset: () => void
  onBack?: () => void
  navigation?: ReactNode
  initialField?: string
  initialPage?: number | null // from a citation chip on the compare view
}

// 152340 → "152 340" (thin space U+2009), sign kept, decimals as-is, null → em dash.
export const fmtValue = (v: Field['value']) =>
  v === null
    ? '—'
    : typeof v === 'number'
      ? v.toLocaleString('en-US', { maximumFractionDigits: 6 }).replaceAll(',', ' ')
      : v

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

const VIEWER_KEY = 'provenance-viewer'
const loadViewer = (): Viewer => {
  try {
    return localStorage.getItem(VIEWER_KEY) === 'image' ? 'image' : 'pdf'
  } catch {
    return 'pdf'
  }
}

export function ResultsView({ extraction, sectionTitle, onUpdated, onReset, onBack, navigation, initialPage, initialField }: Props) {
  const { report_id, company, fiscal_year, currency, section, maturity_basis, fields, checks, warnings } = extraction
  const [selectedKey, setSelectedKey] = useState<string | null>(() => initialField ?? fields.find((f) => f.source)?.key ?? null)
  const [rerunning, setRerunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const rerun = async () => {
    setRerunning(true); setRunError(null)
    try { onUpdated(await extractSection(report_id, section, true)) }
    catch (e) { setRunError((e as Error).message) }
    finally { setRerunning(false) }
  }
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [view, setView] = useState<'figures' | 'review' | 'comparison' | 'ask' | 'export' | 'chart'>(initialField?.startsWith('@') ? 'review' : 'figures')
  const focusSource = useRef(false)
  const [reading, setReading] = useState(false)
  const [brokenPage, setBrokenPage] = useState<number | null>(null)
  const [askPage, setAskPage] = useState<number | null>(initialPage ?? null) // citation chip override; a row click clears it
  // Keep the last evidence page visible when the analyst switches from a sourced field to an
  // empty one. That is the deliberate source-panel handoff for a controlled v177 fill.
  const [viewedPage, setViewedPage] = useState<number | null>(() => initialPage ?? fields.find((field) => field.source)?.source?.page ?? null)
  const [viewer, setViewerState] = useState<Viewer>(loadViewer)
  const [priorYear, setPriorYear] = useState(false) // v091: mirrors MaturityChart's "Show prior year" switch so Export PPTX requests the second series
  const [perYear, setPerYear] = useState(false) // v109: mirrors "Per year" the same way (?per_year=1)
  const [reviewCitation, setReviewCitation] = useState({ page: '', quote: '' })
  const [fillResult, setFillResult] = useState<(FieldFill & { fieldKey: string }) | null>(null)
  const [fillingField, setFillingField] = useState(false)
  const [fillError, setFillError] = useState<string | null>(null)
  // This stays above the per-field form so moving to the next unresolved figure does not make an
  // analyst type their own name again. It is still only submitted with the review they choose.
  const [reviewerName, setReviewerName] = useState('')
  const setViewer = (v: Viewer) => {
    setViewerState(v)
    try {
      localStorage.setItem(VIEWER_KEY, v)
    } catch {
      /* private mode etc. — preference just won't stick */
    }
  }

  useEffect(() => {
    if (initialField === '@basis') {
      const basis = document.getElementById('basis-review') as HTMLDetailsElement | null
      if (basis) { basis.open = true; scrollContent(basis) }
    } else if (initialField === '@checks') scrollContent(document.getElementById('calculation-checks'))
  }, [initialField])
  useEffect(() => {
    if (!focusSource.current || view !== 'figures') return
    const source = document.getElementById('report-source')
    source?.focus({ preventScroll: true })
    scrollContent(source, 'smooth')
    focusSource.current = false
  }, [view])
  const selected = fields.find((f) => f.key === selectedKey) ?? null
  const page = askPage ?? selected?.source?.page ?? viewedPage // what the provenance pane shows
  const selectField = (key: string) => {
    const next = fields.find((field) => field.key === key)
    setSelectedKey(key)
    setAskPage(null)
    if (next?.source) setViewedPage(next.source.page)
    setReviewCitation({ page: '', quote: '' })
    setFillResult(null); setFillError(null)
  }
  const fillSelectedField = async (sourcePage: number) => {
    if (!selected || selected.value !== null) return
    const fieldKey = selected.key
    setFillingField(true); setFillError(null); setFillResult(null)
    try {
      const result = await fillField(report_id, section, fieldKey, [sourcePage])
      setFillResult({ ...result, fieldKey })
    } catch (error) {
      setFillError(error instanceof Error ? error.message : 'Could not read the selected page')
    } finally {
      setFillingField(false)
    }
  }
  // v179: a component citation may sit on a page the field's own source doesn't — reuses the same
  // askPage override an Ask citation chip sets, so Source shows that page instead of the field's own.
  const openComponentPage = (key: string, page: number) => {
    setSelectedKey(key)
    setReviewCitation({ page: '', quote: '' })
    setAskPage(page)
  }
  // The backend's field + check issues are the human's list (an unconfirmed basis is not on it); an undecorated
  // extraction (older backend, fixtures) falls back to counting the rows the table itself flags.
  const notReported = extraction.not_reported ?? []
  const reviewCount = extraction.issues?.length ?? fields.filter((f) => NEEDS_HUMAN.includes(fieldVerification(f, notReported.includes(f.key)).label)).length
  const calculatedCount = fields.filter((f) => fieldVerification(f).label === 'Calculated from report').length
  const unresolvedFields = fields.filter(field => extraction.issues?.some(issue => issue.kind === 'field' && issue.key === field.key))
  const selectedUnresolvedIndex = unresolvedFields.findIndex(field => field.key === selectedKey)
  const nextUnresolved = unresolvedFields.length ? unresolvedFields[(selectedUnresolvedIndex + 1 + unresolvedFields.length) % unresolvedFields.length] : null

  const exportJson = () => {
    // ponytail: Blob URL + synthetic click, fine for a single JSON. Upgrade: File System Access API if size ever matters.
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...extraction, comparison }, null, 2)], { type: 'application/json' }))
    const a = Object.assign(document.createElement('a'), {
      href: url,
      download: `${slug(company ?? 'report')}-${section}.json`,
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="results-page space-y-3">
      <NotFoundBanner extraction={extraction} onSelectField={(key) => { selectField(key); setView('figures') }} />
      {runError && <p role="alert" className="text-sm text-destructive">{runError}</p>}
      {fillError && <p role="alert" className="text-sm text-destructive">{fillError}</p>}
      <PageHeader eyebrow="Results" title={company ?? 'Unknown company'} description={
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {!navigation && <><span>{sectionTitle}</span><span aria-hidden>·</span></>}
          <span>FY {fiscal_year ?? '—'}</span><span aria-hidden>·</span><span>{currency ?? '—'}</span>
          {maturity_basis && <><span aria-hidden>·</span><span>basis: {maturity_basis === 'undiscounted' ? 'contractual undiscounted' : 'carrying amount'}</span></>}
          <Badge variant={reviewCount ? 'warning' : 'secondary'}>{reviewCount ? `${reviewCount} need a human` : 'Nothing needs a human'}</Badge>
          {notReported.length > 0 && <span className="text-xs">{notReported.length} not reported</span>}
          {calculatedCount > 0 && <span className="text-xs">{calculatedCount} calculated from report</span>}
        </div>
      } actions={<>{navigation}{onBack && <Button variant="outline" onClick={onBack}><ArrowLeft />Back to comparison</Button>}<Button onClick={onReset}>New report</Button></>} />
      {extraction.stale && <p role="status" className="text-xs text-warning">This saved result predates the current source, model or extraction settings. Human-reviewed results are preserved.</p>}

      <Workspace label="Report workspace" value={view} onChange={setView} pages={[
        { value: 'figures', label: 'Figures & sources', icon: FileText, content: <>
          <div className={`grid items-start gap-4 ${reading ? '' : 'min-[1100px]:grid-cols-[minmax(280px,2fr)_minmax(0,3fr)]'}`}>
            <div hidden={reading} className="min-w-0 space-y-3">
              <FieldsTable compact fields={fields} notReported={notReported} selectedKey={selectedKey} onSelect={selectField} onOpenPage={openComponentPage} />
              <p className="text-xs text-muted-foreground">Select any figure to read its source. Status icons show verification; details below.</p>
              {nextUnresolved && <Button type="button" variant="outline" onClick={() => selectField(nextUnresolved.key)}>Next unresolved field</Button>}
              {selected && <details className="rounded-lg border p-3" open={initialField === selected.key || undefined}>
                <summary className="cursor-pointer text-sm font-medium">Review {selected.label}</summary>
                <div className="mt-3 space-y-2 text-xs text-muted-foreground"><Badge variant={fieldVerification(selected, notReported.includes(selected.key)).variant}>{fieldVerification(selected, notReported.includes(selected.key)).label}</Badge><p>{fieldVerification(selected, notReported.includes(selected.key)).detail}</p>{selected.human_review && <p>Automated evidence: {fieldVerification({ ...selected, human_review: undefined }).label.toLowerCase()}</p>}</div>
                <div className="mt-4"><HumanReviewForm key={`${selected.key}:${selected.human_review?.at ?? ''}`} extraction={extraction} field={selected} citation={reviewCitation} candidate={fillResult?.fieldKey === selected.key ? fillResult.candidate : null} candidateWarnings={fillResult?.fieldKey === selected.key ? fillResult.warnings : []} onDiscardCandidate={() => setFillResult(null)} reviewerName={reviewerName} onReviewerNameChange={setReviewerName} onCitationChange={setReviewCitation} onSaved={(result) => { setReviewCitation({ page: '', quote: '' }); setFillResult(null); onUpdated(result) }} /></div>
              </details>}
              {selected && fillResult?.fieldKey === selected.key && !fillResult.candidate && <section aria-live="polite" className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm"><p className="font-medium">No candidate for {selected.label}</p><ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">{fillResult.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul><Button type="button" variant="ghost" size="xs" onClick={() => setFillResult(null)}>Discard</Button></section>}
            </div>
            <SourcePanel reading={reading} onReadingChange={setReading} reportId={report_id} stem={extraction.stem} pdfAvailable={extraction.pdf_available} page={page}
              selected={selected} notReported={!!selected && notReported.includes(selected.key)} askPage={askPage} viewer={viewer} onViewerChange={setViewer}
              brokenPage={brokenPage} onBrokenPage={setBrokenPage} onUseSource={(source: Source) => setReviewCitation({ page: String(source.page), quote: source.quote })}
              onFillField={fillSelectedField} fillingField={fillingField} />
          </div>
        </> },
        ...(isMaturitySection(fields) ? [{ value: 'chart' as const, label: 'Maturity profile', icon: ChartColumn, keepMounted: true, content: <MaturityChart extraction={extraction} selectedKey={selectedKey} onSelect={key => { selectField(key); setView('figures') }} onPriorChange={setPriorYear} onPerYearChange={setPerYear} /> }] : []),
        { value: 'review', label: 'Checks & review', icon: ListChecks, count: reviewCount, content: <div className="space-y-4">
          <BasisPanel key={extraction.basis?.at ?? 'unknown'} extraction={extraction} onUpdated={onUpdated} />
          <div id="calculation-checks"><StatusCards checks={checks} warnings={warnings} fields={fields} onSelect={key => { selectField(key); focusSource.current = true; setView('figures') }} /></div>
        </div> },
        { value: 'comparison', label: 'Prior year', icon: Columns3, keepMounted: true, content: extraction.stem
          ? <YearComparison extraction={extraction} onChange={setComparison} />
          : <p className="text-sm text-muted-foreground">Prior-year comparisons are available for saved statements in the knowledge base.</p> },
        { value: 'ask', label: 'Ask report', icon: MessageCircle, content: <AskPanel reports={[{ report_id, label: company ?? 'This report' }]} onCitation={(_id, citedPage) => { setViewedPage(citedPage); setAskPage(citedPage); focusSource.current = true; setView('figures') }} /> },
        { value: 'export', label: 'Export', icon: Download, content: <div className="space-y-5">
          <div><h2 className="text-base font-semibold">Export this statement</h2><p className="mt-1 text-sm text-muted-foreground">Download figures and their source references in your preferred format.</p></div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={exportJson}><Download /> Export JSON</Button>
            <a href={csvUrl(report_id, extraction.stem ? section : undefined, comparison?.previous_stem)} download className={buttonVariants({ variant: 'outline' })}><Download /> Export CSV</a>
            <a href={pptxUrl(report_id, extraction.stem ? section : undefined, comparison?.previous_stem, priorYear || undefined, perYear || undefined)} download className={buttonVariants({ variant: 'outline' })}><Download /> Export PPTX</a>
          </div>
          <div className="space-y-3 border-t pt-5"><h3 className="text-sm font-medium">Extraction</h3>
            {extraction.timings && <p className="text-xs text-muted-foreground">{extraction.cached ? 'Saved result' : 'Fresh extraction'} · {extraction.timings.total ?? 0} s · {extraction.timings.attempts ?? 0} model calls</p>}
            <Button variant="outline" disabled={rerunning || !!extraction.basis_history?.length || fields.some(field => field.review_history?.length)} onClick={rerun}>{rerunning ? 'Extracting…' : 'Run again'}</Button>
          </div>
        </div> },
      ]} />
    </div>
  )
}