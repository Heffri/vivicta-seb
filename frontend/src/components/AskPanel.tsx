import { TriangleAlert } from 'lucide-react'
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { ask, getKbPage, indexReport, pdfUrl } from '@/api'
import { AnswerText } from '@/components/ask/AnswerText'
import { companyMentions, mentionAtCursor } from '@/components/ask/companyMentions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Answer, KbEntry } from '@/types'

type Props = {
  reports: { report_id: string; label: string }[]
  catalog?: KbEntry[] // present only for the global saved-report view
  initialCompany?: string
  onCitation?: (reportId: string, page: number) => void
}
type Turn = { question: string; scope: string; answer?: Answer; error?: string }
type Source = { title: string; text?: string; error?: string }
const EXAMPLES = ['Explain the key figures in plain language', 'What changed from the previous year?', 'What financial risks does the report highlight?']

export function AskPanel({ reports, catalog, initialCompany, onCitation }: Props) {
  const [question, setQuestion] = useState(initialCompany ? `@${initialCompany} ` : '')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [cursor, setCursor] = useState(initialCompany ? initialCompany.length + 2 : 0)
  const [active, setActive] = useState(0)
  const [dismissed, setDismissed] = useState(!!initialCompany)
  const [source, setSource] = useState<Source | null>(null)
  const sourceRequest = useRef(0)
  const input = useRef<HTMLTextAreaElement>(null)
  const pendingSelection = useRef<number | null>(null)
  const inputId = useId()
  const global = catalog !== undefined
  const companies = [...new Set((catalog ?? []).map((entry) => entry.company).filter((name): name is string => !!name))].sort()
  const mentions = companyMentions(question, companies)
  const selected = (catalog ?? []).filter((entry) => entry.company && mentions.selected.includes(entry.company))
  const scope = global ? mentions.unknown.length ? 'Waiting for a valid company mention' : mentions.selected.length ? `${mentions.selected.join(', ')} · ${selected.length} saved reports` : `All ${catalog.length} saved reports` : reports.map((report) => report.label).join(', ')
  const blocked = global ? catalog.length === 0 || mentions.unknown.length > 0 : reports.length === 0
  const mention = global ? mentionAtCursor(question, cursor) : null
  const suggestions = mention ? companies.filter((name) => name.toLocaleLowerCase().startsWith(mention.query.toLocaleLowerCase())).slice(0, 8) : []
  const popup = !!mention && !dismissed && suggestions.length > 0
  const idsKey = reports.map((report) => report.report_id).join()

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
    if (!q || busy || blocked) return
    const parsed = global ? companyMentions(q, companies) : null
    if (parsed?.unknown.length) return
    const stems = parsed?.selected.length ? catalog!.filter((entry) => entry.company && parsed.selected.includes(entry.company)).map((entry) => entry.stem) : global ? catalog!.map((entry) => entry.stem) : undefined
    setBusy(true)
    setDismissed(true)
    try {
      const answer = await ask(q, global ? undefined : reports.map((report) => report.report_id), stems)
      setTurns((previous) => [...previous, { question: q, scope, answer }])
      setQuestion(global && parsed?.selected.length ? parsed.selected.map((name) => `@${name}`).join(' ') + ' ' : '')
    } catch (error) {
      setTurns((previous) => [...previous, { question: q, scope, error: (error as Error).message }])
    } finally { setBusy(false) }
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
    const title = `${citation?.company ?? entry?.company ?? 'Source'} · page ${page}`
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
    <Card>
      <CardHeader><CardTitle>{global ? 'Ask saved reports' : 'Ask the reports'}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {turns.length > 0 && <ol className="space-y-4">{turns.map((turn, i) => <li key={i} className="space-y-2 border-b pb-4 text-sm last:border-b-0">
          <p className="font-medium">{turn.question}</p>
          <p className="text-xs text-muted-foreground">Searched: {turn.scope}</p>
          {turn.error ? <ErrorBlock>{turn.error}</ErrorBlock> : turn.answer && <>
            <AnswerText text={turn.answer.answer} citations={turn.answer.citations} onCitation={(id, page) => void openCitation(turn.answer!, id, page)} />
            <div className="flex flex-wrap gap-1.5">{turn.answer.citations.map((citation, j) => <Badge key={j} variant="outline" render={<button type="button" />} title={citation.quote} className="cursor-pointer hover:bg-accent" onClick={() => void openCitation(turn.answer!, citation.report_id, citation.page)}>
              {citation.company ?? reports.find((report) => report.report_id === citation.report_id)?.label ?? 'Report'} {citation.fiscal_year ? `FY${citation.fiscal_year} · ` : ''}p.{citation.page}
            </Badge>)}</div>
            {turn.answer.warnings.map((warning) => <p key={warning} className="flex gap-1.5 text-xs text-warning"><TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden /><span className="break-words">{warning}</span></p>)}
          </>}
        </li>)}</ol>}
        {source && <section aria-label="Saved source text" className="space-y-2 rounded-lg border bg-background p-3">
          <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-medium">{source.title}</h3><Button variant="ghost" size="xs" onClick={() => { sourceRequest.current++; setSource(null) }}>Close source</Button></div>
          <p className="text-xs text-muted-foreground">Saved report text</p>
          {source.error && <ErrorBlock>{source.error}</ErrorBlock>}
          {source.text ? <p className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words text-sm">{source.text}</p> : !source.error && <LoadingLine>Loading source page…</LoadingLine>}
        </section>}
        {busy && <LoadingLine>Searching reports…</LoadingLine>}
        {global && catalog.length === 0 && <p className="text-sm text-muted-foreground">No saved reports yet. Add and parse a report first, then return here.</p>}
        <div className="space-y-2">
          <p id={`${inputId}-scope`} className="text-sm" aria-live="polite"><span className="font-medium">Scope: </span>{scope || 'No reports selected'}</p>
          {global && <p className="text-xs text-muted-foreground">Type @ to choose a company. Add several mentions to compare companies. Remove all mentions to search every saved report.</p>}
          <div className="flex flex-wrap gap-1.5">{EXAMPLES.map((example) => <Badge key={example} variant="outline" render={<button type="button" />} aria-disabled={busy || blocked} onClick={() => {
            if (busy || blocked) return
            if (global) { setQuestion(`${mentions.selected.map((name) => `@${name} `).join('')}${example}`); setDismissed(true); input.current?.focus() }
            else void submit(example)
          }} className="cursor-pointer hover:bg-accent aria-disabled:pointer-events-none aria-disabled:opacity-40">{example}</Badge>)}</div>
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
            <Button onClick={() => void submit()} disabled={busy || !question.trim() || blocked}>Ask</Button>
          </div>
          {global && mentions.unknown.length > 0 && <p id={`${inputId}-mention-error`} role="status" className="text-xs text-warning">Choose a saved company from the suggestions or remove the unfinished/unknown mention: {mentions.unknown.join(', ')}.</p>}
          <p className="text-xs text-muted-foreground">Enter to send · Shift+Enter for a new line{popup ? ' · ↑↓ to choose a company, Enter to select, Escape to close' : ''}</p>
        </div>
      </CardContent>
    </Card>
  )
}
