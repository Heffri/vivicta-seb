import type { ChunkPage, Answer, Company, Extraction, IndexStatus, KbEntry, LibraryEntry, Report, ReviewComponent, Schema } from './types'

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

export const getLibrary = (collection: 'wallenberg' | 'all' = 'wallenberg') => request<LibraryEntry[]>(`/api/library?collection_name=${collection}`)

export const registerLibraryReport = (file: string) =>
  request<Report>('/api/reports/from-library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file }),
  })

export const getCompanies = (q: string, collection: 'wallenberg' | 'all' = 'wallenberg') => request<Company[]>(`/api/companies?q=${encodeURIComponent(q)}&collection_name=${collection}`)

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
// v112: the KB page's collection switch. 'wallenberg' is the curated roster (the page's default,
// issue #4); 'all' lists every saved extraction in data/kb. The backend default is 'all' — pass one explicitly.
export const getKb = (collection: 'wallenberg' | 'all' = 'wallenberg') =>
  request<KbEntry[]>(`/api/kb?collection_name=${collection}`)
// Whole-universe exports stay browser downloads, matching the existing per-report CSV/PPTX links.
// `q` follows KbView's visible company/stem filter; no client-side data reconstruction is needed.
const kbExportParams = (section: string, collection: 'wallenberg' | 'all', q = '') =>
  new URLSearchParams({ section, collection, ...(q.trim() ? { q: q.trim() } : {}) })
export const kbExportCsvUrl = (section: string, collection: 'wallenberg' | 'all', q = '') =>
  `/api/kb/export.csv?${kbExportParams(section, collection, q)}`
export const kbExportPptxUrl = (section: string, collection: 'wallenberg' | 'all', q = '') =>
  `/api/kb/export.pptx?${kbExportParams(section, collection, q)}`
// Stored extraction, no model call; the backend re-registers the PDF so pageUrl/csvUrl work.
export const openKbExtraction = (stem: string, section: string) =>
  request<Extraction>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}`)

export const getKbPage = (stem: string, page: number) =>
  request<{ page: number; text: string }>(`/api/kb/${encodeURIComponent(stem)}/pages/${page}`)

export const reviewField = (reportId: string, body: { section: string; key: string; expected: import('./types').Field; decision: import('./types').HumanReview['decision']; reviewer: string; note: string; value?: number | string | null; unit?: string | null; period?: string | null; source_page?: number; source_quote?: string; components?: ReviewComponent[] }) =>
  request<Extraction>(`/api/reports/${encodeURIComponent(reportId)}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const getReviewQueue = () => request<import('./types').QueueIssue[]>('/api/review-queue')
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
