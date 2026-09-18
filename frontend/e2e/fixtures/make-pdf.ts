// Hand-rolled, dependency-free PDF bytes: an N-page document, empty pages (no /Contents — valid
// per the spec, MuPDF renders it as blank). The fixture-mode backend never reads page content
// (backend/app.py's run_extract returns the canned fixtures/sample_extraction.json regardless of
// what was uploaded — see common.md); only the page COUNT matters, so a citation's page image
// (GET /api/reports/{id}/pages/64.png) doesn't 404 on a report with fewer than 64 pages.
// Verified against the real backend (upload + extract + ask + pages/64.png all 200) before this
// landed — see the evidence doc.

const EOL = '\r\n' // xref entries must be exactly 20 bytes each; CRLF is the spec-safe line ending

function xrefEntry(offset: number, generation: number, kind: 'n' | 'f'): string {
  return `${String(offset).padStart(10, '0')} ${String(generation).padStart(5, '0')} ${kind}${EOL}`
}

export function makePdf(pageCount: number): Buffer {
  if (!Number.isInteger(pageCount) || pageCount < 1) {
    throw new Error(`makePdf: pageCount must be a positive integer, got ${pageCount}`)
  }

  const pageRefs = Array.from({ length: pageCount }, (_, i) => `${i + 3} 0 R`).join(' ')
  const objects = [
    `1 0 obj${EOL}<< /Type /Catalog /Pages 2 0 R >>${EOL}endobj${EOL}`,
    `2 0 obj${EOL}<< /Type /Pages /Kids [${pageRefs}] /Count ${pageCount} >>${EOL}endobj${EOL}`,
    ...Array.from(
      { length: pageCount },
      (_, i) => `${i + 3} 0 obj${EOL}<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>${EOL}endobj${EOL}`,
    ),
  ]

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
