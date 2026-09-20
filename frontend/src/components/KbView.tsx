import { useEffect, useState } from 'react'
import { getChunks, getKb, getSchemas, openKbExtraction, openKnowledge, pdfUrl, rebuildIndex } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ChunkPage, KbEntry, Result, Schema } from '@/types'

export function KbView({ onOpen }: { onOpen: (results: Result[]) => void }) {
  const [entries, setEntries] = useState<KbEntry[]>([])
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [section, setSection] = useState('debt_maturity')
  const [query, setQuery] = useState('')
  const [year, setYear] = useState('')
  const [status, setStatus] = useState('')
  const [inspected, setInspected] = useState<KbEntry | null>(null)

  const refresh = () => getKb().then(setEntries)
  useEffect(() => {
    Promise.all([getKb(), getSchemas()]).then(([rows, definitions]) => {
      setEntries(rows)
      setSchemas(definitions)
    }).catch((e: Error) => setError(e.message)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    if (!entries.some((e) => e.status === 'building')) return
    let stale = false
    const timer = setTimeout(() => {
      getKb().then((rows) => { if (!stale) setEntries(rows) }).catch((e: Error) => { if (!stale) setError(e.message) })
    }, 2000)
    return () => { stale = true; clearTimeout(timer) }
  }, [entries])

  const open = async (stems: string[]) => {
    setBusy('open')
    setError(null)
    const results: Result[] = await Promise.all(stems.map(async (stem) => {
      const base = { label: entries.find((e) => e.stem === stem)?.company ?? stem,
        sectionTitle: schemas.find((s) => s.name === section)?.title ?? section }
      try { return { ...base, extraction: await openKbExtraction(stem, section) } }
      catch (e) { return { ...base, error: (e as Error).message } }
    }))
    setBusy(null)
    if (results.every((r) => r.error)) setError(results.map((r) => `${r.label}: ${r.error}`).join('\n'))
    else onOpen(results)
  }
  const build = async (stem: string) => {
    setBusy(stem)
    setError(null)
    try { await rebuildIndex(stem); await refresh() }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(null) }
  }
  const visible = entries.filter((e) => `${e.company} ${e.stem}`.toLowerCase().includes(query.toLowerCase())
    && (!year || String(e.fiscal_year) === year) && (!status || e.status === status))
  const comparable = selected.size >= 2 && [...selected].every((s) => entries.find((e) => e.stem === s)?.sections.includes(section))
  const inputClass = 'rounded-md border bg-background px-3 py-2 text-sm'
  return <div className="space-y-5">
    <header className="space-y-2 border-b pb-5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">Knowledge base</p>
      <h1 className="text-2xl font-semibold">{entries.length} reports</h1>
      <p className="text-sm text-muted-foreground">Explore source passages and extracted facts. Ready indexes match the current reports and embedding model.</p>
    </header>
    <div className="flex flex-wrap gap-2">
      <input aria-label="Search reports" placeholder="Search company or report" className={inputClass} value={query} onChange={(e) => setQuery(e.target.value)} />
      <select aria-label="Fiscal year" className={inputClass} value={year} onChange={(e) => setYear(e.target.value)}>
        <option value="">All years</option>{[...new Set(entries.map((e) => e.fiscal_year).filter(Boolean))].sort().reverse().map((y) => <option key={y}>{y}</option>)}
      </select>
      <select aria-label="Index status" className={inputClass} value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>{['ready', 'missing', 'outdated', 'invalid', 'building'].map((s) => <option key={s}>{s}</option>)}
      </select>
      <select aria-label="Extraction section" className={inputClass} value={section} onChange={(e) => setSection(e.target.value)}>
        {schemas.map((s) => <option key={s.name} value={s.name}>{s.title}</option>)}
      </select>
      <Button disabled={!comparable || !!busy} onClick={() => open([...selected])}>Compare {selected.size || ''} selected</Button>
    </div>
    {error && <p role="alert" className="whitespace-pre-line text-sm text-destructive">{error}</p>}
    {loading && <p role="status">Loading reports…</p>}
    {!loading && !visible.length && <p className="text-sm text-muted-foreground">No matching reports.</p>}
    {!!visible.length && <Card className="overflow-x-auto py-0"><Table>
      <TableHeader><TableRow><TableHead>Select</TableHead><TableHead>Report</TableHead><TableHead>Index</TableHead><TableHead>Contents</TableHead><TableHead>Actions</TableHead></TableRow></TableHeader>
      <TableBody>{visible.map((e) => <TableRow key={e.stem}>
        <TableCell><input type="checkbox" aria-label={`Select ${e.company ?? e.stem}`} checked={selected.has(e.stem)} disabled={!e.sections.includes(section)} onChange={() => setSelected((old) => {
          const next = new Set(old); if (!next.delete(e.stem)) next.add(e.stem); return next
        })} /></TableCell>
        <TableCell><p className="font-medium">{e.company ?? e.stem}</p><p className="text-xs text-muted-foreground">FY {e.fiscal_year ?? '?'} · {e.pages} pages</p></TableCell>
        <TableCell><Badge title={e.reason} variant={e.status === 'ready' ? 'default' : 'outline'}>{e.status}</Badge>
          <p className="mt-1 text-xs text-muted-foreground">{e.embed_model ?? 'Model unknown'}{e.dimensions ? ` · ${e.dimensions} dimensions` : ''}</p>
          <p className="text-xs text-muted-foreground">{e.built_at ? new Date(e.built_at).toLocaleString() : 'Not built with metadata'}</p>
        </TableCell>
        <TableCell><p>{e.built_at ? `${e.chunks} chunks` : 'Not catalogued'}</p>{e.built_at && <p className="text-xs text-muted-foreground">{e.page_chunks} passages · {e.fact_chunks} facts</p>}<p className="text-xs text-muted-foreground">{e.sections.join(', ') || 'No extractions'}</p></TableCell>
        <TableCell><div className="flex flex-wrap gap-2">
          <Button size="xs" variant="outline" onClick={() => setInspected(e)}>Inspect</Button>
          <Button size="xs" variant="outline" disabled={!!busy || e.status === 'building'} onClick={() => build(e.stem)}>{busy === e.stem || e.status === 'building' ? 'Building…' : e.status === 'missing' ? 'Build index' : 'Rebuild'}</Button>
          <Button size="xs" variant="outline" disabled={!!busy || !e.sections.includes(section)} onClick={() => open([e.stem])}>Open extraction</Button>
        </div></TableCell>
      </TableRow>)}</TableBody>
    </Table></Card>}
    {inspected && <ChunkBrowser key={`${inspected.stem}-${entries.find((e) => e.stem === inspected.stem)?.built_at}`} entry={entries.find((e) => e.stem === inspected.stem) ?? inspected} onClose={() => setInspected(null)} />}
  </div>
}

function ChunkBrowser({ entry, onClose }: { entry: KbEntry; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<ChunkPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reportId, setReportId] = useState<string | null>(null)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const browse = (nextOffset: number, nextQuery = query) => {
    setOffset(nextOffset)
    setQuery(nextQuery)
    setData(null)
    setError(null)
  }
  useEffect(() => {
    let stale = false
    openKnowledge(entry.stem).then((r) => { if (!stale) setReportId(r.report_id) }).catch((e: Error) => { if (!stale) setSourceError(e.message) })
    return () => { stale = true }
  }, [entry.stem])
  useEffect(() => {
    let stale = false
    const timer = setTimeout(() => {
      getChunks(entry.stem, query, offset).then((r) => { if (!stale) setData(r) }).catch((e: Error) => { if (!stale) setError(e.message) })
    }, 200)
    return () => { stale = true; clearTimeout(timer) }
  }, [entry.stem, query, offset])
  return <section className="space-y-4 rounded-xl border p-5" aria-label="Indexed chunks">
    <div className="flex justify-between gap-3"><h2 className="font-semibold">{entry.company ?? entry.stem}: indexed content</h2><Button variant="outline" size="sm" onClick={onClose}>Close</Button></div>
    {entry.status !== 'ready' && <p role="status" className="text-sm text-amber-700">{entry.reason}.{entry.status !== 'building' && ' Rebuild the index to inspect current content.'}</p>}
    <input aria-label="Search chunk text" placeholder="Search indexed text" maxLength={200} className="w-full rounded-md border p-2 text-sm" value={query} onChange={(e) => browse(0, e.target.value)} />
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {sourceError && <p role="alert" className="text-sm text-destructive">{sourceError}</p>}
    {!data ? !error && <p>Loading chunks…</p> : <>
      <p className="text-sm text-muted-foreground">{data.total} matching chunks</p>
      {data.items.map((chunk, i) => <article key={`${offset}-${i}`} className="space-y-2 rounded-md bg-muted/40 p-3">
        <div className="flex gap-3 text-xs"><Badge variant="outline">{chunk.kind}</Badge>{reportId ? <a className="underline" href={pdfUrl(reportId, chunk.page)} target="_blank" rel="noreferrer">Page {chunk.page}</a> : <span>Page {chunk.page}</span>}</div>
        <p className="whitespace-pre-wrap text-sm">{chunk.text}</p>
      </article>)}
      <div className="flex items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => browse(Math.max(0, offset - 25))}>Previous</Button><span className="text-sm">Page {Math.floor(offset / 25) + 1}</span><Button variant="outline" disabled={offset + 25 >= data.total} onClick={() => browse(offset + 25)}>Next</Button></div>
    </>}
  </section>
}
