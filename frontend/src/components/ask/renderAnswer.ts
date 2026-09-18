import type { Citation } from '@/types'

// Minimal markdown parser for /ask answers. Paragraphs (blank-line separated), **bold**,
// `-`/`*`/`1.` lists, inline `code`, and [Company p.N] citation refs. Anything else is left
// as literal text — no headings, tables, or links. Pure: text in, node tree out; AnswerText.tsx
// turns the tree into React elements.

export type TextNode = { type: 'text'; text: string }
export type BoldNode = { type: 'bold'; children: InlineNode[] }
export type CodeNode = { type: 'code'; text: string }
export type CitationNode = { type: 'citation'; company: string; page: number }
export type InlineNode = TextNode | BoldNode | CodeNode | CitationNode

export type ParagraphBlock = { type: 'paragraph'; children: InlineNode[] }
export type ListBlock = { type: 'list'; ordered: boolean; items: InlineNode[][] }
export type AnswerBlock = ParagraphBlock | ListBlock

const LIST_ITEM_RE = /^(?:[-*]|\d+\.)\s+/
const INLINE_RE = /\*\*(.+?)\*\*|`([^`]+?)`|\[([^[\]]+?)\s+p\.\s?(\d+)\]/g

export function renderAnswer(markdown: string): AnswerBlock[] {
  return splitBlocks(markdown).map(parseBlock)
}

function splitBlocks(markdown: string): string[] {
  return markdown
    .replace(/\r\n/g, '\n')
    .split(/\n[ \t]*\n+/)
    .map((b) => b.trim())
    .filter(Boolean)
}

function parseBlock(block: string): AnswerBlock {
  const lines = block.split('\n').map((l) => l.trim())
  const isList = lines.length > 0 && lines.every((l) => LIST_ITEM_RE.test(l))
  if (isList) {
    return {
      type: 'list',
      ordered: /^\d+\./.test(lines[0]),
      items: lines.map((l) => parseInline(l.replace(LIST_ITEM_RE, ''))),
    }
  }
  return { type: 'paragraph', children: parseInline(block) }
}

function parseInline(text: string): InlineNode[] {
  const nodes: InlineNode[] = []
  let lastIndex = 0
  for (const match of text.matchAll(INLINE_RE)) {
    const index = match.index ?? 0
    if (index > lastIndex) nodes.push({ type: 'text', text: text.slice(lastIndex, index) })
    const [, bold, code, company, page] = match
    if (bold !== undefined) {
      nodes.push({ type: 'bold', children: parseInline(bold) })
    } else if (code !== undefined) {
      nodes.push({ type: 'code', text: code })
    } else if (company !== undefined && page !== undefined) {
      nodes.push({ type: 'citation', company: company.trim(), page: Number(page) })
    }
    lastIndex = index + match[0].length
  }
  if (lastIndex < text.length) nodes.push({ type: 'text', text: text.slice(lastIndex) })
  return nodes
}

// A company can have several fiscal years with identical page numbers. Never guess the report.
export function matchCitation(company: string, page: number, citations: Citation[]): Citation | undefined {
  const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')
  const year = company.match(/\bFY\s*(\d{4})\b/i)?.[1]
  const name = norm(company.replace(/\bFY\s*\d{4}\b/ig, ''))
  const candidates = citations.filter((c) => c.page === page && (!year || c.fiscal_year === Number(year)))
  const exact = candidates.filter((c) => c.company && norm(c.company) === name)
  const matches = exact.length ? exact : candidates.filter((c) => {
    const candidate = norm(c.company ?? '')
    return name && candidate && (candidate.includes(name) || name.includes(candidate))
  })
  return new Set(matches.map((c) => c.report_id)).size === 1 ? matches[0] : undefined
}
