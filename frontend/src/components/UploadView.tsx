import { BookOpenCheck, FileSearch, Files, Info, Loader2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { type ApiError, fetchReport, getCompanies, getConfig, getLibrary, getSchemas, openKbExtraction, registerLibraryReport, uploadReport } from '@/api'
import { Button } from '@/components/ui/button'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock } from '@/components/ui/state'
import { BatchProgress } from '@/components/upload/BatchProgress'
import { CachedReports } from '@/components/upload/CachedReports'
import { CompanySearch } from '@/components/upload/CompanySearch'
import { CollectionPicker } from '@/components/CollectionPicker'
import { useCollection } from '@/hooks/useCollection'
import type { Batch, BatchSpec } from '@/hooks/useBatch'
import type { ReportSearch } from '@/hooks/useReportSearch'
import { Dropzone } from '@/components/upload/Dropzone'
import type { Tab } from '@/components/shell/tabs'
import type { Candidate, Company, LibraryEntry, Result, Schema } from '@/types'

type Props = {
  batch: Batch
  reportSearch: ReportSearch
  onSubmit: (specs: BatchSpec[], section: string, sectionTitle: string, eta: string) => void
  resultsCount: number
  onViewResults: () => void
  onDone: (results: Result[]) => void // openSample only — a single, instant, zero-model result
  onNavigate?: (tab: Tab) => void
}

// The saved real-debt sample the first screen opens directly (supervisor add-on to v164): a stored
// KB extraction, opened with zero model calls, that still awaits its basis confirmation — a demo
// can show real output before any model is configured.
const SAMPLE_STEM = 'karnell_2025'
const SAMPLE_SECTION = 'debt_maturity'

const isPdf = (f: File) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')

export function UploadView({ batch, reportSearch, onSubmit, resultsCount, onViewResults, onDone, onNavigate }: Props) {
  const [collection, setCollection] = useCollection()
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [schemasError, setSchemasError] = useState<string | null>(null)
  const [section, setSection] = useState<string | null>(null)
  const [library, setLibrary] = useState<LibraryEntry[]>([])
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // LibraryEntry.file
  // v194: query/year/discovery/discovering/trace lifted to the App level (useReportSearch) so a
  // search, and the fetch that follows confirming a candidate, survive switching away from Extract.
  const { query, year, discovery, discovering, trace, setQuery, setYear, discover, trackJob } = reportSearch
  const [companies, setCompanies] = useState<Company[]>([])
  const [dirError, setDirError] = useState<string | null>(null)
  const [provider, setProvider] = useState<string | null>(null) // backend /api/config provider; null = not loaded yet
  const [picked, setPicked] = useState<Company[]>([]) // directory picks, deduped by name
  const [files, setFiles] = useState<File[]>([]) // uploads, in drop/pick order, deduped by name+size
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null) // local validation only (bad file type, sample open failure) — batch failures render per-item in BatchProgress
  const [sourceView, setSourceView] = useState<'find' | 'saved' | 'upload'>('find')

  // Retrying a queued item re-invokes the exact same getReport() closure it was built with; reading
  // year off a ref (not the state value captured when the queue was built) means a Retry after
  // changing the year field picks up the new one, not a stale value from when the batch started.
  const yearRef = useRef(year)
  useEffect(() => {
    yearRef.current = year
  }, [year])

  // Debounced directory search; empty query = first 50. 404 = backend route not wired yet → muted one-liner.
  useEffect(() => {
    let stale = false
    const t = setTimeout(() => {
      getCompanies(query, collection)
        .then((list) => {
          if (stale) return
          setCompanies(list)
          setDirError(null)
        })
        .catch((e: ApiError) => !stale && setDirError(e.status === 404 ? '' : e.message))
    }, 250)
    return () => {
      stale = true
      clearTimeout(t)
    }
  }, [query, collection])

  useEffect(() => {
    getSchemas()
      .then((list) => {
        setSchemas(list)
        setSection(list[0]?.name ?? null)
      })
      .catch((e: Error) => setSchemasError(e.message))
    // v074: the web-search action is only offerable when the backend runs on a provider that has a
    // web-search tool (codex/claude); fixture/openai get the "needs a model provider" hint instead.
    getConfig()
      .then((c) => setProvider(c.provider))
      .catch(() => setProvider(null))
  }, [])

  useEffect(() => {
    let alive = true
    getLibrary(collection).then(rows => { if (alive) { setLibrary(rows); setLibraryError(null) } })
      .catch((e: Error) => { if (alive) setLibraryError(e.message) })
    return () => { alive = false }
  }, [collection])

  // Reject non-PDFs individually (named in the error) and keep the rest; re-picking/re-dropping appends.
  const pickFiles = (incoming: File[]) => {
    if (incoming.length === 0) return
    const rejected = incoming.filter((f) => !isPdf(f))
    const accepted = incoming.filter(isPdf)
    setError(rejected.length > 0 ? `Only PDF files are supported: ${rejected.map((f) => f.name).join(', ')}` : null)
    if (accepted.length === 0) return
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
      const next = [...prev]
      for (const f of accepted) {
        const key = `${f.name}:${f.size}`
        if (seen.has(key)) continue
        seen.add(key)
        next.push(f)
      }
      return next
    })
  }

  const removeFile = (target: File) => setFiles((prev) => prev.filter((f) => f !== target))

  const allSelected = (files: string[]) => files.length > 0 && files.every((f) => selected.has(f))
  // Chip semantics: all of the tag already selected → deselect them, otherwise select them.
  const toggleAll = (files: string[]) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (allSelected(files)) files.forEach((f) => next.delete(f))
      else files.forEach((f) => next.add(f))
      return next
    })
  const toggleOne = (f: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (!next.delete(f)) next.add(f)
      return next
    })

  const togglePick = (c: Company) =>
    setPicked((prev) => (prev.some((p) => p.name === c.name) ? prev.filter((p) => p.name !== c.name) : [...prev, c]))

  const anyRetrying = batch.items.some((it) => it.retrying)
  const busy = batch.busy || anyRetrying
  const count = picked.length + selected.size + files.length
  const canExtract = count > 0 && !!section && !busy
  // v164: the expected duration is the provider's to promise. codex/claude subscriptions answer in
  // ~30 s; the OpenAI-compatible endpoint of this setup is the local model, ~1 min; the fixture
  // backend answers instantly, so it promises nothing.
  const eta =
    provider === 'codex' || provider === 'claude'
      ? ' about 30 s with the connected model.'
      : provider === 'openai'
        ? ' about a minute on the local model.'
        : ''

  // The PDF is always wanted (page images, quote checks): the backend reuses a cached PDF, downloads one
  // when only text is saved, and falls back to that saved text if the download fails. jobId (v194,
  // optional): only the AI-searched candidate path (useCandidate below) tracks it — a plain directory
  // pick's fetch stays as before, untracked.
  const fetchWithDownload = (company: string, opts: { country?: string | null; url?: string | null; ocr?: 'full' } = {}, jobId?: string) =>
    fetchReport(company, Number(yearRef.current), { ...opts, download_pdf: true, job_id: jobId })

  // Stored extraction from the knowledge base (supervisor add-on): no model call, works without the
  // original PDF (v092). The result was extracted previously and still awaits its basis
  // confirmation — which is exactly what the Results view's basis form is for. Bypasses the batch
  // entirely (single, instant, zero-model), so it still lands on Results immediately.
  const openSample = async () => {
    setError(null)
    try {
      const extraction = await openKbExtraction(SAMPLE_STEM, SAMPLE_SECTION)
      onDone([{ label: extraction.company ?? 'Karnell Group', sectionTitle: schemas.find((s) => s.name === SAMPLE_SECTION)?.title ?? SAMPLE_SECTION, extraction }])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // Builds the queue and hands it to the App-level batch (v171/consult item 6): submission no
  // longer runs the loop itself, so its progress survives switching away from this tab and back,
  // and the batch doesn't force a tab switch when it ends — see BatchProgress's "View results".
  const runBatch = (extra: BatchSpec[] = [], onlyExtra = false) => {
    if (!section) return
    const sectionTitle = schemas.find((s) => s.name === section)?.title ?? section
    const specs: BatchSpec[] = [
      ...extra,
      ...(onlyExtra ? [] : picked).map((c) => ({
        label: c.name,
        prep: `Opening ${c.name} annual report ${yearRef.current}…`,
        getReport: (opts?: { ocr?: 'full' }) => fetchWithDownload(c.name, opts),
      })),
      ...(onlyExtra ? [] : library)
        .filter((e) => selected.has(e.file))
        .map((e) => ({ label: e.company, getReport: (opts?: { ocr?: 'full' }) => registerLibraryReport(e.file, opts?.ocr) })),
      ...(onlyExtra ? [] : files).map((f) => ({ label: f.name, getReport: (opts?: { ocr?: 'full' }) => uploadReport(f, opts?.ocr), fromUpload: true })),
    ]
    onSubmit(specs, section, sectionTitle, eta)
  }

  // A confirmed candidate runs immediately, independent of any directory picks still queued. Wrapped
  // in trackJob (v194) so CompanySearch's trace panel follows straight through from "resolving the
  // company" into "fetching its report" — the same App-level state, just a new job_id and label.
  const useCandidate = (c: Candidate) =>
    runBatch(
      [
        {
          label: c.legal_name,
          prep: `Opening ${c.legal_name} annual report ${yearRef.current}…`,
          getReport: (opts?: { ocr?: 'full' }) =>
            trackJob('fetch', `Fetching ${c.legal_name}’s annual report`, (jobId) => fetchWithDownload(c.legal_name, { country: c.country, url: c.url, ...opts }, jobId)),
        },
      ],
      true,
    )

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Extract" title="Extract report data" description="Choose a source, then select the statement to extract." actions={<CollectionPicker companies value={collection} disabled={busy} onChange={value => {
        if (value === collection) return
        setCollection(value); setPicked([]); setSelected(new Set()); setCompanies([]); setLibrary([]); setError(null)
      }} />} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => void openSample()}><BookOpenCheck className="size-3.5" />Open a real debt sample · saved result, zero model calls</Button>
        <span className="text-xs text-muted-foreground">Karnell Group FY2025 debt note — extracted previously; its reading basis is still awaiting confirmation.</span>
      </div>

      {provider === 'fixture' && <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-border bg-primary/5 px-5 py-4 shadow-[inset_0_1px_0_var(--glass-hi)]">
        <Info className="size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1"><p className="text-sm font-medium">Demo mode — no model is configured, so extraction returns a built-in sample result.</p><p className="mt-0.5 text-xs text-muted-foreground">Uploads still parse for real (pages, candidate pages, sources); only the figures are fictional.</p></div>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => void openSample()}>View a real sample</Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => onNavigate?.('settings')}>Set up a real model in Settings</Button>
      </div>}

      <Workspace label="Report source" value={sourceView} onChange={setSourceView} pages={[
        { value: 'find', label: 'Find a company', icon: FileSearch, count: picked.length, content: <CompanySearch
          collection={collection} query={query} year={year} companies={companies} dirError={dirError} picked={picked} busy={busy} canRun={!!section}
          discovery={discovery} discovering={discovering} trace={trace} onQueryChange={setQuery} onYearChange={setYear} onTogglePick={togglePick}
          onDiscover={discover} onUseCandidate={useCandidate} /> },
        { value: 'saved', label: 'Saved reports', icon: Files, count: selected.size, content: <CachedReports
          library={library} libraryError={libraryError} selected={selected} busy={busy} onSelectAll={() => setSelected(new Set(library.map(entry => entry.file)))}
          onSelectNone={() => setSelected(new Set())} onToggleTag={toggleAll} onToggleOne={toggleOne} /> },
        { value: 'upload', label: 'Upload PDF', icon: Upload, count: files.length, content: <Dropzone
          files={files} dragging={dragging} busy={busy} onDragStage={setDragging} onPick={pickFiles} onRemove={removeFile} /> },
      ]} footer={<div className="w-full" aria-busy={busy || undefined}>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3 px-5 py-4">
          <div className="w-full max-w-80 space-y-1 min-[1280px]:flex-1">
            <label htmlFor="section" className="text-xs text-muted-foreground">Section</label>
            <Select value={section} onValueChange={setSection} items={Object.fromEntries(schemas.map(schema => [schema.name, schema.title]))} disabled={busy || schemas.length === 0}>
              <SelectTrigger id="section" className="w-full"><SelectValue placeholder={schemasError ? 'No sections available' : 'Loading sections…'} /></SelectTrigger>
              <SelectContent>{schemas.map(schema => <SelectItem key={schema.name} value={schema.name}>{schema.title}</SelectItem>)}</SelectContent>
            </Select>
            {schemasError && <ErrorBlock className="px-3 py-2 text-xs">Could not load sections ({schemasError}). Is the backend running?</ErrorBlock>}
          </div>
          <Button onClick={() => runBatch()} disabled={!canExtract}>{busy && <Loader2 className="animate-spin" />}{count > 1 ? `Extract ${count} reports` : 'Extract'}</Button>
        </div>
        <BatchProgress items={batch.items} busy={busy} stopRequested={batch.stopRequested} resultsCount={resultsCount}
          onStopAfterCurrent={batch.stopAfterCurrent} onRetry={(id, opts) => void batch.retry(id, opts)} onViewResults={onViewResults} onNavigate={onNavigate} />
        {error && <div className="border-t border-border px-5 py-4"><ErrorBlock>{error}</ErrorBlock></div>}
      </div>} />
    </div>
  )
}