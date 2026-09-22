export type TextSpan = { text: string; start: number; end: number }
export type EvidenceRange = { start: number; end: number }
export type SourceBlock =
  | { type: 'text'; lines: TextSpan[] }
  | { type: 'table'; headers: TextSpan[]; rows: { label: TextSpan[]; values: TextSpan[] }[] }

const amount = /^(?:[$€£]\s*)?(?:[−–-]?\d[\d.,'’\u00a0\u2009\u202f ]*%?|\([\d.,'’\u00a0\u2009\u202f ]+\)|[—–-])$/
const year = /^(?:19|20)\d{2}$/
const note = /^(?:note|notes|not|noter)$/i

function inlineTable(lines: TextSpan[], start: number): { block: SourceBlock; end: number; title?: TextSpan } | null {
  const header = lines[start]
  // Explicit maturity headings are retained verbatim, including Swedish labels.
  let matches = [...header.text.matchAll(/(?:[<>≤≥]\s*)?\d+(?:\s*[-–]\s*\d+)?\s*(?:years?|år|months?|månader)|\b(?:Total|Summa|Totalt)\b/gi)]
  // Current parser versions also put year headers and numeric cells on the same line.
  const yearSuffix = header.text.match(/\b(?:19|20)\d{2}(?:\s+(?:19|20)\d{2}){1,3}$/)
  if (yearSuffix) {
    matches = [...header.text.matchAll(/\b(?:19|20)\d{2}\b/g)].filter(m => m.index! >= yearSuffix.index!)
    if (!matches.every((m, i) => !i || Number(matches[i - 1][0]) - Number(m[0]) === 1)) return null
  }
  if (matches.length < 2 || matches.at(-1)!.index! + matches.at(-1)![0].length !== header.text.length) return null
  const first = matches[0].index!
  if (!yearSuffix && header.text.slice(first).replace(/(?:[<>≤≥]\s*)?\d+(?:\s*[-–]\s*\d+)?\s*(?:years?|år|months?|månader)|\b(?:Total|Summa|Totalt)\b/gi, '').trim()) return null
  const headers = matches.map(m => ({ text: m[0], start: header.start + m.index!, end: header.start + m.index! + m[0].length }))
  const rows: { label: TextSpan[]; values: TextSpan[] }[] = []
  let cursor = start + 1
  const token = /^(?:[−–-]?\d+(?:[.,]\d+)*%?|\(\d+(?:[.,]\d+)*\)|[—–-])$/
  while (cursor < lines.length) {
    const line = lines[cursor]
    const parts = [...line.text.matchAll(/\S+/g)]
    const values = parts.slice(-headers.length)
    const labelEnd = values[0]?.index ?? 0
    if (parts.length <= headers.length || !values.every(v => token.test(v[0]))) break
    const label = line.text.slice(0, labelEnd).trimEnd()
    // A label ending in a number suggests ambiguous space-separated thousands; don't guess.
    if (/\d$/.test(label)) break
    rows.push({ label: [{ text: label, start: line.start, end: line.start + label.length }], values: values.map(m => ({ text: m[0], start: line.start + m.index!, end: line.start + m.index! + m[0].length })) })
    cursor++
  }
  if (rows.length < 2) return null
  const title = header.text.slice(0, first).trimEnd()
  return { block: { type: 'table', headers, rows }, end: cursor, title: title ? { text: title, start: header.start, end: header.start + title.length } : undefined }
}

/** Reconstruct only explicit year columns followed by consistently sized numeric rows.
 * Keep offsets into the untouched page so highlighting never invents or moves evidence. */
export function sourceDocument(text: string): SourceBlock[] {
  let offset = 0
  const lines = text.split('\n').map(line => {
    const start = offset + (line.match(/^\s*/)?.[0].length ?? 0)
    offset += line.length + 1
    return { text: line.trim(), start, end: start + line.trim().length }
  })
  const blocks: SourceBlock[] = []
  const plain = (line: TextSpan) => {
    const last = blocks.at(-1)
    if (last?.type === 'text') last.lines.push(line)
    else blocks.push({ type: 'text', lines: [line] })
  }
  for (let i = 0; i < lines.length;) {
    const inline = inlineTable(lines, i)
    if (inline) { if (inline.title) plain(inline.title); blocks.push(inline.block); i = inline.end; continue }
    const hasNote = note.test(lines[i].text)
    const yearStart = i + (hasNote ? 1 : 0)
    let headerEnd = yearStart
    while (headerEnd < lines.length && year.test(lines[headerEnd].text)) headerEnd++
    const years = lines.slice(yearStart, headerEnd)
    const headers = lines.slice(i, headerEnd)
    const validYears = years.length >= 2 && years.length <= 4 && years.every((h, n) => !n || Number(years[n - 1].text) - Number(h.text) === 1)
    if (!validYears) { plain(lines[i++]); continue }
    const rows: { label: TextSpan[]; values: TextSpan[] }[] = []
    let cursor = headerEnd
    while (cursor < lines.length) {
      while (cursor < lines.length && !lines[cursor].text) cursor++
      let valueStart = cursor
      while (valueStart < lines.length && lines[valueStart].text && !amount.test(lines[valueStart].text) && valueStart - cursor < 4) valueStart++
      const label = lines.slice(cursor, valueStart)
      if (!label.length) break
      // Section labels inside a statement retain their own row, without taking the next label.
      if (label[0].text.endsWith(':')) {
        rows.push({ label: [label[0]], values: [] }); cursor++; continue
      }
      while (valueStart < lines.length && !lines[valueStart].text) valueStart++
      let valueEnd = valueStart
      while (valueEnd < lines.length && amount.test(lines[valueEnd].text)) valueEnd++
      const values = lines.slice(valueStart, valueEnd)
      if (values.length !== headers.length && !(hasNote && values.length === years.length)) break
      if (hasNote && values.length === years.length) values.unshift({ text: '', start: valueStart < lines.length ? lines[valueStart].start : 0, end: valueStart < lines.length ? lines[valueStart].start : 0 })
      rows.push({ label, values })
      cursor = valueEnd
    }
    if (rows.filter(row => row.values.length).length < 2) { plain(lines[i++]); continue }
    blocks.push({ type: 'table', headers, rows })
    i = cursor
  }
  return blocks
}

function normalized(text: string) {
  const characters: string[] = []
  const offsets: number[] = []
  for (let i = 0; i < text.length; i++) {
    const char = /\s/.test(text[i]) ? ' ' : text[i]
    if (char === ' ' && characters.at(-1) === ' ') continue
    characters.push(char); offsets.push(i)
  }
  return { text: characters.join(''), offsets }
}

/** Match full verified quotes across PDF line breaks, not isolated values elsewhere on a page. */
export function evidenceRanges(text: string, quotes: string[]): EvidenceRange[] {
  const haystack = normalized(text)
  const ranges: EvidenceRange[] = []
  for (const quote of new Set(quotes)) {
    const needle = normalized(quote).text.trim()
    if (!needle) continue
    for (let from = 0; from < haystack.text.length;) {
      const at = haystack.text.indexOf(needle, from)
      if (at < 0) break
      ranges.push({ start: haystack.offsets[at], end: haystack.offsets[at + needle.length - 1] + 1 })
      from = at + needle.length
    }
  }
  return ranges.sort((a, b) => a.start - b.start)
}

// Horizontal thousands separators only: two figures on separate PDF lines stay separate.
const numbers = /[−–-]?(?:\d{1,3}(?:[,.'’\u00a0\u2009\u202f ]\d{3})+|\d+)(?:[.,]\d+)?%?/g
export function evidenceRuns(span: TextSpan, ranges: EvidenceRange[]) {
  const cuts = new Set([0, span.text.length])
  const hits = ranges.map(r => ({ start: Math.max(0, r.start - span.start), end: Math.min(span.text.length, r.end - span.start) })).filter(r => r.end > r.start)
  const figures = [...span.text.matchAll(numbers)].map(m => ({ start: m.index!, end: m.index! + m[0].length }))
    .filter(f => hits.some(r => f.start >= r.start && f.end <= r.end))
  for (const r of [...hits, ...figures]) { cuts.add(r.start); cuts.add(r.end) }
  const edges = [...cuts].sort((a, b) => a - b)
  return edges.slice(0, -1).map((start, i) => {
    const end = edges[i + 1]
    const cited = hits.some(r => start >= r.start && end <= r.end)
    return { text: span.text.slice(start, end), cited, number: cited && figures.some(r => start >= r.start && end <= r.end) }
  })
}
