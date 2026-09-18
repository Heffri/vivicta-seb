import { useEffect, useState } from 'react'
import { openKbExtraction } from '@/api'
import { ResultsView } from '@/components/ResultsView'
import { Button } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Extraction, KbEntry } from '@/types'

export const statementTitle = (section: string) => ({ debt_maturity: 'Debt maturity', income_statement: 'Consolidated income statement' }[section] ?? section.replaceAll('_', ' '))

export function SavedReportView({ report, onBack, onReset }: { report: KbEntry; onBack: () => void; onReset: () => void }) {
  const [section, setSection] = useState(report.sections.includes('income_statement') ? 'income_statement' : report.sections[0] ?? '')
  const [result, setResult] = useState<{ section: string; extraction?: Extraction; error?: string } | null>(null)
  useEffect(() => {
    if (!section) return
    let stale = false
    openKbExtraction(report.stem, section)
      .then(extraction => { if (!stale) setResult({ section, extraction }) })
      .catch((error: Error) => { if (!stale) setResult({ section, error: error.message }) })
    return () => { stale = true }
  }, [report.stem, section])
  const current = result?.section === section ? result : null
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-4">
      <Button variant="outline" onClick={onBack}>Back to reports</Button>
      <label className="flex flex-wrap items-center gap-3 text-sm font-medium">
        Statement
        <select aria-label="Statement" value={section} onChange={e => setSection(e.target.value)} disabled={!report.sections.length} className="h-10 max-w-full rounded-lg border border-input bg-background px-3 text-foreground">
          {!section && <option value="">No saved statements</option>}
          {[...new Set(['income_statement', 'debt_maturity', ...report.sections])].map(s => <option key={s} value={s} disabled={!report.sections.includes(s)}>{statementTitle(s)}{report.sections.includes(s) ? '' : ' (not extracted)'}</option>)}
        </select>
      </label>
    </div>
    {!section ? <div className="rounded-xl border bg-card p-6"><h1 className="text-xl font-semibold">{report.company ?? report.stem} · {report.fiscal_year ?? 'Year unknown'}</h1><p className="mt-2 text-muted-foreground">No figures have been extracted yet. Saved report text is available through Ask.</p></div>
      : current?.error ? <ErrorBlock>{current.error}</ErrorBlock>
      : current?.extraction ? <ResultsView key={`${report.stem}:${section}`} extraction={current.extraction} onUpdated={extraction => setResult({ section, extraction })} sectionTitle={statementTitle(section)} onReset={onReset} />
      : <LoadingLine>Loading {statementTitle(section).toLowerCase()}…</LoadingLine>}
  </div>
}
