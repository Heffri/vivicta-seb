import { BarChart3 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getMaturityWall } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Collection } from '@/hooks/useCollection'
import type { KbEntry, MaturityWall, MaturityWallRow } from '@/types'

type Props = { collection: Collection; entries: KbEntry[]; onOpenReport: (report: KbEntry) => void }

// Same wording the KB header and Compare's Upcoming maturities use for the shared collection choice.
const collectionLabel = (collection: Collection) =>
  collection === 'wallenberg' ? 'Wallenberg collection' : collection === 'midcap' ? 'SEB Mid Cap universe' : 'all saved reports'

// The one mark vocabulary of results/MaturityChart.tsx, turned 90°: primary bars the identity check
// vouches for, hover one step brighter via the raw accent, hairline grid, four text tones.
const BAR_FILL = 'var(--primary)'
const BAR_FILL_LIT = 'color-mix(in srgb, var(--ring) 45%, var(--primary))'
const BAR_GREY = 'color-mix(in srgb, var(--fg-3) 32%, transparent)'

const VIEW = { w: 940 }
const LABEL_X = 196 // company names right-align to this
const BAR_X = 204
const AXIS_W = 560 // 204..764 spans 0–100 % of total debt
const VALUE_X = 772 // 168px for "100.0% · buckets incomplete" — the longest honest label
const TOP = 30 // the % ticks live above the first row
const ROW_H = 21
const SECTOR_H = 30
const BAR_H = 13

const pct = (share: number) => `${(share * 100).toFixed(1)}%`

// Value-column text, mirroring the deck page's states. A total the report never prints is "not
// read"; incomplete buckets say so (the computable share still sets the grey bar); a complete row
// without a comparable share (no debt outstanding, unmatched units) carries the backend's own reason.
const valueText = (row: MaturityWallRow): string => {
  if (row.total.value === null) return 'not read'
  if (row.share === null) return row.complete ? 'no comparable figure' : 'buckets incomplete'
  return row.complete ? pct(row.share) : `${pct(row.share)} · buckets incomplete`
}

const truncate = (name: string) => (name.length <= 26 ? name : `${name.slice(0, 25)}…`)

// Horizontal sibling of MaturityChart's barPath: rounded data end, square baseline.
const hbarPath = (x: number, y: number, w: number, h: number) => {
  if (w <= 0) return ''
  const r = Math.min(4, w, h / 2)
  return `M${x} ${y} h${w - r} q${r} 0 ${r} ${r} v${h - 2 * r} q0 ${r} -${r} ${r} h${-(w - r)} Z`
}

/** v180 (consult-fable #2): the KB page's "Maturity wall" card, beside the collection switch.
 *  The sector view of GET /api/kb/maturity-wall — one bar per company (due_within_1_year /
 *  total_debt), grouped by sector, honest about buckets that do not reconcile (grey, labelled)
 *  and totals never read ("not read"). Nothing is inferred; a missing bucket is never a 0.
 *  Clicking a row opens that company through KbView's existing Open action. The collection comes
 *  from the KbView picker as a prop — a second useCollection() instance here would read localStorage
 *  once on mount and never follow the picker beside it. Data loads only when the card is opened —
 *  the KB list is expensive enough already. */
export function MaturityWallCard({ collection, entries, onOpenReport }: Props) {
  const [open, setOpen] = useState(false)
  const [wall, setWall] = useState<MaturityWall | null>(null)
  const [loadedFor, setLoadedFor] = useState<Collection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let stale = false
    setError(null)
    getMaturityWall(collection)
      .then((w) => { if (!stale) { setWall(w); setLoadedFor(collection) } })
      .catch((e: Error) => { if (!stale) setError(e.message) })
    return () => { stale = true }
  }, [open, collection])

  const rows = loadedFor === collection ? wall?.rows ?? [] : []
  // Sector blocks: alphabetical with the unknown-sector block last; within a block complete
  // companies first by share descending — the same order the deck's sector pages draw.
  const map = new Map<string | null, MaturityWallRow[]>()
  for (const row of rows) {
    const list = map.get(row.sector)
    if (list) list.push(row)
    else map.set(row.sector, [row])
  }
  const groups = [...map.entries()].sort(([a], [b]) => (a === null ? 1 : 0) - (b === null ? 1 : 0) || (a ?? '').localeCompare(b ?? ''))
  for (const [, list] of groups) {
    list.sort((a, b) =>
      Number(b.complete) - Number(a.complete) ||
      (b.share ?? -1) - (a.share ?? -1) ||
      (a.company ?? a.stem).localeCompare(b.company ?? b.stem))
  }
  const height = TOP + 6 + groups.reduce((acc, [, list]) => acc + SECTOR_H + list.length * ROW_H, 0)
  const completeN = rows.filter((r) => r.complete).length

  const openRow = (row: MaturityWallRow) => {
    const report = entries.find((e) => e.stem === row.stem)
    if (report) onOpenReport(report)
  }

  return (
    <>
      <Button variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <BarChart3 aria-hidden /> Maturity wall
      </Button>
      {open && (
        <Card role="region" aria-label="Maturity wall" className="w-full space-y-3 p-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Maturity wall · {collectionLabel(collection)}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              share of debt due within 1 year · {completeN} of {rows.length} companies with complete buckets
            </p>
          </div>
          {error && <ErrorBlock>{error}</ErrorBlock>}
          {!error && loadedFor !== collection && <LoadingLine>Loading saved debt maturity extractions…</LoadingLine>}
          {!error && loadedFor === collection && rows.length === 0 && (
            <p className="text-sm text-muted-foreground">No saved debt maturity extractions in {collectionLabel(collection)} yet.</p>
          )}
          {!error && rows.length > 0 && (
            <div className="max-h-[70vh] overflow-y-auto">
              <svg viewBox={`0 0 ${VIEW.w} ${height}`} className="h-auto w-full" role="img" aria-label={`Maturity wall by sector: ${groups.length} sector groups, ${rows.length} companies`}>
                {/* the 0–100 % axis, same recessive hairlines as MaturityChart */}
                {[0, 25, 50, 75, 100].map((t) => (
                  <g key={t}>
                    <line
                      x1={BAR_X + (t / 100) * AXIS_W}
                      x2={BAR_X + (t / 100) * AXIS_W}
                      y1={TOP - 8}
                      y2={height - 4}
                      stroke={t === 0 ? 'var(--line-2)' : 'var(--line-0)'}
                    />
                    <text x={BAR_X + (t / 100) * AXIS_W} y={14} fontSize={10} textAnchor="middle" fill="var(--fg-3)" className="tabular-nums">
                      {t}%
                    </text>
                  </g>
                ))}
                {groups.map(([sector, list], gi) => {
                  const y0 = TOP + groups.slice(0, gi).reduce((acc, [, l]) => acc + SECTOR_H + l.length * ROW_H, 0)
                  return (
                    <g key={sector ?? 'unknown'}>
                      {/* role=heading gives the e2e (and screen readers) the group count */}
                      <g role="heading" aria-level={3} aria-label={`Sector ${sector ?? 'Unknown sector'}: ${list.filter((r) => r.complete).length} of ${list.length} with complete buckets`}>
                        <text x={0} y={y0 + 14} fontSize={12} fontWeight={600} fill="var(--fg-1)">
                          {sector ?? 'Unknown sector'}
                          <tspan fontWeight={400} fill="var(--fg-3)">
                            {' '}· {list.filter((r) => r.complete).length} of {list.length} with complete buckets
                          </tspan>
                        </text>
                      </g>
                      {list.map((row, i) => {
                        const y = y0 + SECTOR_H + i * ROW_H
                        const label = row.company ?? row.stem
                        const openable = entries.some((e) => e.stem === row.stem)
                        const lit = row.stem === hovered
                        const value = valueText(row)
                        return (
                          <g
                            key={row.stem}
                            role="button"
                            tabIndex={0}
                            aria-label={`${label}: ${value}`}
                            aria-disabled={!openable}
                            onClick={() => openRow(row)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                openRow(row)
                              }
                            }}
                            onMouseEnter={() => setHovered(row.stem)}
                            onMouseLeave={() => setHovered(null)}
                            className={openable ? 'cursor-pointer outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring' : undefined}
                          >
                            <title>
                              {row.total.value === null
                                ? `${label}: total debt not read in this report`
                                : row.share === null
                                  ? `${label}: ${value}`
                                  : `${label}: ${pct(row.share)} of total debt due within 1 year${row.complete ? '' : ' (buckets incomplete)'}`}
                            </title>
                            <rect x={0} y={y} width={VIEW.w} height={ROW_H} fill="transparent" />
                            <text x={LABEL_X} y={y + ROW_H / 2 + 4} fontSize={11} textAnchor="end" fill={row.complete ? 'var(--fg-1)' : 'var(--fg-3)'}>
                              {truncate(label)}
                            </text>
                            {row.share !== null && (
                              <path
                                d={hbarPath(BAR_X, y + (ROW_H - BAR_H) / 2, Math.min(Math.max(row.share, 0), 1) * AXIS_W, BAR_H)}
                                fill={row.complete ? (lit ? BAR_FILL_LIT : BAR_FILL) : BAR_GREY}
                              />
                            )}
                            <text x={VALUE_X} y={y + ROW_H / 2 + 4} fontSize={11} fill={row.complete && row.share !== null ? 'var(--fg-1)' : 'var(--fg-3)'}>
                              {value}
                            </text>
                          </g>
                        )
                      })}
                    </g>
                  )
                })}
              </svg>
            </div>
          )}
        </Card>
      )}
    </>
  )
}
