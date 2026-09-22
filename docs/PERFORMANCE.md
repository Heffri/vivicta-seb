# Demo performance verification, 20 September 2026

> **Where these numbers come from (added 21 September 2026, no re-test):** every measurement on
> this page — the **26.748 s** fresh-extraction median included — was taken on the 20 September
> revision, before the 21 September main-branch integration (see that section below). The
> integrated app has since changed the pieces these timings ran through: extraction calls go
> through a shared `pipeline.llm` (isolated Codex calls, low reasoning by default), retrieval
> combines the BM25 scorer with local embeddings behind a verified index manifest, and parser 7
> added selective OCR. Cached-repeat lookups (~6 ms) and the general shape "fresh extraction is
> a model call, repeats are free" still hold; the exact seconds should be quoted as *that
> revision's* numbers, not the current build's. Nothing here was re-measured for the integrated
> app.

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


## Main-branch integration (21 September 2026)

The September 20 measurements above describe that revision, not a new performance
claim for the integrated app. The current main branch's analyst reviews, saved-year
comparisons, desktop update channels and deterministic debt extraction are retained.
Its shared `pipeline.llm` replaces the earlier standalone runtime adapter, with
isolated Codex calls and low reasoning by default. Retrieval now combines the newer
BM25 scorer with independent local embeddings and verified index manifests. Parser 7
retains the newer geometric table/header fixes and adds selective OCR. Existing
source caches/indexes refresh once when used.

The integration suite contains 12 runtime checks plus the existing confidence, KB,
global Ask, provider, parser, locator, multi-run merge, path, collection, review and
workbench checks. Frontend type checking and production build pass. Desktop releases
include English/Swedish OCR language files and run the runtime/OCR checks before
packaging. Historical benchmark artifacts remain available for comparison.

Live integration verification also caught a free-text CLI response where JSON was required.
CLI schema output is now enabled by default (LLM_STRICT_SCHEMA=0 retains compatibility
with older CLIs), and failed Ask generation returns an actionable 502.
Live verification after integration returned Ericsson FY2025 revenue of SEK 236,681
million with a verified page-33 quote and no warnings. The browser showed the ready
bge-m3 index (1024 dimensions), passage/fact counts, Inspect and Rebuild. Eight desktop
update/data-sync tests also passed.


## Held-out first extraction — round 1 (Small Cap, blind labels; subsequently used for guard tuning)

This historical, deliberately small measurement is not a market-accuracy estimate. Its fixed
sample was ten FY2025 Small Cap reports drawn with `seed=1`; none had appeared in the seed sets
or `eval/labels.csv`. PDFs, registration, pages and extractions lived in an isolated data
directory; the repository KB and label set were neither read as few-shot context nor changed.
The human labels were committed before the sealed first-extraction results were opened.

The shipped configuration is **`EXTRACT_MERGE_RUNS=off`**, so its raw output was the primary
round-1 result:

| configuration | model extraction calls | value accuracy | cited-page hit rate | empty misses | non-empty wrong values |
| --- | ---: | --- | --- | ---: | ---: |
| default `off` (primary) | 10 | **26/40 (65.0%)** | **8/17 (47.1%)** | 5 | 9 |
| `majority` (non-default comparison, same frozen labels) | 14 | 27/40 (67.5%) | 8/17 (47.1%) | 5 | 8 |

These measurements used **24 extraction calls total**, below their 40-call budget. Majority's
only value change was to withhold Sedana Medical's false-positive total (lease/acquisition
liabilities), making that null label correct; it did not improve a cited page. No result caused a
label, schema, prompt, or pipeline change.

Round 1 was subsequently inspected to attribute failures and develop the v185/v186 guards. It is
therefore no longer the current held-out benchmark; it remains a documented historical first-run
measurement. See [v178](acrylic/evidence/v178.md) for its fixed sample, skips, score vectors,
configuration, and blind-label chronology.

## Held-out first extraction — round 2 (Small Cap, current held-out)

Round 2 is the current blind held-out measurement. It is a separate ten-report FY2025 Small Cap
sample drawn with `seed=2`, excluding round 1's 17 extracted-or-skipped companies. Labels in
`eval/heldout-smallcap-2025-r2.csv` were committed before any extraction output was opened. PDFs,
registration, pages, raw runs, and snapshots remained under an isolated data directory; the
repository KB and `labels.csv` were not read or changed. `LLM_PROVIDER=codex`,
`LLM_MODEL=gpt-5.6-terra`, and `FEWSHOT=0`; the primary run left merge at its shipped `off`
default.

| configuration | model extraction calls | value accuracy | cited-page hit rate | empty misses | non-empty wrong values |
| --- | ---: | --- | --- | ---: | ---: |
| default `off` (primary) | 18 | **36/40 (90.0%)** | **14/17 (82.4%)** | 1 | 3 |
| `majority` (non-default comparison, same frozen labels) | 22 | 36/40 (90.0%) | 14/17 (82.4%) | 1 | 3 |
| `EXTRACT_SECOND_PASS=1` (w211 decision run, same frozen labels) | 41 (16 first-pass + 25 follow-up) | 29/40 (72.5%) | 12/17 (70.6%) | 3 | 8 |

Round 2 used **40 extraction calls total**, exactly its cap. Eight majority comparisons matched the
stored default answer after one run; two needed a second run. The comparison changed no scored
value or cited page, and no result caused a label, schema, prompt, or pipeline change. The sample
fill encountered nine fetch skips: eight scan/OCR 422 cases and one non-JSON HTTP 500; round-1
exclusions are tracked separately. This is an n=10 measurement, not a market-accuracy claim. See
[v190](acrylic/evidence/v190.md) for the sample, skip handling, frozen-label chronology, snapshots,
and per-company score vectors.

The w211 decision run used the current pipeline with merge off and every other optional extraction
switch unset. The follow-up cost averaged **+2.5 model calls and +18.4 model seconds per report**.
Model variation made that run's pre-follow-up answer score 31/40 values and 12/17 pages; applying
the second pass to the same answers then reduced the score to 29/40 by adding two non-empty wrong
values and no correct fill. It therefore failed the rule that values must not fall and non-empty
wrong values must not rise. `EXTRACT_SECOND_PASS` remains **off by default**; see
[w211](acrylic/evidence/w211.md).
