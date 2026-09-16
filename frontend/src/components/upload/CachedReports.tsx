import { ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { LibraryEntry } from '@/types'
import { Face } from './Face'

type CachedReportsProps = {
  library: LibraryEntry[]
  libraryError: string | null
  selected: Set<string>
  busy: boolean
  onSelectAll: () => void
  onSelectNone: () => void
  onToggleTag: (files: string[]) => void
  onToggleOne: (file: string) => void
}

// Path 2: reports already in data/reports/. Collapsible, open by default: it spent v001
// buried inside a collapsed <details>, and a first-class path shouldn't start hidden;
// the grid scrolls internally (max-h-72) so the face keeps its neighbours' height.
export function CachedReports({
  library,
  libraryError,
  selected,
  busy,
  onSelectAll,
  onSelectNone,
  onToggleTag,
  onToggleOne,
}: CachedReportsProps) {
  const [open, setOpen] = useState(true)
  const tags = [...new Set(library.flatMap((e) => e.tags))].sort()
  const allSelected = (files: string[]) => files.length > 0 && files.every((f) => selected.has(f))

  return (
    <Face
      label="Cached reports"
      hint={libraryError ? undefined : `${library.length}${selected.size > 0 ? ` · ${selected.size} selected` : ''}`}
      actions={
        library.length > 0 && !libraryError ? (
          <button
            type="button"
            aria-expanded={open}
            aria-label={open ? 'Collapse cached reports' : 'Expand cached reports'}
            onClick={() => setOpen(!open)}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </button>
        ) : undefined
      }
    >
      {open &&
        (libraryError ? (
          <p className="text-xs text-muted-foreground">Report cache unavailable ({libraryError}).</p>
        ) : library.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Nothing cached yet — pick a company in Directory search, or drop a PDF.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5">
              <Button size="xs" variant="outline" disabled={busy} onClick={onSelectAll}>
                All
              </Button>
              <Button size="xs" variant="outline" disabled={busy} onClick={onSelectNone}>
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
                    onClick={() => onToggleTag(files)}
                  >
                    {t}
                  </Button>
                )
              })}
            </div>
            <div className="grid max-h-72 gap-2 overflow-y-auto pr-0.5 sm:grid-cols-2 min-[1280px]:grid-cols-1">
              {library.map((e) => (
                <label
                  key={e.file}
                  className={`flex cursor-pointer gap-3 rounded-lg border p-3 text-sm transition-colors hover:bg-muted/40 ${
                    selected.has(e.file) ? 'border-ring bg-primary/10' : 'border-border bg-background/50'
                  } ${busy ? 'pointer-events-none opacity-60' : ''}`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-primary"
                    checked={selected.has(e.file)}
                    disabled={busy}
                    onChange={() => onToggleOne(e.file)}
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
        ))}
    </Face>
  )
}
