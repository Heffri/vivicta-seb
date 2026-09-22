import { Check, Loader2, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorBlock } from '@/components/ui/state'
import type { SearchTrace as SearchTraceState } from '@/hooks/useReportSearch'

type Props = {
  trace: SearchTraceState
  onRetry?: () => void // only offered for a failed discover trace — a failed fetch already has its own Retry in BatchProgress
}

const STAGE_LABEL: Record<string, string> = {
  directory: 'Checking saved reports',
  mfn: 'Searching MFN',
  nasdaq: 'Searching Nasdaq',
  ddg: 'Searching the web',
  model_search: 'Asking the connected model',
  ir_page: 'Following the investor-relations page',
  download: 'Downloading',
  verify: 'Checking the document',
  done: 'Done',
  failed: 'Failed',
}

const MAX_EVENTS_SHOWN = 8 // the full trail lives in the job table; this is the "last N" the work order asks for

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// v194: the AI-search progress trail — jobs.py's job table, polled every 1.5 s by useReportSearch —
// rendered as a scrolling trail of recent events, the current stage, a stopwatch and (while a
// download event is the latest one) a byte-progress bar. Closed models have no chain of thought to
// show; these "what it's doing" events are the closest honest substitute, which is the whole point
// of the P0 this fixes: a search that used to look identically "stuck" whether it was working or dead
// now visibly does something the entire time, and switching tabs and back finds it unchanged.
export function SearchTracePanel({ trace, onRetry }: Props) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (trace.done) return
    const t = setInterval(() => setNow(Date.now()), 400)
    return () => clearInterval(t)
  }, [trace.done])

  const elapsed = Math.max(0, Math.round(((trace.finishedAt ?? now) - trace.startedAt) / 1000))
  const shown = trace.events.slice(-MAX_EVENTS_SHOWN)
  const last = trace.events.at(-1)
  const dlBytes = last?.stage === 'download' && typeof last.data?.bytes === 'number' ? last.data.bytes : null
  const dlTotal = last?.stage === 'download' && typeof last.data?.total === 'number' ? last.data.total : null
  const downloadPct = dlBytes !== null && dlTotal !== null && dlTotal > 0 ? Math.min(100, Math.round((dlBytes / dlTotal) * 100)) : null

  return (
    <div className="space-y-2 rounded-lg border border-border bg-background/40 px-3 py-2 text-sm" aria-live="polite">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="shrink-0">
          {trace.error ? (
            <TriangleAlert className="size-4 text-danger" aria-hidden />
          ) : trace.done ? (
            <Check className="size-4 text-success" aria-hidden />
          ) : (
            <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
          )}
        </span>
        <span className="font-medium">{trace.label}</span>
        <span className="text-xs text-muted-foreground tabular-nums">{elapsed}s</span>
        <span className="text-xs text-muted-foreground">· {STAGE_LABEL[trace.stage] ?? trace.stage}</span>
      </div>

      {downloadPct !== null && dlBytes !== null && dlTotal !== null && (
        <div className="space-y-1" role="progressbar" aria-label="Download progress" aria-valuenow={downloadPct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${downloadPct}%` }} />
          </div>
          <p className="text-xs text-muted-foreground tabular-nums">
            {formatBytes(dlBytes)} / {formatBytes(dlTotal)}
          </p>
        </div>
      )}

      {shown.length > 0 && (
        <ul className="space-y-0.5 border-l border-border pl-2.5 text-xs text-muted-foreground" aria-label="Search progress log">
          {shown.map((e, i) => (
            <li key={`${e.t}-${i}`} className="truncate">
              {e.text}
            </li>
          ))}
        </ul>
      )}

      {trace.error && (
        <div className="pt-0.5">
          <ErrorBlock className="px-3 py-2 text-xs">{trace.error}</ErrorBlock>
          {onRetry && (
            <Button variant="outline" size="xs" className="mt-1.5" onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
