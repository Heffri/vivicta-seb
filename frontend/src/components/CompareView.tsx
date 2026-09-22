import { Columns3, Download, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { csvUrl } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { MaturityBar } from '@/components/compare/MaturityBar'
import { MaturityWall } from '@/components/compare/MaturityWall'
import { fmtValue } from '@/components/ResultsView'
import { isMaturitySection } from '@/components/results/MaturityChart'
import { fieldVerification, NEEDS_HUMAN } from '@/components/results/verification'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { KbEntry, Result } from '@/types'

type Props = {
  results: Result[]
  onSelect: (index: number, page?: number) => void
  onReset: () => void
  // Threaded straight through to MaturityWall's row actions ("Open" / "Review"); undefined
  // just disables those buttons, so this view still renders without it.
  onOpenReport?: (report: KbEntry, section?: string, key?: string) => void
}

export function CompareView({ results, onSelect, onReset, onOpenReport }: Props) {
  const [view, setView] = useState<'figures' | 'ask'>('figures')
  // Row order = first successful extraction's schema order; all reports share the section so keys line up.
  const first = results.find((r) => r.extraction)?.extraction
  const rows = first?.fields ?? []
  const ok = results.filter((r) => r.extraction).length
  const reports = results.flatMap((r) => (r.extraction ? [{ report_id: r.extraction.report_id, label: r.label }] : []))
  // Same judgment as MaturityChart, per successful column — one non-bucket column and the
  // matrix stays exactly as it was (no row, nothing else changes).
  const showMaturityRow = ok > 0 && results.every((r) => !r.extraction || isMaturitySection(r.extraction.fields))
  const errorCell = (r: Result, i: number, span: number) => (
    <TableCell key={i} rowSpan={span} className="max-w-60 whitespace-normal align-top text-xs text-danger">
      {r.error}
      <p className="mt-2 text-danger/80">
        Next step: fetch the PDF from Find a company on the Extract tab, then open it here again.
      </p>
    </TableCell>
  )

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Compare" title="Compare reports" description={`${results[0]?.sectionTitle ?? 'Statements'} · ${ok} of ${results.length} reports extracted`} actions={<Button onClick={onReset}>New report</Button>} />
      <Workspace label="Comparison workspace" value={view} onChange={setView} pages={[
      { value: 'figures', label: 'Side by side', icon: Columns3, content: <div className="space-y-5">
      {/* the whole-KB list, independent of the result columns below it. */}
      <MaturityWall onOpenReport={onOpenReport} />
      <Card className="overflow-x-auto py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 z-10 bg-card">Field</TableHead>
              {results.map((r, i) => {
                const x = r.extraction
                const notReported = x?.not_reported ?? []
                const reviewCount = x?.issues?.length ?? x?.fields.filter((f) => NEEDS_HUMAN.includes(fieldVerification(f, notReported.includes(f.key)).label)).length ?? 0
                const calculatedCount = x?.fields.filter((f) => fieldVerification(f).label === 'Calculated from report').length ?? 0
                return (
                  <TableHead key={i} className="min-w-48 p-1.5 align-top">
                    <Card size="sm" className="gap-1">
                      <button
                        type="button"
                        onClick={() => x && onSelect(i)}
                        disabled={!x}
                        className="flex w-full flex-col items-start gap-1 px-3 py-1.5 text-left enabled:cursor-pointer enabled:hover:underline"
                      >
                        <span className="font-medium text-foreground">{r.label}</span>
                        <span className="text-xs font-normal text-muted-foreground">FY {x?.fiscal_year ?? '—'}</span>
                        {x ? (
                          <>
                            <Badge variant={reviewCount ? 'warning' : 'secondary'}>
                              {reviewCount ? `${reviewCount} need a human` : 'Nothing needs a human'}
                            </Badge>
                            {(notReported.length > 0 || calculatedCount > 0) && <span className="text-xs font-normal text-muted-foreground">{[notReported.length > 0 && `${notReported.length} not reported`, calculatedCount > 0 && `${calculatedCount} calculated from report`].filter(Boolean).join(' · ')}</span>}
                          </>
                        ) : (
                          <Badge variant="danger">failed</Badge>
                        )}
                      </button>
                    </Card>
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {showMaturityRow && (
              <TableRow>
                <TableCell className="sticky left-0 z-10 bg-muted/50 font-medium">Maturity profile</TableCell>
                {results.map((r, i) =>
                  r.extraction ? (
                    <TableCell key={i} className="bg-muted/50">
                      <MaturityBar extraction={r.extraction} />
                    </TableCell>
                  ) : (
                    errorCell(r, i, rows.length + 1)
                  ),
                )}
              </TableRow>
            )}
            {rows.map((row, ri) => (
              <TableRow key={row.key}>
                <TableCell className="sticky left-0 z-10 bg-card font-medium">{row.label}</TableCell>
                {results.map((r, i) => {
                  if (!r.extraction) {
                    // One tall cell with the error instead of N empty ones.
                    return ri === 0 && !showMaturityRow ? errorCell(r, i, rows.length) : null
                  }
                  const f = r.extraction.fields.find((x) => x.key === row.key)
                  const verification = f ? fieldVerification(f, (r.extraction.not_reported ?? []).includes(f.key)) : null
                  return (
                    <TableCell key={i} className={`tabular-nums ${f?.value == null ? 'text-muted-foreground' : ''}`}>
                      {fmtValue(f?.value ?? null)}
                      {f?.unit && f.value !== null && <span className="ml-1 text-xs text-muted-foreground">{f.unit}</span>}
                      {verification && (
                        <Badge variant={verification.variant} className="ml-2 px-1.5" title={verification.detail}>
                          {verification.label}
                        </Badge>
                      )}
                      {verification && NEEDS_HUMAN.includes(verification.label) && <details className="mt-2 max-w-sm whitespace-normal text-xs text-muted-foreground"><summary className="cursor-pointer">What to review</summary><p className="mt-2 leading-relaxed">{verification.detail}</p></details>}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell className="sticky left-0 z-10 bg-muted/50" />
              {results.map((r, i) => (
                <TableCell key={i}>
                  {r.extraction && (
                    <div className="flex gap-1.5">
                      <Button size="xs" variant="outline" onClick={() => onSelect(i)}>
                        Details
                      </Button>
                      {/* ponytail: one CSV per column; a merged CSV isn't in the API and isn't worth inventing client-side. */}
                      <a
                        href={csvUrl(r.extraction.report_id, r.extraction.stem ? r.extraction.section : undefined)}
                        download
                        className={buttonVariants({ size: 'xs', variant: 'outline' })}
                      >
                        <Download /> CSV
                      </a>
                    </div>
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableFooter>
        </Table>
      </Card></div> },
      { value: 'ask', label: 'Ask reports', icon: MessageCircle, content:
      <AskPanel
        reports={reports}
        onCitation={(id, page) => {
          const i = results.findIndex((r) => r.extraction?.report_id === id)
          if (i >= 0) onSelect(i, page)
        }}
      />
      },
      ]} />
    </div>
  )
}
