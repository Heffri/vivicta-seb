import { TriangleAlert } from 'lucide-react'
import { confidenceClass, confidenceTitle, fmtValue } from '@/components/ResultsView'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Field } from '@/types'

type FieldsTableProps = {
  fields: Field[]
  warnings: string[]
  selectedKey: string | null
  onSelect: (key: string) => void
}

/** The product's argument, one row per number: the number, its unit and period, how much
 *  the backend could verify. Selecting a row (click or Enter/Space) aims the Source panel;
 *  the selected row carries an accent left edge and a faint accent wash. */
export function FieldsTable({ fields, warnings, selectedKey, onSelect }: FieldsTableProps) {
  const warningFor = (f: Field) => warnings.find((w) => w.startsWith(f.key + ':'))
  return (
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
                <TableCell>
                  <Badge variant="outline" className={`tabular-nums ${confidenceClass(f.confidence)}`} title={confidenceTitle(f)}>
                    {Math.round(f.confidence * 100)}%
                  </Badge>
                </TableCell>
                <TableCell>
                  {warning && <TriangleAlert className="size-3.5 text-warning" role="img" aria-label={warning} />}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Card>
  )
}
