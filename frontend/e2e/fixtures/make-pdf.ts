// Hand-rolled, dependency-free PDF bytes: an N-page document, empty pages (no /Contents — valid
// per the spec, MuPDF renders it as blank). The fixture-mode backend DOES read page
// text at upload time (the zero-model candidate-pages locator scores it — backend/app.py's
// GET /candidates), so `pageTexts` prints lines on individual pages in standard Helvetica
// (base-14 font, nothing to embed). The extraction itself still ignores page content — it returns
// the canned backend/fixtures/sample_extraction.json regardless of what was uploaded — only the
// page COUNT matters there, so a citation's page image (GET /api/reports/{id}/pages/64.png)
// doesn't 404 on a report with fewer than 64 pages. Verified against the real backend (upload +
// extract + ask + pages/64.png all 200).

const EOL = '\r\n' // xref entries must be exactly 20 bytes each; CRLF is the spec-safe line ending

function xrefEntry(offset: number, generation: number, kind: 'n' | 'f'): string {
  return `${String(offset).padStart(10, '0')} ${String(generation).padStart(5, '0')} ${kind}${EOL}`
}

// PDF literal string: backslash and the delimiters need escapes; anything outside printable
// ASCII would need a codepage story, so it fails loudly instead of printing mojibake.
function pdfLine(line: string): string {
  if (/[^\x20-\x7E]/.test(line)) throw new Error(`makePdf: page text must be printable ASCII, got ${JSON.stringify(line)}`)
  return line.replace(/[\\()]/g, (c) => `\\${c}`)
}

function textStream(text: string): { body: string; length: number } {
  // T* (move to the next line per the leading set above) must run BEFORE the line it moves down
  // for, not after the line just drawn. Placed after, it draws every line but the first on top of
  // its predecessor (T* only ever advances position for a line that doesn't exist), and a
  // multi-line pageTexts entry silently collapses into one overlapping run that get_text() /
  // search_for() reads back as a single line with no separator.
  const body = `BT${EOL}/F1 9 Tf${EOL}13 TL${EOL}72 720 Td${EOL}${text
    .split('\n')
    .map((l, i) => `${i === 0 ? '' : `T*${EOL}`}(${pdfLine(l)}) Tj${EOL}`)
    .join('')}ET`
  return { body, length: Buffer.byteLength(body, 'ascii') }
}

export function makePdf(pageCount: number, pageTexts?: readonly (string | undefined)[]): Buffer {
  if (!Number.isInteger(pageCount) || pageCount < 1) {
    throw new Error(`makePdf: pageCount must be a positive integer, got ${pageCount}`)
  }
  const texts = pageTexts ?? []
  if (texts.length > pageCount) {
    throw new Error(`makePdf: got ${texts.length} page texts for a ${pageCount}-page document`)
  }

  // Object numbering: 1 catalog, 2 pages, 3..n+2 page objects, then (when any page has text)
  // one Helvetica font object and one content stream per text page. Stream numbers must be
  // known before the page objects are written, so they are assigned in a first pass.
  const fontObj = pageCount + 3
  const streamObjs = new Map<number, { body: string; length: number }>()
  let nextStream = fontObj + 1
  const pageExtra: string[] = []
  texts.forEach((text, i) => {
    if (!text) {
      pageExtra[i] = ''
      return
    }
    const stream = textStream(text)
    streamObjs.set(nextStream, stream)
    pageExtra[i] = ` /Contents ${nextStream} 0 R /Resources << /Font << /F1 ${fontObj} 0 R >> >>`
    nextStream++
  })

  const pageRefs = Array.from({ length: pageCount }, (_, i) => `${i + 3} 0 R`).join(' ')
  const objects = [
    `1 0 obj${EOL}<< /Type /Catalog /Pages 2 0 R >>${EOL}endobj${EOL}`,
    `2 0 obj${EOL}<< /Type /Pages /Kids [${pageRefs}] /Count ${pageCount} >>${EOL}endobj${EOL}`,
    ...Array.from(
      { length: pageCount },
      (_, i) => `${i + 3} 0 obj${EOL}<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]${pageExtra[i] ?? ''} >>${EOL}endobj${EOL}`,
    ),
  ]
  const hasText = streamObjs.size > 0
  if (hasText) {
    objects.push(`${fontObj} 0 obj${EOL}<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>${EOL}endobj${EOL}`)
    for (const [num, stream] of streamObjs) {
      objects.push(`${num} 0 obj${EOL}<< /Length ${stream.length} >>${EOL}stream${EOL}${stream.body}${EOL}endstream${EOL}endobj${EOL}`)
    }
  }

  const header = `%PDF-1.4${EOL}`
  let body = ''
  const offsets: number[] = [0] // object 0 is the free-list head, never itself written below
  let cursor = Buffer.byteLength(header, 'ascii')
  for (const obj of objects) {
    offsets.push(cursor)
    body += obj
    cursor += Buffer.byteLength(obj, 'ascii')
  }

  const objectCount = objects.length + 1 // + the free entry
  const xrefOffset = cursor
  let xref = `xref${EOL}0 ${objectCount}${EOL}` + xrefEntry(0, 65535, 'f')
  for (let i = 1; i < objectCount; i++) xref += xrefEntry(offsets[i], 0, 'n')

  const trailer = `trailer${EOL}<< /Size ${objectCount} /Root 1 0 R >>${EOL}startxref${EOL}${xrefOffset}${EOL}%%EOF`

  return Buffer.from(header + body + xref + trailer, 'ascii')
}
