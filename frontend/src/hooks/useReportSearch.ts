import { useRef, useState } from 'react'
import { discoverCompanies, getJob } from '@/api'
import type { Discovery, Job } from '@/types'

// Mirrors useBatch.ts. Inside UploadView, query/year/discovery would be silently dropped by a
// mid-search tab switch -- setDiscovery on an unmounted component is a no-op, and the fetch() call
// itself is never aborted (nothing here uses AbortController), so from the user's side "I switched
// to Settings and came back" looks exactly like "the search died".
// Lifted here, called once at the App level, so a search (or the fetch that follows confirming a
// candidate) keeps running -- progress trail included -- and is still there when the user comes back.

export type SearchStage = Job['stage']
export type SearchTrace = {
  jobId: string
  kind: 'discover' | 'fetch'
  label: string        // panel heading, e.g. "Resolving which company you mean" / "Fetching the annual report"
  stage: SearchStage
  startedAt: number     // Date.now()-comparable, for the stopwatch
  finishedAt: number | null // stamped once, the first time `done` is observed true — freezes the stopwatch
  events: Job['events']
  done: boolean
  error: string | null
}

const POLL_MS = 1500

function newJobId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `job-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function useReportSearch() {
  const [query, setQueryState] = useState('')
  const [year, setYearState] = useState(String(new Date().getFullYear() - 1))
  const [discovery, setDiscovery] = useState<Discovery | null>(null)
  const [discovering, setDiscovering] = useState(false)
  const [trace, setTrace] = useState<SearchTrace | null>(null)
  const pollRef = useRef<number | null>(null)
  const traceJobRef = useRef<string | null>(null) // guards a slow, stale poll tick from clobbering a newer trace

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const applyJob = (jobId: string, job: Job) => {
    if (traceJobRef.current !== jobId) return // a later trackJob() already replaced this trace
    setTrace((t) =>
      t && t.jobId === jobId
        ? {
            ...t,
            stage: job.stage ?? t.stage,
            events: Array.isArray(job.events) ? job.events : t.events, // a malformed reply keeps the last-known trail instead of crashing the panel's .slice()
            done: !!job.done,
            error: job.error ?? null,
            finishedAt: job.done ? (t.finishedAt ?? Date.now()) : null,
          }
        : t,
    )
  }

  const poll = (jobId: string) => {
    stopPolling()
    pollRef.current = window.setInterval(() => {
      getJob(jobId)
        .then((job) => {
          applyJob(jobId, job)
          if (job.done) stopPolling()
        })
        .catch(() => stopPolling()) // 404 = expired, or nothing was ever stepped (fixture/no-provider run) -- stop quietly, the trace already shown stands
    }, POLL_MS)
  }

  // Mints a job_id, resets the panel to it, runs `run(jobId)`, and leaves the final trace in place
  // on completion -- including on failure, since "keep the trail, show why, offer Retry" is the point.
  const trackJob = <T,>(kind: SearchTrace['kind'], label: string, run: (jobId: string) => Promise<T>): Promise<T> => {
    const jobId = newJobId()
    traceJobRef.current = jobId
    setTrace({ jobId, kind, label, stage: 'directory', startedAt: Date.now(), finishedAt: null, events: [], done: false, error: null })
    poll(jobId)
    return run(jobId).finally(() =>
      getJob(jobId)
        .then((job) => applyJob(jobId, job))
        .catch(() => {})
        .finally(stopPolling),
    )
  }

  const discover = (hint?: string, forceWeb = false) => {
    setDiscovering(true)
    setDiscovery(null)
    trackJob('discover', 'Resolving which company you mean', (jobId) =>
      discoverCompanies(query.trim(), Number(year), { ...(hint ? { hint } : {}), ...(forceWeb ? { force_web: true } : {}), job_id: jobId }),
    )
      .then(setDiscovery)
      .catch((e: Error) => setTrace((t) => (t ? { ...t, done: true, error: e.message, finishedAt: t.finishedAt ?? Date.now() } : t)))
      .finally(() => setDiscovering(false))
  }

  const setQuery = (q: string) => {
    setQueryState(q)
    setDiscovery(null)
    setTrace(null)
  }
  const setYear = (y: string) => {
    setYearState(y)
    setDiscovery(null)
    setTrace(null)
  }

  return { query, year, discovery, discovering, trace, setQuery, setYear, discover, trackJob }
}

export type ReportSearch = ReturnType<typeof useReportSearch>
