import type { ReactNode } from 'react'
import { pdfUrl } from '@/api'
import { Badge } from '@/components/ui/badge'
import type { Citation } from '@/types'
import { type AnswerBlock, type InlineNode, renderAnswer } from './renderAnswer'

type OnCitation = (reportId: string, page: number) => void

type Props = {
  text: string
  citations: Citation[]
  onCitation?: OnCitation // default: open the PDF on that page in a new tab
}

export function AnswerText({ text, citations, onCitation }: Props) {
  return <div className="space-y-2">{renderAnswer(text).map((block, i) => renderBlock(block, i, citations, onCitation))}</div>
}

function renderBlock(block: AnswerBlock, key: number, citations: Citation[], onCitation?: OnCitation) {
  if (block.type === 'list') {
    const items = block.items.map((item, i) => <li key={i}>{renderInline(item, citations, onCitation)}</li>)
    return block.ordered ? (
      <ol key={key} className="list-decimal space-y-1 pl-5">
        {items}
      </ol>
    ) : (
      <ul key={key} className="list-disc space-y-1 pl-5">
        {items}
      </ul>
    )
  }
  return (
    <p key={key} className="whitespace-pre-wrap break-words leading-relaxed">
      {renderInline(block.children, citations, onCitation)}
    </p>
  )
}

function renderInline(nodes: InlineNode[], citations: Citation[], onCitation?: OnCitation): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case 'text':
        return node.text
      case 'bold':
        return (
          <strong key={i} className="font-semibold">
            {renderInline(node.children, citations, onCitation)}
          </strong>
        )
      case 'code':
        return (
          <code key={i} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
            {node.text}
          </code>
        )
      case 'citation':
        return <CitationChip key={i} company={node.company} page={node.page} citations={citations} onCitation={onCitation} />
    }
  })
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')

// The model doesn't always echo the registered company name verbatim inline (e.g. the fixture
// answer cites "[Nordic Industrials p.64]" but answer.citations[].company is "Nordic Industrials
// AB (fictional fixture)" — same reconciliation problem the backend already solves for its own
// citations[] via substring containment + a single-citation fallback (pipeline/kb.py's `ask`); mirrored here.
function matchCitation(company: string, page: number, citations: Citation[]): Citation | undefined {
  const target = norm(company)
  const byName = citations.filter((c) => {
    if (!c.company) return false
    const n = norm(c.company)
    return n === target || n.includes(target) || target.includes(n)
  })
  return byName.find((c) => c.page === page) ?? byName[0] ?? (citations.length === 1 ? citations[0] : undefined)
}

function CitationChip({
  company,
  page,
  citations,
  onCitation,
}: {
  company: string
  page: number
  citations: Citation[]
  onCitation?: OnCitation
}) {
  const match = matchCitation(company, page, citations)
  const label = `${match?.company ?? company} · p.${page}`

  if (!match) {
    return (
      <Badge
        variant="outline"
        aria-disabled
        title="No matching citation for this report"
        className="mx-0.5 align-middle aria-disabled:pointer-events-none aria-disabled:opacity-40"
      >
        {label}
      </Badge>
    )
  }

  return (
    <Badge
      variant="outline"
      render={<button type="button" />}
      title={match.quote}
      className="mx-0.5 cursor-pointer align-middle transition-colors hover:border-ring hover:bg-accent hover:text-accent-foreground"
      onClick={() =>
        onCitation ? onCitation(match.report_id, page) : window.open(pdfUrl(match.report_id, page), '_blank', 'noopener')
      }
    >
      {label}
    </Badge>
  )
}
