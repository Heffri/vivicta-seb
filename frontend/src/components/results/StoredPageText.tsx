import { useEffect, useRef, useState } from 'react'

type Props = { text: string; quote?: string | null; zoom?: number | null }

const normalize = (s: string) => s.replace(/\s+/g, ' ').trim()

/** The no-PDF saved-text view: scrolls to and highlights the cited quote's
 *  own line instead of leaving the analyst to read the whole page. A line printed more than once
 *  (the same total under two column headers) gets a "1/N ▸" cycler rather than silently landing on
 *  the first hit; a quote that doesn't appear verbatim still shows the full page, with a note.
 *  SourcePanel keys this component by page+quote, so the cycler starts back at 1/N on its own
 *  whenever either changes — a remount, not a reset effect, resets the local index. */
export function StoredPageText({ text, quote, zoom = 100 }: Props) {
  const lines = text.split(/\r?\n/)
  const needle = quote ? normalize(quote) : ''
  const matches = needle ? lines.reduce<number[]>((acc, line, i) => (normalize(line).includes(needle) ? [...acc, i] : acc), []) : []
  const [index, setIndex] = useState(0)
  const activeLine = matches.length ? matches[index % matches.length] : null
  const textRef = useRef<HTMLPreElement | null>(null)
  const activeRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const text = textRef.current
    const active = activeRef.current
    if (activeLine !== null && text && active) {
      text.scrollTo({ top: active.offsetTop - 16, behavior: 'auto' })
    }
  }, [activeLine, text])
  return (
    <div className="space-y-1.5">
      <pre ref={textRef} style={{ fontSize: `${16 * (zoom ?? 100) / 100}px` }} className="h-[72vh] min-h-96 overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words rounded-lg border bg-background p-5 font-sans leading-relaxed">
        {lines.map((line, i) => (
          <div key={i} ref={i === activeLine ? activeRef : undefined} className={i === activeLine ? 'rounded-[4px] bg-ring/25 px-0.5 ring-1 ring-ring/45' : undefined}>
            {line}
          </div>
        ))}
      </pre>
      {needle && matches.length === 0 && <p className="text-xs text-muted-foreground">Quote not found verbatim in saved text.</p>}
      {matches.length > 1 && (
        <button type="button" className="text-xs text-primary underline-offset-2 hover:underline" onClick={() => setIndex((i) => i + 1)}>
          {(index % matches.length) + 1}/{matches.length} ▸
        </button>
      )}
    </div>
  )
}
