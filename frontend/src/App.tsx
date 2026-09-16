import { useEffect, useState } from 'react'
import { type Config, getConfig } from './api'
import { AskPanel } from './components/AskPanel'
import { CompareView } from './components/CompareView'
import { KbView } from './components/KbView'
import { Rail } from './components/shell/Rail'
import { StatusBar } from './components/shell/StatusBar'
import type { Tab } from './components/shell/tabs'
import { Titlebar } from './components/shell/Titlebar'
import { useTone } from './components/shell/useTone'
import { ResultsView } from './components/ResultsView'
import { UploadView } from './components/UploadView'
import type { Result } from './types'

export default function App() {
  const [tone, setTone] = useTone()
  const [tab, setTab] = useState<Tab>('extract')
  const [results, setResults] = useState<Result[]>([])
  const [detail, setDetail] = useState<number | null>(null) // index into results shown on the Results tab
  const [detailPage, setDetailPage] = useState<number | null>(null) // page a citation chip asked for, if any
  const [config, setConfig] = useState<Config | null>(null)

  useEffect(() => {
    getConfig().then(setConfig).catch(() => {})
  }, [])

  const done = (rs: Result[]) => {
    setResults(rs)
    setDetail(null)
    setDetailPage(null)
    setTab(rs.length > 1 ? 'compare' : 'results')
  }
  const reset = () => {
    setResults([])
    setDetail(null)
    setTab('extract')
  }

  const shown = results[detail ?? 0]
  const reports = results.flatMap((r) => (r.extraction ? [{ report_id: r.extraction.report_id, label: r.label }] : []))
  const enabled: Record<Tab, boolean> = {
    extract: true,
    results: !!shown?.extraction,
    compare: results.length > 1,
    ask: reports.length > 0,
    kb: true,
  }

  return (
    <div className="glass flex h-screen flex-col overflow-hidden text-foreground">
      <Titlebar subtitle="PDF annual report in → structured, source-linked data out → JSON/CSV for downstream banking systems." />
      <div className="flex min-h-0 flex-1">
        <Rail active={tab} enabled={enabled} compareCount={results.length} onSelect={setTab} tone={tone} onToneChange={setTone} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-6 py-10">
            {tab === 'extract' && <UploadView onDone={done} />}
            {tab === 'results' && shown?.extraction && (
              <ResultsView
                key={shown.extraction.report_id}
                extraction={shown.extraction}
                sectionTitle={shown.sectionTitle}
                onReset={reset}
                onBack={results.length > 1 ? () => setTab('compare') : undefined}
                initialPage={detailPage}
              />
            )}
            {tab === 'compare' && (
              <CompareView
                results={results}
                onSelect={(i, page) => {
                  setDetail(i)
                  setDetailPage(page ?? null)
                  setTab('results')
                }}
                onReset={reset}
              />
            )}
            {tab === 'ask' && (
              <div className="mx-auto max-w-3xl space-y-5">
                <header className="border-b pb-5">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Ask</p>
                  <h1 className="mt-1 text-2xl font-semibold tracking-tight">
                    {reports.length === 1 ? reports[0].label : `${reports.length} reports`}
                  </h1>
                  <p className="mt-1 text-sm text-muted-foreground">Answers cite pages of the loaded reports; citations open the PDF.</p>
                </header>
                <AskPanel reports={reports} />
              </div>
            )}
            {tab === 'kb' && <KbView onOpen={done} />}
          </div>
        </main>
      </div>
      <StatusBar config={config} />
    </div>
  )
}
