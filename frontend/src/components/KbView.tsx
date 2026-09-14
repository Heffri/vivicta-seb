import { Database, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getKb, getSchemas, openKbExtraction } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { KbEntry, Result, Schema } from '@/types'

type Props = { onOpen: (results: Result[]) => void }

// Everything the parser has learnt so far: one row per report in data/kb, opened from disk without a model call.
export function KbView({ onOpen }: Props) {
  const [entries, setEntries] = useState<KbEntry[] | null>(null)
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // stems
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    getKb().then(setEntries).catch((e: Error) => setError(e.message))
    getSchemas().then(setSchemas).catch(() => {})
  }, [])

  const title = (section: string) => schemas.find((s) => s.name === section)?.title ?? section

  const open = async (stems: string[], section: string) => {
    setBusy(stems.join())
    setError(null)
    const results: Result[] = []
    for (const stem of stems) {
      const label = entries?.find((e) => e.stem === stem)?.company ?? stem
      try {
        results.push({ label, sectionTitle: title(section), extraction: await openKbExtraction(stem, section) })
      } catch (e) {
        results.push({ label, sectionTitle: title(section), error: (e as Error).message })
      }
    }
    setBusy(null)
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
  const section = schemas[0]?.name ?? 'income_statement'

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b pb-5">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">Knowledge base</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            {entries ? `${entries.length} reports` : 'Reports'}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Stored page text, extractions and embeddings in <code>data/kb</code>. Opening a row reads the saved extraction — no model call.
          </p>
        </div>
        <Button disabled={withSection.length < 2 || !!busy} onClick={() => open(withSection, section)}>
          {busy && withSection.join() === busy ? <Loader2 className="animate-spin" /> : <Database />}
          Compare {withSection.length > 1 ? withSection.length : ''} selected
        </Button>
      </header>

      {error && <p className="whitespace-pre-line text-sm text-destructive">{error}</p>}

      {!entries && !error && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </p>
      )}

      {entries && entries.length === 0 && <p className="text-sm text-muted-foreground">Empty — extract a report first.</p>}

      {entries && entries.length > 0 && (
        <Card className="overflow-x-auto py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Company</TableHead>
                <TableHead>FY</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead>Extractions</TableHead>
                <TableHead>Embeddings</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.stem} data-state={selected.has(e.stem) ? 'selected' : undefined}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`Select ${e.company ?? e.stem}`}
                      checked={selected.has(e.stem)}
                      disabled={!e.sections.length}
                      onChange={() => toggle(e.stem)}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    {e.company ?? e.stem}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">{e.stem}</span>
                  </TableCell>
                  <TableCell>{e.fiscal_year ?? '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">{e.pages}</TableCell>
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
                  <TableCell>
                    <Badge variant={e.indexed ? 'default' : 'outline'}>{e.indexed ? 'indexed' : 'not yet'}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {e.sections.map((s) => (
                      <Button key={s} size="xs" variant="outline" disabled={!!busy} onClick={() => open([e.stem], s)}>
                        {busy === e.stem ? <Loader2 className="animate-spin" /> : null}
                        Open
                      </Button>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
