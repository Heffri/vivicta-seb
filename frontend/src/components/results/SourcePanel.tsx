import { ExternalLink, ImageOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getKbPage, pageUrl, pdfUrl } from '@/api'
import { fieldVerification } from './verification'
import { highlightQuote } from '@/components/results/highlight'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Segmented } from '@/components/ui/segmented'
import type { Field, Source } from '@/types'

// Provenance viewer: browser PDF viewer (scroll/zoom/search/select for free) or the rendered PNG as fallback.
export type Viewer = 'pdf' | 'image'

type SourcePanelProps = {
  reportId: string
  stem?: string
  pdfAvailable?: boolean
  page: number | null // what the pane shows: askPage override or the selected field's page
  selected: Field | null
  askPage: number | null // citation chip override in effect
  viewer: Viewer
  onViewerChange: (v: Viewer) => void
  brokenPage: number | null
  onBrokenPage: (page: number) => void
  onUseSource?: (source: Source) => void
  onFillField?: (page: number) => void
  fillingField?: boolean
}

const VIEWER_OPTIONS: { value: Viewer; label: string }[] = [
  { value: 'pdf', label: 'PDF' },
  { value: 'image', label: 'Image' },
]

/** Page N + the PDF/Image toggle + Open PDF, then the page itself, then the verbatim
 *  quote with the field's value highlighted inside it — the "number ↔ line on the page"
 *  link the whole product rests on. */
export function SourcePanel({
  reportId,
  stem,
  pdfAvailable = true,
  page,
  selected,
  askPage,
  viewer,
  onViewerChange,
  brokenPage,
  onBrokenPage,
  onUseSource,
  onFillField,
  fillingField = false,
}: SourcePanelProps) {
  const [savedPage, setSavedPage] = useState<{page: number; stem: string; text: string} | null>(null)
  const [pageError, setPageError] = useState<{page: number; stem: string; message: string} | null>(null)
  useEffect(() => {
    if (!stem || page === null || (pdfAvailable && !onUseSource)) return
    let stale = false
    getKbPage(stem, page).then((result) => { if (!stale) { setSavedPage({...result, stem}); setPageError(null) } })
      .catch((error: Error) => { if (!stale) setPageError({page, stem, message: error.message}) })
    return () => { stale = true }
  }, [pdfAvailable, stem, page, onUseSource])
  return (
    <Card id="report-source" tabIndex={-1} className="self-start scroll-mt-4 focus-visible:outline-2 focus-visible:outline-ring">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>Source</span>
          {page !== null && (
            <span className="flex flex-wrap items-center gap-2 text-sm font-normal text-muted-foreground">
              <span className="mr-1">Page {page}</span>
              {pdfAvailable && <><Segmented options={VIEWER_OPTIONS} value={viewer} onChange={onViewerChange} aria-label="Provenance viewer" />
              <a
                href={pdfUrl(reportId, page)}
                target="_blank"
                rel="noreferrer"
                className={buttonVariants({ size: 'xs', variant: 'ghost' })}
              >
                Open PDF <ExternalLink />
              </a></>}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {selected && askPage === null && (
          <div className="text-sm" aria-live="polite">
            <p className="font-medium">{selected.label}: {fieldVerification(selected).label}</p>
            <p className="mt-1 text-muted-foreground">{fieldVerification(selected).detail}</p>
          </div>
        )}
        {page === null ? (
          <p className="text-sm text-muted-foreground">
            {selected && !selected.source
              ? 'No source reference is available for this figure.'
              : 'Select a row to see where the value comes from.'}
          </p>
        ) : (
          <>
            {!pdfAvailable ? (
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">Saved page text. The original PDF is not available on this device.</p>
                {pageError?.page === page && pageError.stem === stem ? <p role="alert" className="text-sm text-danger">{pageError.message}</p>
                  : savedPage?.page === page && savedPage.stem === stem ? <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border bg-background p-3 text-xs leading-relaxed">{savedPage.text}</pre>
                  : <p className="text-sm text-muted-foreground">{stem ? 'Loading saved page…' : 'Saved page reference unavailable.'}</p>}
              </div>
            ) : viewer === 'pdf' ? (
              // ponytail: key={page} remounts the iframe — swapping only the #page= hash on the same src doesn't
              // reliably navigate in Chromium. PDF is browser-cached after the first load; pdf.js is the upgrade if
              // the remount flicker ever annoys.
              <iframe
                key={page}
                src={pdfUrl(reportId, page)}
                title={`Page ${page} of the report`}
                className="h-[70vh] w-full rounded-lg border bg-white"
              />
            ) : brokenPage === page ? (
              <div className="flex aspect-[1/1.3] flex-col items-center justify-center gap-2 rounded-lg border bg-muted/40 text-sm text-muted-foreground">
                <ImageOff className="size-5" />
                <span>Page preview unavailable</span>
                {/* v092: a KB-only report's pages 404 until the PDF is fetched — same hint the backend's detail carries */}
                <span>Fetch the PDF from Extract (directory search) to see the pages.</span>
              </div>
            ) : (
              <img
                src={pageUrl(reportId, page)}
                alt={`Page ${page} of the report`}
                onError={() => onBrokenPage(page)}
                className="w-full rounded-lg border bg-white"
              />
            )}
            {askPage !== null ? (
              <p className="text-xs text-muted-foreground">
                Page {askPage}, cited in an answer below. Click a row to go back to a field.
              </p>
            ) : (
              selected?.source && (
                <div>
                  <p className="mb-1.5 text-xs text-muted-foreground">
                    {selected.label}
                    {selected.raw_label && selected.raw_label !== selected.label && (
                      <> · printed as “{selected.raw_label}”</>
                    )}
                  </p>
                  <pre className="whitespace-pre-wrap break-words rounded-lg border bg-background/70 p-3 font-mono text-xs leading-relaxed">
                    {highlightQuote(selected.source.quote, selected.value).map((run, i) =>
                      run.hit ? (
                        <mark
                          key={i}
                          className="rounded-[4px] bg-ring/25 px-0.5 text-foreground ring-1 ring-ring/45"
                        >
                          {run.text}
                        </mark>
                      ) : (
                        run.text
                      ),
                    )}
                  </pre>
                  {onUseSource && !stem && page === selected.source.page && <Button type="button" variant="outline" size="xs" className="mt-2" onClick={() => onUseSource(selected.source!)}>Use this line as citation</Button>}
                </div>
              )
            )}
            {onFillField && selected?.value === null && page !== null && (
              <Button type="button" variant="outline" size="xs" disabled={fillingField} onClick={() => onFillField(page)}>
                {fillingField ? 'Reading selected page…' : `Fill ${selected.label} from this page`}
              </Button>
            )}
            {onUseSource && savedPage?.page === page && savedPage.stem === stem && <details open className="rounded-lg border p-3"><summary className="cursor-pointer text-xs font-medium">Choose a saved page line for the review citation</summary><div className="mt-2 max-h-44 space-y-1 overflow-y-auto">{savedPage.text.split(/\r?\n/).map((line, index) => line.trim() && <button key={index} type="button" aria-label="Use this line as citation" className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-muted" onClick={() => onUseSource({ page, quote: line.trim() })}><span className="mr-2 font-medium text-primary">Use this line as citation</span>{line.trim()}</button>)}</div></details>}
          </>
        )}
      </CardContent>
    </Card>
  )
}
