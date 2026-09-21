import { useEffect, useState } from 'react'
import { getKb, getMaturityWall } from '@/api'
import { CollectionPicker } from '@/components/CollectionPicker'
import { fmtValue } from '@/components/ResultsView'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useCollection, type Collection } from '@/hooks/useCollection'
import type { KbEntry, MaturityWall as MaturityWallData, MaturityWallRow } from '@/types'

const DEFAULT_THRESHOLD = 30

type Props = {
  // v174: mirrors ReviewQueue's onOpen shape (report, section, key?) rather than KbView's plain
  // onOpenReport(report) -- "Review" deep-links to the field that made the row not comparable.
  onOpenReport?: (report: KbEntry, section?: string, key?: string) => void
}

const collectionLabel = (collection: Collection) =>
  collection === 'wallenberg' ? 'Wallenberg collection' : collection === 'midcap' ? 'SEB Mid Cap universe' : 'all saved reports'

const basisSummary = (row: MaturityWallRow) => [row.consolidation, row.debt_basis, row.leases && `Leases ${row.leases === 'Included' ? 'in' : 'out'}`].filter(Boolean)

const reviewVariant = (status: string): 'danger' | 'secondary' | 'success' =>
  status === 'unresolved' ? 'danger' : status === 'unreviewed' ? 'secondary' : 'success'

/** Compare view section (v174, consult-gpt6 #8 / consult-fable #2): a deterministic, zero-model list of
 *  every saved debt_maturity extraction's total debt, amount due within a year and their share, sorted
 *  comparable-first by share. No FX conversion, no credit judgment -- an exposure filter over what the
 *  KB already has, honest about what is not yet confirmed (gpt6: don't skip confirmation for a chart). */
export function MaturityWall({ onOpenReport }: Props) {
  const [collection, setCollection] = useCollection()
  const [wall, setWall] = useState<MaturityWallData | null>(null)
  const [entries, setEntries] = useState<Map<string, KbEntry>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD)

  useEffect(() => {
    let stale = false
    setError(null)
    Promise.all([getMaturityWall(collection), getKb(collection)])
      .then(([w, kb]) => {
        if (stale) return
        setWall(w)
        setEntries(new Map(kb.map((e) => [e.stem, e])))
      })
      .catch((e: Error) => { if (!stale) setError(e.message) })
    return () => { stale = true }
  }, [collection])

  const rows = wall?.rows ?? []
  const shown = rows.filter((r) => r.share === null || r.share * 100 >= threshold)
  const open = (row: MaturityWallRow, key?: string) => {
    const report = entries.get(row.stem)
    if (report) onOpenReport?.(report, 'debt_maturity', key)
  }

  return (
    <Card className="overflow-x-auto py-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Upcoming maturities · {collectionLabel(collection)}</h2>
          {wall && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {wall.coverage.comparable} of {wall.coverage.total} comparable
              {wall.coverage.basis_unconfirmed > 0 && ` · ${wall.coverage.basis_unconfirmed} basis unconfirmed`}
              {wall.coverage.missing_total > 0 && ` · ${wall.coverage.missing_total} missing total`}
              {wall.coverage.missing_w1y > 0 && ` · ${wall.coverage.missing_w1y} missing <1y`}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <CollectionPicker value={collection} onChange={setCollection} />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="whitespace-nowrap">Due &lt;1y ≥</span>
            <Input
              type="number"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Math.min(100, Math.max(0, Number(e.target.value) || 0)))}
              className="w-16"
              aria-label="Minimum share due within 1 year, percent"
            />
            <span>%</span>
          </label>
        </div>
      </div>

      <div className="mt-3 px-4">
        {error && <ErrorBlock>{error}</ErrorBlock>}
        {!error && !wall && <LoadingLine>Loading saved debt maturity extractions…</LoadingLine>}
        {!error && wall && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">No saved debt maturity extractions in {collectionLabel(collection)} yet.</p>
        )}
        {!error && wall && rows.length > 0 && shown.length === 0 && (
          <p className="text-sm text-muted-foreground">No company's amount due within 1 year reaches {threshold}% of total debt.</p>
        )}
      </div>

      {shown.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead className="text-right">Total debt</TableHead>
              <TableHead className="text-right">Due &lt;1y</TableHead>
              <TableHead className="text-right">Share</TableHead>
              <TableHead>Basis</TableHead>
              <TableHead>Review</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((row) => (
              <TableRow key={row.stem} className={row.comparable ? undefined : 'opacity-70'}>
                <TableCell className="font-medium">
                  {row.company ?? row.stem}
                  <span className="ml-1.5 text-xs font-normal text-muted-foreground">FY {row.fiscal_year ?? '—'}</span>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmtValue(row.total.value)}
                  {row.total.unit && row.total.value !== null && <span className="ml-1 text-xs text-muted-foreground">{row.total.unit}</span>}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmtValue(row.due_within_1_year.value)}
                  {row.due_within_1_year.unit && row.due_within_1_year.value !== null && <span className="ml-1 text-xs text-muted-foreground">{row.due_within_1_year.unit}</span>}
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.share === null ? <span className="text-muted-foreground">N/A</span> : `${(row.share * 100).toFixed(1)}%`}</TableCell>
                <TableCell>
                  {row.basis_confirmed ? (
                    <div className="flex flex-wrap gap-1">
                      {basisSummary(row).map((label) => (
                        <Badge key={label} variant="outline">{label}</Badge>
                      ))}
                    </div>
                  ) : (
                    <Badge variant="warning">Not confirmed</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={reviewVariant(row.review_status)}>{row.review_status}</Badge>
                </TableCell>
                <TableCell className="max-w-52 whitespace-normal text-xs text-muted-foreground">
                  {row.comparable ? (
                    row.reason || '—'
                  ) : (
                    <details>
                      <summary className="cursor-pointer text-warning">Not comparable</summary>
                      <p className="mt-1 leading-relaxed">{row.reason}</p>
                    </details>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1.5">
                    <Button size="xs" variant="outline" disabled={!entries.has(row.stem)} onClick={() => open(row)}>Open</Button>
                    <Button size="xs" variant="outline" disabled={!entries.has(row.stem)} onClick={() => open(row, row.total.value === null ? 'total_debt' : 'due_within_1_year')}>Review</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  )
}
