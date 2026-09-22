import { useEffect, useState } from 'react'
import { Library, MessageCircle, Search } from 'lucide-react'
import { getKb } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { KbEntry } from '@/types'

type Props = { initialCompany?: string }

export function AskView({ initialCompany }: Props) {
  const [view, setView] = useState<'ask' | 'coverage'>('ask')
  const [query, setQuery] = useState('')
  const [catalog, setCatalog] = useState<KbEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let alive = true
    getKb().then((entries) => { if (alive) setCatalog(entries) }).catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [retry])
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Ask" title="Ask your saved reports" description="Explore figures and risks. Follow every answer back to its source." />
      {error ? <div className="space-y-2"><ErrorBlock>Could not load saved reports: {error}</ErrorBlock><Button onClick={() => { setError(null); setCatalog(null); setRetry((n) => n + 1) }}>Retry</Button></div>
        : catalog === null ? <LoadingLine>Loading saved reports…</LoadingLine>
        : <Workspace label="Ask workspace" value={view} onChange={setView} pages={[
          { value: 'ask', label: 'Conversation', icon: MessageCircle, content: <div className="mx-auto max-w-4xl"><AskPanel reports={[]} catalog={catalog.filter(e => e.text_available !== false)} initialCompany={initialCompany} /></div> },
          { value: 'coverage', label: 'Available reports', icon: Library, count: catalog.length, content: <>
            <div className="flex flex-wrap items-center gap-3"><Input icon={<Search />} aria-label="Search available reports" placeholder="Search companies…" value={query} onChange={e => setQuery(e.target.value)} /><p className="text-xs text-muted-foreground" role="status">{catalog.filter(e => e.text_available !== false).length} reports with saved text · {catalog.filter(e => e.figures_available ?? e.sections.length > 0).length} with extracted figures · {catalog.filter(e => e.pdf_available).length} PDFs downloaded</p></div>
            {catalog.some(e => e.text_available === false) && <p className="text-xs text-muted-foreground">{catalog.filter(e => e.text_available === false).length} catalog entries have no readable page text and are excluded from Ask.</p>}
            <Table><TableHeader><TableRow><TableHead>Company</TableHead><TableHead>Year</TableHead><TableHead>Available to Ask</TableHead><TableHead>Original PDF</TableHead></TableRow></TableHeader><TableBody>
              {catalog.filter(e => (e.company ?? e.stem).toLowerCase().includes(query.trim().toLowerCase())).map(e => <TableRow key={e.stem}><TableCell className="font-medium">{e.company ?? e.stem}</TableCell><TableCell>{e.fiscal_year ?? '—'}</TableCell><TableCell>{e.text_available !== false ? 'Saved text' : 'No readable text'}</TableCell><TableCell>{e.pdf_available ? 'Downloaded' : 'Not downloaded'}</TableCell></TableRow>)}
            </TableBody></Table>
            {!catalog.some(e => (e.company ?? e.stem).toLowerCase().includes(query.trim().toLowerCase())) && <p className="text-sm text-muted-foreground">No reports match your search.</p>}
          </> },
        ]} />}
    </div>
  )
}
