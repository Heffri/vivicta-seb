import { Database, Loader2, Search } from 'lucide-react'
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
  const [query, setQuery] = useState('')

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
  // Batch section = the first schema (in schema order) every selected report actually has; schemas[0] is
  // debt_maturity since that schema landed, which no KB entry has yet, so it 404'd both legs of a Compare.
  const has = (stem: string, name: string) => !!entries?.find((e) => e.stem === stem)?.sections.includes(name)
  const section =
    schemas.map((s) => s.name).find((n) => withSection.length > 0 && withSection.every((s) => has(s, n))) ??
    entries?.find((e) => e.stem === withSection[0])?.sections[0] ??
    'income_statement'

  // Display-only: narrows which rows render, never touches `selected`.
  const q = query.trim().toLowerCase()
  const filtered = (entries ?? []).filter((e) => !q || (e.company ?? '').toLowerCase().includes(q) || e.stem.toLowerCase().includes(q))

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

      {error && (
        <div className="whitespace-pre-line rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {!entries && !error && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </p>
      )}

      {entries && entries.length === 0 && <p className="text-sm text-muted-foreground">Empty — extract a report first.</p>}

      {entries && entries.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by company or stem…"
              aria-label="Filter reports"
              className="h-8 w-full rounded-lg border border-input bg-background py-2 pr-2.5 pl-8 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {filtered.length} / {entries.length}
          </span>
        </div>
      )}

      {entries && entries.length > 0 && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">No matches for "{query}".</p>
      )}

      {filtered.length > 0 && (
        <Card className="overflow-hidden py-0 [&_[data-slot=table-container]]:max-h-[70vh] [&_[data-slot=table-container]]:overflow-y-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-muted">
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Company</TableHead>
                <TableHead className="text-right">FY</TableHead>
                <TableHead className="text-right max-[900px]:hidden">Pages</TableHead>
                <TableHead>Extractions</TableHead>
                <TableHead>Embeddings</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((e) => {
                const isSelected = selected.has(e.stem)
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
                        onChange={() => toggle(e.stem)}
                        className="size-3.5 accent-ring"
                      />
                    </TableCell>
                    <TableCell className="font-medium">
                      {e.company ?? e.stem}
                      <span className="ml-2 font-mono text-xs text-muted-foreground max-[900px]:hidden">{e.stem}</span>
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
                    <TableCell>
                      <Badge variant={e.indexed ? 'success' : 'outline'} className={e.indexed ? undefined : 'text-muted-foreground'}>
                        {e.indexed ? 'indexed' : 'not yet'}
                      </Badge>
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
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
