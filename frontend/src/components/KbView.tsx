import { Database, Library, Loader2, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type ApiError, getChunks, rebuildIndex, openKnowledge, pdfUrl, getConfig, getKb, getLibrary, getSchemas, openKbExtraction, type Config } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import { CollectionPicker } from '@/components/CollectionPicker'
import { useCollection, type Collection } from '@/hooks/useCollection'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ChunkPage, KbEntry, Result, Schema } from '@/types'

type Props = { onOpen: (results: Result[]) => void; onOpenReport: (report: KbEntry) => void }

const NO_PDF_DESC_ID = 'kb-no-pdf-desc'
const NO_PDF_TITLE = 'Saved figures and page text are available; the original PDF is not cached'

// Everything the parser has learnt so far: one row per report in data/kb, opened from disk without a model call.
export function KbView({ onOpen, onOpenReport }: Props) {
  const [entries, setEntries] = useState<KbEntry[] | null>(null)
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [config, setConfig] = useState<Config | null>(null) // retrieval mode decides what the Embeddings column says
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // stems
  const [busy, setBusy] = useState<string | null>(null)
  const [notCached, setNotCached] = useState(false) // last error was the 409 "PDF no longer cached"
  const [query, setQuery] = useState('')
  const [collection, setCollection] = useCollection()
  // Basenames present in data/reports/ right now (GET /api/library, disk-backed). null = not known yet — either
  // still loading or the call failed (old backend / network); either way fall back to "everything openable".
  const [pdfFiles, setPdfFiles] = useState<Set<string> | null>(null)
  const [pdfOnly, setPdfOnly] = useState(false)
  const [view, setView] = useState<'reports' | 'index'>('reports')
  const [inspected, setInspected] = useState<KbEntry | null>(null)
  const build = async (stem: string) => {
    setBusy(stem)
    setError(null)
    try { await rebuildIndex(stem); setEntries(await getKb(collection)) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(null) }
  }
  useEffect(() => {
    if (!entries?.some((e) => e.status === 'building')) return
    let stale = false
    const timer = setTimeout(() => {
      getKb(collection).then((rows) => { if (!stale) setEntries(rows) }).catch((e: Error) => { if (!stale) setError(e.message) })
    }, 2000)
    return () => { stale = true; clearTimeout(timer) }
  }, [entries, collection])

  useEffect(() => {
    let alive = true
    getKb(collection).then(rows => { if (alive) setEntries(rows) }).catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [collection])

  useEffect(() => {
    getSchemas().then(setSchemas).catch(() => {})
    getConfig().then(setConfig).catch(() => {}) // v034-era backend without `retrieval` -> null, column unchanged
    getLibrary('all')
      .then((lib) => setPdfFiles(new Set(lib.map((l) => l.file))))
      .catch(() => {}) // fixture-era backend or a blip: stay null, every row stays openable
  }, [])

  const switchCollection = (c: Collection) => {
    if (c === collection) return
    setCollection(c) // the [collection] effect refetches; the previous list stays up until it lands
    setSelected(new Set()) // selected stems may be invisible in the other collection — never keep them
    setError(null)
  }

  // Same join the backend's own GET /api/kb/{stem}/{section} 409 check uses (app.py: file == f"{stem}.pdf").
  const hasPdf = (stem: string) => entries?.find((entry) => entry.stem === stem)?.pdf_available ?? (!pdfFiles || pdfFiles.has(`${stem}.pdf`))

  const title = (section: string) => schemas.find((s) => s.name === section)?.title ?? section

  const open = async (stems: string[], section: string) => {
    setBusy(stems.join())
    setError(null)
    const results: Result[] = []
    let missingPdf = false
    for (const stem of stems) {
      const label = entries?.find((e) => e.stem === stem)?.company ?? stem
      try {
        results.push({ label, sectionTitle: title(section), extraction: await openKbExtraction(stem, section) })
      } catch (e) {
        results.push({ label, sectionTitle: title(section), error: (e as Error).message })
        if ((e as ApiError).status === 409) missingPdf = true // backend re-registration needs the PDF in data/reports
      }
    }
    setBusy(null)
    setNotCached(missingPdf)
    if (results.every((r) => r.error)) setError(results.map((r) => `${r.label}: ${r.error}`).join('\n'))
    else onOpen(results)
  }

  const toggle = (stem: string) =>
    setSelected((s) => {
      const n = new Set(s)
      if (!n.delete(stem)) n.add(stem)
      return n
    })

  const withSection = [...selected].filter((s) => entries?.find((e) => e.stem === s)?.sections.length)
  // Batch section = the first schema (in schema order) every selected report actually has; schemas[0] is
  // debt_maturity since that schema landed, which no KB entry has yet, so it 404'd both legs of a Compare.
  const has = (stem: string, name: string) => !!entries?.find((e) => e.stem === stem)?.sections.includes(name)
  const section =
    schemas.map((s) => s.name).find((n) => withSection.length > 0 && withSection.every((s) => has(s, n))) ??
    entries?.find((e) => e.stem === withSection[0])?.sections[0] ??
    'income_statement'

  // Display-only: narrows which rows render, never touches `selected`.
  const q = query.trim().toLowerCase()
  const filtered = (entries ?? []).filter(
    (e) =>
      (!q || (e.company ?? '').toLowerCase().includes(q) || e.stem.toLowerCase().includes(q)) &&
      (!pdfOnly || hasPdf(e.stem)),
  )

  const reportTable = filtered.length > 0 ? (<Card className="overflow-hidden py-0 [&_[data-slot=table-container]]:max-h-[70vh] [&_[data-slot=table-container]]:overflow-y-auto">
          <span id={NO_PDF_DESC_ID} className="sr-only">
            {NO_PDF_TITLE}
          </span>
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-muted">
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Company</TableHead>
                <TableHead className="text-right">FY</TableHead>
                <TableHead className="text-right max-[900px]:hidden">Pages</TableHead>
                <TableHead>Extractions</TableHead>
                {view === 'index' && <TableHead>Search index</TableHead>}
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((e) => {
                const isSelected = selected.has(e.stem)
                const available = hasPdf(e.stem)
                return (
                  <TableRow
                    key={e.stem}
                    className={`border-l-2 ${isSelected ? 'border-l-ring bg-primary/10 hover:bg-primary/15' : 'border-l-transparent hover:bg-primary/5'}`}
                  >
                    <TableCell>
                      <input
                        type="checkbox"
                        aria-label={`Select ${e.company ?? e.stem}`}
                        checked={isSelected}
                        disabled={!e.sections.length}
                        title={available ? undefined : NO_PDF_TITLE}
                        onChange={() => toggle(e.stem)}
                        className="size-3.5 accent-ring"
                      />
                    </TableCell>
                    <TableCell className="font-medium">
                      {e.company ?? e.stem}
                      {view === 'index' && <span className="mt-1 block font-mono text-xs text-muted-foreground">{e.stem}</span>}
                      {!available && (
                        <Badge variant="outline" className="ml-2 text-muted-foreground">
                          no PDF
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{e.fiscal_year ?? '—'}</TableCell>
                    <TableCell className="text-right tabular-nums max-[900px]:hidden">{e.pages}</TableCell>
                    <TableCell>
                      <span className="flex flex-wrap gap-1">
                        {e.sections.length ? (
                          e.sections.map((s) => (
                            <Badge key={s} variant="secondary">
                              {title(s)}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">none yet</span>
                        )}
                      </span>
                    </TableCell>
                    {view === 'index' && <TableCell>
                      {config?.retrieval === 'bm25' ? (
                        // Keyword-only retrieval uses no embeddings file: "not yet" on every row read like
                        // breakage (v034), so name the index that actually serves /ask here instead.
                        <Badge variant="outline" className="text-muted-foreground">
                          BM25
                        </Badge>
                      ) : (
                        <Badge variant={e.indexed ? 'success' : 'outline'} className={e.indexed ? undefined : 'text-muted-foreground'}>
                          {e.status ?? (e.indexed ? 'ready' : 'missing')}
                        </Badge>
                      )}
                      <p className="text-xs text-muted-foreground" title={e.reason}>{e.embed_model ?? config?.embed_model} · {e.dimensions ?? "?"} dimensions<br />{e.page_chunks} passages · {e.fact_chunks} facts</p>
                    </TableCell>}
                    <TableCell className="space-x-2 text-right">
                      {view === 'index' && <><Button size="xs" variant="outline" onClick={() => setInspected(e)}>Inspect</Button>
                      <Button size="xs" variant="outline" disabled={!!busy || e.status === 'building'} onClick={() => build(e.stem)}>{busy === e.stem || e.status === 'building' ? 'Building…' : 'Rebuild'}</Button></>}
                      <Button size="xs" variant="outline" disabled={!!busy} onClick={() => onOpenReport(e)}>
                        Open
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>) : null

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Knowledge base" title="Saved reports" description="Browse saved figures and source pages, or manage the report search index." actions={
        <Button disabled={withSection.length < 2 || !!busy} onClick={() => open(withSection, section)}>
          {busy && withSection.join() === busy ? <Loader2 className="animate-spin" /> : <Database />}
          Compare {withSection.length > 1 ? withSection.length : ''} selected
        </Button>
      } />


      {error && (
        <ErrorBlock
          details={
            notCached ? (
              <p className="mt-2 text-xs">
                Next step: fetch the PDF from the Extract tab’s Directory search, then open it here again.
              </p>
            ) : undefined
          }
        >
          {error}
        </ErrorBlock>
      )}

      {!entries && !error && <LoadingLine>Loading…</LoadingLine>}

      {entries && entries.length === 0 && <p className="text-sm text-muted-foreground">Empty — extract a report first.</p>}

      <Workspace label="Knowledge base workspace" value={view} onChange={setView} toolbar={<div className="flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by company or stem…"
              aria-label="Filter reports"
              className="h-8 w-full rounded-lg border border-input bg-background py-2 pr-2.5 pl-8 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring"
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {filtered.length} / {entries?.length ?? 0}
          </span>
          <CollectionPicker value={collection} onChange={switchCollection} />
          <label
            className={`flex items-center gap-1.5 text-xs ${pdfFiles ? 'text-muted-foreground' : 'text-muted-foreground/50'}`}
            title={pdfFiles ? undefined : 'PDF cache list unavailable — cannot filter by it'}
          >
            <input
              type="checkbox"
              checked={pdfOnly}
              disabled={!pdfFiles}
              onChange={(e) => setPdfOnly(e.target.checked)}
              className="size-3.5 accent-ring"
            />
            With PDF only
          </label>
        </div>} pages={[
        { value: 'reports', label: 'Reports', icon: Library, content: view === 'reports' ? reportTable : null },
        { value: 'index', label: 'Search index', icon: Database, content: view === 'index' ? <>
          <p className="text-sm text-muted-foreground">Inspect the text used to answer questions and rebuild an index when needed.</p>
          {inspected && <ChunkBrowser key={inspected.stem} entry={entries?.find(e => e.stem === inspected.stem) ?? inspected} onClose={() => setInspected(null)} />}
          {reportTable}
        </> : null },
      ]} />

      {entries && entries.length > 0 && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">No matches for "{query}".</p>
      )}


    </div>
  )
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
        <div className="flex gap-3 text-xs"><Badge variant="outline">{chunk.kind}</Badge>{reportId && entry.pdf_available ? <a className="underline" href={pdfUrl(reportId, chunk.page)} target="_blank" rel="noreferrer">Page {chunk.page}</a> : <span>Page {chunk.page}</span>}</div>
        <p className="whitespace-pre-wrap text-sm">{chunk.text}</p>
      </article>)}
      <div className="flex items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => browse(Math.max(0, offset - 25))}>Previous</Button><span className="text-sm">Page {Math.floor(offset / 25) + 1}</span><Button variant="outline" disabled={offset + 25 >= data.total} onClick={() => browse(offset + 25)}>Next</Button></div>
    </>}
  </section>
}
