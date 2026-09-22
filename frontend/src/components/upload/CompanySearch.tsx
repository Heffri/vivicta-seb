import { Check, Filter, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { ErrorBlock } from '@/components/ui/state'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Company } from '@/types'
import { Face } from './Face'

type CompanySearchProps = {
  collection: 'wallenberg' | 'all'
  query: string
  year: string
  companies: Company[]
  dirError: string | null
  picked: Company[]
  busy: boolean
  onQueryChange: (query: string) => void
  onYearChange: (year: string) => void
  onTogglePick: (company: Company) => void
}

// Path 1: pick listed companies; /fetch pulls the PDF on demand.
export function CompanySearch({
  collection,
  query,
  year,
  companies,
  dirError,
  picked,
  busy,
  onQueryChange,
  onYearChange,
  onTogglePick,
}: CompanySearchProps) {
  const [sector, setSector] = useState('all')
  const [availability, setAvailability] = useState('all')
  const sectors = useMemo(
    () => [...new Set(companies.map((company) => company.sector).filter((value): value is string => Boolean(value)))].sort(),
    [companies],
  )
  const filteredCompanies = companies.filter((company) =>
    (sector === 'all' || company.sector === sector) &&
    (availability !== 'cached' || company.cached_years.includes(Number(year))),
  )

  return (
    <Face label="Find a company" hint={collection === 'all' ? 'Local matches below · AI search works worldwide' : 'Wallenberg matches below · AI search works worldwide'}>
      <div className="flex gap-2">
        <Input
          id="company-q"
          type="search"
          icon={<Search />}
          value={query}
          disabled={busy}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Any company… e.g. Sandvik, Siemens, Toyota"
          aria-label="Search companies"
          maxLength={100}
        />
        <Select
          value={year}
          onValueChange={(v) => v && onYearChange(v)}
          items={{ 2025: '2025', 2024: '2024', 2023: '2023' }}
          disabled={busy}
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
      </div>

      <div className="flex flex-wrap items-center gap-2" aria-label="Company filters">
        <Filter className="size-3.5 text-muted-foreground" aria-hidden />
        <Select value={sector} onValueChange={(value) => value && setSector(value)} items={Object.fromEntries([['all', 'All sectors'], ...sectors.map((value) => [value, value])])} disabled={busy}>
          <SelectTrigger aria-label="Filter companies by sector" size="sm" className="min-w-30 max-w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sectors</SelectItem>
            {sectors.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={availability} onValueChange={(value) => value && setAvailability(value)} items={{ all: 'Any availability', cached: `Cached in ${year}` }} disabled={busy}>
          <SelectTrigger aria-label="Filter companies by report availability" size="sm" className="min-w-34">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any availability</SelectItem>
            <SelectItem value="cached">Cached in {year}</SelectItem>
          </SelectContent>
        </Select>
        {(sector !== 'all' || availability !== 'all') && <span className="text-xs text-muted-foreground">{filteredCompanies.length} shown</span>}
      </div>

      {dirError !== null ? (
        <ErrorBlock className="px-3 py-2 text-xs">Company directory unavailable{dirError && ` (${dirError})`}.</ErrorBlock>
      ) : (
        <ul className="max-h-64 min-[1280px]:max-h-80 divide-y divide-border overflow-y-auto rounded-lg border border-border bg-background/50 text-sm">
          {filteredCompanies.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">{companies.length ? 'No companies match these filters.' : 'No local matches. Use AI web search below.'}</li>}
          {filteredCompanies.map((c) => {
            const on = picked.some((p) => p.name === c.name)
            return (
              <li key={c.name}>
                <button
                  type="button"
                  disabled={busy}
                  aria-pressed={on}
                  onClick={() => onTogglePick(c)}
                  className={`flex w-full flex-wrap items-center gap-1.5 px-3 py-1.5 text-left transition-colors hover:bg-muted/50 disabled:opacity-60 ${
                    on ? 'bg-primary/10' : ''
                  }`}
                >
                  {on && <Check className="size-3.5 shrink-0 text-primary" />}
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
                onClick={() => onTogglePick(c)}
                className="rounded-sm hover:bg-muted"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </Face>
  )
}
