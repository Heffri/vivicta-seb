import { BookOpenCheck, Globe, Info, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { type ApiError, fetchReport, getCompanies, getConfig, getLibrary, getSchemas, openKbExtraction, registerLibraryReport, uploadReport } from '@/api'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock } from '@/components/ui/state'
import { BatchProgress } from '@/components/upload/BatchProgress'
import { CachedReports } from '@/components/upload/CachedReports'
import { CompanySearch } from '@/components/upload/CompanySearch'
import { CollectionPicker } from '@/components/CollectionPicker'
import { useCollection } from '@/hooks/useCollection'
import type { Batch, BatchSpec } from '@/hooks/useBatch'
import { Dropzone } from '@/components/upload/Dropzone'
import type { Tab } from '@/components/shell/tabs'
import type { Company, LibraryEntry, Result, Schema } from '@/types'

type Props = {
  batch: Batch
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

export function UploadView({ batch, onSubmit, resultsCount, onViewResults, onDone, onNavigate }: Props) {
  const [collection, setCollection] = useCollection()
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [schemasError, setSchemasError] = useState<string | null>(null)
  const [section, setSection] = useState<string | null>(null)
  const [library, setLibrary] = useState<LibraryEntry[]>([])
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // LibraryEntry.file
  const [query, setQuery] = useState('')
  const [year, setYear] = useState('2025')
  const [downloadPdf, setDownloadPdf] = useState(false)
  const [companies, setCompanies] = useState<Company[]>([])
  const [dirError, setDirError] = useState<string | null>(null)
  const [provider, setProvider] = useState<string | null>(null) // backend /api/config provider; null = not loaded yet
  const [picked, setPicked] = useState<Company[]>([]) // directory picks, deduped by name
  const [files, setFiles] = useState<File[]>([]) // uploads, in drop/pick order, deduped by name+size
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null) // local validation only (bad file type, sample open failure) — batch failures render per-item in BatchProgress

  // Retrying a queued item re-invokes the exact same getReport() closure it was built with; reading
  // these two off refs (not the state values captured when the queue was built) means checking
  // "Allow PDF download" after a download-needed failure and clicking Retry actually picks it up.
  const liveRef = useRef({ year, downloadPdf })
  useEffect(() => {
    liveRef.current = { year, downloadPdf }
  }, [year, downloadPdf])

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
  const hasWebQuery = query.trim().length > 0
  const webSearchAvailable = provider === 'codex' || provider === 'claude'
  // v164: the expected duration is the provider's to promise. codex/claude subscriptions answer in
  // ~30 s; the OpenAI-compatible endpoint of this setup is the local model, ~1 min; the fixture
  // backend answers instantly, so it promises nothing.
  const eta =
    provider === 'codex' || provider === 'claude'
      ? ' about 30 s with the connected model.'
      : provider === 'openai'
        ? ' about a minute on the local model.'
        : ''

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
        prep: `Opening ${c.name} annual report ${liveRef.current.year}…`,
        getReport: () => fetchReport(c.name, Number(liveRef.current.year), { download_pdf: liveRef.current.downloadPdf }),
      })),
      ...(onlyExtra ? [] : library)
        .filter((e) => selected.has(e.file))
        .map((e) => ({ label: e.company, getReport: () => registerLibraryReport(e.file) })),
      ...(onlyExtra ? [] : files).map((f) => ({ label: f.name, getReport: () => uploadReport(f), fromUpload: true })),
    ]
    onSubmit(specs, section, sectionTitle, eta)
  }

  // Any company name can use live discovery; other queued picks stay untouched.
  const runWeb = (name: string) => {
    runBatch([
      {
        label: name,
        prep: `Finding ${name} annual report ${year}…`,
        getReport: async () => {
          try { return await fetchReport(name, Number(liveRef.current.year), { download_pdf: false }) }
          catch (error) {
            if ((error as ApiError).status !== 409) throw error
            return fetchReport(name, Number(liveRef.current.year), { download_pdf: true })
          }
        },
      },
    ], true)
  }

  return (
    <div className="mx-auto w-full max-w-3xl min-[1280px]:max-w-none">
      <header className="mb-6">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Extract</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Pick reports, get source-linked numbers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Find a company’s annual report with AI web search, reuse saved reports, or upload a PDF.
        </p>
        <div className="mt-4"><CollectionPicker companies value={collection} disabled={busy} onChange={value => {
          if (value === collection) return
          setCollection(value); setPicked([]); setSelected(new Set()); setCompanies([]); setLibrary([]); setError(null)
        }} /></div>
        {/* Direct line to a real result (supervisor add-on to v164): a stored KB extraction opens
            with zero model calls — and its title says plainly that the basis is still unconfirmed. */}
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void openSample()}>
            <BookOpenCheck className="size-3.5" />
            Open a real debt sample · saved result, zero model calls
          </Button>
          <span className="text-xs text-muted-foreground">
            Karnell Group FY2025 debt note — extracted previously; its reading basis is still awaiting confirmation.
          </span>
        </div>
      </header>

      {/* Fixture mode says so before any upload (supervisor add-on): the figures a run returns are
          the built-in sample, not this report's. Prominent but secondary-styled — it is a mode
          explanation, not an error (DESIGN.md keeps danger for data-status failures). */}
      {provider === 'fixture' && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-border bg-primary/5 px-5 py-4 shadow-[inset_0_1px_0_var(--glass-hi)]">
          <Info className="size-5 shrink-0 text-primary" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Demo mode — no model is configured, so extraction returns a built-in sample result.</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Uploads still parse for real (pages, candidate pages, sources); only the figures are fictional.</p>
          </div>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void openSample()}>
            View a real sample
          </Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => onNavigate?.('settings')}>
            Set up a real model in Settings
          </Button>
        </div>
      )}

      {/* One material: the whole screen is a single flat translucent step over the shell glass —
          a --bg-1..2 gradient, hairline border, specular top edge, no backdrop-filter of its own
          (DESIGN.md: one blurred pane per window, everything inside is a flat --bg-N step). */}
      <section
        aria-busy={busy || undefined}
        className="overflow-hidden rounded-xl border border-border bg-linear-to-b from-background to-muted/60 shadow-[inset_0_1px_0_var(--glass-hi)]"
      >
        {/* The three paths. Busy dims the faces as a whole; the action bar below stays live. */}
        <div
          className={`grid transition-opacity duration-200 min-[1280px]:grid-cols-[1.1fr_1.1fr_1fr] ${
            busy ? 'pointer-events-none opacity-60' : ''
          }`}
        >
          <CompanySearch
            collection={collection}
            query={query}
            year={year}
            companies={companies}
            dirError={dirError}
            picked={picked}
            busy={busy}
            onQueryChange={setQuery}
            onYearChange={setYear}
            onTogglePick={togglePick}
          />
          <CachedReports
            library={library}
            libraryError={libraryError}
            selected={selected}
            busy={busy}
            onSelectAll={() => setSelected(new Set(library.map((e) => e.file)))}
            onSelectNone={() => setSelected(new Set())}
            onToggleTag={toggleAll}
            onToggleOne={toggleOne}
          />
          <Dropzone
            files={files}
            dragging={dragging}
            busy={busy}
            onDragStage={setDragging}
            onPick={pickFiles}
            onRemove={removeFile}
          />
        </div>

        {/* Live discovery is independent of the local directory and collection. */}
        {hasWebQuery && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border bg-background/50 px-5 py-3">
            <div className="min-w-0 flex-1"><p className="text-sm font-medium">Find “{query.trim()}” on the web</p><p className="text-xs text-muted-foreground">Reuses saved reports first. Otherwise AI finds the official report, downloads the PDF and extracts your selected section.</p></div>
            {webSearchAvailable ? (
              <Button variant="outline" size="sm" disabled={busy || !section} onClick={() => runWeb(query.trim())}>
                <Globe className="size-3.5" />
                AI search, download & extract · {year}
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">Web search needs a model provider (Settings).</span>
            )}
          </div>
        )}

        <label className="flex items-start gap-2 border-t px-5 py-3 text-sm"><input type="checkbox" className="mt-1" checked={downloadPdf} disabled={busy} onChange={e => setDownloadPdf(e.target.checked)} /><span>Allow PDF download for this request<span className="block text-xs text-muted-foreground">Off by default. Saved text and figures work without the original PDF. Turn on only to fetch a missing report or its original PDF.</span></span></label>
        {/* Action bar: section choice, run button. Per-item progress now lives in BatchProgress
            below, not a single shared line — it keeps going after this section re-renders and
            after a tab switch away and back, since it reads App-level batch state. */}
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3 border-t border-border bg-background/50 px-5 py-4">
          <div className="w-full max-w-80 space-y-1 min-[1280px]:flex-1">
            <label htmlFor="section" className="text-xs text-muted-foreground">
              Section
            </label>
            <Select
              value={section}
              onValueChange={setSection}
              items={Object.fromEntries(schemas.map((s) => [s.name, s.title]))}
              disabled={busy || schemas.length === 0}
            >
              <SelectTrigger id="section" className="w-full">
                <SelectValue placeholder={schemasError ? 'No sections available' : 'Loading sections…'} />
              </SelectTrigger>
              <SelectContent>
                {schemas.map((s) => (
                  <SelectItem key={s.name} value={s.name}>
                    {s.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {schemasError && (
              <ErrorBlock className="px-3 py-2 text-xs">
                Could not load sections ({schemasError}). Is the backend running?
              </ErrorBlock>
            )}
          </div>
          <Button
            onClick={() => runBatch()}
            disabled={!canExtract}
          >
            {busy && <Loader2 className="animate-spin" />}
            {downloadPdf && picked.length ? 'Download PDF and extract' : count > 1 ? `Extract ${count} reports` : 'Extract'}
          </Button>
        </div>

        <BatchProgress
          items={batch.items}
          busy={busy}
          stopRequested={batch.stopRequested}
          resultsCount={resultsCount}
          onStopAfterCurrent={batch.stopAfterCurrent}
          onRetry={(id) => void batch.retry(id)}
          onViewResults={onViewResults}
          onNavigate={onNavigate}
        />

        {/* Local validation only — bad file type on drop/pick, or the sample failing to open.
            Batch failures (fetch/candidates/extract) render per-item in BatchProgress above,
            with their own next-step copy, not here. */}
        {error && (
          <div className="border-t border-border px-5 py-4">
            <ErrorBlock>{error}</ErrorBlock>
          </div>
        )}
      </section>
    </div>
  )
}
