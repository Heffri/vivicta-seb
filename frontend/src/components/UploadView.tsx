import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type ApiError, extractSection, fetchReport, getCompanies, getLibrary, getSchemas, registerLibraryReport, uploadReport } from '@/api'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import { CachedReports } from '@/components/upload/CachedReports'
import { CompanySearch } from '@/components/upload/CompanySearch'
import { Dropzone } from '@/components/upload/Dropzone'
import type { Company, LibraryEntry, Report, Result, Schema } from '@/types'

type Props = { onDone: (results: Result[]) => void }

export function UploadView({ onDone }: Props) {
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [schemasError, setSchemasError] = useState<string | null>(null)
  const [section, setSection] = useState<string | null>(null)
  const [library, setLibrary] = useState<LibraryEntry[]>([])
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // LibraryEntry.file
  const [query, setQuery] = useState('')
  const [year, setYear] = useState('2025')
  const [companies, setCompanies] = useState<Company[]>([])
  const [dirError, setDirError] = useState<string | null>(null)
  const [picked, setPicked] = useState<Company[]>([]) // directory picks, deduped by name
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<string | null>(null) // non-null = busy
  const [error, setError] = useState<string | null>(null)
  const [tried, setTried] = useState<Record<string, string[]>>({}) // label → URLs /fetch tried, for the all-failed block

  // Debounced directory search; empty query = first 50. 404 = backend route not wired yet → muted one-liner.
  useEffect(() => {
    let stale = false
    const t = setTimeout(() => {
      getCompanies(query)
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
  }, [query])

  useEffect(() => {
    getSchemas()
      .then((list) => {
        setSchemas(list)
        setSection(list[0]?.name ?? null)
      })
      .catch((e: Error) => setSchemasError(e.message))
    getLibrary()
      .then(setLibrary)
      .catch((e: Error) => setLibraryError(e.message))
  }, [])

  const pickFile = (f: File | undefined) => {
    if (!f) return
    if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.')
      return
    }
    setError(null)
    setFile(f)
  }

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

  const busy = progress !== null
  const count = picked.length + selected.size + (file ? 1 : 0)
  const canExtract = count > 0 && !!section && !busy

  const run = async () => {
    if (!section) return
    setError(null)
    setTried({})
    const sectionTitle = schemas.find((s) => s.name === section)?.title ?? section
    // Queue = directory picks (fetched on demand) + selected cached entries (library order) + the uploaded file.
    // Sequential on purpose: the local LLM is one GPU, parallel requests would only queue there and we'd lose the
    // per-report progress line.
    const queue = [
      ...picked.map((c) => ({
        label: c.name,
        prep: `Fetching ${c.name} annual report ${year}…`,
        getReport: () => fetchReport(c.name, Number(year)),
      })),
      ...library
        .filter((e) => selected.has(e.file))
        .map((e) => ({ label: e.company, getReport: () => registerLibraryReport(e.file) })),
      ...(file ? [{ label: file.name, getReport: () => uploadReport(file) }] : []),
    ] as { label: string; prep?: string; getReport: () => Promise<Report> }[]
    const results: Result[] = []
    for (const [i, item] of queue.entries()) {
      const n = `(${i + 1}/${queue.length}${item.prep ? ', can take a minute' : ''})`
      try {
        setProgress(`${item.prep ?? `Preparing ${item.label}`} ${n}`)
        const report = await item.getReport()
        setProgress(`Extracting ${item.label} ${n}… about a minute per report with a local model.`)
        const extraction = await extractSection(report.report_id, section)
        // Library entries keep the curated name; the upload gets whatever the backend/LLM guessed.
        const label = item.label === file?.name ? (extraction.company ?? report.company ?? item.label) : item.label
        results.push({ label, sectionTitle, extraction })
      } catch (e) {
        results.push({ label: item.label, sectionTitle, error: (e as Error).message })
        // ponytail: Result has no `tried` slot (types.ts is off-limits); kept here for the all-failed block only.
        const t = (e as ApiError).tried
        if (t?.length) setTried((prev) => ({ ...prev, [item.label]: t }))
      }
    }
    setProgress(null)
    if (results.every((r) => r.error)) setError(results.map((r) => `${r.label}: ${r.error}`).join('\n'))
    else onDone(results)
  }

  return (
    <div className="mx-auto w-full max-w-3xl min-[1280px]:max-w-none">
      <header className="mb-6">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Extract</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Pick reports, get source-linked numbers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search the directory, tick cached reports or drop a PDF. One report opens Results, several open Compare.
        </p>
      </header>

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
          <Dropzone file={file} dragging={dragging} busy={busy} onDragStage={setDragging} onPick={pickFile} />
        </div>

        {/* Action bar: section choice, run button, progress line. */}
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
          <Button onClick={run} disabled={!canExtract}>
            {busy && <Loader2 className="animate-spin" />}
            {count > 1 ? `Extract ${count} reports` : 'Extract'}
          </Button>
          {progress && <LoadingLine className="w-full">{progress}</LoadingLine>}
        </div>

        {/* All-failed block. The shared danger block (v010); the tried URL list stays inside
            it as collapsible details for the /fetch 404 case, where the backend reports
            what it attempted. */}
        {error && (
          <div className="border-t border-border px-5 py-4">
            <ErrorBlock
              details={Object.entries(tried).map(([label, urls]) => (
                <details key={label} className="mt-1 text-xs">
                  <summary className="cursor-pointer">
                    {label}: tried {urls.length} URL{urls.length === 1 ? '' : 's'}
                  </summary>
                  <ul className="mt-1 list-inside list-disc break-all">
                    {urls.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                </details>
              ))}
            >
              {error}
            </ErrorBlock>
          </div>
        )}
      </section>
    </div>
  )
}
