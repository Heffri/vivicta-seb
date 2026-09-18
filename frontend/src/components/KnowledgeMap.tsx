import { Building2, ChevronRight, FileText, GitBranch, MessageCircle, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getKb, getSchemas, openKbExtraction } from '@/api'
import { Button } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { KbEntry, Result, Schema } from '@/types'

type Props = { onAsk: (company: string) => void; onOpen: (results: Result[]) => void }
const countLabel = (count: number, singular: string, plural = `${singular}s`) => `${count} ${count === 1 ? singular : plural}`
const COLORS = ['#3b82f6', '#a855f7', '#14b8a6', '#f59e0b', '#ec4899', '#6366f1', '#84cc16']
const nodeClass = 'rounded-xl border bg-background p-4 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring'

export function KnowledgeMap({ onAsk, onOpen }: Props) {
  const [entries, setEntries] = useState<KbEntry[] | null>(null)
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [sector, setSector] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getKb().then((data) => { if (active) setEntries(data) }).catch((e: Error) => { if (active) setError(e.message) })
    getSchemas().then((data) => { if (active) setSchemas(data) }).catch(() => {})
    return () => { active = false }
  }, [])

  // Unnamed reports stay separate: a missing company name does not establish a relationship.
  const groups = new Map<string, { name: string; company: string | null; sector: string; reports: KbEntry[] }>()
  for (const report of entries ?? []) {
    const company = report.company?.trim() || null
    const key = company ? `company:${company.toLocaleLowerCase()}` : `report:${report.stem}`
    const existing = groups.get(key)
    if (existing) {
      existing.reports.push(report)
      if (existing.sector === 'Unclassified' && report.sector) existing.sector = report.sector
    } else groups.set(key, { name: company ?? report.stem, company, sector: report.sector || 'Unclassified', reports: [report] })
  }
  const companies = [...groups.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name))
  const sectors = [...new Set(companies.map(([, c]) => c.sector))].sort()
  const q = query.trim().toLocaleLowerCase()
  const filtered = companies.filter(([, c]) => (!sector || c.sector === sector) && (!q || c.name.toLocaleLowerCase().includes(q) || c.reports.some((r) => r.stem.toLocaleLowerCase().includes(q))))
  const current = filtered.find(([key]) => key === selected) ?? filtered[0]
  const company = current?.[1]
  const companyCount = companies.filter(([, c]) => c.company !== null).length
  const unnamedCount = companies.length - companyCount
  const colorFor = (s: string) => COLORS[sectors.indexOf(s) % COLORS.length]
  const sectionTitle = (name: string) => schemas.find((s) => s.name === name)?.title ?? name.replaceAll('_', ' ')

  const open = async (report: KbEntry, section: string) => {
    setBusy(`${report.stem}:${section}`)
    setError(null)
    try {
      const extraction = await openKbExtraction(report.stem, section)
      onOpen([{ label: report.company ?? report.stem, sectionTitle: sectionTitle(section), extraction }])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Explore your reports</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Knowledge map</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Follow a sector to its companies, then explore the reports behind the numbers.</p>
        </div>
        {entries && <p className="text-sm text-muted-foreground">{countLabel(companyCount, 'company', 'companies')} · {countLabel(entries.length, 'report')} · {entries.reduce((n, e) => n + e.pages, 0).toLocaleString()} pages</p>}
      </header>
      {error && <ErrorBlock>{error}</ErrorBlock>}
      {!entries && !error && <LoadingLine>Mapping your stored reports…</LoadingLine>}
      {!entries && error && <Button variant="outline" onClick={() => { setError(null); getKb().then(setEntries).catch((e: Error) => setError(e.message)) }}>Try again</Button>}
      {entries?.length === 0 && <div className="rounded-2xl border bg-background p-10 text-center"><GitBranch className="mx-auto mb-3 size-8 text-muted-foreground" /><h2 className="font-medium">Your map starts with a report</h2><p className="mt-2 text-sm text-muted-foreground">Extract or index a report to add its company and source material here.</p></div>}
      {entries && entries.length > 0 && <>
        <section aria-label="Sector map" className="rounded-2xl border bg-background/70 p-5 sm:p-6">
          <div className="flex justify-center">
            <button type="button" aria-pressed={sector === null} onClick={() => setSector(null)} className={`${nodeClass} flex items-center gap-3 border-primary/40 shadow-sm`}>
              <span className="rounded-lg bg-primary/10 p-2 text-foreground"><GitBranch className="size-5" aria-hidden /></span>
              <span><span className="block font-semibold">All knowledge</span><span className="block text-xs text-muted-foreground">{countLabel(sectors.length, 'sector group')} · {countLabel(companyCount, 'company', 'companies')}{unnamedCount ? ` · ${countLabel(unnamedCount, 'unnamed report')}` : ''}</span></span>
            </button>
          </div>
          <div aria-hidden className="mx-auto h-7 w-px bg-border" />
          <div className="relative grid gap-3 border-t pt-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sectors.map((name) => {
              const members = companies.filter(([, c]) => c.sector === name)
              return <button key={name} type="button" aria-pressed={sector === name} onClick={() => { setSector(sector === name ? null : name); setSelected(null) }} className={`${nodeClass} relative border-l-4 ${sector === name ? 'ring-2 ring-ring' : ''}`} style={{ borderLeftColor: colorFor(name) }}>
                <span aria-hidden className="absolute -top-5 left-1/2 h-5 w-px bg-border" />
                <span className="flex items-start justify-between gap-2"><span className="font-medium">{name}</span><ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden /></span>
                <span className="mt-1 block text-xs text-muted-foreground">{countLabel(members.filter(([, c]) => c.company).length, 'company', 'companies')} · {countLabel(members.reduce((n, [, c]) => n + c.reports.length, 0), 'report')}</span>
              </button>
            })}
          </div>
          <p className="mt-4 text-xs text-muted-foreground">Branches show sector membership and report ownership. Unclassified means no sector is recorded.</p>
        </section>
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.75fr)]">
          <section aria-label="Companies" className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">{sector ?? 'All companies'} <span className="font-normal text-muted-foreground">({filtered.length})</span></h2>
              {sector && <Button variant="ghost" size="sm" onClick={() => setSector(null)}>Show all sectors</Button>}
            </div>
            <label className="relative block">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input type="search" aria-label="Search companies or reports" placeholder="Find a company or report…" value={query} onChange={(e) => setQuery(e.target.value)} className="h-10 w-full rounded-xl border border-input bg-background pr-3 pl-10 text-sm focus-visible:outline-2 focus-visible:outline-ring" />
            </label>
            <div className="grid max-h-[65vh] gap-3 overflow-y-auto p-1 sm:grid-cols-2">
              {filtered.map(([key, c]) => <button key={key} type="button" aria-pressed={current?.[0] === key} onClick={() => setSelected(key)} className={`${nodeClass} border-t-2 ${current?.[0] === key ? 'ring-2 ring-ring' : ''}`} style={{ borderTopColor: colorFor(c.sector) }}>
                <Building2 className="mb-3 size-4 text-muted-foreground" aria-hidden />
                <span className="block break-words font-medium">{c.name}</span>
                {!c.company && <span className="block text-xs text-muted-foreground">Company not identified</span>}
                <span className="mt-1 block text-xs text-muted-foreground">{c.sector}</span>
                <span className="mt-3 block text-xs text-muted-foreground">{countLabel(c.reports.length, 'report')} · {[...new Set(c.reports.map((r) => r.fiscal_year ?? 'Year unknown'))].sort().join(', ')}</span>
              </button>)}
            </div>
            {filtered.length === 0 && <p className="rounded-xl border p-6 text-sm text-muted-foreground">No matching companies in {sector ?? 'your reports'}. Clear the search or choose another sector.</p>}
          </section>
          {company && <aside aria-label="Company reports" className="min-w-0 rounded-2xl border bg-background p-5 lg:sticky lg:top-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{company.sector}</p>
            <h2 className="mt-2 break-words text-xl font-semibold">{company.name}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{countLabel(company.reports.length, 'report')} · {company.reports.reduce((n, r) => n + r.pages, 0).toLocaleString()} stored pages</p>
            {company.company && <Button className="mt-4" onClick={() => onAsk(company.company!)}><MessageCircle aria-hidden />Ask about company</Button>}
            <div className="mt-6 space-y-4 border-l pl-4">
              {[...company.reports].sort((a, b) => (b.fiscal_year ?? 0) - (a.fiscal_year ?? 0)).map((report) => <article key={report.stem} className="relative rounded-xl border bg-muted/30 p-4">
                <span aria-hidden className="absolute top-6 -left-4 w-4 border-t" />
                <h3 className="flex items-center gap-2 font-medium"><FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />{report.fiscal_year ?? 'Year unknown'} report</h3>
                <p className="mt-3 text-xs text-muted-foreground">{report.pages.toLocaleString()} pages · {report.pdf_available ? 'PDF available' : 'Saved text only'}</p>
                {!report.pdf_available && <p className="mt-1 text-xs text-muted-foreground">The original PDF is not cached. Saved figures are still available.</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {report.sections.map((section) => <Button key={section} variant="outline" size="sm" className="h-auto min-h-7 whitespace-normal py-1 text-left" disabled={busy !== null} onClick={() => open(report, section)}>{busy === `${report.stem}:${section}` ? 'Opening…' : sectionTitle(section)}<ChevronRight aria-hidden /></Button>)}
                  {report.sections.length === 0 && <p className="text-xs text-muted-foreground">No saved figures yet. Ask a question to explore the stored report text.</p>}
                </div>
              </article>)}
            </div>
          </aside>}
        </div>
      </>}
    </div>
  )
}
