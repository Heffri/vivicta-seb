# Docling vs our parser — parsing-step comparison (time-boxed, decision: not worth pursuing further)

## TL;DR

Docling's out-of-the-box settings (`TableFormerMode.ACCURATE` + `do_ocr=True`) are **~270x slower**
than this project's own parser (`backend/pipeline/parse.py`) on the same PDF, with no accuracy
upside demonstrated — the accuracy comparison itself couldn't be completed in the time available,
because the two companies with actual ground truth (`atlas_copco_2025`, `ericsson_2025`) have too
many pages to convert at the observed rate within a reasonable budget. Decision: kill the remaining
background conversions and report what was actually measured, rather than wait ~1.5-2h more for
numbers that would still only cover 10 labelled fields total.

## What was measured (real, completed)

Same PDF (`skf_2025.pdf`, 163 pages) through both parsers, isolating the parsing step only:

| parser | time | notes |
|---|---|---|
| ours (`parse.py`) | 6.3s | full 163-page text extraction |
| Docling (`ACCURATE` table mode + OCR) | 1710s (1619s convert + 91s export) | same 163 pages, CPU-only, no GPU on this machine |

**~271x slower**, same file, same page count, apples-to-apples.

## What was NOT measured, and why

`eval/labels.csv` only has ground-truth rows for 2 of the 5 benchmark PDFs:
**atlas_copco_2025** (income_statement, 8 rows) and **ericsson_2025** (debt_maturity, 2 rows).
`investor_2025`, `saab_2025`, and `skf_2025` have zero labelled rows for either section — so even a
completed conversion of those three would never produce a scored accuracy number, only a parse-time
one.

At the ~10.5s/page rate measured on `skf_2025`, converting the two PDFs that actually matter for
accuracy would take:

| stem | pages | est. Docling convert time |
|---|---|---|
| atlas_copco_2025 | 174 | ~30 min |
| ericsson_2025 | 236 | ~41 min |

Neither fit the time available. The background conversion (`docling_convert.py --all`, covering
atlas_copco/ericsson/investor/saab) was killed rather than left running for ~1.5-2h to score just
10 labelled fields total across both companies.

## The one real capability gap found

`atlas_copco_2025` contains scanned pages and triggered our own parser's `OCRUnavailable` error:
when this ran, `parse.py` had no OCR fallback at all, while Docling ships OCR on by default.

Since closed: `parse.py` now runs a bounded, selective OCR pass over the pages a locate pass would
target (`OCR_PAGE_BUDGET`, default 40 pages) and raises `OCRUnavailable` only when the Tesseract
language files are missing — `scripts/setup_ocr.py` installs them. It was a capability difference
either way, not something the (incomplete) accuracy numbers above can speak to, and it never
required paying Docling's ~270x time cost across an entire document just to cover the scanned pages
within it.

## Verdict for the jury deck

**Not worth it at default settings.** Docling costs ~270x the parse time of this project's own
parser on a report that didn't even need OCR, and the only demonstrated advantage (handling scanned
pages atlas_copco_2025 needs) was a narrow gap in our own parser — since closed — rather than
evidence Docling wins on accuracy. A real accuracy comparison remains untested — this is a speed
verdict, stated as such, not a disguised accuracy one.

## Raw numbers

`experiments/docling/cache/` and `experiments/docling/pdfs/` are gitignored local artifacts — the
paths below were not committed and are not in a fresh clone.

- `experiments/docling/cache/skf_2025.json` — Docling's own conversion output/timing for skf_2025
  (`num_pages: 163, convert_seconds: 1619.108, export_seconds: 90.991, status: SUCCESS`).
- Our own parser's timing (6.307s, 163 pages) measured directly against the same
  `experiments/docling/pdfs/skf_2025.pdf`, in that session, not re-derived from cached KB text.
- Page counts for the two labelled-but-unconverted stems (`atlas_copco_2025`: 174,
  `ericsson_2025`: 236) via `fitz.open(path).page_count` on the downloaded PDFs in
  `experiments/docling/pdfs/`.
