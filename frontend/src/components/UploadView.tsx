import { FileText, Loader2, UploadCloud } from 'lucide-react'
import { useEffect, useState } from 'react'
import { extractSection, getSchemas, uploadReport } from '@/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Extraction, Schema } from '@/types'

type Props = { onDone: (extraction: Extraction, sectionTitle: string) => void }

type Status = { step: 'idle' } | { step: 'uploading' } | { step: 'extracting'; pages: number }

const fmtSize = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.round(bytes / 1000)} kB` : `${(bytes / 1_000_000).toFixed(1)} MB`

export function UploadView({ onDone }: Props) {
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [schemasError, setSchemasError] = useState<string | null>(null)
  const [section, setSection] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState<Status>({ step: 'idle' })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSchemas()
      .then((list) => {
        setSchemas(list)
        setSection(list[0]?.name ?? null)
      })
      .catch((e: Error) => setSchemasError(e.message))
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

  const busy = status.step !== 'idle'
  const canExtract = !!file && !!section && !busy

  const run = async () => {
    if (!file || !section) return
    setError(null)
    try {
      setStatus({ step: 'uploading' })
      const report = await uploadReport(file)
      setStatus({ step: 'extracting', pages: report.pages })
      const extraction = await extractSection(report.report_id, section)
      onDone(extraction, schemas.find((s) => s.name === section)?.title ?? section)
    } catch (e) {
      setError((e as Error).message)
      setStatus({ step: 'idle' })
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Annual Report Parser</h1>
        <p className="mt-1 text-sm text-muted-foreground">PDF in → structured, source-linked data out</p>
      </header>

      <Card>
        <CardContent className="space-y-6">
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
              'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center transition-colors',
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
                <span className="text-sm font-medium">Drop an annual report PDF here</span>
                <span className="text-xs text-muted-foreground">or click to browse</span>
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
              Extract
            </Button>
            {status.step === 'uploading' && <span className="text-sm text-muted-foreground">Uploading…</span>}
            {status.step === 'extracting' && (
              <span className="text-sm text-muted-foreground">
                Reading {status.pages} pages… this can take about a minute with a local model.
              </span>
            )}
          </div>

          {error && (
            <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
