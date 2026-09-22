import { useEffect, useState } from 'react'
import { openKbExtraction } from '@/api'
import { ResultsView } from '@/components/ResultsView'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Extraction, KbEntry } from '@/types'

export const statementTitle = (section: string) => ({ debt_maturity: 'Debt maturity', income_statement: 'Consolidated income statement' }[section] ?? section.replaceAll('_', ' '))

export function SavedReportView({ report, onBack, onReset, initialSection, initialField }: { initialSection?: string; initialField?: string; report: KbEntry; onBack: () => void; onReset: () => void }) {
  const [section, setSection] = useState(initialSection ?? (report.sections.includes('income_statement') ? 'income_statement' : report.sections[0] ?? ''))
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
  const navigation = <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" onClick={onBack}>Back to reports</Button>
      <div className="flex flex-wrap items-center gap-3 text-sm font-medium">
        <span>Statement</span>
        <Select value={section || null} onValueChange={(value) => value && setSection(value)} items={Object.fromEntries([...new Set(['income_statement', 'debt_maturity', ...report.sections])].map((value) => [value, statementTitle(value)]))} disabled={!report.sections.length}>
          <SelectTrigger aria-label="Statement" className="min-w-62 max-w-full">
            <SelectValue placeholder="No saved statements" />
          </SelectTrigger>
          <SelectContent>
            {[...new Set(['income_statement', 'debt_maturity', ...report.sections])].map((value) => (
              <SelectItem key={value} value={value} disabled={!report.sections.includes(value)}>
                {statementTitle(value)}{report.sections.includes(value) ? '' : ' · not extracted'}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  return <div className="space-y-5">
    {!current?.extraction && navigation}
    {!section ? <div className="rounded-xl border bg-card p-6"><h1 className="text-xl font-semibold">{report.company ?? report.stem} · {report.fiscal_year ?? 'Year unknown'}</h1><p className="mt-2 text-muted-foreground">No figures have been extracted yet. Saved report text is available through Ask.</p></div>
      : current?.error ? <ErrorBlock>{current.error}</ErrorBlock>
      : current?.extraction ? <ResultsView navigation={navigation} key={`${report.stem}:${section}`} initialField={initialField} extraction={current.extraction} onUpdated={extraction => setResult({ section, extraction })} sectionTitle={statementTitle(section)} onReset={onReset} />
      : <LoadingLine>Loading {statementTitle(section).toLowerCase()}…</LoadingLine>}
  </div>
}
