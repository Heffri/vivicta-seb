import { Ban, Check, ChevronRight, CircleDashed, Loader2, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Tab } from '@/components/shell/tabs'
import type { BatchErrorKind, BatchItem, RegisterOpts } from '@/hooks/useBatch'
import type { ReportListing } from '@/api'

type Props = {
  items: BatchItem[]
  busy: boolean
  stopRequested: boolean
  resultsCount: number
  onStopAfterCurrent: () => void
  onExtractAgain: () => void
  onRetry: (id: string, opts?: RegisterOpts) => void
  onDownload: (id: string, listing: ReportListing) => void
  onViewResults: () => void
  onNavigate?: (tab: Tab) => void
}

// Next-step copy per error kind: 409 means two different things depending which call failed
// (see useBatch's classify()), 422 = no text candidates, 502 = the provider itself. No canned copy
// for 'other' (400 bad file, 404 unknown company, network) — the raw message alone is the only
// honest thing to say there.
const ERROR_COPY: Record<BatchErrorKind, { text: string; settings?: boolean; kb?: boolean }> = {
  'review-protected': { text: 'This report already has a human-reviewed result, which was kept as-is.', kb: true },
  'download-needed': { text: 'No saved text or local PDF for this one — download the report in your browser and upload the PDF above.' },
  'needs-ocr': { text: 'No text found on the candidate pages — this file may need OCR, or try a different one.', settings: true },
  // Only the pages a locator would check were OCR'd; the rest of this scan was left unread to
  // keep registration synchronous. "Run OCR anyway" resends with ocr=full.
  'ocr-budget': { text: 'This is a scanned PDF. Only the pages a locator would check were read — run OCR on the rest to extract from anywhere else in it.' },
  'provider-failed': { text: 'The model provider failed. Check Settings › Test connection, then retry just this one.', settings: true },
  'report-unavailable': { text: 'Automatic search could not verify a report. This does not mean it is unpublished. Upload this company’s annual-report PDF above if you have one, or check a registry or the company’s report archive.' },
  'report-listed': { text: 'Open the listing below, download the annual-report PDF using the site’s normal process, then upload it above. The listing is confirmed; the PDF’s contents have not yet been verified.' },
  'download-failed': { text: 'A source site could not be reached or refused the download. Retry later, or download the report in your browser and upload the PDF above.' },
  other: { text: '' },
}

// The backend's own 422 message already names the estimate ("...~N min for P pages"); read it back
// instead of recomputing it, so the button's number can never drift from what the request actually said.
const ocrMinutes = (message: string | undefined): string | null => message?.match(/~(\d+) min/)?.[1] ?? null

const stageIcon = (item: BatchItem) => {
  switch (item.stage) {
    case 'done':
      return <Check className="size-4 text-success" aria-hidden />
    case 'failed':
      return <TriangleAlert className="size-4 text-danger" aria-hidden />
    case 'skipped':
      return <Ban className="size-4 text-muted-foreground" aria-hidden />
    case 'queued':
      return <CircleDashed className="size-4 text-muted-foreground" aria-hidden />
    default:
      return <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
  }
}

// The wait line carries its own running stopwatch ("… · Note 20 Borrowings … · 2 s"), kept inline
// here (not folded into the header badge below, which covers every other active stage) so that
// exact reading doesn't move or double up. Built as one string, not JSX text mixed with
// an expression across lines — that split is exactly what silently drops the space a regex like
// /· \d+ s$/ depends on.
function stageLine(item: BatchItem, seconds: number | null): string {
  const suffix = item.stage === 'extracting' && item.wait && seconds !== null ? ` · ${seconds} s` : ''
  switch (item.stage) {
    case 'queued':
      return 'Queued'
    case 'registering':
      return item.prep ?? `Preparing ${item.label}`
    case 'candidates':
      return 'Reading candidate pages…'
    case 'extracting':
      return (item.wait ? `Reading pages ${item.wait.pages} of ${item.wait.total} · ${item.wait.heading || item.sectionTitle}` : `Extracting…${item.eta}`) + suffix
    case 'done':
      return 'Done'
    case 'skipped':
      return 'Stopped after current — not started'
    case 'failed':
      return item.errorKind === 'report-listed' ? 'Report listed — manual download needed' : item.errorKind === 'report-unavailable' ? 'Report not found automatically' : item.errorKind === 'download-failed' ? 'Download could not complete' : 'Failed'
  }
}

const hasWaitStopwatch = (item: BatchItem, seconds: number | null) => item.stage === 'extracting' && !!item.wait && seconds !== null

const ACTIVE_STAGES: BatchItem['stage'][] = ['registering', 'candidates', 'extracting']

// Batch state (App-level, this application session only): each report's own
// stage, a stopwatch, whether it reused a cached result, and — for failures — which next step
// applies. Lives below the action bar as its own bordered step of the one glass pane (DESIGN.md);
// survives switching tabs and back because the state itself lives in App, not here.
export function BatchProgress({ items, busy, stopRequested, resultsCount, onStopAfterCurrent, onExtractAgain, onRetry, onDownload, onViewResults, onNavigate }: Props) {
  // The stopwatch: like UploadView's own, the elapsed string is read off `now` — a state
  // value refreshed inside the interval — never off a bare Date.now()/performance.now() call made
  // directly during render, so render stays pure.
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    if (!busy) return
    const t = setInterval(() => setNow(performance.now()), 400)
    return () => clearInterval(t)
  }, [busy])

  if (items.length === 0) return null

  const settledCount = items.filter((it) => it.stage === 'done' || it.stage === 'failed').length
  const remainingCount = items.filter((it) => it.stage === 'queued').length
  const elapsedSeconds = (item: BatchItem) => (item.startedAt == null ? null : Math.max(0, Math.round(((item.finishedAt ?? now) - item.startedAt) / 1000)))

  return (
    <div className="border-t border-border bg-background/50 px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {busy ? `Working · ${settledCount}/${items.length}` : `Batch · ${settledCount}/${items.length}`}
        </p>
        <div className="flex items-center gap-2">
          {resultsCount > 0 && (
            <Button variant="outline" size="xs" onClick={onViewResults}>
              View results ({resultsCount})
              <ChevronRight className="size-3" />
            </Button>
          )}
          {!busy && remainingCount === 0 && (
            <Button variant="outline" size="xs" onClick={onExtractAgain}>
              Extract again
            </Button>
          )}
          {busy && remainingCount > 0 && (
            <Button variant="ghost" size="xs" disabled={stopRequested} onClick={onStopAfterCurrent}>
              {stopRequested ? 'Stopping after this one…' : 'Stop after current'}
            </Button>
          )}
        </div>
      </div>
      <ul className="space-y-2" aria-label="Batch progress">
        {items.map((item) => {
          const copy = item.errorKind ? ERROR_COPY[item.errorKind] : null
          const seconds = elapsedSeconds(item)
          const inlineStopwatch = hasWaitStopwatch(item, seconds)
          return (
            <li key={item.id} className="rounded-lg border border-border bg-background/40 px-3 py-2 text-sm">
              <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                <span className="mt-0.5 shrink-0">{stageIcon(item)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-medium">{item.label}</span>
                    {item.result?.extraction?.cached && (
                      <Badge variant="secondary" className="normal-case">
                        saved result
                      </Badge>
                    )}
                    {/* this report's registration OCR'd a bounded set of pages -- said here so a
                        scanned report doesn't look silently skipped once it reaches Results. */}
                    {item.ocrPages && item.ocrPages.length > 0 && (
                      <Badge variant="secondary" className="normal-case">
                        OCR: {item.ocrPages.length} page{item.ocrPages.length === 1 ? '' : 's'}
                      </Badge>
                    )}
                    {ACTIVE_STAGES.includes(item.stage) && seconds !== null && !inlineStopwatch && (
                      <span className="text-xs text-muted-foreground tabular-nums">{seconds}s</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{stageLine(item, seconds)}</p>
                  {item.sourceNotice && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{item.sourceNotice}</p>}
                  {item.stage === 'failed' && (
                    <div className="mt-1.5">
                      <p className="text-xs text-danger">{item.errorKind === 'report-listed' && window.arp?.downloadReport
                        ? 'The report is listed online, but automatic download could not retrieve its PDF. Use the report website below to continue.'
                        : item.result?.error}</p>
                      {copy?.text && <p className="mt-0.5 text-xs text-muted-foreground">{item.errorKind === 'report-listed' && window.arp?.downloadReport
                        ? 'Choose Download and continue, then use the website’s download button. Complete any site verification yourself. The app checks the downloaded PDF’s company and year, then resumes this extraction automatically.'
                        : copy.text}</p>}
                      {!!item.listings?.length && <ul aria-label="Report listings" className="my-2 space-y-2">{item.listings.filter(listing => /^https?:\/\//i.test(listing.url)).map(listing => <li key={listing.url} className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs">
                        {window.arp?.downloadReport
                          ? <Button variant="outline" size="sm" disabled={busy} onClick={() => onDownload(item.id, listing)}>Download and continue — {listing.title}</Button>
                          : <a className="font-medium text-primary underline" href={listing.url} target="_blank" rel="noreferrer">Open report listing — {listing.title}</a>}
                        <p className="mt-1 text-muted-foreground">{listing.company} · FY{listing.fiscal_year}</p><p className="mt-1 break-words">{listing.evidence}</p>
                      </li>)}</ul>}
                      {item.downloadPending && <p role="status" className="my-2 text-sm">Waiting for the report download in the separate window. Closing that window cancels this step.</p>}
                      {item.downloadError && <p role="alert" className="my-2 text-sm text-danger">{item.downloadError}</p>}
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {item.errorKind === 'ocr-budget' ? (
                          <Button variant="outline" size="xs" disabled={item.retrying} onClick={() => onRetry(item.id, { ocr: 'full' })}>
                            {item.retrying
                              ? 'Running OCR…'
                              : `Run OCR anyway${ocrMinutes(item.result?.error) ? ` (~${ocrMinutes(item.result?.error)} min)` : ''}`}
                          </Button>
                        ) : (
                          <>
                            {copy?.kb && (
                              <Button variant="outline" size="xs" onClick={() => onNavigate?.('kb')}>
                                Open Knowledge base
                              </Button>
                            )}
                            {copy?.settings && (
                              <Button variant="outline" size="xs" onClick={() => onNavigate?.('settings')}>
                                Open Settings
                              </Button>
                            )}
                            {!copy?.kb && (
                              <Button variant="outline" size="xs" disabled={item.retrying} onClick={() => onRetry(item.id)}>
                                {item.retrying ? 'Retrying…' : 'Retry this one'}
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                      {!!item.attempts?.length && <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted-foreground">Source checks ({item.attempts.length})</summary><ul className="mt-1 space-y-2">{item.attempts.map((attempt, i) => <li key={i} className="break-words">{attempt.url.startsWith('https://') || attempt.url.startsWith('http://') ? <a className="underline" href={attempt.url} target="_blank" rel="noreferrer">{attempt.url}</a> : attempt.url}<p className="text-muted-foreground">{attempt.reason}</p></li>)}</ul></details>}
                      {!item.attempts?.length && item.tried && item.tried.length > 0 && (
                        <details className="mt-1 text-xs">
                          <summary className="cursor-pointer text-muted-foreground">
                            tried {item.tried.length} URL{item.tried.length === 1 ? '' : 's'}
                          </summary>
                          <ul className="mt-1 list-inside list-disc break-all text-muted-foreground">
                            {item.tried.map((u) => (
                              <li key={u}>{u}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
