import { ExternalLink, ImageOff } from 'lucide-react'
import { pageUrl, pdfUrl } from '@/api'
import { highlightQuote } from '@/components/results/highlight'
import { Segmented } from '@/components/results/Segmented'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Field } from '@/types'

// Provenance viewer: browser PDF viewer (scroll/zoom/search/select for free) or the rendered PNG as fallback.
export type Viewer = 'pdf' | 'image'

type SourcePanelProps = {
  reportId: string
  page: number | null // what the pane shows: askPage override or the selected field's page
  selected: Field | null
  askPage: number | null // citation chip override in effect
  viewer: Viewer
  onViewerChange: (v: Viewer) => void
  brokenPage: number | null
  onBrokenPage: (page: number) => void
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
  page,
  selected,
  askPage,
  viewer,
  onViewerChange,
  brokenPage,
  onBrokenPage,
}: SourcePanelProps) {
  return (
    <Card className="self-start">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>Source</span>
          {page !== null && (
            <span className="flex flex-wrap items-center gap-2 text-sm font-normal text-muted-foreground">
              <span className="mr-1">Page {page}</span>
              <Segmented options={VIEWER_OPTIONS} value={viewer} onChange={onViewerChange} aria-label="Provenance viewer" />
              <a
                href={pdfUrl(reportId, page)}
                target="_blank"
                rel="noreferrer"
                className={buttonVariants({ size: 'xs', variant: 'ghost' })}
              >
                Open PDF <ExternalLink />
              </a>
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {page === null ? (
          <p className="text-sm text-muted-foreground">
            {selected && !selected.source
              ? 'No source — value not found.'
              : 'Select a row to see where the value comes from.'}
          </p>
        ) : (
          <>
            {viewer === 'pdf' ? (
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
                Page preview unavailable
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
                </div>
              )
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
