import { fmtValue } from '@/components/ResultsView'
import { fieldVerification, NEEDS_HUMAN } from './verification'
import { Fragment } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Check, CircleHelp, TriangleAlert } from 'lucide-react'
import type { Field } from '@/types'

type FieldsTableProps = {
  compact?: boolean
  fields: Field[]
  notReported?: string[] // Extraction.not_reported: optional rows the report does not print
  selectedKey: string | null
  onSelect: (key: string) => void
  onOpenPage?: (key: string, page: number) => void // a component's own citation may sit on a page the field's own source doesn't
}

/** The product's argument, one row per number: the number, its unit and period, how much
 *  the backend could verify. Selecting a row (click or Enter/Space) aims the Source panel;
 *  the selected row carries an accent left edge and a faint accent wash. */
export function FieldsTable({ fields, notReported = [], selectedKey, onSelect, onOpenPage, compact = false }: FieldsTableProps) {
  const openPage = onOpenPage ?? ((key: string) => onSelect(key))
  const mostCommon = (values: (string | null | undefined)[]) => [...new Set(values)].sort((a, b) => values.filter(value => value === b).length - values.filter(value => value === a).length)[0]
  const unit = mostCommon(fields.map(field => field.unit))
  const period = mostCommon(fields.map(field => field.period))
  return (
    <Card className={compact ? 'gap-0 overflow-hidden py-0' : 'py-0'}>
      {compact ? <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5"><h2 className="text-sm font-semibold">All figures</h2><span className="text-xs text-muted-foreground">{unit ?? 'Unit not stated'} · {period ?? 'Period not stated'}</span></div>
        : <p className="px-4 pt-4 text-xs text-muted-foreground">Select a figure to see its source and add a human review below the table.</p>}
      <Table aria-label="Statement figures" className={compact ? '[&_td]:px-3 [&_td]:py-1.5 [&_th]:h-8 [&_th]:px-3 [&_th]:text-xs' : undefined}>
        <TableHeader>
          <TableRow>
            <TableHead>Label</TableHead>
            <TableHead className="text-right">Value</TableHead>
            {compact && <TableHead className="w-9"><span className="sr-only">Verification</span></TableHead>}
            {!compact && <><TableHead>Unit</TableHead><TableHead>Period</TableHead><TableHead>Verification</TableHead></>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((f) => {
            const isSelected = f.key === selectedKey
            const unreported = notReported.includes(f.key)
            const verification = fieldVerification(f, unreported)
            const Status = verification.variant === 'success' ? Check : verification.variant === 'warning' ? TriangleAlert : CircleHelp
            const reason = f.value === null ? f.missing_reason : undefined
            const showReason = reason && reason.code !== 'absent_in_table'
            return (
              <Fragment key={f.key}>
                <TableRow
                  tabIndex={0}
                  aria-selected={isSelected}
                  data-state={isSelected ? 'selected' : undefined}
                  onClick={() => onSelect(f.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(f.key)
                    }
                  }}
                  className="cursor-pointer outline-none focus-visible:bg-muted/50 data-[state=selected]:bg-ring/10 data-[state=selected]:shadow-[inset_2px_0_0_var(--ring)]"
                >
                  <TableCell className="whitespace-normal font-medium">
                    <span>{f.label}</span>
                    {compact && f.evidence?.includes('ocr_text') && <span className="mt-1 block text-[11px] font-medium text-warning">From OCR — check the scanned image</span>}
                    {compact && (f.human_review?.source_verified && f.source || !!f.components?.length) && <details className="mt-1 text-[11px] font-normal text-muted-foreground" onClick={event => event.stopPropagation()}>
                      <summary className="cursor-pointer text-primary">{f.human_review?.source_verified && f.source ? `Reviewed source · p.${f.source.page}${f.components?.length ? ` · ${f.components.length} components` : ''}` : `${f.components?.length} source components`}</summary>
                      {f.human_review?.source_verified && f.source && <button type="button" className="mt-1 block text-left text-primary underline-offset-2 hover:underline" title={f.source.quote} onClick={() => onSelect(f.key)}>“{f.source.quote.length > 96 ? `${f.source.quote.slice(0, 93).trimEnd()}…` : f.source.quote}”</button>}
                      {!!f.components?.length && <span className="mt-1 flex flex-wrap gap-x-2 gap-y-1">{f.components.map((component, index) => <button key={index} type="button" className="text-primary underline-offset-2 hover:underline" title={component.quote} onClick={() => openPage(f.key, component.page)}>{component.label || `Component ${index + 1}`} · p.{component.page}</button>)}</span>}
                    </details>}
                  </TableCell>
                  <TableCell className={`text-right tabular-nums ${f.value === null ? 'text-muted-foreground' : ''}`}>
                    {fmtValue(f.value)}
                    {compact && f.value !== null && (f.unit !== unit || f.period !== period) && <span className="text-xs text-muted-foreground">{' '}{f.unit !== unit ? f.unit ?? 'Unit unknown' : ''}{f.period !== period ? ` · ${f.period ?? 'Period unknown'}` : ''}</span>}
                  </TableCell>
                  {compact && <TableCell><span className={verification.variant === 'warning' ? 'text-warning' : verification.variant === 'success' ? 'text-success' : 'text-muted-foreground'} title={`${verification.label}: ${verification.detail}`}><Status className="size-3.5" aria-hidden /><span className="sr-only">{verification.label}</span></span></TableCell>}
                  {!compact && <>
                  <TableCell className="text-muted-foreground">{f.unit ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{f.period ?? '—'}</TableCell>
                  <TableCell className="min-w-52 max-w-sm whitespace-normal align-top">
                    <Badge variant={verification.variant} title={verification.detail}>
                      {verification.label}
                    </Badge>
                    {f.human_review && <p className="mt-2 text-xs text-muted-foreground" title={fieldVerification({ ...f, human_review: undefined }, unreported).detail}>Automated evidence: {fieldVerification({ ...f, human_review: undefined }, unreported).label.toLowerCase()}</p>}
                    {f.human_review?.source_verified && f.source && <button type="button" className="mt-2 block text-left text-xs text-primary underline-offset-2 hover:underline" title={f.source.quote} onClick={(e) => { e.stopPropagation(); onSelect(f.key) }}>
                      Reviewed source · p.{f.source.page} · “{f.source.quote.length > 96 ? `${f.source.quote.slice(0, 93).trimEnd()}…` : f.source.quote}”{f.components?.length ? ` · ${f.components.length} components` : ''}
                    </button>}
                    {/* each summed component gets its own page link — a total's components don't all sit on the field's own source page. */}
                    {!!f.components?.length && (
                      <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-muted-foreground">
                        {f.components.map((c, i) => (
                          <button key={i} type="button" className="text-primary underline-offset-2 hover:underline" title={c.quote} onClick={(e) => { e.stopPropagation(); openPage(f.key, c.page) }}>
                            {c.label || `Component ${i + 1}`} · p.{c.page}
                          </button>
                        ))}
                      </p>
                    )}
                    {/* an OCR'd page is read text, not a photograph — flag it beside the check result, not only inside Source. */}
                    {f.evidence?.includes('ocr_text') && <p className="mt-2 text-xs font-medium text-warning">From OCR — check the scanned image</p>}
                    {NEEDS_HUMAN.includes(verification.label) && !reason && (
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{verification.detail}</p>
                    )}
                  </TableCell>
                  </>}
                </TableRow>
                {showReason && (
                  <TableRow className="bg-muted/20 hover:bg-muted/20">
                    <TableCell colSpan={compact ? 3 : 5} className="whitespace-normal px-4 py-3 text-xs leading-relaxed text-muted-foreground">
                      <p><span className="font-medium text-foreground">Why empty:</span> {reason.detail}</p>
                      {reason.disclosed?.length ? (
                        <div className="mt-2 overflow-x-auto">
                          <p className="mb-1 font-medium text-foreground">As disclosed in the report</p>
                          <table className="min-w-80 border-collapse text-left text-xs">
                            <thead><tr className="border-b"><th className="px-2 py-1 font-medium">Span</th><th className="px-2 py-1 font-medium">Amount</th><th className="px-2 py-1 font-medium">Source</th></tr></thead>
                            <tbody>{reason.disclosed.map((item, index) => (
                              <tr key={`${item.page}-${item.span}-${index}`} className="border-b border-border/60 last:border-0">
                                <td className="px-2 py-1">{item.span}</td>
                                <td className="px-2 py-1 tabular-nums">{fmtValue(item.amount)}{item.unit ? ` ${item.unit}` : ''}</td>
                                <td className="px-2 py-1"><button type="button" className="text-primary underline-offset-2 hover:underline" title={item.quote} onClick={(e) => { e.stopPropagation(); openPage(f.key, item.page) }}>p. {item.page}</button></td>
                              </tr>
                            ))}</tbody>
                          </table>
                        </div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </Card>
  )
}
