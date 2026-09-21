import type { ChunkPage, Answer, Company, Extraction, FieldFill, IndexStatus, KbEntry, LibraryEntry, MaturityWall, Report, ReviewComponent, Schema } from './types'
import type { Collection } from './hooks/useCollection'

export type ApiError = Error & { status: number; tried?: string[] }

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    // Errors are JSON { detail } per docs/API.md (fetch 404s add tried[]); fall back to status text for proxy/network errors.
    const body: { detail?: string; tried?: string[] } = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body.detail ?? `${res.status} ${res.statusText}`), {
      status: res.status,
      tried: body.tried,
    }) satisfies ApiError
  }
  return res.json() as Promise<T>
}

export const getSchemas = () => request<Schema[]>('/api/schemas')

export function uploadReport(file: File) {
  const body = new FormData()
  body.append('file', file)
  return request<Report>('/api/reports', { method: 'POST', body })
}

export const getLibrary = (collection: Collection = 'wallenberg') => request<LibraryEntry[]>(`/api/library?collection_name=${collection}`)

export const registerLibraryReport = (file: string) =>
  request<Report>('/api/reports/from-library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file }),
  })

export const getCompanies = (q: string, collection: Collection = 'wallenberg') => request<Company[]>(`/api/companies?q=${encodeURIComponent(q)}&collection_name=${collection}`)

// country/hint provide optional context for AI-first report discovery.
export const fetchReport = (company: string, year: number, opts?: { country?: string; hint?: string; download_pdf?: boolean }) =>
  request<Report>('/api/reports/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, year, ...opts }),
  })

export const extractSection = (reportId: string, section: string, force = false) =>
  request<Extraction>(`/api/reports/${reportId}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section, reuse_saved: !force, force }),
  })

// v164: the deterministic page locator (the same one the extractor runs) served before the model
// call, so the waiting line can name the pages being read. Zero-model; advisory for the UI only —
// an older backend's 404 just means the wait stays on the generic wording.
export type CandidatePage = { page: number; heading: string }
export const getCandidates = (reportId: string, section: string) =>
  request<CandidatePage[]>(`/api/reports/${encodeURIComponent(reportId)}/candidates?section=${encodeURIComponent(section)}`)

// [30, 31, 32, 35] → "30–32, 35" (en dash), for the extraction wait line and the not-found banner.
export function formatPageRanges(pages: number[]): string {
  const sorted = [...new Set(pages)].sort((a, b) => a - b)
  const out: string[] = []
  let i = 0
  while (i < sorted.length) {
    let j = i
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++
    out.push(i === j ? `${sorted[i]}` : `${sorted[i]}–${sorted[j]}`)
    i = j + 1
  }
  return out.join(', ')
}

export const indexReport = (reportId: string) =>
  request<IndexStatus>(`/api/reports/${reportId}/index`, { method: 'POST' })

export const ask = (question: string, reportIds?: string[], reportStems?: string[], signal?: AbortSignal) =>
  request<Answer>('/api/ask', {
    signal,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...(reportIds === undefined ? {} : { report_ids: reportIds }), ...(reportStems === undefined ? {} : { report_stems: reportStems }) }),
  })

export const pageUrl = (reportId: string, page: number) => `/api/reports/${reportId}/pages/${page}.png`
// v179: where a citation's quote sits on the rendered page (page-point rects, same top-down space
// pageUrl renders) — zero-model, advisory for Image-mode framing only. `rects` holds every
// occurrence at whichever tier matched; an older backend's 404 just leaves the page unframed.
// `occurrences` divides `rects.length` back out by the searched text's own line count, so a citation
// that merely wraps across two printed lines still reports 1 (with 2 rects to draw) rather than
// crying "2 matches" — only a truly repeated line reports 2+.
export type PageLocate = { page: number; width: number; height: number; matched: 'quote' | 'line' | 'value' | 'none'; rects: [number, number, number, number][]; occurrences: number }
export const locateQuote = (reportId: string, page: number, quote: string) =>
  request<PageLocate>(`/api/reports/${reportId}/pages/${page}/locate?quote=${encodeURIComponent(quote)}`)
export const csvUrl = (reportId: string, section?: string, previous?: string) => `/api/reports/${reportId}/extraction.csv?${new URLSearchParams({ ...(section ? { section } : {}), ...(previous ? { previous_stem: previous } : {}) })}`
// v091: prior=1 asks the pptx for the prior-year series alongside the current one (ignored by the
// backend when the extraction carries no prior_year). v109: perYear=1 asks for the report's own
// calendar-year columns instead of the three buckets (ignored without buckets_by_year).
export const pptxUrl = (reportId: string, section?: string, previous?: string, prior?: boolean, perYear?: boolean) => `/api/reports/${reportId}/extraction.pptx?${new URLSearchParams({ ...(section ? { section } : {}), ...(previous ? { previous_stem: previous } : {}), ...(prior ? { prior_year: '1' } : {}), ...(perYear ? { per_year: '1' } : {}) })}`
export const pdfUrl = (reportId: string, page?: number) =>
  `/api/reports/${reportId}/pdf${page ? `#page=${page}` : ''}`

// provider added in v031 (backend/app.py); this type lagged behind until v033's Settings view needed it.
// retrieval (v034, consumed by KbView since v059) is how /ask retrieves: embeddings+keywords or keywords only.
// Optional: main.tsx's SetSettingsResult (desktop save path) predates it and is outside lane territory —
// an absent field just keeps KbView's column on the pre-v059 wording.
export type Config = {
  model: string
  embed_model: string
  base_url: string | null
  llm: boolean
  provider: string
  retrieval?: 'hybrid' | 'bm25' | 'fixture'
  maturity_basis?: 'carrying' | 'undiscounted' // v089: the backend's live DEBT_BASIS; absent on older backends
  merge_runs?: 'off' | 'union' | 'majority' // v140: the backend's live EXTRACT_MERGE_RUNS; absent on older backends
}
export const getConfig = () => request<Config>('/api/config')
// The KB page's collection switch. Wallenberg remains the UI default; midcap is the 132-company
// SEB universe from data/companies.json. The backend default is 'all' — pass one explicitly.
export const getKb = (collection: Collection = 'wallenberg') =>
  request<KbEntry[]>(`/api/kb?collection_name=${collection}`)
// Whole-universe exports stay browser downloads, matching the existing per-report CSV/PPTX links.
// `q` follows KbView's visible company/stem filter; no client-side data reconstruction is needed.
const kbExportParams = (section: string, collection: Collection, q = '') =>
  new URLSearchParams({ section, collection, ...(q.trim() ? { q: q.trim() } : {}) })
export const kbExportCsvUrl = (section: string, collection: Collection, q = '') =>
  `/api/kb/export.csv?${kbExportParams(section, collection, q)}`
export const kbExportPptxUrl = (section: string, collection: Collection, q = '') =>
  `/api/kb/export.pptx?${kbExportParams(section, collection, q)}`
// Stored extraction, no model call; the backend re-registers the PDF so pageUrl/csvUrl work.
export const openKbExtraction = (stem: string, section: string) =>
  request<Extraction>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}`)

export const getKbPage = (stem: string, page: number) =>
  request<{ page: number; text: string }>(`/api/kb/${encodeURIComponent(stem)}/pages/${page}`)

// v174: deterministic upcoming-maturities list over the saved collection (Compare view). Zero model calls.
export const getMaturityWall = (collection: Collection = 'wallenberg') =>
  request<MaturityWall>(`/api/kb/maturity-wall?collection=${collection}`)

export const reviewField = (reportId: string, body: { section: string; key: string; expected: import('./types').Field; decision: import('./types').HumanReview['decision']; reviewer: string; note: string; value?: number | string | null; unit?: string | null; period?: string | null; source_page?: number; source_quote?: string; components?: ReviewComponent[] }) =>
  request<Extraction>(`/api/reports/${encodeURIComponent(reportId)}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// A controlled single-field candidate: the response is never persisted or merged into the
// extraction. Its caller must copy it into the normal stale-checked human review form.
export const fillField = (reportId: string, section: string, field: string, pages: number[]) =>
  request<FieldFill>(`/api/reports/${encodeURIComponent(reportId)}/fill?section=${encodeURIComponent(section)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ field, pages }),
  })

export const getReviewQueue = (collection: Collection = 'wallenberg') => request<import('./types').QueueIssue[]>(`/api/review-queue?collection_name=${collection}`)
export const saveBasis = (reportId: string, body: { section: string; expected: Partial<import('./types').Basis>; values: Record<string, string>; reviewer: string; note: string }) =>
  request<Extraction>(`/api/reports/${encodeURIComponent(reportId)}/basis`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const getComparison = (stem: string, section: string, previous?: string) =>
  request<import('./types').Comparison>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}/comparison${previous ? `?previous_stem=${encodeURIComponent(previous)}` : ''}`)

export const getChunks = (stem: string, q = '', offset = 0) =>
  request<ChunkPage>(`/api/knowledge/${encodeURIComponent(stem)}/chunks?${new URLSearchParams({ q, offset: String(offset) })}`)
export const rebuildIndex = (stem: string) =>
  request<IndexStatus>(`/api/knowledge/${encodeURIComponent(stem)}/index`, { method: 'POST' })
export const openKnowledge = (stem: string) =>
  request<Report>(`/api/knowledge/${encodeURIComponent(stem)}/open`, { method: 'POST' })
