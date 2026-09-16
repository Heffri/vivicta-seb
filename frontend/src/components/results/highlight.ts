import type { Field } from '@/types'

// The product's whole argument is "this number ← this line on that page". Highlighting the
// value inside the verbatim quote is the display side of it. Reports print numbers with
// locale furniture, so the matcher accepts a small set of shapes — optional separators
// between the thousands groups (space / NBSP / thin space / . , '), "." or "," as the
// decimal separator (Swedish reports use the comma), and for negatives an en dash "–",
// real minus "−" or hyphen prefix, or accounting parentheses. Anything it can't read is
// not an error: the quote just renders without a highlight.

const THOUSANDS = "[\\u00a0\\u2009\\u202f\\s.,']?" // optional separator between thousands groups
const NEGATIVE = '\\u2013\\u2212-' // en dash, real minus, hyphen — Swedish reports use the en dash

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function valueRegExp(v: Field['value']): RegExp | null {
  if (v === null) return null
  if (typeof v === 'string') {
    const s = v.trim()
    return s ? new RegExp(`(?<!\\d)${escapeRegExp(s)}(?!\\d)`) : null
  }
  const [int, dec] = String(Math.abs(v)).split('.')
  const groups = int.match(/\d{1,3}(?=(?:\d{3})*$)/g) // 168343 → ["168", "343"], 96131 → ["96", "131"]
  if (!groups) return null
  const core = groups.join(THOUSANDS) + (dec ? `[.,]${dec}0*` : '') // 0*: "4,80" printed for a stored 4.8
  const before = '(?<!\\d)' // never start inside a longer number
  const after = dec ? '(?!\\d)' : '(?![.,]?\\d)' // a stored 5 must not light up inside "5.43"
  const body = v < 0 ? `(?:[${NEGATIVE}]${core}|\\(${core}\\)|${core})` : core
  return new RegExp(`${before}${body}${after}`)
}

export type QuoteRun = { text: string; hit: boolean }

/** Split `quote` around the first printed form of `value` found in it. Pure display helper:
 *  no match (or an engine that rejects a lookbehind) returns the whole quote as one plain run. */
export function highlightQuote(quote: string, value: Field['value']): QuoteRun[] {
  try {
    const m = valueRegExp(value)?.exec(quote)
    if (!m || m[0] === '') return [{ text: quote, hit: false }]
    const end = m.index + m[0].length
    return [
      ...(m.index > 0 ? [{ text: quote.slice(0, m.index), hit: false }] : []),
      { text: m[0], hit: true },
      ...(end < quote.length ? [{ text: quote.slice(end), hit: false }] : []),
    ]
  } catch {
    return [{ text: quote, hit: false }]
  }
}
