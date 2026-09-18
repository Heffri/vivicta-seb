import { fmtValue } from '@/components/ResultsView'
import { BUCKET_LABELS, BUCKET_ORDER, IDENTITY_CHECK, bucketSlots, numeric } from '@/components/results/MaturityChart'
import type { Extraction } from '@/types'

// Ordinal ramp, one hue: --primary -> --ring, monotone step per bucket (dataviz skill,
// "ordinal" job — swapping bucket order would change the meaning, so it's a ramp, not
// categorical colors). Near-term most emphasized; the boldest step (50%) matches
// MaturityChart's own "lit" mix (45%) so the two views read as the same accent language.
const SEG_RING_MIX = [50, 28, 12] // one per BUCKET_ORDER slot
const segColor = (i: number) => `color-mix(in srgb, var(--ring) ${SEG_RING_MIX[i]}%, var(--primary))`

// Below this, don't bother drawing a sliver for it — same rounding tolerance as
// backend/schemas/debt_maturity.json's maturity_sums_to_total check (pass/fail itself
// always comes from that check's own result below, never recomputed).
const SUM_TOLERANCE = 2

const tooltipCls =
  'glass pointer-events-none absolute bottom-full left-1/2 z-20 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs text-popover-foreground opacity-0 ring-1 ring-foreground/10 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100'
// Each segment rounds itself (never the track): a shared `overflow-hidden` on the track
// would clip the hover tooltip, which must escape upward past the bar's own top edge.
const segCls =
  'group relative h-full min-w-1.5 shrink-0 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1'

/** One row of the Compare matrix (v020): a horizontal three-segment bar per column, each
 *  segment sized to its bucket's share of total_debt — the same bucket judgment as
 *  MaturityChart (results view), reused rather than re-decided. Renders unconditionally;
 *  CompareView only mounts it once every successful column is bucket-shaped. */
export function MaturityBar({ extraction }: { extraction: Extraction }) {
  const slots = bucketSlots(extraction.fields)
  const total = numeric(extraction.fields.find((f) => f.key === 'total_debt') ?? null)
  const unit = extraction.currency ?? ''
  const sum = slots.reduce((s, f) => s + (numeric(f) ?? 0), 0)

  // Pass/fail comes from the backend's own check (same judgment as MaturityChart's header
  // indicator) — never recomputed here. Only the sliver's *width* is derived locally, from
  // the same numbers already needed to size the three real segments.
  const check = extraction.checks.find((c) => c.name === IDENTITY_CHECK) ?? null
  const missing = check?.status === 'unavailable' || !!check?.stale || (check?.detail.startsWith('missing:') ?? false)
  const mismatch = check ? !check.passed && !missing : false
  const shortfall = (total ?? 0) - sum
  const denom = Math.max(total ?? 0, sum, 1e-9)
  const sliverPct = mismatch && shortfall > SUM_TOLERANCE ? (shortfall / denom) * 100 : 0
  // Sum overshooting total (or total missing) has no free space to draw a sliver in —
  // ring the whole bar instead, per the work order's explicit fallback.
  const outlineOnly = mismatch && sliverPct === 0

  return (
    <div className="w-full max-w-48">
      <div
        role="group"
        aria-label="Maturity profile"
        className={`flex h-2.5 w-full gap-0.5 rounded-full bg-[var(--bg-4)] ${outlineOnly ? 'ring-1 ring-danger' : ''}`}
      >
        {slots.map((f, i) => {
          const key = BUCKET_ORDER[i]
          const label = BUCKET_LABELS[key]
          const v = numeric(f)
          const pct = v === null ? 0 : (v / denom) * 100
          return (
            <div
              key={key}
              tabIndex={0}
              aria-label={`${label}: ${v === null ? 'no value' : fmtValue(v)}${unit ? ` ${unit}` : ''}`}
              style={{ width: `${pct}%`, background: v === null ? 'transparent' : segColor(i) }}
              className={segCls}
            >
              <span className={tooltipCls}>
                {label}: {v === null ? '—' : fmtValue(v)}
                {unit ? ` ${unit}` : ''}
              </span>
            </div>
          )
        })}
        {sliverPct > 0 && (
          <div
            tabIndex={0}
            aria-label={`Unaccounted vs. total: ${fmtValue(shortfall)}${unit ? ` ${unit}` : ''}`}
            style={{ width: `${sliverPct}%`, background: 'color-mix(in srgb, var(--danger) 65%, transparent)' }}
            className={segCls}
          >
            <span className={tooltipCls}>
              Unaccounted: {fmtValue(shortfall)}
              {unit ? ` ${unit}` : ''}
            </span>
          </div>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        total {total === null ? '—' : fmtValue(total)}
        {unit && total !== null ? ` ${unit}` : ''}
      </p>
      {check && (
        <p className={`mt-1 text-xs ${mismatch ? 'text-danger' : 'text-muted-foreground'}`}>
          {check.stale ? 'Needs recalculation after human correction' : missing ? 'Not enough data to check the total' : check.passed ? 'Repayments add up (within rounding)' : 'Repayments do not add up to total debt'}
        </p>
      )}
    </div>
  )
}
