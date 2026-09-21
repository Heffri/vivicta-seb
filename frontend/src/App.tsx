import { ReviewQueue } from './components/AnalystWorkbench'
import { useEffect, useState } from 'react'
import { type Config, getConfig } from './api'
import { AskView } from './components/AskView'
import { CompareView } from './components/CompareView'
import { KnowledgeMap } from './components/KnowledgeMap'
import { KbView } from './components/KbView'
import { Rail } from './components/shell/Rail'
import { SkipLink } from './components/shell/SkipLink'
import { StatusBar } from './components/shell/StatusBar'
import type { Tab } from './components/shell/tabs'
import { Titlebar } from './components/shell/Titlebar'
import { useHeadingFocus } from './components/shell/useHeadingFocus'
import { useTone } from './components/shell/useTone'
import { ResultsView } from './components/ResultsView'
import { SettingsView } from './components/SettingsView'
import { UploadView } from './components/UploadView'
import { SavedReportView } from './components/SavedReportView'
import type { KbEntry, Result } from './types'

export default function App() {
  const [tone, setTone] = useTone()
  const [tab, setTab] = useState<Tab>('extract')
  const [savedReport, setSavedReport] = useState<KbEntry | null>(null)
  const [reportOrigin, setReportOrigin] = useState<'kb' | 'map' | 'review'>('kb')
  const [reviewTarget, setReviewTarget] = useState<{ section?: string; key?: string }>({})
  const [results, setResults] = useState<Result[]>([])
  const [detail, setDetail] = useState<number | null>(null) // index into results shown on the Results tab
  const [detailPage, setDetailPage] = useState<number | null>(null) // page a citation chip asked for, if any
  const [askCompany, setAskCompany] = useState<string | undefined>()
  const [config, setConfig] = useState<Config | null>(null)

  useEffect(() => {
    getConfig().then(setConfig).catch(() => {})
  }, [])

  useHeadingFocus(tab)

  const done = (rs: Result[]) => {
    setSavedReport(null)
    setResults(rs)
    setDetail(null)
    setDetailPage(null)
    setTab(rs.length > 1 ? 'compare' : 'results')
  }
  const reset = () => {
    setSavedReport(null)
    setResults([])
    setDetail(null)
    setTab('extract')
  }

  const shown = results[detail ?? 0]
  const enabled: Record<Tab, boolean> = {
    extract: true,
    results: !!savedReport || !!shown?.extraction,
    compare: results.length > 1,
    ask: true,
    kb: true,
    review: true,
    map: true,
    settings: true,
  }

  return (
    <div className="glass fixed inset-0 flex flex-col overflow-hidden text-foreground">
      <SkipLink />
      <Titlebar subtitle="PDF annual report in → structured, source-linked data out → JSON/CSV for downstream banking systems." />
      <div className="flex min-h-0 flex-1">
        <Rail active={tab} enabled={enabled} compareCount={results.length} onSelect={(next) => { setAskCompany(undefined); setTab(next) }} tone={tone} onToneChange={setTone} />
        <main id="content" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-6 py-10">
            {tab === 'extract' && <UploadView onDone={done} />}
            {tab === 'results' && savedReport && <SavedReportView initialSection={reportOrigin === 'review' ? reviewTarget.section : undefined} initialField={reportOrigin === 'review' ? reviewTarget.key : undefined} key={`${savedReport.stem}:${reviewTarget.section}:${reviewTarget.key}`} report={savedReport} onBack={() => setTab(reportOrigin)} onReset={reset} />}
            {tab === 'results' && !savedReport && shown?.extraction && (
              <ResultsView
                key={shown.extraction.report_id}
                extraction={shown.extraction}
                onUpdated={extraction => setResults(previous => previous.map((result, i) => i === (detail ?? 0) ? { ...result, extraction } : result))}
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
                  setSavedReport(null)
                  setDetail(i)
                  setDetailPage(page ?? null)
                  setTab('results')
                }}
                onReset={reset}
              />
            )}
            {tab === 'ask' && <AskView key={askCompany ?? 'global'} initialCompany={askCompany} />}
            {tab === 'review' && <ReviewQueue onOpen={(report, section, key) => { setReviewTarget({ section, key }); setSavedReport(report); setReportOrigin('review'); setTab('results') }} />}
            {tab === 'kb' && <KbView onOpen={done} onOpenReport={report => { setSavedReport(report); setReportOrigin('kb'); setTab('results') }} />}
            {tab === 'map' && <KnowledgeMap onOpenReport={report => { setSavedReport(report); setReportOrigin('map'); setTab('results') }} onAsk={(company) => { setAskCompany(company); setTab('ask') }} />}
            {/* v065: a Save restarts the backend, leaving this mount-time `config` stale until
                relaunch (v061 §6-5) -- SettingsView hands the post-restart config back so StatusBar
                follows the save without one. */}
            {tab === 'settings' && <SettingsView onConfigChange={setConfig} />}
          </div>
        </main>
      </div>
      <StatusBar config={config} />
    </div>
  )
}
