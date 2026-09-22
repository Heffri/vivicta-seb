import { Check, Globe, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBlock } from '@/components/ui/state'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Collection } from '@/hooks/useCollection'
import type { SearchTrace } from '@/hooks/useReportSearch'
import type { Candidate, Company, Discovery } from '@/types'
import { Face } from './Face'
import { SearchTracePanel } from './SearchTrace'

type CompanySearchProps = {
  collection: Collection
  query: string
  year: string
  companies: Company[]
  dirError: string | null
  picked: Company[]
  busy: boolean
  canRun: boolean // a section is picked; 'Use this company' runs the extraction straight away
  discovery: Discovery | null // null = nothing searched for this query yet
  discovering: boolean
  trace: SearchTrace | null // v194: the current/last discover or fetch job's progress trail
  onQueryChange: (query: string) => void
  onYearChange: (year: string) => void
  onTogglePick: (company: Company) => void
  onOpenReportedCompany: (company: Company) => void
  onDiscover: (hint?: string) => void
  onUseCandidate: (candidate: Candidate) => void
}

// Path 1: pick listed companies (/fetch pulls the PDF on demand), or Enter/search → /discover resolves
// the typed text to concrete legal entities as cards; the user confirms one before anything downloads.
export function CompanySearch({
  collection,
  query,
  year,
  companies,
  dirError,
  picked,
  busy,
  canRun,
  discovery,
  discovering,
  trace,
  onQueryChange,
  onYearChange,
  onTogglePick,
  onOpenReportedCompany,
  onDiscover,
  onUseCandidate,
}: CompanySearchProps) {
  const [hint, setHint] = useState('')
  const [refining, setRefining] = useState(false) // "None of these" opens the hint input; empty results open it too
  const canSearch = query.trim().length > 0 && !busy && !discovering
  const locked = busy || discovering // query/year frozen while /discover runs, so a late reply never lands under a new query or year
  useEffect(() => { if (!discovery) { setRefining(false); setHint('') } }, [discovery])
  const refine = () => hint.trim() && onDiscover(hint.trim())
  const identity = (c: Candidate) =>
    [c.ticker && (c.exchange ? `${c.exchange}: ${c.ticker}` : c.ticker), c.country, c.fiscal_year_end && `FY ends ${c.fiscal_year_end}`]
      .filter(Boolean)
      .join(' · ')
  return (
    <Face label="Find a company" hint={collection === 'all' ? 'Local matches below · AI search works worldwide' : collection === 'midcap' ? 'SEB Mid Cap matches below · AI search works worldwide' : 'Wallenberg matches below · AI search works worldwide'}>
      <div className="flex gap-2">
        <Input
          id="company-q"
          type="search"
          icon={<Search />}
          value={query}
          disabled={locked}
          onChange={(e) => {
            setRefining(false)
            setHint('')
            onQueryChange(e.target.value)
          }}
          onKeyDown={(e) => e.key === 'Enter' && canSearch && onDiscover()}
          placeholder="Any company… e.g. Sandvik, Siemens, Toyota"
          aria-label="Search companies"
          maxLength={100}
        />
        <Select
          value={year}
          onValueChange={(v) => v && onYearChange(v)}
          items={{ 2025: '2025', 2024: '2024', 2023: '2023' }}
          disabled={locked}
        >
          <SelectTrigger aria-label="Fiscal year" className="w-24 shrink-0">
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
        <Button variant="outline" disabled={!canSearch} onClick={() => onDiscover()}>
          <Globe className="size-3.5" />
          Search
        </Button>
      </div>

      {dirError !== null ? (
        <ErrorBlock className="px-3 py-2 text-xs">Company directory unavailable{dirError && ` (${dirError})`}.</ErrorBlock>
      ) : (
        <ul className="max-h-64 min-[1280px]:max-h-80 divide-y divide-border overflow-y-auto rounded-lg border border-border bg-background/50 text-sm">
          {companies.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No local matches. Press Enter for AI search.</li>}
          {companies.map((c) => {
            const on = picked.some((p) => p.name === c.name)
            const privateHolding = c.no_standalone_report === true
            const reportLabel = privateHolding && c.reports_in && c.collection_group
              ? `Private company — reported inside ${c.reports_in}'s annual report (${c.collection_group})`
              : null
            return (
              <li key={c.name}>
                <button
                  type="button"
                  disabled={busy || (privateHolding && !c.report_stem)}
                  aria-pressed={on}
                  aria-label={privateHolding ? `Open ${c.reports_in} report for ${c.name}` : undefined}
                  title={privateHolding && !c.report_stem ? `${c.reports_in}'s parent report is not saved locally` : undefined}
                  onClick={() => privateHolding ? onOpenReportedCompany(c) : onTogglePick(c)}
                  className={`flex w-full flex-wrap items-center gap-1.5 px-3 py-1.5 text-left transition-colors hover:bg-muted/50 disabled:opacity-60 ${
                    on ? 'bg-primary/10' : ''
                  }`}
                >
                  {on && <Check className="size-3.5 shrink-0 text-primary" />}
                  <span className="font-medium">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.ticker}</span>
                  {c.sector && <span className="text-xs text-muted-foreground">· {c.sector}</span>}
                  {reportLabel && <span className="basis-full text-xs text-muted-foreground">{reportLabel}</span>}
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
                onClick={() => onTogglePick(c)}
                className="rounded-sm hover:bg-muted"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {/* Candidate cards: what the query resolved to. Every identity field is model-reported (or the
          saved entry's own name); the PDF is only validated once a card is confirmed. v194: the
          progress trail replaces the old bare "Resolving…" line — it covers discover *and* the fetch
          that follows confirming a candidate, survives switching tabs away and back, and on failure
          keeps the trail up with the reason and a Retry (discover only; a failed fetch already has
          its own Retry in BatchProgress, so this one isn't offered there — see SearchTrace.tsx). */}
      {trace && <SearchTracePanel trace={trace} onRetry={trace.kind === 'discover' ? () => onDiscover() : undefined} />}
      {discovery && !discovering && (
        <div className="space-y-2" aria-label="Company candidates">
          <p className="text-xs text-muted-foreground">
            {discovery.candidates.length === 0 ? `No company found for “${query.trim()}” · ${year}.` : `Which company did you mean? · ${year}`}
          </p>
          {discovery.candidates.map((c) => (
            <Card key={c.legal_name} size="sm">
              <CardHeader>
                <CardTitle>{c.legal_name}</CardTitle>
                {identity(c) && <CardDescription>{identity(c)}</CardDescription>}
                {c.saved && (
                  <CardAction>
                    <Badge variant="secondary">saved</Badge>
                  </CardAction>
                )}
              </CardHeader>
              {(c.document_title || c.reason || c.org_number_or_lei) && (
                <CardContent className="space-y-0.5 text-xs text-muted-foreground">
                  {c.document_title && (
                    <p className="text-foreground">
                      {c.document_title}
                      {c.document_type && ` · ${c.document_type}`}
                    </p>
                  )}
                  {c.org_number_or_lei && <p>{c.org_number_or_lei}</p>}
                  {c.reason && <p>{c.reason}</p>}
                </CardContent>
              )}
              <CardFooter>
                <Button size="sm" disabled={busy || !canRun} title={canRun ? undefined : 'Pick a section first'} onClick={() => onUseCandidate(c)}>
                  Use this company
                </Button>
              </CardFooter>
            </Card>
          ))}
          {discovery.note && <p className="text-xs text-muted-foreground">{discovery.note}</p>}
          {discovery.candidates.length > 0 && !refining && (
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => setRefining(true)}>
              None of these
            </Button>
          )}
          {(refining || discovery.candidates.length === 0) && (
            <div className="flex gap-2">
              <Input
                value={hint}
                disabled={busy}
                onChange={(e) => setHint(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && refine()}
                placeholder="e.g. Swedish bank, ticker, city"
                aria-label="Hint"
                maxLength={300}
              />
              <Button variant="outline" size="sm" disabled={busy || !hint.trim()} onClick={refine}>
                Search again
              </Button>
            </div>
          )}
        </div>
      )}
    </Face>
  )
}
