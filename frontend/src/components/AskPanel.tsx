import { TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ask, indexReport, pdfUrl } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { Answer } from '@/types'

type Props = {
  reports: { report_id: string; label: string }[]
  onCitation?: (reportId: string, page: number) => void // default: open the PDF on that page in a new tab
}

type Turn = { question: string; answer?: Answer; error?: string }

const EXAMPLES = [
  'Which page is the income statement on?',
  'Compare revenue and operating margin',
  'Vad var rörelseresultatet?',
]

export function AskPanel({ reports, onCitation }: Props) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)

  const ids = reports.map((r) => r.report_id)
  const idsKey = ids.join() // stable dep; the array literal from the parent is new every render
  useEffect(() => {
    // Warm the KB so the first answer doesn't also pay for embedding. Sequential: one GPU. Fire-and-forget —
    // /ask indexes on demand anyway, and a 404 here just means the backend isn't there yet.
    let alive = true
    ;(async () => {
      for (const id of idsKey ? idsKey.split(',') : []) {
        if (!alive) return
        await indexReport(id).catch(() => undefined)
      }
    })()
    return () => {
      alive = false
    }
  }, [idsKey])

  const submit = async (q = question.trim()) => {
    if (!q || busy || ids.length === 0) return
    setBusy(true)
    setQuestion('')
    try {
      const answer = await ask(q, ids)
      setTurns((t) => [...t, { question: q, answer }])
    } catch (e) {
      setTurns((t) => [...t, { question: q, error: (e as Error).message }])
    }
    setBusy(false)
  }

  const labelFor = (reportId: string) => reports.find((r) => r.report_id === reportId)?.label ?? 'Report'

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-baseline justify-between gap-2">
          <span>Ask the reports</span>
          <span className="text-xs font-normal text-muted-foreground">
            {reports.length === 1 ? reports[0].label : `${reports.length} reports`}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {turns.length > 0 && (
          <ol className="space-y-4">
            {turns.map((t, i) => (
              <li key={i} className="space-y-2 border-b pb-4 text-sm last:border-b-0">
                <p className="font-medium">{t.question}</p>
                {t.error ? (
                  <ErrorBlock>{t.error}</ErrorBlock>
                ) : (
                  t.answer && (
                    <>
                      {/* ponytail: answer is markdown per the contract; plain text + stripped ** is enough — the inline [Company p.N] cites read fine as-is. */}
                      <p className="whitespace-pre-wrap break-words leading-relaxed">{t.answer.answer.replaceAll('**', '')}</p>
                      {t.answer.citations.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {t.answer.citations.map((c, j) => (
                            <Badge
                              key={j}
                              variant="outline"
                              render={<button type="button" />}
                              title={c.quote}
                              className="cursor-pointer transition-colors hover:border-ring hover:bg-accent hover:text-accent-foreground"
                              onClick={() =>
                                onCitation
                                  ? onCitation(c.report_id, c.page)
                                  : window.open(pdfUrl(c.report_id, c.page), '_blank', 'noopener')
                              }
                            >
                              {c.company ?? labelFor(c.report_id)} · p.{c.page}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {t.answer.warnings.map((w) => (
                        <p key={w} className="flex gap-1.5 text-xs text-warning">
                          <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
                          <span className="break-words">{w}</span>
                        </p>
                      ))}
                    </>
                  )
                )}
              </li>
            ))}
          </ol>
        )}

        {busy && <LoadingLine>Thinking… local model, 10–40 s</LoadingLine>}

        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((q) => (
              <Badge
                key={q}
                variant="outline"
                render={<button type="button" />}
                aria-disabled={busy || ids.length === 0}
                onClick={() => {
                  if (busy || ids.length === 0) return
                  submit(q)
                }}
                className="cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground aria-disabled:pointer-events-none aria-disabled:opacity-40"
              >
                {q}
              </Badge>
            ))}
          </div>
          <div className="flex items-end gap-2">
            <textarea
              value={question}
              rows={2}
              placeholder="Ask about these reports… Enter to send, Shift+Enter for a new line"
              disabled={busy}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  submit()
                }
              }}
              className="min-h-16 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
            />
            <Button onClick={() => submit()} disabled={busy || !question.trim() || ids.length === 0}>
              Ask
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
