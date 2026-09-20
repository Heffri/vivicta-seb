import { Download } from 'lucide-react'
import { csvUrl } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { confidenceClass, confidenceTitle, fmtValue } from '@/components/ResultsView'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Result } from '@/types'

type Props = { results: Result[]; onSelect: (index: number, page?: number) => void; onReset: () => void }

export function CompareView({ results, onSelect, onReset }: Props) {
  // Row order = first successful extraction's schema order; all reports share the section so keys line up.
  const first = results.find((r) => r.extraction)?.extraction
  const rows = first?.fields ?? []
  const ok = results.filter((r) => r.extraction).length
  const reports = results.flatMap((r) => (r.extraction ? [{ report_id: r.extraction.report_id, label: r.label }] : []))

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Annual Report Parser</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Comparison</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {results[0].sectionTitle} · {ok} of {results.length} reports extracted
          </p>
        </div>
        <Button onClick={onReset}>New report</Button>
      </header>

      <Card className="overflow-x-auto py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              {results.map((r, i) => {
                const x = r.extraction
                const failed = x?.checks.filter((c) => !c.passed).length ?? 0
                return (
                  <TableHead key={i} className="min-w-40 align-top">
                    <button
                      type="button"
                      onClick={() => x && onSelect(i)}
                      disabled={!x}
                      className="flex flex-col items-start gap-1 py-2 text-left enabled:cursor-pointer enabled:hover:underline"
                    >
                      <span className="font-medium text-foreground">{r.label}</span>
                      <span className="text-xs font-normal">FY {x?.fiscal_year ?? '—'}</span>
                      {x ? (
                        <Badge
                          variant="outline"
                          className={
                            failed === 0
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                              : 'border-red-200 bg-red-50 text-red-700'
                          }
                        >
                          {x.checks.length === 0 ? 'No checks' : `${x.checks.length - failed}/${x.checks.length} checks`}
                        </Badge>
                      ) : (
                        <Badge variant="destructive">failed</Badge>
                      )}
                    </button>
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, ri) => (
              <TableRow key={row.key}>
                <TableCell className="font-medium">{row.label}</TableCell>
                {results.map((r, i) => {
                  if (!r.extraction) {
                    // One tall cell with the error instead of N empty ones.
                    return ri === 0 ? (
                      <TableCell key={i} rowSpan={rows.length} className="max-w-60 whitespace-normal align-top text-xs text-destructive">
                        {r.error}
                      </TableCell>
                    ) : null
                  }
                  const f = r.extraction.fields.find((x) => x.key === row.key)
                  return (
                    <TableCell key={i} className={`tabular-nums ${f?.value == null ? 'text-muted-foreground' : ''}`}>
                      {fmtValue(f?.value ?? null)}
                      {f?.unit && f.value !== null && <span className="ml-1 text-xs text-muted-foreground">{f.unit}</span>}
                      {f && (
                        <Badge variant="outline" className={`ml-2 px-1.5 tabular-nums ${confidenceClass(f.confidence)}`} title={confidenceTitle(f)}>
                          {Math.round(f.confidence * 100)}%
                        </Badge>
                      )}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell />
              {results.map((r, i) => (
                <TableCell key={i}>
                  {r.extraction && (
                    <div className="flex gap-1.5">
                      <Button size="xs" variant="outline" onClick={() => onSelect(i)}>
                        Details
                      </Button>
                      {/* ponytail: one CSV per column; a merged CSV isn't in the API and isn't worth inventing client-side. */}
                      <a
                        href={csvUrl(r.extraction.report_id, r.extraction.section)}
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
      </Card>

      <AskPanel
        reports={reports}
        onCitation={(id, page) => {
          const i = results.findIndex((r) => r.extraction?.report_id === id)
          if (i >= 0) onSelect(i, page)
        }}
      />
    </div>
  )
}
