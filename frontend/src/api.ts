import type { Answer, Company, Extraction, IndexStatus, KbEntry, LibraryEntry, Report, Schema } from './types'

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

export const getLibrary = () => request<LibraryEntry[]>('/api/library?collection_name=wallenberg')

export const registerLibraryReport = (file: string) =>
  request<Report>('/api/reports/from-library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file }),
  })

export const getCompanies = (q: string) => request<Company[]>(`/api/companies?q=${encodeURIComponent(q)}&collection_name=wallenberg`)

// v074: country/hint are optional context for the backend's model search (its fourth fetch source,
// used when the directory has no hit); they are ignored by the feed levels.
export const fetchReport = (company: string, year: number, opts?: { country?: string; hint?: string; download_pdf?: boolean }) =>
  request<Report>('/api/reports/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, year, ...opts }),
  })

export const extractSection = (reportId: string, section: string) =>
  request<Extraction>(`/api/reports/${reportId}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section, reuse_saved: true }),
  })

export const indexReport = (reportId: string) =>
  request<IndexStatus>(`/api/reports/${reportId}/index`, { method: 'POST' })

export const ask = (question: string, reportIds?: string[], reportStems?: string[]) =>
  request<Answer>('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...(reportIds === undefined ? {} : { report_ids: reportIds }), ...(reportStems === undefined ? {} : { report_stems: reportStems }) }),
  })

export const pageUrl = (reportId: string, page: number) => `/api/reports/${reportId}/pages/${page}.png`
export const csvUrl = (reportId: string, section?: string, previous?: string) => `/api/reports/${reportId}/extraction.csv?${new URLSearchParams({ ...(section ? { section } : {}), ...(previous ? { previous_stem: previous } : {}) })}`
// v091: prior=1 asks the pptx for the prior-year series alongside the current one (ignored by the
// backend when the extraction carries no prior_year).
export const pptxUrl = (reportId: string, section?: string, previous?: string, prior?: boolean) => `/api/reports/${reportId}/extraction.pptx?${new URLSearchParams({ ...(section ? { section } : {}), ...(previous ? { previous_stem: previous } : {}), ...(prior ? { prior_year: '1' } : {}) })}`
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
}
export const getConfig = () => request<Config>('/api/config')
export const getKb = () => request<KbEntry[]>('/api/kb?collection_name=wallenberg')
// Stored extraction, no model call; the backend re-registers the PDF so pageUrl/csvUrl work.
export const openKbExtraction = (stem: string, section: string) =>
  request<Extraction>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}`)

export const getKbPage = (stem: string, page: number) =>
  request<{ page: number; text: string }>(`/api/kb/${encodeURIComponent(stem)}/pages/${page}`)

export const reviewField = (reportId: string, body: { section: string; key: string; expected: import('./types').Field; decision: import('./types').HumanReview['decision']; reviewer: string; note: string; value?: number | string | null; unit?: string | null; period?: string | null }) =>
  request<Extraction>(`/api/reports/${encodeURIComponent(reportId)}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const getReviewQueue = () => request<import('./types').QueueIssue[]>('/api/review-queue')
export const saveBasis = (reportId: string, body: { section: string; expected: Partial<import('./types').Basis>; values: Record<string, string>; reviewer: string; note: string }) =>
  request<Extraction>(`/api/reports/${encodeURIComponent(reportId)}/basis`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const getComparison = (stem: string, section: string, previous?: string) =>
  request<import('./types').Comparison>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}/comparison${previous ? `?previous_stem=${encodeURIComponent(previous)}` : ''}`)
