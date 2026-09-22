import { ArrowUp, BookOpen, Copy, RotateCcw, Square, TriangleAlert } from 'lucide-react'
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { ask, getKbPage, indexReport, pdfUrl } from '@/api'
import { AnswerText } from '@/components/ask/AnswerText'
import { companyMentions, mentionAtCursor } from '@/components/ask/companyMentions'
import { ThinkingOrb } from '@/components/ask/ThinkingOrb'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Answer, KbEntry } from '@/types'

type Props = {
  reports: { report_id: string; label: string }[]
  catalog?: KbEntry[] // present only for the global saved-report view
  initialCompany?: string
  onCitation?: (reportId: string, page: number) => void
}
type Turn = { id: number; question: string; scope: string; answer?: Answer; error?: string; pending?: boolean; stopped?: boolean }
type Source = { title: string; text?: string; error?: string }
const EXAMPLES = [
  { title: 'Understand the figures', question: 'Explain the key figures in plain language', hint: 'Revenue, earnings, and the story behind them' },
  { title: 'Compare periods', question: 'What changed from the previous year?', hint: 'Find changes across saved annual reports' },
  { title: 'Explore financial risk', question: 'What financial risks does the report highlight?', hint: 'Debt maturities, liquidity, and uncertainty' },
]

export function AskPanel({ reports, catalog, initialCompany, onCitation }: Props) {
  const [question, setQuestion] = useState(initialCompany ? `@${initialCompany} ` : '')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [cursor, setCursor] = useState(initialCompany ? initialCompany.length + 2 : 0)
  const [active, setActive] = useState(0)
  const [dismissed, setDismissed] = useState(!!initialCompany)
  const [source, setSource] = useState<Source | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [copyStatus, setCopyStatus] = useState<{ id: number; message: string } | null>(null)
  const currentRequest = useRef<AbortController | null>(null)
  const nextTurn = useRef(0)
  const sourcePanel = useRef<HTMLElement>(null)
  const sourceRequest = useRef(0)
  const input = useRef<HTMLTextAreaElement>(null)
  const pendingSelection = useRef<number | null>(null)
  const inputId = useId()
  const global = catalog !== undefined
  const companies = [...new Set((catalog ?? []).map((entry) => entry.company).filter((name): name is string => !!name))].sort()
  const mentions = companyMentions(question, companies)
  const selected = (catalog ?? []).filter((entry) => entry.company && mentions.selected.includes(entry.company))
  const scope = global ? mentions.unknown.length ? 'Waiting for a valid company mention' : mentions.selected.length ? `${mentions.selected.join(', ')} · text from ${selected.length} reports` : `Saved text from ${catalog.length} reports` : reports.map((report) => report.label).join(', ')
  const blocked = global ? catalog.length === 0 || mentions.unknown.length > 0 : reports.length === 0
  const mention = global ? mentionAtCursor(question, cursor) : null
  const suggestions = mention ? companies.filter((name) => name.toLocaleLowerCase().startsWith(mention.query.toLocaleLowerCase())).slice(0, 8) : []
  const popup = !!mention && !dismissed && suggestions.length > 0
  const idsKey = reports.map((report) => report.report_id).join()

  useEffect(() => () => { currentRequest.current?.abort(); currentRequest.current = null; sourceRequest.current++ }, [])
  useEffect(() => {
    if (!busy) return
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [busy])
  useEffect(() => { if (source) sourcePanel.current?.scrollIntoView({ block: 'nearest' }) }, [source])

  useEffect(() => {
    if (global) return // Global queries index on demand, never warm the whole catalog.
    let alive = true
    ;(async () => {
      for (const id of idsKey ? idsKey.split(',') : []) {
        if (!alive) return
        await indexReport(id).catch(() => undefined)
      }
    })()
    return () => { alive = false }
  }, [idsKey, global])

  const submit = async (q = question.trim()) => {
    if (!q || currentRequest.current || (global ? catalog.length === 0 : reports.length === 0)) return
    const parsed = global ? companyMentions(q, companies) : null
    if (parsed?.unknown.length) return
    const stems = parsed?.selected.length ? catalog!.filter((entry) => entry.company && parsed.selected.includes(entry.company)).map((entry) => entry.stem) : global ? catalog!.map((entry) => entry.stem) : undefined
    const requestScope = global ? parsed?.selected.length ? `${parsed.selected.join(', ')} · text from ${stems!.length} reports` : `Saved text from ${catalog!.length} reports` : scope
    const controller = new AbortController()
    currentRequest.current = controller
    const id = ++nextTurn.current
    setTurns(previous => [...previous, { id, question: q, scope: requestScope, pending: true }])
    setElapsed(0); setBusy(true)
    setDismissed(true)
    setQuestion(global && parsed?.selected.length ? parsed.selected.map(name => `@${name}`).join(' ') + ' ' : '')
    try {
      const answer = await ask(q, global ? undefined : reports.map((report) => report.report_id), stems, controller.signal)
      if (currentRequest.current !== controller) return
      setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, pending: false, answer } : turn))
    } catch (error) {
      if (currentRequest.current !== controller) return
      setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, pending: false,
        ...(controller.signal.aborted ? { stopped: true } : { error: (error as Error).message }) } : turn))
    } finally { if (currentRequest.current === controller) { currentRequest.current = null; setBusy(false) } }
  }

  useLayoutEffect(() => {
    const position = pendingSelection.current
    if (position === null) return
    pendingSelection.current = null
    input.current?.focus()
    input.current?.setSelectionRange(position, position)
  }, [question])

  const choose = (name: string) => {
    if (!mention) return
    const text = `${question.slice(0, mention.start)}@${name} ${question.slice(cursor)}`
    const position = mention.start + name.length + 2
    pendingSelection.current = position
    setQuestion(text)
    setCursor(position)
    setDismissed(true)

  }

  const openCitation = async (answer: Answer, reportId: string, page: number) => {
    if (onCitation) { onCitation(reportId, page); return }
    const citation = answer.citations.find((item) => item.report_id === reportId && item.page === page)
    const entry = catalog?.find((item) => item.report_id === reportId || item.stem === citation?.stem)
    if (entry?.pdf_available || !global && !citation?.stem) {
      window.open(pdfUrl(reportId, page), '_blank', 'noopener')
      return
    }
    const request = ++sourceRequest.current
    const title = `${citation?.company ?? entry?.company ?? 'Source'}${citation?.fiscal_year ? ` · FY${citation.fiscal_year}` : ''} · page ${page}`
    const stem = entry?.stem ?? citation?.stem
    setSource({ title, text: stem ? undefined : citation?.quote, error: stem || citation?.quote ? undefined : 'No saved source text is available.' })
    if (!stem) return
    try {
      const saved = await getKbPage(stem, page)
      if (request === sourceRequest.current) setSource({ title, text: saved.text || citation?.quote || 'This page has no saved text.' })
    } catch (error) {
      if (request === sourceRequest.current) setSource({ title, text: citation?.quote, error: `Could not load the saved page: ${(error as Error).message}` })
    }
  }

  return (
    <section aria-label={global ? 'Ask saved reports' : 'Ask the reports'} className="space-y-6">
        {!turns.length && <div className={`flex flex-col items-center text-center ${global ? 'py-7' : 'py-2'}`}>
          <BookOpen className="size-8 text-muted-foreground" aria-hidden />
          <h2 className="mt-4 text-xl font-medium tracking-tight">What would you like to understand?</h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">{global ? `Search saved report text across ${companies.length} companies, or mention a company to narrow your question. Original PDFs are only available where downloaded.` : 'Ask about these statements and inspect the source behind each answer.'}</p>
        </div>}
        {!!turns.length && <div className="flex items-center justify-between gap-3"><h2 className="text-sm font-medium">Questions & answers</h2><Button variant="ghost" size="sm" disabled={busy} onClick={() => { setTurns([]); setQuestion(''); setSource(null); setCopyStatus(null); sourceRequest.current++; input.current?.focus() }}><RotateCcw />New conversation</Button></div>}
        {turns.length > 0 && <ol aria-label="Questions and answers" className="space-y-7">{turns.map(turn => <li key={turn.id} className="space-y-4 text-sm">
          <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-sm border bg-muted/60 px-4 py-3"><p className="whitespace-pre-wrap break-words font-medium leading-relaxed">{turn.question}</p></div>
          <div className="rounded-2xl border bg-card p-5">
          <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground"><BookOpen className="size-3.5" aria-hidden />{turn.scope}</p>
          {turn.pending && <div role="status" className="flex items-center gap-4"><ThinkingOrb thinking className="size-16" /><div><p className="font-medium">Finding a source-backed answer…</p><p className="mt-1 text-xs text-muted-foreground">Searching saved text and preparing a response · {elapsed}s</p>{elapsed >= 30 && <p className="mt-1 text-xs text-muted-foreground">Still working. Larger questions can take a little longer.</p>}</div></div>}
          {(turn.error || turn.stopped) && <div className="space-y-3">{turn.error ? <ErrorBlock>{turn.error}</ErrorBlock> : <p className="text-muted-foreground">Stopped waiting. The model may finish processing in the background.</p>}<Button variant="outline" size="sm" disabled={busy} onClick={() => void submit(turn.question)}><RotateCcw />Retry question</Button></div>}
          {turn.answer && <div className="space-y-4">
            <AnswerText text={turn.answer.answer} citations={turn.answer.citations} onCitation={(id, page) => void openCitation(turn.answer!, id, page)} />
            <div className="border-t pt-3"><p className="mb-2 text-xs font-medium text-muted-foreground">{turn.answer.citations.length ? 'Sources · select a page to inspect the evidence' : 'No verified source citations returned'}</p>
            <div className="flex flex-wrap gap-2">{turn.answer.citations.map((citation, j) => <Badge key={j} variant="outline" render={<button type="button" />} title={citation.quote} className="cursor-pointer hover:bg-accent" onClick={() => void openCitation(turn.answer!, citation.report_id, citation.page)}>
              {citation.company ?? reports.find((report) => report.report_id === citation.report_id)?.label ?? 'Report'} {citation.fiscal_year ? `FY${citation.fiscal_year} · ` : ''}p.{citation.page}
            </Badge>)}</div></div>
            {turn.answer.warnings.map((warning) => <p key={warning} className="flex gap-1.5 text-xs text-warning"><TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden /><span className="break-words">{warning}</span></p>)}
            <div className="flex items-center gap-3"><Button variant="ghost" size="xs" aria-label="Copy answer" onClick={async () => {
              try { await navigator.clipboard.writeText(`${turn.answer!.answer}\n\n${turn.answer!.citations.map(c => `${c.company ?? 'Report'}${c.fiscal_year ? ` FY${c.fiscal_year}` : ''}, p.${c.page}: ${c.quote}`).join('\n')}`); setCopyStatus({ id: turn.id, message: 'Copied' }) }
              catch { setCopyStatus({ id: turn.id, message: 'Could not copy. Select the answer text to copy it.' }) }
            }}><Copy />Copy answer</Button>{copyStatus?.id === turn.id && <span role="status" className="text-xs text-muted-foreground">{copyStatus.message}</span>}</div>
          </div>}
          </div>
        </li>)}</ol>}
        {source && <section ref={sourcePanel} aria-label="Saved source text" className="space-y-3 rounded-xl border border-primary/30 bg-background p-5">
          <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-medium">{source.title}</h3><Button variant="ghost" size="xs" onClick={() => { sourceRequest.current++; setSource(null) }}>Close source</Button></div>
          <p className="text-xs text-muted-foreground">Saved report text</p>
          {source.error && <ErrorBlock>{source.error}</ErrorBlock>}
          {source.text ? <p className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words text-sm">{source.text}</p> : !source.error && <LoadingLine>Loading source page…</LoadingLine>}
        </section>}
        {global && catalog.length === 0 && <p className="text-sm text-muted-foreground">No saved reports yet. Add and parse a report first, then return here.</p>}
        <div className="space-y-3 rounded-2xl border bg-background p-4 shadow-sm">
          <p id={`${inputId}-scope`} className="text-sm" aria-live="polite"><span className="font-medium">Scope: </span>{scope || 'No reports selected'}</p>
          {global && <p className="text-xs text-muted-foreground">Use @Company to focus your question. Each answer searches the selected reports independently.</p>}
          {!turns.length && <div className="grid gap-2 sm:grid-cols-3">{EXAMPLES.map(example => <button type="button" key={example.title} disabled={busy || blocked} onClick={() => {
            if (busy || blocked) return
            if (global) { const text = `${mentions.selected.map(name => `@${name} `).join('')}${example.question}`; setQuestion(text); setCursor(text.length); setDismissed(true); input.current?.focus() }
            else void submit(example.question)
          }} className="rounded-xl border bg-card px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent disabled:opacity-40"><span className="block text-xs font-medium">{example.title}</span><span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{example.hint}</span></button>)}</div>}
          <label htmlFor={inputId} className="sr-only">Question about reports</label>
          <div className="flex items-end gap-2">
            <div className="relative min-w-0 flex-1">
              {popup && <ul id={`${inputId}-companies`} role="listbox" aria-label="Saved companies" className="absolute bottom-full z-50 mb-1 max-h-64 w-full overflow-y-auto rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg">
                {suggestions.map((name, index) => <li id={`${inputId}-company-${index}`} key={name} role="option" aria-selected={index === active} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(name)} className={`cursor-pointer rounded px-3 py-2 text-sm ${index === active ? 'bg-accent text-accent-foreground' : ''}`}>{name}</li>)}
              </ul>}
              <textarea ref={input} id={inputId} aria-label="Question" value={question} rows={2} role={global ? 'combobox' : undefined} aria-autocomplete={global ? 'list' : undefined} aria-expanded={global ? popup : undefined} aria-controls={popup ? `${inputId}-companies` : undefined} aria-activedescendant={popup ? `${inputId}-company-${active}` : undefined} aria-describedby={`${inputId}-scope${mentions.unknown.length ? ` ${inputId}-mention-error` : ''}`} placeholder={global ? 'Ask a question, or type @Company…' : 'Ask about these reports…'} disabled={busy || global && catalog.length === 0}
                onChange={(event) => { setQuestion(event.target.value); setCursor(event.target.selectionStart); setActive(0); setDismissed(false) }}
                onSelect={(event) => setCursor(event.currentTarget.selectionStart)}
                onKeyDown={(event) => {
                  if (event.nativeEvent.isComposing) return
                  if (popup && ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) {
                    event.preventDefault()
                    if (event.key === 'Escape') setDismissed(true)
                    else if (event.key === 'Enter') choose(suggestions[active] ?? suggestions[0])
                    else setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : suggestions.length - 1)) % suggestions.length)
                  } else if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
                }}
                className="min-h-16 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50" />
            </div>
            {busy ? <Button variant="outline" onClick={() => currentRequest.current?.abort()} title="Stop waiting for this response; the model may continue processing"><Square />Stop waiting</Button> : <Button onClick={() => void submit()} disabled={!question.trim() || blocked}><ArrowUp />Ask</Button>}
          </div>
          {global && mentions.unknown.length > 0 && <p id={`${inputId}-mention-error`} role="status" className="text-xs text-warning">Choose a saved company from the suggestions or remove the unfinished/unknown mention: {mentions.unknown.join(', ')}.</p>}
          <p className="text-xs text-muted-foreground">Enter to send · Shift+Enter for a new line{popup ? ' · ↑↓ to choose a company, Enter to select, Escape to close' : ''}</p>
        </div>
    </section>
  )
}
