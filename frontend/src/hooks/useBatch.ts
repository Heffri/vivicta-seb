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
// explicit download). 422 during registration with an ocr_pages_needed body = a scanned PDF whose
// bounded OCR pass alone is over budget (v191) -- 'ocr-budget', offering a full-OCR retry; any other
// 422 = no text candidates (needs OCR some other way, or a different file). 502 = the model provider
// itself failed. Everything else (400 bad file, 404 unknown company, network errors) is 'other' — the
// raw message is still shown, just without a canned next step.
export type BatchErrorKind = 'review-protected' | 'download-needed' | 'needs-ocr' | 'ocr-budget' | 'provider-failed' | 'other'
export type BatchWait = { pages: string; total: number; heading: string }
export type RegisterOpts = { ocr?: 'full' }

// What UploadView knows how to build for one queued report; the hook doesn't need to know whether
// it came from a directory pick, a library entry, an upload or a web search. `opts` is forwarded
// as-is to whichever api.ts call the closure wraps; a closure that ignores it (most of them, most of
// the time) just repeats its first attempt.
export type BatchSpec = {
  label: string
  prep?: string       // e.g. "Opening X annual report 2025…"; default "Preparing <label>"
  fromUpload?: boolean // the final result label may be upgraded to the model's own company guess
  getReport: (opts?: RegisterOpts) => Promise<Report>
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
  ocrPages: number[] | null // v191: pages this item's own registration actually OCR'd, once known
  retrying: boolean
}

function classify(stage: 'fetch' | 'extract', err: ApiError): BatchErrorKind {
  if (err.status === 409) return stage === 'fetch' ? 'download-needed' : 'review-protected'
  if (stage === 'fetch' && err.status === 422 && err.ocrPagesNeeded != null) return 'ocr-budget'
  if (err.status === 422) return 'needs-ocr'
  if (err.status === 502) return 'provider-failed'
  return 'other'
}

let seq = 0
const BATCH_CONCURRENCY = 3

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
  // locator, advisory) → extracting → done/failed. `opts` only matters on a retry (e.g. { ocr: 'full' }
  // after an 'ocr-budget' failure); the first attempt always runs with none.
  const runItem = async (id: string, opts?: RegisterOpts) => {
    const before = itemsRef.current.find((it) => it.id === id)
    if (!before) return
    patch(id, (it) => ({ ...it, stage: 'registering', startedAt: performance.now(), finishedAt: null, wait: null, errorKind: null, tried: undefined }))
    let report: Report
    try {
      report = await before.getReport(opts)
    } catch (e) {
      const err = e as ApiError
      patch(id, (it) => ({
        ...it,
        stage: 'failed',
        finishedAt: performance.now(),
        errorKind: classify('fetch', err),
        tried: err.tried,
        result: { label: before.label, sectionTitle: before.sectionTitle, error: err.message },
      }))
      notifySettle()
      return
    }
    patch(id, (it) => ({ ...it, stage: 'candidates', ocrPages: report.ocr_pages ?? null }))
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
        errorKind: classify('extract', err),
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
      ocrPages: null,
      retrying: false,
    }))
    commit(initial)
    setBusy(true)
    void (async () => {
      // Match the backend's hosted-model semaphore. Each worker claims its next item only after
      // the previous one settles, so a five-report batch starts three extracts and holds the
      // remaining two until a slot is free. The shared cursor is synchronous between awaits.
      let cursor = 0
      const worker = async () => {
        while (!stopRef.current) {
          const item = initial[cursor++]
          if (!item) return
          await runItem(item.id)
        }
      }
      await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, initial.length) }, worker))
      // Stop never aborts an in-flight request (the backend would continue it anyway); it prevents
      // the workers from claiming another item and marks every still-queued row honestly.
      if (stopRef.current) commit(itemsRef.current.map((item) => (item.stage === 'queued' ? { ...item, stage: 'skipped' } : item)))
      setBusy(false)
    })()
  }

  const stopAfterCurrent = () => {
    stopRef.current = true
    setStopRequested(true)
  }

  const retry = async (id: string, opts?: RegisterOpts) => {
    const item = itemsRef.current.find((it) => it.id === id)
    if (!item || item.retrying || item.stage === 'done') return
    patch(id, (it) => ({ ...it, retrying: true }))
    await runItem(id, opts)
    patch(id, (it) => ({ ...it, retrying: false }))
  }

  return { items, busy, stopRequested, start, stopAfterCurrent, retry }
}

export type Batch = ReturnType<typeof useBatch>
