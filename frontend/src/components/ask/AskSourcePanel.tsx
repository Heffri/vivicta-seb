import { ExternalLink, FileText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { getKbPage, getPageEvidence, highlightedPdfUrl, pageUrl, pdfUrl, restoreSourcePdf, type PageEvidence } from '@/api'
import { scrollContent } from '@/components/shell/scrollContent'
import { Button, buttonVariants } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import { evidenceRanges, evidenceRuns, sourceDocument, type EvidenceRange, type TextSpan } from './sourceDocument'

export type AskSource = { id: number; title: string; reportId: string; page: number; stem?: string; pdfAvailable: boolean; quotes: string[] }
const numberStyle = 'rounded px-0.5 bg-amber-200 text-amber-950 font-semibold ring-1 ring-amber-400/60'

function EvidenceText({ span, ranges }: { span: TextSpan; ranges: EvidenceRange[] }) {
  return <>{evidenceRuns(span, ranges).map((run, i) => run.number
    ? <mark key={i} className={numberStyle} title="Figure in the cited passage">{run.text}</mark>
    : run.cited ? <span key={i} className="rounded bg-blue-200/85 text-blue-950">{run.text}</span> : run.text)}</>
}

function FormattedPage({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges = evidenceRanges(text, quotes)
  const container = useRef<HTMLDivElement>(null)
  const supported = (spans: TextSpan[]) => spans.some(s => ranges.some(r => s.start < r.end && s.end > r.start))
  useEffect(() => {
    const root = container.current
    const row = root?.querySelector<HTMLElement>('[data-cited="true"]')
    if (root && row) root.scrollTop += row.getBoundingClientRect().top - root.getBoundingClientRect().top - 100
  }, [text, quotes])
  return <>
    {!ranges.length && quotes.length > 0 && <p className="text-xs text-muted-foreground">The cited passage could not be located in this saved page. See the excerpt above.</p>}
    <div role="region" aria-label="Saved source text">
      <div ref={container} aria-label="Formatted source page" tabIndex={0} className="max-h-[65vh] overflow-auto rounded-xl border bg-card px-4 py-5 sm:px-6">
      {sourceDocument(text).map((block, i) => block.type === 'table'
        ? <table key={i} className="my-4 w-full min-w-[420px] border-collapse text-sm tabular-nums">
          <caption className="sr-only">Financial statement from the saved report</caption>
          <thead className="sticky top-0 z-10 bg-[#303039] [[data-tone=light]_&]:bg-white"><tr className="border-y-2 border-foreground/25"><th scope="col" className="px-3 py-3 text-left font-medium">Reported item</th>{block.headers.map(h => <th key={h.start} scope="col" className="px-4 py-3 text-right font-semibold">{h.text}</th>)}</tr></thead>
          <tbody>{block.rows.map(row => <tr key={row.label[0].start} data-cited={supported([...row.label, ...row.values])} className={`border-b border-border/60 ${supported([...row.label, ...row.values]) ? 'bg-primary/10' : ''}`}>
            <th scope="row" colSpan={row.values.length ? undefined : block.headers.length + 1} className={`px-3 py-2.5 text-left leading-relaxed ${row.values.length ? 'font-normal' : 'pt-5 font-semibold'}`}>{row.label.map((s, j) => <span key={s.start}>{j > 0 && ' '}<EvidenceText span={s} ranges={ranges} /></span>)}</th>
            {row.values.map((s, column) => <td key={column} className="whitespace-nowrap px-4 py-2.5 text-right">{/^(note|notes|not|noter)$/i.test(block.headers[column].text) ? s.text : <EvidenceText span={s} ranges={ranges} />}</td>)}
          </tr>)}</tbody>
        </table>
        : <div key={i} className="my-3 space-y-1 text-sm leading-relaxed">{block.lines.map(line => <div key={line.start} data-cited={supported([line])} className={line.text ? 'min-h-5 whitespace-pre-wrap break-words' : 'h-2'}><EvidenceText span={line} ranges={ranges} /></div>)}</div>)}
      </div>
    </div>
  </>
}

export function AskSourcePanel({ source, onClose }: { source: AskSource; onClose: () => void }) {
  const panel = useRef<HTMLElement>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<PageEvidence | null>(null)
  const [evidenceError, setEvidenceError] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const [pdfAvailable, setPdfAvailable] = useState(source.pdfAvailable)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [view, setView] = useState<'page' | 'text' | 'pdf'>(source.pdfAvailable ? 'page' : 'text')
  useEffect(() => { scrollContent(panel.current) }, [saved, error, imageFailed, view])
  useEffect(() => {
    if (!source.stem) return
    let alive = true
    getKbPage(source.stem, source.page).then(result => { if (alive) setSaved(result.text) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [source.stem, source.page])
  useEffect(() => {
    if (!pdfAvailable || !source.quotes.length) return
    let alive = true
    getPageEvidence(source.reportId, source.page, source.quotes).then(result => { if (alive) setEvidence(result) })
      .catch(() => { if (alive) setEvidenceError(true) })
    return () => { alive = false }
  }, [pdfAvailable, source.reportId, source.page, source.quotes])
  async function downloadSource() {
    if (!source.stem) return
    setDownloading(true)
    setDownloadError(null)
    try {
      await restoreSourcePdf(source.stem)
      setPdfAvailable(true)
      setView('page')
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : 'Could not download the source PDF.')
    } finally {
      setDownloading(false)
    }
  }
  const highlightedPdf = highlightedPdfUrl(source.reportId, source.page, source.quotes)
  return <section ref={panel} aria-label="Source evidence" className="space-y-4 rounded-2xl border border-primary/25 bg-background p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground"><FileText className="size-3.5" />Source evidence</p><h3 className="text-base font-semibold">{source.title}</h3></div><Button variant="ghost" size="xs" onClick={onClose}>Close source</Button></div>
    {source.quotes.length > 0 && <div className="rounded-xl border border-primary/20 bg-primary/5 p-4"><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Supporting passage</p>{source.quotes.map((quote, i) => <blockquote key={i} className="mt-2 whitespace-pre-wrap text-sm leading-7"><EvidenceText span={{ text: quote.replace(/\s+/g, ' ').trim(), start: 0, end: quote.length }} ranges={[{ start: 0, end: quote.length }]} /></blockquote>)}</div>}
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground"><span><mark className={numberStyle}>123</mark> Cited figures</span><span><mark className="rounded bg-blue-200 px-1 text-blue-950">Keywords</mark> Supporting text</span></div>
    {!pdfAvailable && source.stem && <div className="space-y-2"><Button size="sm" disabled={downloading} onClick={downloadSource}>{downloading ? 'Downloading original PDF…' : 'Download original PDF'}</Button><p className="text-xs text-muted-foreground">Download the matching source to enable page highlights and save a highlighted copy.</p>{downloadError && <ErrorBlock>{downloadError}</ErrorBlock>}</div>}
    {pdfAvailable && <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Source view"><Button size="xs" aria-pressed={view === 'page'} variant={view === 'page' ? 'secondary' : 'ghost'} onClick={() => setView('page')}>Original page</Button>{source.stem && <Button size="xs" aria-pressed={view === 'text'} variant={view === 'text' ? 'secondary' : 'ghost'} onClick={() => setView('text')}>Readable text</Button>}{source.quotes.length > 0 && <Button size="xs" aria-pressed={view === 'pdf'} variant={view === 'pdf' ? 'secondary' : 'ghost'} onClick={() => setView('pdf')}>Highlighted PDF</Button>}<a className={buttonVariants({ size: 'xs', variant: 'ghost' })} href={pdfUrl(source.reportId, source.page)} target="_blank" rel="noreferrer">Open original PDF<ExternalLink /></a>{source.quotes.length > 0 && <a className={buttonVariants({ size: 'xs', variant: 'ghost' })} href={highlightedPdf} download={`report-page-${source.page}-highlighted.pdf`}>Download highlighted PDF</a>}</div>}
    {pdfAvailable && view !== 'text' && <p className="text-xs text-muted-foreground">PDF page {source.page} · page numbers refer to the PDF viewer. {evidenceError ? 'Highlights could not be loaded; the original page is still available.' : evidence && !evidence.matched_quotes ? 'No exact evidence could be located in this PDF’s text layer. Use the supporting passage above to check the page manually.' : evidence && evidence.matched_quotes < evidence.total_quotes ? 'Some passages could not be located; only matched evidence is highlighted.' : 'Blue marks the cited keywords; yellow marks matching figures in their source context.'}</p>}
    {view === 'pdf' ? <><p className="text-xs text-muted-foreground">The full report opens at page {source.page}. Highlights are included in the downloaded copy; the original file is unchanged.</p><iframe className="h-[75vh] w-full rounded-xl border bg-white" title={`Highlighted PDF, page ${source.page}`} src={highlightedPdf} /></>
      : view === 'page' && !imageFailed ? <div className="max-h-[70vh] overflow-auto rounded-xl border bg-white"><div className="relative"><img className="block h-auto w-full" src={pageUrl(source.reportId, source.page)} alt={`Original report, page ${source.page}`} onError={() => setImageFailed(true)} />{evidence && <div className="pointer-events-none absolute inset-0" aria-label="PDF evidence highlights">{(['keywords', 'numbers'] as const).flatMap(kind => evidence[kind].map(([x0, y0, x1, y1], i) => <span key={`${kind}-${i}`} data-evidence={kind} className={`absolute rounded-sm mix-blend-multiply ${kind === 'numbers' ? 'bg-amber-300/60' : 'bg-blue-300/50'}`} style={{ left: `${x0 / evidence.width * 100}%`, top: `${y0 / evidence.height * 100}%`, width: `${(x1 - x0) / evidence.width * 100}%`, height: `${(y1 - y0) / evidence.height * 100}%` }} />))}</div>}</div></div>
      : <><p className="text-xs text-muted-foreground">{imageFailed ? 'Page preview unavailable. ' : ''}{!pdfAvailable ? 'Original PDF not downloaded. ' : ''}Formatted from saved text. Recognizable table columns are aligned; wording and figures are unchanged.</p>
        {error && <ErrorBlock>Could not load the full saved page: {error}</ErrorBlock>}
        {saved ? <FormattedPage text={saved} quotes={source.quotes} /> : source.stem && saved === null && !error ? <LoadingLine>Loading source page…</LoadingLine> : !error && <p className="text-sm text-muted-foreground">Full page text is unavailable. The supporting passage is shown above.</p>}</>}
  </section>
}
