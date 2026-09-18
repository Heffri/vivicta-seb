import { BasisPanel, YearComparison } from '@/components/AnalystWorkbench'
import { ArrowLeft, Download } from 'lucide-react'
import { useEffect, useState } from 'react'
import { csvUrl, pptxUrl } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { HumanReviewForm } from '@/components/results/HumanReviewForm'
import { FieldsTable } from '@/components/results/FieldsTable'
import { MaturityChart } from '@/components/results/MaturityChart'
import { SourcePanel, type Viewer } from '@/components/results/SourcePanel'
import { StatusCards } from '@/components/results/StatusCards'
import { Badge } from '@/components/ui/badge'
import { fieldVerification } from '@/components/results/verification'
import { Button, buttonVariants } from '@/components/ui/button'
import type { Comparison, Extraction, Field } from '@/types'

type Props = {
  extraction: Extraction
  sectionTitle: string
  onUpdated: (result: Extraction) => void
  onReset: () => void
  onBack?: () => void
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

export function ResultsView({ extraction, sectionTitle, onUpdated, onReset, onBack, initialPage, initialField }: Props) {
  const { report_id, company, fiscal_year, currency, section, maturity_basis, fields, checks, warnings } = extraction
  const [selectedKey, setSelectedKey] = useState<string | null>(() => initialField ?? fields.find((f) => f.source)?.key ?? null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [brokenPage, setBrokenPage] = useState<number | null>(null)
  const [askPage, setAskPage] = useState<number | null>(initialPage ?? null) // citation chip override; a row click clears it
  const [viewer, setViewerState] = useState<Viewer>(loadViewer)
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
      if (basis) { basis.open = true; basis.scrollIntoView({ block: 'start' }) }
    } else if (initialField === '@checks') document.getElementById('calculation-checks')?.scrollIntoView({ block: 'start' })
  }, [initialField])
  const selected = fields.find((f) => f.key === selectedKey) ?? null
  const page = askPage ?? selected?.source?.page ?? null // what the provenance pane shows
  const selectField = (key: string) => {
    setSelectedKey(key)
    setAskPage(null)
  }
  const reviewCount = fields.filter((f) => ['Needs review', 'Not checked', 'Not found'].includes(fieldVerification(f).label)).length

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
    <div className="space-y-6">
      {/* Top bar: who, what, how well verified; exports on the right. */}
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5">
        <div>
          {onBack ? (
            <Button variant="link" size="xs" className="-ml-2 h-auto p-0 text-xs" onClick={onBack}>
              <ArrowLeft /> Back to comparison
            </Button>
          ) : (
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Results</p>
          )}
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{company ?? 'Unknown company'}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            <span>{sectionTitle}</span>
            <span aria-hidden>·</span>
            <span>FY {fiscal_year ?? '—'}</span>
            <span aria-hidden>·</span>
            <span>{currency ?? '—'}</span>
            {/* v089: debt_maturity extractions name the maturity basis their fields were read on (env DEBT_BASIS);
                older or non-debt extractions carry none and show nothing. Distinct from the analyst-confirmed `basis`. */}
            {maturity_basis && (
              <>
                <span aria-hidden>·</span>
                <span>basis: {maturity_basis === 'undiscounted' ? 'contractual undiscounted' : 'carrying amount'}</span>
              </>
            )}
            <Badge variant={reviewCount ? 'warning' : 'secondary'}>
              {reviewCount ? `${reviewCount} figures to review` : 'Source checks recorded'}
            </Badge>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={exportJson}>
            <Download /> Export JSON
          </Button>
          <a href={csvUrl(report_id, extraction.stem ? section : undefined, comparison?.previous_stem)} download className={buttonVariants({ variant: 'outline' })}>
            <Download /> Export CSV
          </a>
          <a href={pptxUrl(report_id, extraction.stem ? section : undefined, comparison?.previous_stem)} download className={buttonVariants({ variant: 'outline' })}>
            <Download /> Export PPTX
          </a>
          <Button onClick={onReset}>New report</Button>
        </div>
      </header>

      <BasisPanel key={extraction.basis?.at ?? 'unknown'} extraction={extraction} onUpdated={onUpdated} />
      <YearComparison extraction={extraction} onChange={setComparison} />
      {/* Two columns from 1280px (fields + verification left, provenance + Ask right);
          below that one column, Source directly under the table. The maturity chart
          (v009) leads the grid full-width so it clears the fold on a 900px screen —
          v010 moved it up from between Source and Checks per v009's suggestion; income
          sections never render it, so their v003 layout is untouched. */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Maturity buckets — nothing renders unless the fields look like maturity
            buckets, the same rule ppt.py uses to pick chart over table. */}
        <MaturityChart extraction={extraction} selectedKey={selectedKey} onSelect={selectField} />

        <div className="space-y-4">
          <FieldsTable fields={fields} selectedKey={selectedKey} onSelect={selectField} />
          {selected && <HumanReviewForm key={`${selected.key}:${selected.human_review?.at ?? ''}`} extraction={extraction} field={selected} onSaved={onUpdated} />}
        </div>

        {/* ponytail: no longer sticky — it would slide over the Ask panel below it. */}
        <SourcePanel
          reportId={report_id}
          stem={extraction.stem}
          pdfAvailable={extraction.pdf_available}
          page={page}
          selected={selected}
          askPage={askPage}
          viewer={viewer}
          onViewerChange={setViewer}
          brokenPage={brokenPage}
          onBrokenPage={setBrokenPage}
        />

        <div id="calculation-checks"><StatusCards checks={checks} warnings={warnings} fields={fields} onSelect={(key) => {
          selectField(key)
          const source = document.getElementById('report-source')
          source?.focus({ preventScroll: true })
          source?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }} /></div>

        <AskPanel reports={[{ report_id, label: company ?? 'This report' }]} onCitation={(_id, p) => setAskPage(p)} />
      </div>
    </div>
  )
}
