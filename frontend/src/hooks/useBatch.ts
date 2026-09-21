import { useRef, useState } from 'react'
import { type ApiError, type CandidatePage, extractSection, formatPageRanges, getCandidates } from '@/api'
import type { Report, Result } from '@/types'

// v171 (consult item 6): the extraction queue's state used to live inside UploadView, so switching
// tabs mid-batch unmounted it -- progress vanished, and the still-running promise chain (fetch/extract
// calls don't care about React unmounting) called the old onDone at the end regardless, yanking the
// user back to Results even if they'd since navigated elsewhere. This hook lifts that state to
// whoever calls it once, at the App level, so it survives every tab switch; the queue loop itself
// keeps running against `itemsRef` (a mirror of `items` that's always synchronously current, since
// state updates from `setItems` don't apply until the next render — a `retry()` mid-loop needs the
// live value, not a stale one from whenever the closure was created).

export type BatchStage = 'queued' | 'registering' | 'candidates' | 'extracting' | 'done' | 'failed' | 'skipped'
// 409 means two different things depending which call failed: the extractor's own guard (a saved,
// human-reviewed result must not be overwritten) vs. /fetch's (no saved text or PDF without an
// explicit download). 422 = no text candidates (needs OCR or a different file). 502 = the model
// provider itself failed. Everything else (400 bad file, 404 unknown company, network errors) is
// 'other' — the raw message is still shown, just without a canned next step.
export type BatchErrorKind = 'review-protected' | 'download-needed' | 'needs-ocr' | 'provider-failed' | 'other'
export type BatchWait = { pages: string; total: number; heading: string }

// What UploadView knows how to build for one queued report; the hook doesn't need to know whether
// it came from a directory pick, a library entry, an upload or a web search.
export type BatchSpec = {
  label: string
  prep?: string       // e.g. "Opening X annual report 2025…"; default "Preparing <label>"
  fromUpload?: boolean // the final result label may be upgraded to the model's own company guess
  getReport: () => Promise<Report>
}

export type BatchItem = BatchSpec & {
  id: string
  section: string       // schema name, for the candidates/extract calls
  sectionTitle: string  // display title, carried onto the Result
  eta: string            // provider duration hint, e.g. " about 30 s with the connected model."
  stage: BatchStage
  startedAt: number | null
  finishedAt: number | null
  wait: BatchWait | null
  result: Result | null // set once done or failed; null while queued/running
  errorKind: BatchErrorKind | null
  tried: string[] | undefined // /fetch 404's attempted URLs, when the backend reports them
  retrying: boolean
}

function classify(stage: 'fetch' | 'extract', status: number | undefined): BatchErrorKind {
  if (status === 409) return stage === 'fetch' ? 'download-needed' : 'review-protected'
  if (status === 422) return 'needs-ocr'
  if (status === 502) return 'provider-failed'
  return 'other'
}

let seq = 0

type Handlers = {
  onSettle: (results: Result[]) => void // called with the full current results list after every item settles
}

export function useBatch({ onSettle }: Handlers) {
  const [items, setItems] = useState<BatchItem[]>([])
  const itemsRef = useRef<BatchItem[]>([])
  const [busy, setBusy] = useState(false)
  const [stopRequested, setStopRequested] = useState(false)
  const stopRef = useRef(false)

  const commit = (next: BatchItem[]) => {
    itemsRef.current = next
    setItems(next)
  }
  const patch = (id: string, fn: (it: BatchItem) => BatchItem) => commit(itemsRef.current.map((it) => (it.id === id ? fn(it) : it)))
  const currentResults = () => itemsRef.current.map((it) => it.result).filter((r): r is Result => r !== null)
  const notifySettle = () => onSettle(currentResults())

  // Shared by the queue loop and retry() — a manual retry runs the exact same steps as the first
  // attempt, not a special case: registering (fetch/upload/register) → candidates (zero-model
  // locator, advisory) → extracting → done/failed.
  const runItem = async (id: string) => {
    const before = itemsRef.current.find((it) => it.id === id)
    if (!before) return
    patch(id, (it) => ({ ...it, stage: 'registering', startedAt: performance.now(), finishedAt: null, wait: null, errorKind: null, tried: undefined }))
    let report: Report
    try {
      report = await before.getReport()
    } catch (e) {
      const err = e as ApiError
      patch(id, (it) => ({
        ...it,
        stage: 'failed',
        finishedAt: performance.now(),
        errorKind: classify('fetch', err.status),
        tried: err.tried,
        result: { label: before.label, sectionTitle: before.sectionTitle, error: err.message },
      }))
      notifySettle()
      return
    }
    patch(id, (it) => ({ ...it, stage: 'candidates' }))
    let pages: CandidatePage[] | null = null
    try {
      pages = await getCandidates(report.report_id, before.section)
    } catch {
      pages = null
    }
    patch(id, (it) => ({
      ...it,
      stage: 'extracting',
      wait: pages && pages.length > 0 ? { pages: formatPageRanges(pages.map((c) => c.page)), total: report.pages, heading: pages[0].heading } : null,
    }))
    try {
      const extraction = await extractSection(report.report_id, before.section)
      const label = before.fromUpload ? (extraction.company ?? report.company ?? before.label) : before.label
      patch(id, (it) => ({ ...it, stage: 'done', finishedAt: performance.now(), wait: null, result: { label, sectionTitle: before.sectionTitle, extraction } }))
    } catch (e) {
      const err = e as ApiError
      patch(id, (it) => ({
        ...it,
        stage: 'failed',
        finishedAt: performance.now(),
        wait: null,
        errorKind: classify('extract', err.status),
        result: { label: before.label, sectionTitle: before.sectionTitle, error: err.message },
      }))
    }
    notifySettle()
  }

  const start = (specs: BatchSpec[], section: string, sectionTitle: string, eta = '') => {
    stopRef.current = false
    setStopRequested(false)
    const initial: BatchItem[] = specs.map((spec) => ({
      ...spec,
      id: `b${++seq}`,
      section,
      sectionTitle,
      eta,
      stage: 'queued',
      startedAt: null,
      finishedAt: null,
      wait: null,
      result: null,
      errorKind: null,
      tried: undefined,
      retrying: false,
    }))
    commit(initial)
    setBusy(true)
    void (async () => {
      for (const item of initial) {
        if (stopRef.current) {
          patch(item.id, (it) => (it.stage === 'queued' ? { ...it, stage: 'skipped' } : it))
          continue
        }
        await runItem(item.id)
      }
      setBusy(false)
    })()
  }

  const stopAfterCurrent = () => {
    stopRef.current = true
    setStopRequested(true)
  }

  const retry = async (id: string) => {
    const item = itemsRef.current.find((it) => it.id === id)
    if (!item || item.retrying || item.stage === 'done') return
    patch(id, (it) => ({ ...it, retrying: true }))
    await runItem(id)
    patch(id, (it) => ({ ...it, retrying: false }))
  }

  return { items, busy, stopRequested, start, stopAfterCurrent, retry }
}

export type Batch = ReturnType<typeof useBatch>
