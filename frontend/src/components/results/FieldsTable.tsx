import { fmtValue } from '@/components/ResultsView'
import { fieldVerification } from './verification'
import { Fragment } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Field } from '@/types'

type FieldsTableProps = {
  fields: Field[]
  selectedKey: string | null
  onSelect: (key: string) => void
  onOpenPage?: (key: string, page: number) => void // v179: a component's own citation may sit on a page the field's own source doesn't
}

/** The product's argument, one row per number: the number, its unit and period, how much
 *  the backend could verify. Selecting a row (click or Enter/Space) aims the Source panel;
 *  the selected row carries an accent left edge and a faint accent wash. */
export function FieldsTable({ fields, selectedKey, onSelect, onOpenPage }: FieldsTableProps) {
  const openPage = onOpenPage ?? ((key: string) => onSelect(key))
  return (
    <Card className="py-0">
      <p className="px-4 pt-4 text-xs text-muted-foreground">Select a figure to see its source and add a human review below the table.</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Label</TableHead>
            <TableHead className="text-right">Value</TableHead>
            <TableHead>Unit</TableHead>
            <TableHead>Period</TableHead>
            <TableHead>Verification</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((f) => {
            const isSelected = f.key === selectedKey
            const verification = fieldVerification(f)
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
                  <TableCell className="font-medium">{f.label}</TableCell>
                  <TableCell className={`text-right tabular-nums ${f.value === null ? 'text-muted-foreground' : ''}`}>
                    {fmtValue(f.value)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{f.unit ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{f.period ?? '—'}</TableCell>
                  <TableCell className="min-w-52 max-w-sm whitespace-normal align-top">
                    <Badge variant={verification.variant} title={verification.detail}>
                      {verification.label}
                    </Badge>
                    {f.human_review && <p className="mt-2 text-xs text-muted-foreground" title={fieldVerification({ ...f, human_review: undefined }).detail}>Automated evidence: {fieldVerification({ ...f, human_review: undefined }).label.toLowerCase()}</p>}
                    {f.human_review?.source_verified && f.source && <button type="button" className="mt-2 block text-left text-xs text-primary underline-offset-2 hover:underline" title={f.source.quote} onClick={(e) => { e.stopPropagation(); onSelect(f.key) }}>
                      Reviewed source · p.{f.source.page} · “{f.source.quote.length > 96 ? `${f.source.quote.slice(0, 93).trimEnd()}…` : f.source.quote}”{f.components?.length ? ` · ${f.components.length} components` : ''}
                    </button>}
                    {/* v179: each summed component gets its own page link — a total's components don't all sit on the field's own source page. */}
                    {!!f.components?.length && (
                      <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-muted-foreground">
                        {f.components.map((c, i) => (
                          <button key={i} type="button" className="text-primary underline-offset-2 hover:underline" title={c.quote} onClick={(e) => { e.stopPropagation(); openPage(f.key, c.page) }}>
                            {c.label || `Component ${i + 1}`} · p.{c.page}
                          </button>
                        ))}
                      </p>
                    )}
                    {/* v179: an OCR'd page is read text, not a photograph — flag it beside the check result, not only inside Source. */}
                    {f.evidence?.includes('ocr_text') && <p className="mt-2 text-xs font-medium text-warning">From OCR — check the scanned image</p>}
                    {['Needs review', 'Not checked', 'Not found'].includes(verification.label) && !reason && (
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{verification.detail}</p>
                    )}
                  </TableCell>
                </TableRow>
                {showReason && (
                  <TableRow className="bg-muted/20 hover:bg-muted/20">
                    <TableCell colSpan={5} className="whitespace-normal px-4 py-3 text-xs leading-relaxed text-muted-foreground">
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
