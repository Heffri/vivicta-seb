# Demo performance verification, 20 September 2026

Provider: Codex CLI using the existing ChatGPT login, `gpt-5.6-terra`, low reasoning.
Embeddings: local Ollama `bge-m3`, 1024 dimensions. One extraction at a time.
Five cached PDFs, two sections per PDF. Benchmark few-shot examples were disabled to
keep prompts independent of run order. Generated KB data used a temporary directory.

| Report | Income statement | Debt maturity | Cold index | Ask with ready index |
|---|---:|---:|---:|---:|
| Atlas Copco | 26.810 s | 26.685 s | 32.541 s | 7.982 s |
| Ericsson | 24.478 s | 15.060 s | 33.024 s | 12.704 s |
| Investor | 22.923 s | 29.520 s | 22.308 s | 7.941 s |
| Saab, English PDF | No text candidates | No text candidates | No indexable text | Not run |
| SKF | 30.988 s | 29.202 s | 22.610 s | 10.071 s |

Successful fresh extraction median: **26.748 seconds**. Immediate repeats: **6 ms
median, 6–7 ms range**, with zero model calls. Timings are backend processing times,
not browser round-trip measurements. This measures removal of repeated work, not an
improvement in fresh model inference over a previous model. No previous-model latency
baseline was taken. Registration time is reported separately in the raw results.

All four Ask runs returned one verified citation and no warnings. A separate request
through the running FastAPI server returned Ericsson revenue of SEK 236,681 million,
citing page 33 with a verified quote.

All eight matching numerical labels available in `eval/labels.csv` matched the benchmark
output. This is limited coverage, not a claim of accuracy across all fields or reports.
The initial pass left debt maturity incomplete and Saab unreadable. Follow-up source review
found that Investor's apparently passing debt result was a lease-only table, not group
borrowings. The follow-up below supersedes that result.

Verification: existing confidence checks, seven offline cache/provider regression tests,
API smoke checks, TypeScript compilation, Vite production build, and manual browser checks
for KB filtering, chunk search, and page links. Lint has five existing Fast Refresh export
warnings and no errors. The smoke suite's unknown-company path ran with network restricted,
so that check establishes error handling rather than live report discovery.

Reproduce from the repository root:

```powershell
backend/.venv/Scripts/python scripts/benchmark.py --live --index --count 5 --output benchmark-results.json
```

Raw measurements are in `benchmark-results.json` at the repository root. The corpus was
not replaced by benchmark results. Only Ericsson's derived embedding index was rebuilt
in the real KB to verify the live application. Legacy indexes require rebuilding before
retrieval because their embedding model was never recorded.


## Follow-up: component evidence and OCR (20 September 2026)

Debt extraction now verifies and sums printed components, preserves their individual
page/quote references, uses consolidated carrying amounts, and withholds a maturity
split when its components do not reconcile. The UI and CSV show component evidence.

- Atlas Copco: 34,899 = 6,471 + 16,025 + 12,403 MSEK. All four values verified on
  PDF page 135, including visual inspection of the maturity table.
- Ericsson: 32,703 total and 3,538 current, excluding leases. Other buckets remain
  unavailable. The parent-company schedule and interest-inclusive contractual cash
  flows cannot fill consolidated carrying-amount buckets. In particular, 29,165 of
  non-current borrowings is NOT established as all due within five years.
- Investor: component sum 115,312 total and 1,424 current, including leases and
  excluding derivatives. The lease-only maturity table is no longer substituted for
  all borrowings. Remaining buckets are unavailable. These component sums can differ
  from printed subtotals due to rounding.
- SKF: 14,984 total including leases. A 2,167 long-term lease amount crosses the
  five-year boundary. The unreconciled maturity split is withheld, including its
  otherwise-readable current bucket, rather than publishing incomplete buckets.

Fresh debt calls in the four-report run took 19.5–49.5 seconds. Repeats took 6–8 ms
with zero model calls. See `debt-benchmark-results.json`; its SKF row predates the
final withholding guard, verified separately in `debt-skf-check.json`. These are
small-sample checks, not a broad accuracy evaluation.

Saab's English PDF contains outlined text with no usable text layer. The local OCR
pass took 506 seconds for 231 pages; cached registration took 56 ms. Seven income
figures were recovered and checked against the rendered page 151: revenue 79,146,
gross profit 17,168, operating profit 8,066, pretax profit 8,019, tax -1,663, net
profit 6,356, and basic EPS 11.77. Cost of sales remained null because OCR did not
read it reliably. Its correct visible amount is -61,978; arithmetic alone is not
accepted as printed evidence. Debt extraction recovered 9,785 total on page 194,
but its current quote did not verify and longer buckets lacked carrying-amount
disaggregation. See `ocr-benchmark-results.json`. That timing run preceded the
additional 80% confidence cap now applied to OCR-sourced fields.

OCR uses PyMuPDF's bundled Tesseract engine and official English/Swedish fast
language data. No OCR server or report upload is used. OCR is fallible, and debt
scope/column interpretation still depends on the extraction model. Confidence is
not an accuracy probability. No fabricated zero fills or inferred missing buckets.

Verification: seven existing runtime tests, confidence checks, component/OCR regression
checks (including wrong scope/year/quote, duplicate components and unreconciled
subtotals), TypeScript and production build. Existing Fast Refresh lint warnings remain.


## Reliability follow-up

- Export URLs now name their section. Opening debt after income cannot silently
  replace the CSV/PPTX content the income view requests. Decimal values, missing
  fields and component sources survive PPTX export. Strict unsigned chart-axis IDs
  also fix an import failure seen during visual verification.
- Ask identifies each citation by report ID, so two years of the same issuer cannot
  be resolved by an ambiguous company-name match. Quotes must appear in both the
  retrieved excerpt and the source page. Answers with rejected citations are withheld.
- Fact chunks require matching fiscal year, printed amounts, verified source quotes
  and sufficient confidence. Derived sums and failed-check results no longer enter
  retrieval as if they were printed on one source page. Page passages remain available.
- OCR settings and page provenance now survive uploads, reopen and CLI cache reuse.
- Explicit Rebuild recomputes embeddings. Normal automatic refresh still reuses
  compatible vectors. Chunker version 2 requires existing indexes to refresh once.
- Saved-result views show staleness and load time rather than the original model-call
  count. Chunk inspection clears old search results and labels outdated content.

Regression suite: 12 offline runtime tests plus confidence and maturity/OCR checks.
Export QA: complete maturity chart, incomplete debt table and income table rendered
with the bundled presentation engine and inspected. TypeScript, build and lint checked.

Live Ask verification returned Ericsson FY2025 revenue of SEK 236,681 million from
page 33 with a verified citation and no warnings. This first request rebuilt its
index under the new fact rules. A concurrency check additionally verifies that KB
status listing returns `building` immediately while a report index lock is held,
rather than waiting for the embedding request to finish.
