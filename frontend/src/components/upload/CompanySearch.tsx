import { Check, Search, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Company } from '@/types'
import { Face } from './Face'
import { Input } from './Input'

type CompanySearchProps = {
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
  return (
    <Face label="Directory search" hint="fetches the PDF on demand">
      <div className="flex gap-2">
        <Input
          id="company-q"
          type="search"
          icon={<Search />}
          value={query}
          disabled={busy}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search listed companies… e.g. Sandvik"
          aria-label="Search listed companies"
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

      {dirError !== null ? (
        <p className="text-xs text-muted-foreground">Company directory unavailable{dirError && ` (${dirError})`}.</p>
      ) : (
        <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border bg-background/50 text-sm">
          {companies.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No matches.</li>}
          {companies.map((c) => {
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
