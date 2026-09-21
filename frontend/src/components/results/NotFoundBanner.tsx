import { useEffect, useState } from 'react'
import { type CandidatePage, formatPageRanges, getCandidates } from '@/api'
import { Button } from '@/components/ui/button'
import type { Extraction } from '@/types'

type Props = {
  extraction: Extraction
  onSelectField: (key: string) => void // selects a row -> its review form opens below the table
}

// v164 (consult item 8): a page of "Not found" rows reads as a parser failure when it is often just
// the report not printing the figures. When the model answered nothing (every value null) or the
// identity check cannot close for missing values, one secondary banner at the top says which pages
// were searched and hands over to the manual review form below. Secondary styling on purpose — a
// figure the report never prints is a fact, not an error (verification.ts badges null the same way).
export function NotFoundBanner({ extraction, onSelectField }: Props) {
  const { fields, checks, report_id, section } = extraction
  const allNull = fields.length > 0 && fields.every((f) => f.value === null)
  // The identity "cannot close for missing values" case: a check marked unavailable *and* a figure
  // actually missing. An unavailable check with every value present is a unit/period mismatch —
  // the figures were found, so the banner has nothing to say there (work order: 全 null 或因缺值失败).
  const identityMissing = checks.some((c) => c.status === 'unavailable') && fields.some((f) => f.value === null)
  const show = allNull || identityMissing
  const [candidates, setCandidates] = useState<CandidatePage[] | null>(null)
  useEffect(() => {
    if (!show) return
    let stale = false
    // Advisory only: an older backend (404) or a textless report leaves the page list out and the
    // banner still says what happened.
    getCandidates(report_id, section)
      .then((list) => !stale && setCandidates(list))
      .catch(() => !stale && setCandidates([]))
    return () => {
      stale = true
    }
  }, [show, report_id, section])
  if (!show) return null
  const pages = (candidates ?? []).map((c) => c.page)
  const target = fields.find((f) => f.value === null) ?? fields[0]
  const openReview = () => {
    if (!target) return
    onSelectField(target.key)
    requestAnimationFrame(() => {
      // The row is already mounted (the table always renders); selecting it opens the review form
      // right below. Aiming at the row keeps this timing-proof, unlike waiting for the form itself.
      document.querySelector('[data-state="selected"]')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }
  return (
    <section
      aria-label="Figures the model did not find"
      className="rounded-xl border border-border bg-muted/40 px-5 py-4 shadow-[inset_0_1px_0_var(--glass-hi)]"
    >
      <p className="text-sm font-medium">
        {allNull ? 'The model did not find these figures on the pages it read.' : 'Figures are missing, so the totals cannot be checked.'}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {pages.length
          ? `Candidates were pages ${formatPageRanges(pages)} of this report; none of the figures were found there.`
          : 'The pages the locator ranks highest carried none of the figures.'}{' '}
        The report may simply not print them. Check the source and fill in what you find.
      </p>
      {target && (
        <Button variant="outline" size="sm" className="mt-3" onClick={openReview}>
          Fill in below
        </Button>
      )}
    </section>
  )
}
