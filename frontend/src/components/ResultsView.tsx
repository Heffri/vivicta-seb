import { ArrowLeft, Check, Download, ExternalLink, ImageOff, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import { csvUrl, pageUrl, pdfUrl } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Extraction, Field } from '@/types'

type Props = {
  extraction: Extraction
  sectionTitle: string
  onReset: () => void
  onBack?: () => void
  initialPage?: number | null // from a citation chip on the compare view
}

// 152340 → "152 340" (thin space U+2009), sign kept, decimals as-is, null → em dash.
export const fmtValue = (v: Field['value']) =>
  v === null
    ? '—'
    : typeof v === 'number'
      ? v.toLocaleString('en-US', { maximumFractionDigits: 6 }).replaceAll(',', ' ')
      : v

const EVIDENCE = ['quote_on_page', 'value_in_quote', 'arith_ok', 'label_known', 'period_ok', 'page_is_statement', 'unit_ok'] // docs/CONFIDENCE.md

/** Tooltip for the confidence badge: which evidence the backend could not verify. */
export const confidenceTitle = (f: { confidence: number; evidence?: string[] }) => {
  const missing = EVIDENCE.filter((e) => !(f.evidence ?? []).includes(e))
  return missing.length ? `missing: ${missing.join(', ')}` : 'all evidence verified'
}

export const confidenceClass = (c: number) =>
  c >= 0.9
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : c >= 0.7
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : 'border-red-200 bg-red-50 text-red-700'

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

// Provenance viewer: browser PDF viewer (scroll/zoom/search/select for free) or the rendered PNG as fallback.
type Viewer = 'pdf' | 'image'
const VIEWER_KEY = 'provenance-viewer'
const loadViewer = (): Viewer => {
  try {
    return localStorage.getItem(VIEWER_KEY) === 'image' ? 'image' : 'pdf'
  } catch {
    return 'pdf'
  }
}

export function ResultsView({ extraction, sectionTitle, onReset, onBack, initialPage }: Props) {
  const { report_id, company, fiscal_year, currency, section, fields, checks, warnings } = extraction
  const [selectedKey, setSelectedKey] = useState<string | null>(() => fields.find((f) => f.source)?.key ?? null)
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

  const selected = fields.find((f) => f.key === selectedKey) ?? null
  const page = askPage ?? selected?.source?.page ?? null // what the provenance pane shows
  const selectField = (key: string) => {
    setSelectedKey(key)
    setAskPage(null)
  }
  const warningFor = (f: Field) => warnings.find((w) => w.startsWith(f.key + ':'))
  const failed = checks.filter((c) => !c.passed).length

  const exportJson = () => {
    // ponytail: Blob URL + synthetic click, fine for a single JSON. Upgrade: File System Access API if size ever matters.
    const url = URL.createObjectURL(new Blob([JSON.stringify(extraction, null, 2)], { type: 'application/json' }))
    const a = Object.assign(document.createElement('a'), {
      href: url,
      download: `${slug(company ?? 'report')}-${section}.json`,
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5">
        <div>
          {onBack ? (
            <Button variant="link" size="xs" className="-ml-2 h-auto p-0 text-xs" onClick={onBack}>
              <ArrowLeft /> Back to comparison
            </Button>
          ) : (
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Annual Report Parser</p>
          )}
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{company ?? 'Unknown company'}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            <span>{sectionTitle}</span>
            <span aria-hidden>·</span>
            <span>FY {fiscal_year ?? '—'}</span>
            <span aria-hidden>·</span>
            <span>{currency ?? '—'}</span>
            <Badge
              variant="outline"
              className={
                failed === 0
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-700'
              }
            >
              {checks.length === 0
                ? 'No checks'
                : failed === 0
                  ? `${checks.length}/${checks.length} checks passed`
                  : `${failed} failed`}
            </Badge>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={exportJson}>
            <Download /> Export JSON
          </Button>
          <a href={csvUrl(report_id)} download className={buttonVariants({ variant: 'outline' })}>
            <Download /> Export CSV
          </a>
          <Button onClick={onReset}>New report</Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Left: fields + checks + warnings. Spans both rows so the Ask panel lands right under Source. */}
        <div className="space-y-6 lg:row-span-2">
          <Card className="py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((f) => {
                  const isSelected = f.key === selectedKey
                  const warning = warningFor(f)
                  return (
                    <TableRow
                      key={f.key}
                      tabIndex={0}
                      aria-selected={isSelected}
                      data-state={isSelected ? 'selected' : undefined}
                      onClick={() => selectField(f.key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          selectField(f.key)
                        }
                      }}
                      className={`cursor-pointer outline-none focus-visible:bg-muted/50 ${
                        isSelected ? 'shadow-[inset_2px_0_0_var(--primary)]' : ''
                      }`}
                    >
                      <TableCell className="font-medium">{f.label}</TableCell>
                      <TableCell className={`text-right tabular-nums ${f.value === null ? 'text-muted-foreground' : ''}`}>
                        {fmtValue(f.value)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{f.unit ?? '—'}</TableCell>
                      <TableCell className="text-muted-foreground">{f.period ?? '—'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`tabular-nums ${confidenceClass(f.confidence)}`} title={confidenceTitle(f)}>
                          {Math.round(f.confidence * 100)}%
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {warning && <TriangleAlert className="size-3.5 text-amber-600" role="img" aria-label={warning} />}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Card>

          <div className="grid gap-6 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Checks</CardTitle>
              </CardHeader>
              <CardContent>
                {checks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No checks for this section.</p>
                ) : (
                  <ul className="space-y-3">
                    {checks.map((c) => (
                      <li key={c.name} className="flex gap-2 text-sm">
                        {c.passed ? (
                          <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-label="passed" />
                        ) : (
                          <X className="mt-0.5 size-4 shrink-0 text-red-600" aria-label="failed" />
                        )}
                        <div className="min-w-0">
                          <div className="font-medium">{c.name}</div>
                          <div className="break-words font-mono text-xs text-muted-foreground">{c.detail}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Warnings</CardTitle>
              </CardHeader>
              <CardContent>
                {warnings.length === 0 ? (
                  <p className="text-sm text-muted-foreground">None.</p>
                ) : (
                  <ul className="space-y-3">
                    {warnings.map((w) => (
                      <li key={w} className="flex gap-2 text-sm">
                        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
                        <span className="break-words">{w}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Right: provenance. ponytail: no longer sticky — it would slide over the Ask panel below it. */}
        <Card className="self-start">
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              <span>Source</span>
              {page !== null && (
                <span className="flex items-center gap-1.5 text-sm font-normal text-muted-foreground">
                  <span className="mr-1">Page {page}</span>
                  {(['pdf', 'image'] as const).map((v) => (
                    <Button
                      key={v}
                      size="xs"
                      variant={viewer === v ? 'default' : 'outline'}
                      aria-pressed={viewer === v}
                      onClick={() => setViewer(v)}
                    >
                      {v === 'pdf' ? 'PDF' : 'Image'}
                    </Button>
                  ))}
                  <a
                    href={pdfUrl(report_id, page)}
                    target="_blank"
                    rel="noreferrer"
                    className={buttonVariants({ size: 'xs', variant: 'ghost' })}
                  >
                    Open PDF <ExternalLink />
                  </a>
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {page === null ? (
              <p className="text-sm text-muted-foreground">
                {selected && !selected.source
                  ? 'No source — value not found.'
                  : 'Select a row to see where the value comes from.'}
              </p>
            ) : (
              <>
                {viewer === 'pdf' ? (
                  // ponytail: key={page} remounts the iframe — swapping only the #page= hash on the same src doesn't
                  // reliably navigate in Chromium. PDF is browser-cached after the first load; pdf.js is the upgrade if
                  // the remount flicker ever annoys.
                  <iframe
                    key={page}
                    src={pdfUrl(report_id, page)}
                    title={`Page ${page} of the report`}
                    className="h-[70vh] w-full rounded border bg-white"
                  />
                ) : brokenPage === page ? (
                  <div className="flex aspect-[1/1.3] flex-col items-center justify-center gap-2 rounded-md border bg-muted/40 text-sm text-muted-foreground">
                    <ImageOff className="size-5" />
                    Page preview unavailable
                  </div>
                ) : (
                  <img
                    src={pageUrl(report_id, page)}
                    alt={`Page ${page} of the report`}
                    onError={() => setBrokenPage(page)}
                    className="w-full rounded-md border bg-white"
                  />
                )}
                {askPage !== null ? (
                  <p className="text-xs text-muted-foreground">
                    Page {askPage}, cited in an answer below. Click a row to go back to a field.
                  </p>
                ) : (
                  selected?.source && (
                    <div>
                      <p className="mb-1 text-xs text-muted-foreground">
                        {selected.label}
                        {selected.raw_label && selected.raw_label !== selected.label && (
                          <> · printed as “{selected.raw_label}”</>
                        )}
                      </p>
                      <pre className="whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
                        {selected.source.quote}
                      </pre>
                    </div>
                  )
                )}
              </>
            )}
          </CardContent>
        </Card>

        <div className="lg:col-start-2">
          <AskPanel reports={[{ report_id, label: company ?? 'This report' }]} onCitation={(_id, p) => setAskPage(p)} />
        </div>
      </div>
    </div>
  )
}
