import { fmtValue } from '@/components/ResultsView'
import { fieldVerification } from './verification'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Field } from '@/types'

type FieldsTableProps = {
  fields: Field[]
  selectedKey: string | null
  onSelect: (key: string) => void
}

/** The product's argument, one row per number: the number, its unit and period, how much
 *  the backend could verify. Selecting a row (click or Enter/Space) aims the Source panel;
 *  the selected row carries an accent left edge and a faint accent wash. */
export function FieldsTable({ fields, selectedKey, onSelect }: FieldsTableProps) {
  return (
    <Card className="py-0">
      <p className="px-4 pt-4 text-xs text-muted-foreground">Select a figure to see its source and verification details.</p>
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
                  <Badge variant={verification.variant} title={verification.detail}>
                    {verification.label}
                  </Badge>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Card>
  )
}
