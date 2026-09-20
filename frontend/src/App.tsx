import { Cpu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type Config, getConfig } from './api'
import { AskPanel } from './components/AskPanel'
import { CompareView } from './components/CompareView'
import { KbView } from './components/KbView'
import { ResultsView } from './components/ResultsView'
import { UploadView } from './components/UploadView'
import type { Result } from './types'

type Tab = 'extract' | 'results' | 'compare' | 'ask' | 'kb'
const TABS: { id: Tab; label: string }[] = [
  { id: 'extract', label: 'Extract' },
  { id: 'results', label: 'Results' },
  { id: 'compare', label: 'Compare' },
  { id: 'ask', label: 'Ask' },
  { id: 'kb', label: 'Knowledge base' },
]

export default function App() {
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
    <>
      <nav className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
          <span className="text-sm font-semibold tracking-tight" title="PDF in → structured, source-linked data out">
            Annual Report Parser
          </span>
          <ul className="flex flex-wrap gap-1">
            {TABS.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  disabled={!enabled[t.id]}
                  aria-current={tab === t.id ? 'page' : undefined}
                  onClick={() => setTab(t.id)}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors disabled:opacity-40 ${
                    tab === t.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  {t.label}
                  {t.id === 'compare' && results.length > 1 && <span className="ml-1.5 text-xs opacity-70">{results.length}</span>}
                </button>
              </li>
            ))}
          </ul>
          {config && (
            <span className="ml-auto flex items-center gap-1.5 font-mono text-xs text-muted-foreground" title={config.provider === 'codex' ? 'Codex CLI login for extraction and Ask' : config.base_url ?? 'no LLM configured'}>
              <Cpu className="size-3.5" />
              {config.model}
              <span className="opacity-60">· {config.embed_model}</span>
            </span>
          )}
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <div hidden={tab !== 'extract'}><UploadView onDone={done} /></div>
        {tab === 'results' && shown?.extraction && (
          <ResultsView
            key={shown.extraction.report_id}
            extraction={shown.extraction}
            onUpdate={(extraction) => setResults((rs) => rs.map((r, i) => i === (detail ?? 0) ? { ...r, extraction } : r))}
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
      </main>
    </>
  )
}
