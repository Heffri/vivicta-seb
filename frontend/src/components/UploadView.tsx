import { FileText, Loader2, Search, UploadCloud, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type ApiError, extractSection, fetchReport, getCompanies, getLibrary, getSchemas, registerLibraryReport, uploadReport } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Company, LibraryEntry, Report, Result, Schema } from '@/types'

type Props = { onDone: (results: Result[]) => void }

const fmtSize = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.round(bytes / 1000)} kB` : `${(bytes / 1_000_000).toFixed(1)} MB`

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

  const tags = [...new Set(library.flatMap((e) => e.tags))].sort()
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
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Extract</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Pick reports, get source-linked numbers</h1>
        <p className="mt-1 text-sm text-muted-foreground">Search the directory, tick cached reports or drop a PDF. One report opens Results, several open Compare.</p>
      </header>

      <Card>
        <CardContent className="space-y-6">
          {/* Directory search (primary path): pick listed companies, /fetch pulls the PDF on demand. */}
          <div className="space-y-3">
            <label htmlFor="company-q" className="text-sm font-medium">
              Companies
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="company-q"
                  type="search"
                  value={query}
                  disabled={busy}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search listed companies… e.g. Sandvik"
                  className="h-8 w-full rounded-lg border bg-transparent pr-3 pl-8 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                />
              </div>
              <Select value={year} onValueChange={(v) => v && setYear(v)} items={{ 2025: '2025', 2024: '2024', 2023: '2023' }} disabled={busy}>
                <SelectTrigger aria-label="Fiscal year" className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['2025', '2024', '2023'].map((y) => (
                    <SelectItem key={y} value={y}>
                      {y}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {dirError !== null ? (
              <p className="text-xs text-muted-foreground">Company directory unavailable{dirError && ` (${dirError})`}.</p>
            ) : (
              <ul className="max-h-56 divide-y overflow-y-auto rounded-lg border text-sm">
                {companies.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No matches.</li>}
                {companies.map((c) => {
                  const on = picked.some((p) => p.name === c.name)
                  return (
                    <li key={c.name}>
                      <button
                        type="button"
                        disabled={busy}
                        aria-pressed={on}
                        onClick={() => togglePick(c)}
                        className={`flex w-full flex-wrap items-center gap-1.5 px-3 py-1.5 text-left hover:bg-muted/50 disabled:opacity-60 ${
                          on ? 'bg-primary/5' : ''
                        }`}
                      >
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-muted-foreground">{c.ticker}</span>
                        {c.sector && <span className="text-xs text-muted-foreground">· {c.sector}</span>}
                        {c.cached_years.includes(Number(year)) && (
                          <Badge variant="secondary" className="ml-auto">
                            cached
                          </Badge>
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
            {picked.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground">Selected:</span>
                {picked.map((c) => (
                  <Badge key={c.name} variant="secondary" className="gap-1 pr-1">
                    {c.name}
                    <button
                      type="button"
                      aria-label={`Remove ${c.name}`}
                      disabled={busy}
                      onClick={() => togglePick(c)}
                      className="rounded-sm hover:bg-muted"
                    >
                      <X className="size-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {/* Cached reports (secondary): chips = tag collections, grid = individual reports. */}
          <details className="space-y-3">
            <summary className="cursor-pointer text-xs text-muted-foreground select-none">
              Cached reports ({library.length}){selected.size > 0 && ` · ${selected.size} selected`}
            </summary>
            {libraryError ? (
              <p className="text-xs text-muted-foreground">Report cache unavailable ({libraryError}).</p>
            ) : library.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Nothing cached yet — pick a company above to fetch its report, or upload a PDF below.
              </p>
            ) : (
              <>
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={busy}
                    onClick={() => setSelected(new Set(library.map((e) => e.file)))}
                  >
                    All
                  </Button>
                  <Button size="xs" variant="outline" disabled={busy} onClick={() => setSelected(new Set())}>
                    None
                  </Button>
                  {tags.map((t) => {
                    const files = library.filter((e) => e.tags.includes(t)).map((e) => e.file)
                    return (
                      <Button
                        key={t}
                        size="xs"
                        variant={allSelected(files) ? 'default' : 'outline'}
                        disabled={busy}
                        onClick={() => toggleAll(files)}
                      >
                        {t}
                      </Button>
                    )
                  })}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {library.map((e) => (
                    <label
                      key={e.file}
                      className={`flex cursor-pointer gap-3 rounded-lg border p-3 text-sm transition-colors hover:bg-muted/50 ${
                        selected.has(e.file) ? 'border-primary bg-primary/5' : ''
                      } ${busy ? 'pointer-events-none opacity-60' : ''}`}
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-primary"
                        checked={selected.has(e.file)}
                        disabled={busy}
                        onChange={() => toggleOne(e.file)}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium">{e.company}</span>
                          <span className="text-muted-foreground">FY {e.fiscal_year}</span>
                          <Badge variant="secondary" className="uppercase">
                            {e.language}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{e.pages} p</span>
                        </span>
                        {e.note && <span className="mt-0.5 block text-xs text-muted-foreground">{e.note}</span>}
                      </span>
                    </label>
                  ))}
                </div>
              </>
            )}
          </details>

          {/* Dropzone. The <label> makes the whole area click-to-open the hidden input. */}
          <label
            htmlFor="pdf"
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              pickFile(e.dataTransfer.files[0])
            }}
            className={[
              'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors',
              dragging ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50',
              busy ? 'pointer-events-none opacity-60' : '',
            ].join(' ')}
          >
            {file ? (
              <>
                <FileText className="size-6 text-primary" />
                <span className="text-sm font-medium">{file.name}</span>
                <span className="text-xs text-muted-foreground">{fmtSize(file.size)} · click or drop to replace</span>
              </>
            ) : (
              <>
                <UploadCloud className="size-6 text-muted-foreground" />
                <span className="text-sm font-medium">…or upload your own annual report PDF</span>
                <span className="text-xs text-muted-foreground">drop it here or click to browse</span>
              </>
            )}
            <input
              id="pdf"
              type="file"
              accept="application/pdf"
              className="sr-only"
              disabled={busy}
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </label>

          <div className="space-y-1.5">
            <label htmlFor="section" className="text-sm font-medium">
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
              <p className="text-xs text-destructive">
                Could not load sections ({schemasError}). Is the backend running on :8000?
              </p>
            )}
          </div>

          <div className="flex items-center gap-4">
            <Button onClick={run} disabled={!canExtract}>
              {busy && <Loader2 className="animate-spin" />}
              {count > 1 ? `Extract ${count} reports` : 'Extract'}
            </Button>
            {progress && <span className="text-sm text-muted-foreground">{progress}</span>}
          </div>

          {error && (
            <div
              role="alert"
              className="whitespace-pre-wrap rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
              {Object.entries(tried).map(([label, urls]) => (
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
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
