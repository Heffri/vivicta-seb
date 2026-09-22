import { FileText, Filter, Network, MessageCircle, Minus, Plus, RotateCcw, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { getKb } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader, Workspace } from '@/components/ui/workspace'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { KbEntry } from '@/types'

type Props = { onAsk: (company: string) => void; onOpenReport: (report: KbEntry) => void }
type Point = { x: number; y: number }
const COLORS = ['#3b82f6', '#a855f7', '#14b8a6', '#f59e0b', '#ec4899', '#6366f1', '#84cc16']
const polar = (angle: number, radius: number): Point => ({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })

export function KnowledgeMap({ onAsk, onOpenReport }: Props) {
  const [view, setView] = useState<'map' | 'reports'>('map')
  const [entries, setEntries] = useState<KbEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [sector, setSector] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 })
  const [moved, setMoved] = useState<Record<string, Point>>({})
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ id?: string; last: Point; moved: boolean } | null>(null)
  const suppressClick = useRef(false)

  useEffect(() => {
    let stale = false
    getKb().then(data => { if (!stale) setEntries(data) }).catch((e: Error) => { if (!stale) setError(e.message) })
    return () => { stale = true }
  }, [])
  useEffect(() => {
    const element = svg.current
    if (!element) return
    const wheel = (event: WheelEvent) => {
      event.preventDefault()
      setZoom(z => Math.max(0.4, Math.min(4, z * (event.deltaY > 0 ? 0.9 : 1.1))))
    }
    element.addEventListener('wheel', wheel, { passive: false })
    return () => element.removeEventListener('wheel', wheel)
  }, [entries])

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
  const filtered = companies.filter(([, c]) => (!sector || c.sector === sector) && (!q || c.name.toLocaleLowerCase().includes(q) || c.reports.some(r => r.stem.toLocaleLowerCase().includes(q))))
  const current = filtered.find(([key]) => key === selected) ?? filtered[0]
  const company = current?.[1]
  const colorFor = (s: string) => COLORS[sectors.indexOf(s) % COLORS.length]
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); setMoved({}) }

  // Fixed radial clusters keep the map stable when selecting a company. Dragging adjusts only
  // display positions; edges represent recorded sector membership and report ownership.
  const positions: Record<string, Point> = { root: { x: 0, y: 0 } }
  sectors.forEach((s, i) => {
    const angle = -Math.PI / 2 + i * 2 * Math.PI / sectors.length
    positions[`sector:${s}`] = polar(angle, sectors.length === 1 ? 150 : 240)
    const members = companies.filter(([, c]) => c.sector === s)
    members.forEach(([key], j) => {
      const spread = Math.min(1.4, 2 * Math.PI / sectors.length * 0.85)
      positions[key] = polar(angle + ((j + 0.5) / members.length - 0.5) * spread, 365 + (j % 3) * 48)
    })
  })
  Object.assign(positions, moved)
  if (current) company?.reports.forEach((report, i) => {
    const offset = polar(Math.PI / 4 + i * 2 * Math.PI / company.reports.length, 140)
    positions[`page:${report.stem}`] = moved[`page:${report.stem}`] ?? { x: positions[current[0]].x + offset.x, y: positions[current[0]].y + offset.y }
  })
  const point = (clientX: number, clientY: number) => {
    const matrix = svg.current?.getScreenCTM()?.inverse()
    return matrix ? new DOMPoint(clientX, clientY).matrixTransform(matrix) : { x: clientX, y: clientY }
  }
  const node = (id: string, label: string, caption: string, radius: number, color: string, active: boolean, activate: () => void, showLabel = true) => {
    const p = positions[id]
    return <g key={id} data-node-id={id} role="button" tabIndex={0} aria-label={label} aria-pressed={active}
      transform={`translate(${p.x} ${p.y})`} className="cursor-pointer outline-none [&:focus-visible>circle]:stroke-foreground [&:focus-visible>circle]:stroke-[4px]"
      onPointerEnter={() => setHovered(id)} onPointerLeave={() => setHovered(null)}
      onClick={() => { if (!suppressClick.current) activate() }}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate() } }}>
      <title>{label}</title>
      <circle r={radius + 9} fill="transparent" />
      {active && <circle r={radius + 6} fill="none" stroke={color} strokeOpacity="0.35" strokeWidth="3" />}
      <circle r={radius} fill={color} stroke="var(--background)" strokeWidth="2" />
      {(showLabel || hovered === id || active) && <text y={radius + 20} textAnchor="middle" fill="var(--foreground)" stroke="var(--background)" strokeWidth="4" paintOrder="stroke" fontSize="20" fontWeight={active ? 600 : 400} className="pointer-events-none select-none">{caption.length > 28 ? caption.slice(0, 26) + '…' : caption}</text>}
    </g>
  }
  const edge = (from: string, to: string, color: string, selectedEdge = false) => <line key={`${from}-${to}`} x1={positions[from].x} y1={positions[from].y} x2={positions[to].x} y2={positions[to].y} stroke={color} strokeOpacity={selectedEdge ? 0.7 : 0.2} strokeWidth={selectedEdge ? 2 : 1} />

  return <div className="space-y-5">
    <PageHeader eyebrow="Companies" title="Company map" description="Explore sectors and companies, then open their saved reports." />
    {error && <ErrorBlock>{error}</ErrorBlock>}
    {!entries && !error && <LoadingLine>Mapping your stored reports…</LoadingLine>}
    {entries?.length === 0 && <p>Your map starts with a report. Extract or index one to get started.</p>}
    {!!entries?.length && <>
      <Workspace label="Company workspace" value={view} onChange={setView} toolbar={<div className="flex w-full flex-wrap items-center gap-2">
        <Input type="search" icon={<Search />} aria-label="Search companies or reports" placeholder="Search companies or reports…" value={query} onChange={e => setQuery(e.target.value)} className="min-w-52 flex-1" />
        <Filter className="ml-1 size-3.5 text-muted-foreground" aria-hidden />
        <Select value={sector ?? 'all'} onValueChange={(value) => { setSector(value === 'all' ? null : value); setSelected(null) }} items={Object.fromEntries([['all', 'All sectors'], ...sectors.map((value) => [value, value])])}>
          <SelectTrigger aria-label="Filter companies by sector" className="min-w-32 max-w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sectors</SelectItem>
            {sectors.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={current?.[0] ?? null} onValueChange={(value) => value && setSelected(value)} items={Object.fromEntries(filtered.map(([key, value]) => [key, value.name]))} disabled={!filtered.length}>
          <SelectTrigger aria-label="Select company" className="min-w-44 max-w-full">
            <SelectValue placeholder={filtered.length ? 'Select company' : 'No matches'} />
          </SelectTrigger>
          <SelectContent>
            {filtered.map(([key, value]) => <SelectItem key={key} value={key}>{value.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">{filtered.length} of {companies.length} companies · {entries.length} reports</span>
      </div>} pages={[
        { value: 'map', label: 'Map', icon: Network, content: <>
          <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted-foreground">Drag to explore. Scroll to zoom.</p>{company && <Button variant="outline" size="sm" onClick={() => setView('reports')}>View {company.name} reports</Button>}</div>
          <section aria-label="Interactive company graph" className="relative min-w-0 overflow-hidden rounded-2xl border bg-background">
          <div className="absolute left-3 top-3 z-10 flex items-center gap-1 rounded-lg border bg-card p-1">
            <Button size="icon" variant="ghost" aria-label="Zoom in" onClick={() => setZoom(z => Math.min(4, z * 1.25))}><Plus /></Button>
            <Button size="icon" variant="ghost" aria-label="Zoom out" onClick={() => setZoom(z => Math.max(0.4, z / 1.25))}><Minus /></Button>
            <Button size="icon" variant="ghost" aria-label="Reset graph view" onClick={reset}><RotateCcw /></Button>
            <span className="px-2 text-xs tabular-nums" aria-live="polite">{Math.round(zoom * 100)}%</span>
          </div>
          <svg ref={svg} viewBox="-600 -550 1200 1100" className="h-[65vh] min-h-96 w-full touch-none select-none" aria-label="Sectors connected to companies and their reports" role="group"
            onPointerDown={e => {
              if (e.button !== 0) return
              const id = (e.target as Element).closest('[data-node-id]')?.getAttribute('data-node-id') ?? undefined
              drag.current = { id, last: point(e.clientX, e.clientY), moved: false }
              suppressClick.current = false
            }}
            onPointerMove={e => {
              const d = drag.current
              if (!d) return
              const next = point(e.clientX, e.clientY), dx = next.x - d.last.x, dy = next.y - d.last.y
              if (Math.abs(dx) + Math.abs(dy) < 2 && !d.moved) return
              if (!d.moved) e.currentTarget.setPointerCapture(e.pointerId)
              d.moved = true; d.last = next
              if (d.id) { const id = d.id; setMoved(old => ({ ...old, [id]: { x: (old[id] ?? positions[id]).x + dx / zoom, y: (old[id] ?? positions[id]).y + dy / zoom } })) }
              else setPan(old => ({ x: old.x + dx, y: old.y + dy }))
            }}
            onPointerUp={e => { suppressClick.current = drag.current?.moved ?? false; drag.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId) }}
            onPointerCancel={() => { drag.current = null }}>
            <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {sectors.map(s => edge('root', `sector:${s}`, colorFor(s), sector === s))}
              {filtered.map(([key, c]) => edge(`sector:${c.sector}`, key, colorFor(c.sector), current?.[0] === key))}
              {current && company?.reports.map(r => edge(current[0], `page:${r.stem}`, colorFor(company.sector), true))}
              {node('root', 'All knowledge', 'All knowledge', 18, 'var(--primary)', false, () => { setSector(null); setQuery(''); reset() })}
              {sectors.map(s => node(`sector:${s}`, `${s} · ${companies.filter(([, c]) => c.sector === s).length} companies`, s, 13, colorFor(s), sector === s, () => { setSector(sector === s ? null : s); setSelected(null) }))}
              {filtered.map(([key, c]) => node(key, `${c.name} ${c.sector} ${c.reports.length} reports`, c.name, current?.[0] === key ? 10 : 6, colorFor(c.sector), current?.[0] === key, () => setSelected(key), filtered.length <= 25 || zoom > 1.5 || !!q))}
              {company?.reports.map(r => node(`page:${r.stem}`, `Open ${company.name} ${r.fiscal_year ?? 'undated'} report`, `${r.fiscal_year ?? 'Undated'} report`, 5, 'var(--muted-foreground)', false, () => onOpenReport(r)))}
            </g>
          </svg>
          <p className="px-4 pb-4 text-xs text-muted-foreground">Lines show recorded sector membership and report ownership, not business relationships. Select a company to reveal its reports.</p>
          {!filtered.length && <p role="status" className="absolute inset-x-0 bottom-16 text-center text-sm">No matching companies. Clear the search or choose another sector.</p>}
        </section>
        </> },
        { value: 'reports', label: 'Company reports', icon: FileText, count: company?.reports.length, content: company ? <aside aria-label="Company reports" className="min-w-0 space-y-5">
          <p className="text-xs uppercase text-muted-foreground">{company.sector}</p><h2 className="mt-2 break-words text-xl font-semibold">{company.name}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{company.reports.length} {company.reports.length === 1 ? 'report' : 'reports'} · {company.reports.reduce((n, r) => n + r.pages, 0).toLocaleString()} stored pages</p>
          {company.company && <Button className="mt-4" onClick={() => onAsk(company.company!)}><MessageCircle />Ask about company</Button>}
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{[...company.reports].sort((a, b) => (b.fiscal_year ?? 0) - (a.fiscal_year ?? 0)).map(report => <article key={report.stem} className="rounded-xl border p-3">
            <h3 className="flex items-center gap-2 text-sm font-medium"><FileText className="size-4" />{report.fiscal_year ?? 'Year unknown'} report</h3>
            <p className="my-2 text-xs text-muted-foreground">{report.pages} pages · {report.pdf_available ? 'PDF available' : 'Saved text only'}</p>
            <Button size="sm" variant="outline" onClick={() => onOpenReport(report)}>Open report</Button>
          </article>)}</div>
        </aside> : <p className="text-sm text-muted-foreground">Select a matching company to view its reports.</p> },
      ]} />
    </>}
  </div>
}
