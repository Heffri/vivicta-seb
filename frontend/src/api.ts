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

export const getLibrary = () => request<LibraryEntry[]>('/api/library')

export const registerLibraryReport = (file: string) =>
  request<Report>('/api/reports/from-library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file }),
  })

export const getCompanies = (q: string) => request<Company[]>(`/api/companies?q=${encodeURIComponent(q)}`)

export const fetchReport = (company: string, year: number) =>
  request<Report>('/api/reports/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, year }),
  })

export const extractSection = (reportId: string, section: string) =>
  request<Extraction>(`/api/reports/${reportId}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section }),
  })

export const indexReport = (reportId: string) =>
  request<IndexStatus>(`/api/reports/${reportId}/index`, { method: 'POST' })

export const ask = (question: string, reportIds: string[]) =>
  request<Answer>('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, report_ids: reportIds }),
  })

export const pageUrl = (reportId: string, page: number) => `/api/reports/${reportId}/pages/${page}.png`
export const csvUrl = (reportId: string) => `/api/reports/${reportId}/extraction.csv`
export const pptxUrl = (reportId: string) => `/api/reports/${reportId}/extraction.pptx`
export const pdfUrl = (reportId: string, page?: number) =>
  `/api/reports/${reportId}/pdf${page ? `#page=${page}` : ''}`

export type Config = { model: string; embed_model: string; base_url: string | null; llm: boolean }
export const getConfig = () => request<Config>('/api/config')
export const getKb = () => request<KbEntry[]>('/api/kb')
// Stored extraction, no model call; the backend re-registers the PDF so pageUrl/csvUrl work.
export const openKbExtraction = (stem: string, section: string) =>
  request<Extraction>(`/api/kb/${encodeURIComponent(stem)}/${encodeURIComponent(section)}`)
