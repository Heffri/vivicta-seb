import type { Extraction, LibraryEntry, Report, Schema } from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    // Errors are JSON { detail } per docs/API.md; fall back to status text for proxy/network errors.
    const detail = await res
      .json()
      .then((b: { detail?: string }) => b.detail)
      .catch(() => undefined)
    throw new Error(detail ?? `${res.status} ${res.statusText}`)
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

export const extractSection = (reportId: string, section: string) =>
  request<Extraction>(`/api/reports/${reportId}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section }),
  })

export const pageUrl = (reportId: string, page: number) => `/api/reports/${reportId}/pages/${page}.png`
export const csvUrl = (reportId: string) => `/api/reports/${reportId}/extraction.csv`
export const pdfUrl = (reportId: string, page?: number) =>
  `/api/reports/${reportId}/pdf${page ? `#page=${page}` : ''}`
