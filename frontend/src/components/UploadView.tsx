import { FileText, Loader2, UploadCloud } from 'lucide-react'
import { useEffect, useState } from 'react'
import { extractSection, getLibrary, getSchemas, registerLibraryReport, uploadReport } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { LibraryEntry, Report, Result, Schema } from '@/types'

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
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<string | null>(null) // non-null = busy
  const [error, setError] = useState<string | null>(null)

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

  const busy = progress !== null
  const count = selected.size + (file ? 1 : 0)
  const canExtract = count > 0 && !!section && !busy

  const run = async () => {
    if (!section) return
    setError(null)
    const sectionTitle = schemas.find((s) => s.name === section)?.title ?? section
    // Queue = selected library entries (library order) + the uploaded file. Sequential on purpose: the local LLM
    // is one GPU, parallel requests would only queue there and we'd lose the per-report progress line.
    const queue = [
      ...library
        .filter((e) => selected.has(e.file))
        .map((e) => ({ label: e.company, getReport: () => registerLibraryReport(e.file) })),
      ...(file ? [{ label: file.name, getReport: () => uploadReport(file) }] : []),
    ] satisfies { label: string; getReport: () => Promise<Report> }[]
    const results: Result[] = []
    for (const [i, item] of queue.entries()) {
      const n = `(${i + 1}/${queue.length})`
      try {
        setProgress(`Preparing ${item.label} ${n}…`)
        const report = await item.getReport()
        setProgress(`Extracting ${item.label} ${n}… about a minute per report with a local model.`)
        const extraction = await extractSection(report.report_id, section)
        // Library entries keep the curated name; the upload gets whatever the backend/LLM guessed.
        const label = item.label === file?.name ? (extraction.company ?? report.company ?? item.label) : item.label
        results.push({ label, sectionTitle, extraction })
      } catch (e) {
        results.push({ label: item.label, sectionTitle, error: (e as Error).message })
      }
    }
    setProgress(null)
    if (results.every((r) => r.error)) setError(results.map((r) => `${r.label}: ${r.error}`).join('\n'))
    else onDone(results)
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Annual Report Parser</h1>
        <p className="mt-1 text-sm text-muted-foreground">PDF in → structured, source-linked data out</p>
      </header>

      <Card>
        <CardContent className="space-y-6">
          {/* Library picker: chips = tag collections, grid = individual reports. */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-medium">Companies</span>
              {library.length > 0 && (
                <span className="text-xs text-muted-foreground">
                  {selected.size} of {library.length} selected
                </span>
              )}
            </div>
            {libraryError ? (
              <p className="text-xs text-muted-foreground">Bundled library unavailable ({libraryError}).</p>
            ) : library.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No bundled reports on disk — run <code>python data/fetch.py</code>, or upload a PDF below.
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
          </div>

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
            <p
              role="alert"
              className="whitespace-pre-wrap rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
