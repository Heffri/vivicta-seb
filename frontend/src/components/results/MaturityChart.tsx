import { Check, Minus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fmtValue } from '@/components/ResultsView'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Extraction, Field } from '@/types'

// Copied verbatim from backend/pipeline/ppt.py — change it there first, then here.
// HANDOFF.md: "update BUCKET_ORDER / BUCKET_LABELS in ppt.py — that is the only coupling."
// Exported for reuse by components/compare/MaturityBar.tsx (v020) — same bucket judgment,
// not re-derived — per the "only coupling" note above, this file stays the one place a
// bucket-key change must land.
export const BUCKET_ORDER = ['due_within_1_year', 'due_1_to_5_years', 'due_after_5_years'] as const
export const BUCKET_LABELS: Record<(typeof BUCKET_ORDER)[number], string> = {
  due_within_1_year: '< 1 year',
  due_1_to_5_years: '1–5 years',
  due_after_5_years: '> 5 years',
}
// The schema's one identity check (backend/schemas/debt_maturity.json). checks carry no
// identity flag over the API (docs/API.md), so the result is looked up by name — never recomputed here.
export const IDENTITY_CHECK = 'maturity_sums_to_total'

// v091: "Show prior year" remembers its last position per browser (default off = the exact
// pre-v091 rendering). Same pattern as ResultsView's provenance-viewer key.
const PRIOR_KEY = 'maturity-prior-year'
// v109: "Per year" likewise remembers its position (default off = the three-bucket rendering).
const PER_YEAR_KEY = 'maturity-per-year'

type Props = {
  extraction: Extraction
  selectedKey: string | null
  onSelect: (key: string) => void
  onPriorChange?: (shown: boolean) => void // v091: mirrors the toggle so the Export PPTX href can follow it (?prior_year=1)
  onPerYearChange?: (shown: boolean) => void // v109: same mirror for "Per year" (?per_year=1)
}

// Same rule as ppt.py build_pptx, translated verbatim: draw a bar chart iff any bucket
// key is present with a non-null value — decided on field keys, never the section name.
// Every bucket gets a slot even when null (a missing bucket is the normal case, HANDOFF.md).
export const bucketSlots = (fields: Field[]) => {
  const byKey = new Map(fields.map((f) => [f.key, f]))
  return BUCKET_ORDER.map((key) => byKey.get(key) ?? null)
}
export const numeric = (f: Field | null) => (f && typeof f.value === 'number' ? f.value : null)

// The chart-vs-nothing judgment, exported so CompareView can decide the same way per
// column before it draws anything (v020) — never a second, independently-maintained rule.
export const isMaturitySection = (fields: Field[]) => bucketSlots(fields).some((f) => f && f.value !== null)

// Round the axis top up to a clean step so ticks land on printed numbers: 29 165 → step
// 10 000, top 40 000, ticks 0/10 000/20 000/30 000/40 000.
const niceStep = (v: number) => {
  const pow = 10 ** Math.floor(Math.log10(Math.max(v, 1)))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= v) return m * pow
  return 10 * pow
}

// Column with a 4px rounded data-end and a square baseline (dataviz mark spec).
const barPath = (cx: number, top: number, w: number, baseline: number) => {
  const h = baseline - top
  if (h <= 0) return ''
  const r = Math.min(4, h)
  const x = cx - w / 2
  return `M${x} ${baseline} V${top + r} Q${x} ${top} ${x + r} ${top} H${x + w - r} Q${x + w} ${top} ${x + w} ${top + r} V${baseline} Z`
}

const VIEW = { w: 640, h: 300 }
const M = { top: 32, right: 16, bottom: 40, left: 64 }
const PLOT = { w: VIEW.w - M.left - M.right, h: VIEW.h - M.top - M.bottom }
const BASELINE = M.top + PLOT.h
const BAR_W = 24 // mark cap: thin columns, the band's leftover stays air
const TICKS = 4

// Bars read as the primary sticker on glass (DESIGN.md); hover/selection one step
// brighter via the raw accent, failure stays on the check line, not the marks.
const BAR_FILL = 'var(--primary)'
const BAR_FILL_LIT = 'color-mix(in srgb, var(--ring) 45%, var(--primary))'
// v091: the prior year sits beside the current one as the same mark one step fainter — the
// accent at 60% opacity over the glass, never a second hue competing with the primary series.
const BAR_FILL_PRIOR = 'color-mix(in srgb, var(--primary) 60%, transparent)'

const loadPrior = () => {
  try {
    return localStorage.getItem(PRIOR_KEY) === '1'
  } catch {
    return false
  }
}

const loadPerYear = () => {
  try {
    return localStorage.getItem(PER_YEAR_KEY) === '1'
  } catch {
    return false
  }
}

/** The ppt.py slide, on the results view: total debt + one column per maturity bucket.
 *  Renders nothing unless the section has bucket fields (see bucketSlots). Clicking a
 *  column selects its field row, so the Source panel jumps to that field's page — the
 *  same selection the table drives. Pure SVG, no chart library.
 *
 *  v091: when the extraction carries `prior_year` (the prior fiscal year's own figures,
 *  read deterministically from the same table and identity-gated by the backend), a
 *  "Show prior year (FY<n>)" switch offers them beside each bucket — default off, and off
 *  renders exactly the chart this file drew before the switch existed.
 *
 *  v109: when the extraction carries `buckets_by_year` (the report's own calendar-year
 *  columns, identity-gated against total_debt), a "Per year" switch redraws the body as
 *  one column per printed year — the report's own granularity instead of the three fixed
 *  buckets. Default off; off (or no key) renders exactly the chart above, and the two
 *  switches are mutually exclusive: one chart, one question. */
export function MaturityChart({ extraction, selectedKey, onSelect, onPriorChange, onPerYearChange }: Props) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)
  const [showPrior, setShowPrior] = useState(loadPrior)
  const [showPerYear, setShowPerYear] = useState(loadPerYear)
  const prior = extraction.prior_year ?? null
  const byYear = extraction.buckets_by_year ?? null
  // v109: the two switches are mutually exclusive — one chart, one question. "Per year" redraws
  // the body as the report's own calendar-year columns (no bucket fields behind the bars); the
  // prior-year series is bucket-shaped and cannot ride along on year categories. Turning either
  // on turns the other off, so at most one non-default view ever renders.
  const years = showPerYear && byYear ? byYear.years : null
  const perYearView = years !== null
  const py = showPrior && prior && !years ? prior : null // the prior year actually drawn (null when off / not carried / per-year view)
  const dual = !!py

  const priorValue = (key: string) => {
    const v = py?.fields[key]?.value
    return typeof v === 'number' ? v : null
  }

  const persist = (key: string, next: boolean) => {
    try {
      localStorage.setItem(key, next ? '1' : '0')
    } catch {
      /* private mode etc. — preference just won't stick */
    }
  }

  useEffect(() => {
    onPriorChange?.(dual)
  }, [dual, onPriorChange])
  useEffect(() => {
    onPerYearChange?.(perYearView)
  }, [perYearView, onPerYearChange])

  const slots = bucketSlots(extraction.fields)
  if (!slots.some((f) => f && f.value !== null)) return null

  const byKey = new Map(extraction.fields.map((f) => [f.key, f]))
  const total = byKey.get('total_debt') ?? null
  const priorTotal = priorValue('total_debt')
  const check = extraction.checks.find((c) => c.name === IDENTITY_CHECK) ?? null
  const missing = check?.status === 'unavailable' || !!check?.stale || (check?.detail.startsWith('missing:') ?? false)
  const unit = extraction.currency ?? ''

  const step = years
    ? niceStep(Math.max(0, ...years.map((yr) => yr.value)) / TICKS)
    : niceStep(
        Math.max(...slots.map(numeric).map((v) => v ?? 0), ...(dual ? BUCKET_ORDER.map((k) => priorValue(k) ?? 0) : [])) / TICKS,
      )
  const top = step * TICKS
  const y = (v: number) => BASELINE - (v / top) * PLOT.h
  const band = PLOT.w / (years ? years.length : slots.length)

  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle>Maturity profile</CardTitle>
        <CardAction>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {byYear && (
              <button
                type="button"
                role="switch"
                aria-checked={perYearView}
                onClick={() => {
                  const next = !perYearView
                  setShowPerYear(next)
                  persist(PER_YEAR_KEY, next)
                  if (next && showPrior) {
                    // mutually exclusive: the per-year view has no bucket bars for a prior series
                    setShowPrior(false)
                    persist(PRIOR_KEY, false)
                  }
                }}
                className="inline-flex cursor-pointer items-center gap-2 rounded-md text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span
                  aria-hidden
                  className={`relative inline-flex h-4.5 w-8 shrink-0 items-center rounded-full border transition-colors ${
                    perYearView ? 'border-primary/50 bg-primary/30' : 'border-line-2 bg-transparent'
                  }`}
                >
                  <span
                    aria-hidden
                    className={`absolute size-3 rounded-full transition-[left,background-color] ${
                      perYearView ? 'left-[calc(100%-0.9375rem)] bg-primary-foreground' : 'left-0.5 bg-fg-3'
                    }`}
                  />
                </span>
                Per year
              </button>
            )}
            {prior && (
              <button
                type="button"
                role="switch"
                aria-checked={dual}
                onClick={() => {
                  // keyed on what is actually drawn (dual), not the raw state: if both switches were
                  // remembered on across a reload, the per-year view wins and this switch honestly
                  // reads off until clicked — the click then restores the bucket view with prior bars
                  const next = !dual
                  setShowPrior(next)
                  persist(PRIOR_KEY, next)
                  if (next && perYearView) {
                    // mutually exclusive, the other direction: bucket bars are back, years are not
                    setShowPerYear(false)
                    persist(PER_YEAR_KEY, false)
                  }
                }}
                className="inline-flex cursor-pointer items-center gap-2 rounded-md text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span
                  aria-hidden
                  className={`relative inline-flex h-4.5 w-8 shrink-0 items-center rounded-full border transition-colors ${
                    dual ? 'border-primary/50 bg-primary/30' : 'border-line-2 bg-transparent'
                  }`}
                >
                  <span
                    className={`absolute size-3 rounded-full transition-[left,background-color] ${
                      dual ? 'left-[calc(100%-0.9375rem)] bg-primary-foreground' : 'left-0.5 bg-fg-3'
                    }`}
                  />
                </span>
                Show prior year (FY{prior.fiscal_year})
              </button>
            )}
            <span>
              Total debt <span className="font-semibold">{fmtValue(total?.value ?? null)}</span>
              {unit ? ` ${unit}` : ''}
              {py && priorTotal !== null ? (
                <>
                  {' · '}
                  <span className="text-muted-foreground">
                    FY{py.fiscal_year} <span className="font-semibold">{fmtValue(priorTotal)}</span>
                  </span>
                </>
              ) : null}
            </span>
            {check && (
              <span
                className={`flex items-center gap-1.5 ${missing ? 'text-muted-foreground' : check.passed ? 'text-success' : 'text-danger'}`}
                title={check.detail}
              >
                {missing ? <Minus className="size-4" aria-hidden /> : check.passed ? <Check className="size-4" aria-hidden /> : <X className="size-4" aria-hidden />}
                {check.stale ? 'Needs recalculation after human correction' : missing ? 'Not enough data to check the total' : check.passed ? 'Repayments add up to total debt (within rounding)' : 'Repayments do not add up to total debt'}
              </span>
            )}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} className="mx-auto h-auto w-full max-w-3xl">
          {/* unit of the value axis, top left */}
          <text x={2} y={14} fontSize={11} fill="var(--fg-3)">
            {unit}
          </text>

          {/* v091: with both years on, the legend names them beside the unit, top right */}
          {py && (
            <g fontSize={11}>
              <rect x={VIEW.w - M.right - 196} y={4} width={10} height={10} rx={2} fill={BAR_FILL} />
              <text x={VIEW.w - M.right - 181} y={13} fill="var(--fg-2)">
                FY{extraction.fiscal_year ?? '—'}
              </text>
              <rect x={VIEW.w - M.right - 128} y={4} width={10} height={10} rx={2} fill={BAR_FILL_PRIOR} stroke="var(--line-2)" />
              <text x={VIEW.w - M.right - 113} y={13} fill="var(--fg-2)">
                FY{py.fiscal_year}
              </text>
            </g>
          )}

          {/* value axis: recessive solid hairlines, clean tick numbers */}
          {Array.from({ length: TICKS + 1 }, (_, i) => i * step).map((t) => (
            <g key={t}>
              <line
                x1={M.left}
                x2={VIEW.w - M.right}
                y1={y(t)}
                y2={y(t)}
                stroke={t === 0 ? 'var(--line-2)' : 'var(--line-0)'}
              />
              <text x={M.left - 8} y={y(t)} dy={4} fontSize={11} textAnchor="end" fill="var(--fg-3)" className="tabular-nums">
                {fmtValue(t)}
              </text>
            </g>
          ))}

          {years ? (
            /* v109: the report's own calendar-year columns, one bar per printed year — the same
               marks, the same color, no field key behind a year so the bars are not selectable;
               the header's total line and check indicator are the view's own provenance */
            years.map((yr, i) => {
              const cx = M.left + band * i + band / 2
              const v = typeof yr.value === 'number' ? yr.value : 0
              return (
                <g key={`${yr.label}:${i}`}>
                  <title>{`${yr.label}: ${fmtValue(v)}${unit ? ` ${unit}` : ''}`}</title>
                  {v > 0 && <path d={barPath(cx, y(v), BAR_W, BASELINE)} fill={BAR_FILL} />}
                  <text x={cx} y={(v > 0 ? y(v) : BASELINE) - 7} fontSize={12} fontWeight={500} textAnchor="middle" fill="var(--fg-1)">
                    {fmtValue(v)}
                  </text>
                  <text x={cx} y={BASELINE + 24} fontSize={12} textAnchor="middle" fill="var(--fg-2)">
                    {yr.label}
                  </text>
                </g>
              )
            })
          ) : (
          slots.map((f, i) => {
            const key = f?.key ?? BUCKET_ORDER[i]
            const cx = M.left + band * i + band / 2
            const v = numeric(f)
            const lit = f && (key === selectedKey || key === hoveredKey)
            const pv = dual ? priorValue(key) : null
            // grouped columns while both years show: current left, prior right; single-centred
            // otherwise — the exact pre-v091 geometry, unchanged when the switch is off
            const curCx = pv === null ? cx : cx - BAR_W / 2 - 2
            const priCx = cx + BAR_W / 2 + 2
            return (
              <g
                key={key}
                role="button"
                tabIndex={0}
                aria-label={f ? (f.value === null ? `${f.label} — no value` : f.label) : key}
                aria-pressed={key === selectedKey}
                onClick={() => onSelect(key)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect(key)
                  }
                }}
                onMouseEnter={() => setHoveredKey(key)}
                onMouseLeave={() => setHoveredKey(null)}
                className="cursor-pointer rounded-md outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
              >
                {f && <title>{`${f.label}: ${f.value === null ? 'no value' : fmtValue(f.value)}${unit ? ` ${unit}` : ''}`}</title>}

                {/* null bucket: an empty column on the baseline, never a zero bar */}
                {f && v === null && (
                  <>
                    <rect x={curCx - BAR_W / 2} y={BASELINE - 12} width={BAR_W} height={12} rx={2} fill="none" stroke="var(--line-2)" strokeDasharray="3 3" />
                    <text x={curCx} y={BASELINE - 19} fontSize={12} textAnchor="middle" fill="var(--fg-3)">
                      {fmtValue(null)}
                    </text>
                  </>
                )}

                {v !== null && v > 0 && <path d={barPath(curCx, y(v), BAR_W, BASELINE)} fill={lit ? BAR_FILL_LIT : BAR_FILL} />}
                <text
                  x={curCx}
                  y={(v !== null ? y(v) : BASELINE) - 7}
                  fontSize={12}
                  fontWeight={lit ? 600 : 500}
                  textAnchor="middle"
                  fill={f && f.value === null ? 'var(--fg-3)' : 'var(--fg-1)'}
                >
                  {fmtValue(f && f.value !== null ? f.value : null)}
                </text>
                {pv !== null && pv > 0 && (
                  <path d={barPath(priCx, y(pv), BAR_W, BASELINE)} fill={BAR_FILL_PRIOR}>
                    {py && <title>{`FY${py.fiscal_year} ${BUCKET_LABELS[BUCKET_ORDER[i]]}: ${fmtValue(pv)}${unit ? ` ${unit}` : ''}`}</title>}
                  </path>
                )}
                {pv !== null && (
                  <text x={priCx} y={y(pv) - 7} fontSize={11} textAnchor="middle" fill="var(--fg-3)">
                    {fmtValue(pv)}
                  </text>
                )}
                <text x={cx} y={BASELINE + 24} fontSize={12} textAnchor="middle" fill="var(--fg-2)">
                  {BUCKET_LABELS[BUCKET_ORDER[i]]}
                </text>

                {/* the hit target is the whole band, not the 24px mark */}
                <rect x={M.left + band * i} y={M.top} width={band} height={PLOT.h + 28} fill="transparent" />
              </g>
            )
          })
          )}
        </svg>
      </CardContent>
    </Card>
  )
}
