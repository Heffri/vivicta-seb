import { useEffect, useState } from 'react'
import { locateQuote, type PageLocate } from '@/api'
import { Badge } from '@/components/ui/badge'

type Props = { reportId: string; page: number; quote: string }

/** Image-mode overlay: frames the cited quote on the rendered page image.
 *  The backend degrades quote -> longest line -> longest digit run (GET .../locate); this component
 *  draws every rect that came back (one per printed line a hit touches — an ordinary citation
 *  wrapped across two lines draws two adjacent boxes), scaled by the page's own point size against
 *  the <img>'s rendered box. The "N matches" badge reads `occurrences` (the backend's own rects/line
 *  count already divided out), so a wrapped citation never wrongly cries "2 matches" — only a line
 *  truly repeated elsewhere on the page does. No match, no PDF, or a failed request all leave the
 *  page unframed — advisory only, never an error the console needs to show. SourcePanel keys this
 *  component by page+quote, so a stale result from the previous citation is never shown — remounting
 *  starts state fresh instead of a synchronous reset inside the effect. */
export function PageLocateOverlay({ reportId, page, quote }: Props) {
  const [locate, setLocate] = useState<PageLocate | null>(null)
  useEffect(() => {
    let stale = false
    locateQuote(reportId, page, quote)
      .then((result) => { if (!stale) setLocate(result) })
      .catch(() => { /* advisory only — the page still renders, just unframed */ })
    return () => { stale = true }
  }, [reportId, page, quote])
  if (!locate || locate.matched === 'none' || !locate.rects.length) return null
  return (
    <div className="absolute inset-0 overflow-hidden">
      {locate.rects.map(([x0, y0, x1, y1], i) => (
        <div
          key={i}
          className="absolute rounded-[4px] bg-ring/25 ring-1 ring-ring/45"
          style={{
            left: `${(x0 / locate.width) * 100}%`,
            top: `${(y0 / locate.height) * 100}%`,
            width: `${((x1 - x0) / locate.width) * 100}%`,
            height: `${((y1 - y0) / locate.height) * 100}%`,
          }}
        />
      ))}
      {locate.occurrences > 1 && (
        <Badge variant="secondary" className="absolute right-2 top-2 shadow">
          {locate.occurrences} matches
        </Badge>
      )}
    </div>
  )
}
