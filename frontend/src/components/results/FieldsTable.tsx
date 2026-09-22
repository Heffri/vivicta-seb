import { fmtValue } from '@/components/ResultsView'
import { fieldVerification } from './verification'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Field } from '@/types'
import { Check, CircleHelp, TriangleAlert } from 'lucide-react'

type FieldsTableProps = {
  compact?: boolean
  fields: Field[]
  selectedKey: string | null
  onSelect: (key: string) => void
}

/** The product's argument, one row per number: the number, its unit and period, how much
 *  the backend could verify. Selecting a row (click or Enter/Space) aims the Source panel;
 *  the selected row carries an accent left edge and a faint accent wash. */
export function FieldsTable({ fields, selectedKey, onSelect, compact = false }: FieldsTableProps) {
  // Share the most common unit/period once; exceptions remain beside their values.
  const mostCommon = (values: (string | null | undefined)[]) => [...new Set(values)].sort((a, b) => values.filter(v => v === b).length - values.filter(v => v === a).length)[0]
  const unit = mostCommon(fields.map(f => f.unit))
  const period = mostCommon(fields.map(f => f.period))
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
            const verification = fieldVerification(f)
            const Status = verification.variant === 'success' ? Check : verification.variant === 'warning' ? TriangleAlert : CircleHelp
            return (
              <TableRow
                key={f.key}
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
                <TableCell className="whitespace-normal font-medium"><span>{f.label}</span></TableCell>
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
                  {f.human_review && <p className="mt-2 text-xs text-muted-foreground" title={fieldVerification({ ...f, human_review: undefined }).detail}>Automated evidence: {fieldVerification({ ...f, human_review: undefined }).label.toLowerCase()}</p>}
                  {['Needs review', 'Not checked', 'Not found'].includes(verification.label) && (
                    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{verification.detail}</p>
                  )}
                </TableCell>
                </>}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Card>
  )
}
