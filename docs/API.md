# API contract — backend ⇄ frontend

Frontend and backend are built in parallel against this document. Change it here first, then code.
Backend runs on `http://localhost:8000`, frontend dev server proxies `/api` to it.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET`  | `/api/schemas` | – | `Schema[]` (section definitions, see below) |
| `POST` | `/api/reports?ocr=bounded\|full` | `multipart/form-data`, field `file` = PDF | `Report` — `ocr` (v191, default `bounded`) bounds a scanned PDF's registration OCR to the pages a debt-maturity locate pass could reach; `full` OCRs every such page unconditionally. See "Bounded OCR" below |
| `GET`  | `/api/reports/{report_id}` | – | `Report` |
| `POST` | `/api/reports/{report_id}/extract` | `{ "section": "<schema name>" }` | `Extraction` (synchronous; may take up to ~60 s with a local model) |
| `POST` | `/api/reports/{report_id}/fill?section=<schema name>` | `{ "field": "<empty schema key>", "pages": [<one or two 1-based pages>] }` | `{ candidate: Field \| null, warnings: string[] }` — an analyst-directed, one-field candidate; it never saves or replaces the extraction |
| `GET`  | `/api/reports/{report_id}/candidates` | `?section=<schema name>` | `[{ page, heading }]` — the section's ranked candidate pages (1-based, best first), from the same deterministic locator the extractor runs, computed with no model call (fixture mode included). `heading` is the page's de-boilerplated opening, whitespace-normalized, ≤80 chars. Powers the extraction waiting UI (v164) |
| `GET`  | `/api/reports/{report_id}/pages/{n}.png` | – | PNG of page `n` (1-based), ~150 dpi. 404 if out of range |
| `GET`  | `/api/reports/{report_id}/pages/{n}/locate` | `?quote=<verbatim text>` | `{ page, width, height, matched: "quote"\|"line"\|"value"\|"none", rects: [[x0,y0,x1,y1], ...], occurrences }` — zero-model (v179): where `quote` sits on page `n`, in page-point coordinates (the same top-down space `pages/{n}.png` renders, so a box scales directly against the image's rendered width/height). Tries `quote` verbatim, then its own longest line (a citation that never prints as one contiguous run), then the longest digit run inside it. `rects` holds one box per *printed line* a hit touches — a match spanning two lines (an ordinary wrapped citation) reports two adjacent rects the same way a genuine second occurrence would add two more, so `occurrences` divides that back out by the searched text's own line count: a wrapped citation reports `occurrences: 1` (still with 2 rects to draw), a truly repeated line reports 2+. `matched: "none"`, empty `rects`, `occurrences: 0` when nothing was found. 404 if `n` is out of range, 409 if the PDF is no longer cached (`require_pdf`, same as the other page endpoints) |
| `GET`  | `/api/reports/{report_id}/extraction.csv` | – | last extraction for this report as CSV (one row per field). 404 if none |
| `GET`  | `/api/reports/{report_id}/pdf` | – | the PDF itself, `Content-Disposition: inline`, so `<iframe src=".../pdf#page=64">` opens the browser's own viewer on that page |
| `GET`  | `/api/companies?q=<text>&collection_name=wallenberg\|midcap\|all` | – | `Company[]` — the listed-company directory (`data/companies.json`, Nasdaq Stockholm), filtered by collection then name/ticker substring; max 50. Empty `q` = first 50. `midcap` is the 132 companies whose `market` is `Mid Cap` |
| `POST` | `/api/reports/discover` | `{ "company": "<typed query>", "year": 2025, "country"?, "hint"?, "job_id"? }` | `{ candidates: Candidate[], note: string \| null }` — which legal entities the query could mean, for the user to confirm one **before** anything is downloaded. Saved reports for that year first (`saved: true`, no model call), then one model web-search ask for up to 5 distinct entities with their official report PDF `url` when known; capped at 5, deduped on the normalized legal name. Without a codex/claude provider only saved matches come back and `note` says why; a failed model call is a `note` too. Nothing is downloaded. `job_id` (v194, optional) — see Progress tracking below |
| `POST` | `/api/reports/fetch` | `{ "company": "<Candidate.legal_name or Company.name>", "year": 2025, "country"?, "hint"?, "url"?, "download_pdf"?: true, "ocr"?: "bounded"\|"full", "job_id"? }` | `Report` — finds the company's annual report for that year on the web, downloads it into the cache (`data/reports/`), registers it like an upload. 10–90 s. `download_pdf` defaults to **true** (the PDF is always wanted); `false` is the text-only reuse of a saved report for API callers (409 when nothing is saved). When the download fails but page text is saved, the saved report is returned instead of a 404. Any company name is accepted — not just directory entries; `country`/`hint` are optional context for the model search (v074). `url` (a confirmed `/discover` candidate's link) is downloaded and validated **first**, before any source of the backend's own, and falls through to them when it fails. `404` with `{detail, tried: string[]}` when nothing usable was found (a failed model search says so in `detail`). Cached = instant. `ocr` (v191, default `bounded`): see "Bounded OCR" below. `job_id` (v194, optional) — see Progress tracking below |
| `GET`  | `/api/jobs/{job_id}` | – | `Job` — progress trail for a `job_id` passed to `/discover` or `/fetch` (v194). `404` once unknown or expired (1 h TTL). See Progress tracking below |
| `GET`  | `/api/library?collection_name=wallenberg\|midcap\|all` | – | `LibraryEntry[]` — the report **cache** in `data/reports/` (only files present on disk), filtered by the requested collection. Populated by `/fetch`; hand-curated entries also live in `index.json` |
| `POST` | `/api/reports/{report_id}/index` | – | `IndexStatus` — chunk + embed the report into the knowledge base (idempotent, cached on disk). ~10–30 s per report locally |
| `POST` | `/api/ask` | `{ "question": string, "report_ids"?: string[], "report_stems"?: string[] }` | `Answer` — omit both scopes to search all saved reports. Explicit scopes must be non-empty and mutually exclusive; unknown entries fail rather than widening the search. Global retrieval uses BM25 with bounded context, without embedding the entire library |
| `GET`  | `/api/kb` | `?collection_name=wallenberg\|midcap\|all` | `KbEntry[]` — what is in `data/kb/` (one per parsed report: pages indexed, sections extracted). `collection_name` filters the list: `all` (the backend default), the curated Wallenberg roster (`wallenberg` — what the KB page sends by default), or the 132-company SEB Mid Cap universe (`midcap`) |
| `GET` | `/api/kb/export.csv` | `?section=debt_maturity&collection=wallenberg\|midcap\|all&q=` | One CSV row per saved company extraction. `collection` follows the KB page scope; optional `q` matches its company/stem filter. No PDF or model call is needed. |
| `GET` | `/api/kb/export.pptx` | `?section=debt_maturity&collection=wallenberg\|midcap\|all&q=` | A PPTX deck with one maturity-wall summary table, then one established PowerPoint slide per saved company. Filtering is identical to the whole-KB CSV and no PDF or model call is needed. |
| `GET` | `/api/kb/maturity-wall` | `?section=debt_maturity&collection=wallenberg\|midcap\|all` | `MaturityWall` — deterministic upcoming-maturities list (v174): total debt, amount due within 1 year and their share for every saved `debt_maturity` extraction in the collection, sorted comparable-first by share descending. Each row also names its `data/companies.json` sector and whether its buckets are complete (v180), and the wall is aggregated per sector — counts plus median/min/max share over complete companies only. Reads the same decorated extracts as the CSV/PPTX exports (no PDF, no model call); 200 with `rows: []` when the collection has none yet |
| `GET` | `/api/kb/{stem}/pages/{page}` | – | `{ page: number, text: string }` — saved page text, available even without the PDF; exact known stem and valid page required |
| `GET` | `/api/kb/{stem}/{section}` | – | Saved `Extraction`, no model call, available without the original PDF |
| `GET`  | `/api/config` | – | `{ model, embed_model, base_url, llm, provider, retrieval, maturity_basis }` — what the backend runs with; `retrieval` is `"hybrid"` (cosine+BM25) \| `"bm25"` (keyword-only, e.g. codex/claude subscription with no embeddings endpoint) \| `"fixture"`; `maturity_basis` (v089) is `"carrying"` (default) \| `"undiscounted"`, from env `DEBT_BASIS` |
| `POST` | `/api/reports/from-library` | `{ "file": "<LibraryEntry.file>", "ocr"?: "bounded"\|"full" }` | `Report` — registers a bundled report exactly like an upload would. Same file twice = same `report_id`. `ocr` (v191, default `bounded`): see "Bounded OCR" below |

Errors: JSON `{ "detail": "message" }` with 4xx/5xx.

## Types

```ts
type Report = {
  report_id: string;        // opaque id, use in later calls
  filename: string;
  pages: number;
  company?: string | null;  // best-effort guess from first pages, may be null
  fiscal_year?: number | null;
  ocr_pages?: number[];     // v191: 1-based pages this registration actually OCR'd (empty for a text-layer PDF)
};

type Company = {
  name: string;             // as listed, e.g. "Sandvik AB"
  ticker: string;           // "SAND"
  sector: string | null;    // ICB sector text
  isin: string | null;
  cached_years: number[];   // years already present in the report cache, e.g. [2025]
};

type Candidate = {          // one entity POST /api/reports/discover proposes; identity fields are model-reported unless saved
  legal_name: string;       // registered name, e.g. "Intel Corporation" — never the typed fragment
  ticker: string | null;    // "INTC"
  exchange: string | null;  // "NASDAQ"
  country: string | null;   // ISO 3166-1 alpha-2, "US"
  org_number_or_lei: string | null;
  fiscal_year_end: string | null;  // month the fiscal year ends, "Dec"
  document_title: string | null;   // the report's own title for that year
  document_type: string | null;    // "annual report" | "10-K" | "20-F" | "annual and sustainability report" | other
  url: string | null;       // official report PDF for that year when known; /fetch tries it first
  reason: string;
  saved: boolean;           // already in the report cache or knowledge base for that year: no download needed
  stem: string | null;      // data/kb/<stem> when saved
};

type JobEvent = { t: number; stage: string; text: string; data?: Record<string, unknown> };
// data (v194): download carries { bytes, total: number | null }; model_search carries { queries: string[] } and/or
// { candidates / urls }, whichever the stage produced — see Progress tracking above
type Job = {                // GET /api/jobs/{job_id} (v194)
  job_id: string;
  stage: string;             // directory | mfn | nasdaq | ddg | model_search | ir_page | download | verify | done | failed
  started: number;           // unix seconds
  updated: number;
  done: boolean;
  error: string | null;      // the failed event's own text; null until then
  events: JobEvent[];
};

type LibraryEntry = {
  file: string;             // basename in data/reports/, e.g. "atlas_copco_2025.pdf"; key for from-library
  company: string;          // display name, curated in data/reports/index.json
  fiscal_year: number;
  language: 'en' | 'sv';
  pages: number;
  source_url: string | null;
  tags: string[];           // collections, e.g. ["wallenberg", "industrials"]; UI offers each tag as a one-click set
  note?: string | null;     // e.g. "image-only PDF, no text layer"
};

type IndexStatus = { report_id: string; chunks: number; embed_model: string; cached: boolean };

type Citation = {
  report_id: string;
  stem?: string;            // exact saved report for source text, also disambiguates fiscal years
  company: string | null;
  fiscal_year: number | null;
  page: number;
  quote: string;            // verbatim, verified against the page text like Field.source (unverified => dropped from citations, warning added)
  score: number;            // retrieval similarity 0..1, for the UI only
};

type Answer = {
  question: string;
  answer: string;           // markdown; cites as [Company p.N]
  citations: Citation[];
  warnings: string[];
  model: string;
};

type KbEntry = {
  stem: string;             // data/kb/<stem>/, = report filename without .pdf
  report_id: string | null; // stable ID restored from saved metadata after restart
  company: string | null;
  fiscal_year: number | null;
  pages: number;
  sections: string[];       // extractions present, e.g. ["income_statement"]
  indexed: boolean;         // embeddings cached
  sector: string | null;    // company directory sector, exact normalized name match; unknown stays null
  pdf_available: boolean;   // whether the source PDF currently exists
  text_available: boolean;  // at least one nonempty saved page; empty catalog entries are excluded from Ask
  figures_available: boolean; // at least one non-null field in a saved extraction, not merely a section file
};

type Source = {
  page: number;             // 1-based page in the uploaded PDF
  quote: string;            // verbatim text from that page that supports the value, or a proven reason why a null cannot be mapped
};

type MissingReasonDisclosed = {
  span: string;             // original report interval, never a standard bucket label invented by the parser
  amount: number | null;    // amount printed for that interval; null only when the row has no safely-readable amount
  unit: string | null;      // printed/inherited table unit when known
  page: number;
  quote: string;            // verbatim row carrying the disclosed amount
};

type MissingReason = {
  code: "absent_in_table" | "offgrid_span" | "noncurrent_only" | "lease_table_only" | "parent_only" | "straddle" | "not_found";
  detail: string;           // human-readable fact established by the existing extraction guard; never model-generated prose
  page?: number;
  quote?: string;
  disclosed?: MissingReasonDisclosed[]; // original off-grid intervals/amounts, never substituted into a standard bucket
};

type ReviewComponent = {
  value: number;            // one printed amount; the corrected field is their exact sum
  page: number;             // 1-based page holding this component's quoted row
  quote: string;            // verbatim row, checked against that saved page
  label: string;            // a short analyst label, e.g. "Current borrowings"
};

type Field = {
  key: string;              // canonical key from the schema, e.g. "revenue"
  label: string;            // human label from the schema
  value: number | string | null;  // null = not found, or (with "absent_in_table" evidence) not printed in this report
  unit: string | null;      // "MSEK", "SEK", "%", ...
  period: string | null;    // "2025", "2024", "2025-Q4"
  raw_label: string | null; // the label as printed in the report, e.g. "Intäkter"
  source: Source | null;
  missing_reason?: MissingReason; // debt_maturity only; present only while this field's value is null. It explains a known absence/refusal without changing the field, check, or standard-bucket semantics.
  components?: ReviewComponent[]; // analyst-reviewed printed amounts used to derive this field; never a claim that one printed row equals their sum
  confidence: number;       // 0..1, computed from evidence by the backend — see docs/CONFIDENCE.md. Never the model's opinion.
  evidence: string[];       // satisfied evidence codes, e.g. ["quote_on_page","value_in_quote","arith_ok"]; 1.0 <=> all seven present
                            // "absent_in_table" (v165, debt_maturity buckets): the maturity table's own parsed header prints no
                            // column for this window — value stays null and `source` quotes the header row that proves it; the
                            // identity check counts the operand as 0 (see docs/acrylic/evidence/v165.md)
};

type Check = {
  name: string;             // from schema.checks[].name
  passed: boolean;
  detail: string;           // human-readable, e.g. "152340 + -88120 = 64220 == 64220"
};

// v182: a deterministic, unconfirmed starting point for the basis-review form. Every
// suggestion names its provenance: metadata for the company/year, or a saved field
// citation for a value inferred from a printed unit/header. It is never a review.
type BasisSuggestion = {
  key: string;              // one allowed `basis.values` key
  value: string;
  source: Source | "report metadata";
};

type Extraction = {
  report_id: string;
  stem?: string;            // saved source, provided when opening the knowledge base
  pdf_available?: boolean; // false means use saved page text instead of the PDF
  company: string | null;
  fiscal_year: number | null;
  currency: string | null;  // dominant unit in the section
  section: string;          // schema name
  maturity_basis?: "carrying" | "undiscounted"; // v089, debt_maturity only: which maturity table total_debt + the buckets were read from (env DEBT_BASIS); distinct from the analyst-confirmed `basis` object below
  prior_year?: PriorYear;   // v091, debt_maturity only: the prior fiscal year's own figures (see below); the key is absent when they cannot be read deterministically
  buckets_by_year?: BucketsByYear; // v109, debt_maturity only: the report's own calendar-year maturity columns (see below); the key is absent unless the report prints years and they close on total_debt
  basis_suggestions?: BasisSuggestion[]; // v182: source-backed, deterministic suggestions; omitted keys remain unknown
  fields: Field[];          // one entry per schema field, in schema order (value null if missing)
  checks: Check[];
  warnings: string[];       // free text, e.g. "revenue: quote not found on page 64"
};

// v091: FY-1 alongside FY, read from the same table the current year came from (same basis),
// never a model answer. Written only when total_debt and at least two buckets were read and they
// close maturity_sums_to_total within the check's own tolerance on explicit values — a bucket
// whose prior-year figure the table does not print is absent from `fields` and named in the detail.
type PriorYear = {
  fiscal_year: number;                       // the current fiscal year minus one
  fields: Record<string, {                   // keyed like Field.key ("total_debt", "due_within_1_year", ...)
    value: number;
    source: Source | null;                   // the prior year's own printed row (page + verbatim quote)
  }>;
  check: { passed: boolean; detail: string }; // the identity re-run on the prior year's values
};

// v109: the report's own calendar-year maturity columns, read deterministically from the same table
// the current year's buckets came from — never a model answer. Written only when the years sum to
// total_debt within the check's own ±2 (a dash in a year column is the report's explicit 0).
type BucketsByYear = {
  basis: "carrying" | "undiscounted";        // the same maturity basis total_debt + the buckets were read on
  years: {                                   // one per printed year column, in print order
    label: string;                           // as printed: "2026" … the tail word "Later"/"Senare"/"2031 and later", or an open-end "2031–"
    value: number;
    source: Source | null;                   // the printed row the year came from (page + verbatim quote)
  }[];
};

// v174: GET /api/kb/maturity-wall. No FX conversion: total/due_within_1_year keep the printed unit
// unless both fields share a recognised currency at different scales (MSEK vs TSEK), in which case
// both are shown at the coarser scale. `comparable` is false when the basis is unconfirmed, either
// field lacks verified evidence, or the two units don't share a recognised currency — `share` can
// still be present in that case (an analyst can read an unconfirmed number); `reason` explains why,
// or carries a soft note (e.g. "No debt outstanding.") when comparable but share is still null.
type MaturityAmount = { value: number | null; unit: string | null };
type MaturityWallRow = {
  stem: string; report_id: string | null; company: string | null; fiscal_year: number | null;
  total: MaturityAmount; due_within_1_year: MaturityAmount;
  share: number | null;                      // due_within_1_year / total, 0..1; null if not computable
  basis_confirmed: boolean;
  consolidation: string | null; debt_basis: string | null; leases: string | null; // the confirmed basis values, when present
  review_status: string;                     // e.g. "confirmed", "unreviewed", "unresolved"
  comparable: boolean;
  reason: string;
  sector: string | null;                     // v180: data/companies.json sector, null when unknown
  complete: boolean;                         // v180: identity check passed AND total AND <1y present
};
// v180: the wall aggregated per sector (alphabetical, the null sector last). median/min/max count
// complete companies' shares only — a missing bucket is never back-filled with 0, so a sector with
// no complete company reports null stats while still counting its companies.
type MaturityWallSector = {
  sector: string | null; companies: number; complete: number;
  median_share: number | null; min: number | null; max: number | null;
};
type MaturityWall = {
  rows: MaturityWallRow[];                   // sorted comparable-first, then by share descending
  coverage: { total: number; comparable: number; missing_total: number; missing_w1y: number; basis_unconfirmed: number };
  sectors: MaturityWallSector[];
};
```

Every non-null `value` **must** carry a `source`. Backend verifies `source.quote` occurs on `source.page`
(whitespace-normalised; note references like `6, 7` may sit between label and number; a bare number is never
accepted); if not, it appends a warning and caps `confidence` at 0.25. If the value is a ×10/×100/×1000 rescale
of the figure printed in a verified quote, the value is repaired to what is printed and a warning says so; the same goes for a prior-year column, a `Total ...` row that sums the quoted one, and a label the model renamed (see `docs/CONFIDENCE.md`). `source.quote` is widened to the full printed row. This is the provenance + anti-hallucination story — do not drop it.

Reference example: [`backend/fixtures/sample_extraction.json`](../backend/fixtures/sample_extraction.json)
(fictional company, internally consistent numbers).

## Section schema files — `backend/schemas/<name>.json`

One file per report section. Adding a section = adding a file. The prompt is generated from it.

```jsonc
{
  "name": "income_statement",            // used in POST /extract { section }
  "title": "Consolidated income statement",
  "description": "...",
  "keywords": ["income statement", "resultaträkning", ...],   // sv + en, used to locate pages
  "value_convention": "Numbers as printed; unit from table header; period as YYYY",
  "fields": [
    { "key": "revenue", "label": "Revenue", "description": "...", "unit_hint": "currency_millions",
      "synonyms": ["revenue", "revenues", "net sales", "intäkter", "nettoomsättning"] }   // for the label_known evidence
  ],
  "checks": [
    // expr is a Python expression over field keys (numbers). Missing key => check reported as failed with detail "missing: <key>".
    { "name": "gross_profit_arith", "expr": "abs((revenue + cost_of_sales) - gross_profit) <= 2", "detail": "..." }
  ]
}
```

`GET /api/schemas` returns these files as-is (array).

## CSV export

Header begins `report_id,company,fiscal_year,section,key,label,value,unit,period,raw_label,page,quote,confidence` and adds current review metadata plus `human_source_page`, `human_source_quote`, and JSON-encoded `components`.
One row per field. UTF-8, comma-separated, quotes escaped per RFC 4180. JSON export carries the same field source, components, and append-only history; a human citation is not reclassified as automated evidence.

### Whole-KB maturity CSV

`GET /api/kb/export.csv` is the downstream-universe variant: it emits one row per saved company that has the requested section (rather than one row per field). Its leading columns are the header above, populated from the `total_debt` field and its source; it then adds `stem`, `due_within_1_year`, `due_1_to_5_years`, `due_after_5_years`, `review_status`, `human_review`, `ready`, `human_source_page`, `human_source_quote`, and `components`. `review_status` preserves every present human-review decision (for example `confirmed`); `human_review=yes` makes reviewed values visible without changing them. Missing amounts remain blank, never zero-filled.

## Company directory + on-demand report fetching

Reports are **not** bundled. `data/companies.json` supplies local directory suggestions;
`POST /api/reports/fetch` accepts any company name, including companies outside that directory.

**Discover, then confirm.** Typing a query and pressing Enter (or the search button) calls
`POST /api/reports/discover`, which resolves the query to concrete legal entities — a fragment like
"intel" comes back as "Intel Corporation, INTC, NASDAQ, US, FY ends Dec" with the report's title and
PDF `url` when known — saved reports first, then one model web-search call. The UI renders one card
per candidate (`saved` badge when the report is already local) and the user confirms one ("Use this
company") or refines with a free-text hint ("None of these" re-runs discover with `hint`). Nothing is
downloaded until a candidate is confirmed. The confirmed card's `legal_name` becomes the `company`
sent to `/fetch` (so the cache filename and index entry carry the legal name, not the typed text) and
its `url` is tried first. A search runs only that query, not other queued picks.

**AI-first fetch.** Existing saved text is reused without downloading. For a missing report,
a PDF-download request first tries the confirmed `url`, then the connected Codex/Claude model's live
web-search tool, looking for official annual-report PDFs or investor-relations pages for the
requested fiscal year.

A report search makes at most two model calls: official report links, then a targeted IR/archive
follow-up if needed. Discovered IR pages may be followed to their PDF links. Every downloaded PDF —
the confirmed `url` included — still passes issuer, fiscal-year, report-type and text-layer checks,
with complete reports preferred over summary volumes. Confirmed-url results carry
`note: "confirmed url"` (`"; summary volume"` appended under 80 pages); model results retain
`note: "model search (<provider>)"` and the legacy `tags: ["fetched", "foreign"]`; IR-page results
use `note: "IR page crawl"`.

MFN/Cision, Nasdaq and traditional web discovery are fallback sources if model search is unavailable
or cannot retrieve a valid report. This is public-web discovery, not guaranteed access to every site.
`country` and `hint` provide optional context for the model. Search errors remain in the 404 detail.

Validated PDFs are cached in `data/reports/<slug>_<year>.pdf`, with their actual source URL recorded
in `data/reports/index.json`. Repeated requests reuse the cache without another model search.

### Progress tracking (v194)

`/discover` and `/fetch` can each take an optional `job_id` — a uuid the frontend generates once per
call. When present, every stage the call passes through (checking the cache, MFN/Nasdaq/DuckDuckGo,
the connected model's own web search — its query terms and the candidates it names — following an
IR page, a PDF download's byte progress, page-count/issuer verification) is appended as an event to
an in-memory table `GET /api/jobs/{job_id}` serves back. The frontend polls it every 1.5 s while
either call is in flight, so a search that would otherwise look stuck shows a live, scrolling trail
instead. `job_id` is a no-op when omitted — every existing caller is unaffected. The table is
per-process (no persistence) and entries expire after an hour.

`GET /api/jobs/{job_id}` → `Job` (below), or `404` once unknown or expired. `stage` names are fixed:
`directory`, `mfn`, `nasdaq`, `ddg`, `model_search`, `ir_page`, `download`, `verify`, then a terminal
`done` or `failed`. `done: true` on either terminal stage; `error` (the `failed` event's own text) is
set only then. A call that fails outright (the `/fetch` 404 case) still leaves its trail in place —
the frontend does not need to guess a job crashed vs. finished with nothing found.

## Knowledge base — `data/kb/` (RAG + memory)

Every parsed report leaves its data behind as plain files so the corpus grows and the local model gets more context
with every run. Layout, one folder per report:

```
data/kb/<stem>/
  meta.json                 # company, fiscal_year, language, source_url, pages, sha256 of the PDF
  pages.jsonl               # {"page": 1, "text": "..."} per page — the text layer, committed (public data, ~1 MB/report)
  extractions/<section>.json# the Extraction returned by /extract, latest run wins — committed; doubles as eval + few-shot bank
  extractions/<section>.run<n>.json # per-run raw answers behind EXTRACT_MERGE_RUNS (audit only — never listed as a section)
  embeddings.jsonl          # {"page", "start", "text", "vec"} per chunk — DERIVED, gitignored, rebuilt by /index
```

- Upload or library registration writes `meta.json` + `pages.jsonl`. `/extract` writes `extractions/<section>.json`.
- `EXTRACT_MERGE_RUNS=off|union|majority` (default `off` — the route is unchanged): with `union` or `majority`, `/extract`
  runs the extraction a second time on the same pages and merges field by field — the run whose identity check passed
  wins; when the checks agree, values within ±2 count as the same answer and higher confidence picks whose copy to keep
  (a confidence tie keeps the second run), while a conflicting pair publishes null — with neither check nor a
  corroborating vote on either side, no signal says which run is right (v129's rules with the v145/v145-b conflict rule,
  measured on the v129/v136/v141 rerun data). Agreement is a same-financial-question comparison (v168): the unit counts
  too, by magnitude and currency — `MSEK`, `SEK m`, `SEKm` and `SEK million` are one unit, `KSEK`/`TSEK`/`SEK '000` are
  another, so 100 MSEK and 100 TSEK are a conflict, not a corroborating pair — and so does the period when both sides
  carry one; a unit or period printed on one side only is not proof of sameness. Both raw
  answers are saved as `extractions/<section>.run1.json` / `.run2.json` beside the merged `<section>.json`, and the merged
  result carries a top-level `"merge"` block (`mode`, `runs`, per-field `decisions`) plus a `merge:` summary warning.
  `majority` counts the stored answer as a third vote when it is pipeline-generated (a reviewed extraction never votes)
  and it answers the same financial question: same report, section, fiscal_year and maturity_basis — a stored answer read
  on the other debt basis, another year, or one missing that metadata sits out, and the merge block then says
  `"stored_vote": "not eligible: <reason>"`. When run 1 already matches an eligible stored answer field by field the
  second run is skipped (`"runs": 1`). Run 1's `prior_year`/`buckets_by_year` attachments are deterministic reads of
  run 1's own rows, so they ride along only while every field they cover still carries run 1's answer — a conflict-null,
  another run's different value or unit scale drops the attachment, with a `merge: … dropped` warning saying which field
  no longer supports it.
- `/index` chunks `pages.jsonl` (~800 chars, page-aware) **and** turns each extracted field into a fact chunk
  (`"Atlas Copco FY2025 · Consolidated income statement · Revenue = 176 771 MSEK (p.106)"`), embeds both with `EMBED_MODEL`.
- `/ask` retrieves top-k chunks — hybrid cosine+BM25 when `LLM_BASE_URL` provides embeddings, pure BM25 otherwise
  (a codex/claude subscription has no embeddings endpoint; see `GET /api/config`'s `retrieval`) — prompts `LLM_MODEL` with
  the chunks labelled `[Company p.N]`, requires verbatim quotes, verifies them on the page — same provenance rule as fields.
- "Gets better over time": `/extract` includes up to 2 prior *checks-passed* extractions of the same section from the KB
  as few-shot examples in the prompt (`FEWSHOT=0` disables). Fine-tuning is out of scope; the KB is the training set if it ever isn't.

## LLM configuration (backend)

Environment variables, read from `backend/.env`:

```
LLM_BASE_URL=http://localhost:11434/v1   # Ollama (OpenAI-compatible). Unset => backend returns the fixture (frontend dev mode)
LLM_MODEL=qwen3:8b
LLM_API_KEY=ollama                       # any non-empty string for Ollama
EMBED_MODEL=bge-m3                       # via the same base URL's /embeddings; multilingual (sv+en). `ollama pull bge-m3`
KB_DIR=../data/kb                        # optional override
```

Same variables point at Azure OpenAI / OpenAI / OpenRouter with no code change.

`PAGE_SELECT_HINTS=1` opts debt-maturity pass-1 into the candidate-page markers and carrying-versus-liquidity prompt sentence; unset (the default) retains the prior page-select prompt byte-for-byte. `PAGE_SELECT_HINTS=retry` requires `EXTRACT_MERGE_RUNS=union|majority`: run 1 stays unhinted, and run 2 gets the markers only when run 1's first identity check fails or any schema field is null (an exact majority match still skips run 2). A hinted retry records `"hints": "run2"` in the merged result.

`EXTRACT_SECOND_PASS` is off by default. Set `EXTRACT_SECOND_PASS=1` to opt into the bounded retry for **required** fields that are still null after the ordinary extraction (and any configured merge). It makes at most three separate fixed-page calls per report, one field at a time, on the locator's first two or three candidate pages with their complete extracted text and that field's schema synonyms. The follow-up can write a value only when the normal quote-on-page, value-in-quote, known-label and debt scope guards accept it; otherwise the null remains a null. Accepted fields add `second_pass` to their evidence. Set `EXTRACT_SECOND_PASS=0` (or leave it unset) to make no follow-up calls. Extraction `timings` reports `second_pass_calls` and `second_pass` seconds alongside the aggregate `model`, `validate` and `attempts` totals.

## Global Ask and company map

Ask searches saved page text and extracted facts. `@Company` is a UI scope selector, resolved
against the parsed-company catalogue to exact `report_stems` across available years. Unknown or
unfinished mentions must be corrected before submission. No mentions means the entire saved library.
Question length is limited to 2,000 characters. The UI shows the effective company/report scope.

The knowledge map groups real saved reports by company-directory sector, then company and fiscal
year. Edges represent membership, not embedding similarity or inferred business relationships.
Unknown sectors remain unclassified. Company actions open saved extractions or prefill a scoped Ask.
Source PDFs are optional: page-text citations remain available, while PDF/image requests return an
explicit missing-PDF response when the original file is absent. The existing selected-report Ask
continues to accept `report_ids` and retains its retrieval mode.


### Human review
`POST /api/reports/{report_id}/review` accepts `section`, `key`, `expected` (the complete field last read), `decision` (`confirmed`, `corrected`, `unresolved`), `reviewer` (self-reported name), `note`, and optional `value`, `unit`, `period` for corrections. A correction may also provide a paired `source_page` (positive integer) + `source_quote`; the backend checks that quote against the saved page text before replacing the field's source. A correction may instead provide `components: [{value, page, quote, label}]`: every component quote is checked on its own page and the backend writes the exact component sum as the field value, records the components, and uses the first component as the field's clickable source. `value` is required for a direct correction and ignored for a component sum; `unit` and `period` are required for both. The current `human_review` records `source_verified: true` only when the submitted source or every submitted component was found on its page; a human decision without a new citation does not gain that key.

Returns the updated Extraction. Requires a saved extraction. Stale fields return 409. Reviews persist inside each field as `human_review` and append-only `review_history` with the previous field snapshot and a UTC timestamp. Corrections replace the field source only when a new citation was supplied, retain the original value and source in history, replace automated evidence with human-review evidence, and mark calculation checks stale/unavailable. Review does not certify automated checks. Re-extraction of a reviewed section is rejected (409) to prevent loss of reviews. JSON export includes the full history and components. Per-report and whole-KB CSV add `human_source_page`, `human_source_quote`, and JSON-encoded `components`; PPTX writes the first reviewed field's page/quote and component count on the slide while full history remains in speaker notes.

### Analyst-directed field fill
`POST /api/reports/{report_id}/fill?section=<schema name>` is a controlled retry for an analyst who has already found one or two evidence pages for an **empty** field. Its body is `{field, pages}`. It uses the normal section schema, configured model, provenance and scope guards, but its extraction window is exactly those supplied pages: it does not run locator ranking or the optional page-selection pass. It returns only the requested `candidate` plus warnings; `candidate` is `null` if the target remains empty, has no source, or cites a page outside the supplied set. It never writes `data/kb`, changes the stored extraction, or changes another field. A human must explicitly accept the candidate through the review endpoint, so the ordinary expected-snapshot and citation checks still apply. Sections with any prior human review return 409, matching re-extraction protection. Fixture/demo mode returns 422 (`Demo mode does not support targeted field fill`), rather than presenting synthetic evidence as a candidate.


### Collections, discovery, and always-on PDFs
The desktop UI defaults to `collection_name=wallenberg` on GET `/api/companies`, `/api/library`, and `/api/kb`; `all` remains available. `midcap` is the SEB Mid Cap universe: every company in `data/companies.json` whose `market` is `Mid Cap` (132 at publication), normalized with the same identity matching as the Wallenberg roster. The Collection switch includes SEB Mid Cap and carries its choice through the directory, saved reports, Ask's explicit report stems, and whole-KB exports. GET `/api/review-queue` also accepts `collection_name=wallenberg|midcap|all` and defaults to Wallenberg. The Wallenberg roster is defined in `pipeline/collection.py`, sourced from Investor and FAM; it is a curated holdings collection, not an exhaustive ownership graph.
POST `/api/reports/discover` resolves a typed query to concrete legal entities before anything downloads; the UI renders the candidates as cards and the user confirms one (or refines with a hint) rather than the typed fragment becoming the company identity. POST `/api/reports/fetch` defaults `download_pdf` to **true**: a cached PDF is reused as-is, otherwise the report is downloaded, and if the download fails while page text is saved, that saved report is returned (the Source panel says the PDF is missing). `download_pdf: false` is the text-only path for API callers: reuse saved text or an existing PDF, 409 if neither exists, never a web request. The UI has no download checkbox — every directory pick and confirmed candidate sends one request with `download_pdf: true`, and a confirmed candidate's `url` is downloaded and validated before any source of the backend's own. POST `/api/reports/{id}/extract` accepts `reuse_saved: true` to return the saved extraction before calling a model, preserving human reviews. A new extraction can use saved page text without a PDF.


### Analyst workbench
Extractions gain optional `basis`, `basis_history`, `check_history`, `issues`, `basis_issues`, `basis_suggested`, `not_reported`, and derived `ready`. Basis records entity, consolidation, period, currency, scale, source page, restatement status and (debt only) debt basis, leases and bucket mapping. Values are analyst-confirmed, never inferred as confirmed from legacy data: `basis_suggested` is a prefill for the form (entity = report company, consolidation `Group`, period = fiscal year, currency + scale read from the section's unit, source `Annual report`, restatement `As reported`; debt adds `debt_basis` from `maturity_basis`, empty `leases` and `bucket_mapping` — nothing extracted says whether leases are in). A bare currency code as unit (`SEK`) prefills the currency and leaves `scale` empty, shown only until a human saves. GET `/api/review-queue` returns unresolved field and check issues for the Wallenberg collection. POST `/api/reports/{id}/basis` accepts section, expected basis, values, reviewer and note, returning the updated extraction. Existing field reviews recalculate deterministic checks and archive previous checks. GET `/api/kb/{stem}/{section}/comparison?previous_stem=...` returns compatible saved-report deltas or reasons why unavailable. Exports accept optional section and previous_stem to bind the exact statement and comparison. Missing values never implicitly become zero. No endpoint in this workflow downloads PDFs.


`basis` is `{values: Record<string,string>, reviewer, note, at}`. Shared value keys: `entity`, `consolidation`, `period`, `currency`, `scale`, `source`, `restatement`. Debt adds `debt_basis`, `leases`, `bucket_mapping`. Empty values remain unknown. `basis_suggestions` is a separate optional list of `{key, value, source}` generated deterministically from report metadata and already-cited field evidence: it may suggest entity, period, a unanimous parsed unit's currency/scale, a complete cited-page list, debt measurement, and an exact standard maturity-bucket mapping. It never suggests consolidation, leases, or restatement; a missing citation means no suggestion. Suggestions prefill the client only and do not make a basis confirmed or a result ready. Basis review accepts `{section, expected: previousBasisOrEmptyObject, values, reviewer, note}` and rejects stale snapshots with 409. `basis_history` records each prior basis. `check_history` records previous checks when recalculation changes them.

Checks include `status: passed|failed|unavailable`. Reconciliation requires every operand to be explicit and use the same nonempty unit and period — except a bucket whose evidence marks it `absent_in_table` (the report's maturity table prints no column for that window): it joins the reconciliation as 0. Source evidence remains distinct from arithmetic and human review. `issues` contains `{kind: field|check, key, detail}`: a field is an issue unless a human confirmed or corrected it, or the backend verified its quote on the page, its value in that quote (or exactly one stand-in: `value_derived`, `stated_zero`, `printed_nil` — see docs/CONFIDENCE.md), label, period, statement page and unit, with a source; a check is an issue only when it `failed` (`unavailable` means an operand is missing, which is already a field issue or not reported); an `absent_in_table` bucket is not an issue (a reviewer marking it unresolved re-opens it). A null on a schema field marked `optional` (income statement `cost_of_sales`, `gross_profit`, `profit_discontinued`) is listed in `not_reported` instead of `issues` — it is still null, never zero — unless a reviewer marked it unresolved, or an optional peer in the same identity check has a value (`cost_of_sales` present with `gross_profit` null is a miss). A null optional field with a schema `default` (`profit_discontinued`: 0) counts as that default in the checks, as in extraction, so `net_profit_arith` evaluates without it. PPT footers and the CSV `unresolved` column list field, check and basis issues together. `label_known` is re-derived on every decorate from the field's own label, synonyms and row synonyms (debt: "Borrowings", "Interest-bearing liabilities"), so saved extractions scored before that vocabulary resolve without re-extraction; a bare "Total" stays a task unless the closing-row marker identified it. `basis_issues` holds `{kind: basis, key, detail}` entries, one per unconfirmed definition. `ready` = no `issues`; an unconfirmed basis does not block it. Queue entries add `report: KbEntry` and `section`.

Comparison responses include saved `candidates`, `previous_stem`, `current_year`, `previous_year`, `reasons`, and per-field `rows` with current/previous values, delta, percent, sign-change flag, sources and human reviews. Missing immediate prior years and duplicate sources require explicit selection. Definitions must be confirmed and compatible before calculating changes. Period formats must match after replacing each fiscal year. A zero previous value gives a null percentage, never infinity. Alternate intervals and declared restatements remain explicit. Export query parameters `section` and `previous_stem` select the saved statement and comparison, regardless of the last statement opened.

### Prior-year maturity metadata and the PPTX second series (v091)
`GET /api/reports/{report_id}/extraction.pptx` additionally accepts `prior_year=1`: the maturity chart gains a second, fainter series named `FY<n-1>` beside the current one (plus a legend naming both). The flag is ignored — the slide renders exactly as before — when the extraction carries no `prior_year` or the parameter is absent. The two deterministic sources are: a maturity table printing one row per bucket under year columns (the prior year is the prior-year column of the same rows), and one printing buckets as columns under stacked per-year blocks (the prior year is the same-labelled row of the FY-1 block, read with the same column keys). Date-per-instrument notes and model-only answers never produce a prior year.

`GET /api/reports/{report_id}/extraction.pptx` also accepts `per_year=1` (v109): when the extraction carries `buckets_by_year`, the maturity chart's three bucket categories are replaced by the report's own calendar-year columns, one "Debt due" series of the printed years (labels as printed). The flag is ignored — the slide renders exactly the three buckets — when the extraction carries no `buckets_by_year` or the parameter is absent; when both `per_year=1` and `prior_year=1` are sent, the year series wins (a year series and a bucket series answer two different questions). See "Per-year maturity metadata (`buckets_by_year`)" in `backend/README.md`.


## Cache and embedding integration (21 September 2026)

- `POST /api/reports/{id}/extract` accepts `force: true` to bypass the automatic
  source/model/settings cache. `reuse_saved: true` still opens the saved result,
  including human reviews. Force never replaces human-reviewed fields or definitions.
- Extraction responses add `cached`, `stale`, `model`, `provider`, and `timings`
  (`total`, `model`, `validate`, `attempts`, `second_pass_calls`, `second_pass`). Opening a saved result reports zero model
  calls and its current load time. `stale` compares pipeline, report, prompt and model
  configuration. Saved files with invalid structure return 409.
- `EMBED_BASE_URL`, `EMBED_API_KEY` and `EMBED_TIMEOUT` independently configure
  embeddings. Selected-report Ask uses cosine plus BM25 when an embedding endpoint
  is configured. Subscription-only setups retain BM25. Global Ask retains bounded
  keyword retrieval across all saved reports. Embedding identity, dimensions, source
  hashes and chunk counts are checked in the derived `index.json` manifest.
- `/api/kb` rows add `status` (`ready`, `missing`, `outdated`, `invalid`, `building`),
  `reason`, `embed_model`, `dimensions`, `chunks`, `page_chunks`, `fact_chunks`, `built_at`.
  Listing never waits for a long index build.
- `GET /api/knowledge/{stem}/chunks?q=&offset=0&limit=25` returns
  `{items: [{page,start,text,kind}], total,offset,limit}` without vectors. Limit is 1–100.
  `POST /api/knowledge/{stem}/index` rebuilds all embeddings.
  `POST /api/knowledge/{stem}/open` restores a report, including saved-text-only reports.
- Fact chunks require printed amounts, verified sources, matching year and confidence
  at least 0.7. Raw per-run extraction records are excluded. Answers containing rejected
  citations are withheld, with warnings explaining the rejected evidence.
- Parser 7 combines the current column/header reconstruction with selective local OCR.
  OCR language/path and page provenance are recorded with the cached text. OCR-derived
  fields are capped at 0.8 confidence. Missing language files return an actionable 422.
- **Bounded OCR (v191).** A scanned PDF's registration request (`POST /api/reports`,
  `/api/reports/from-library`, `/api/reports/fetch`) does not OCR the whole document
  synchronously by default: it OCRs only the pages a debt-maturity locate pass could reach
  (the report's own front matter plus any outline/bookmark entry naming a debt/maturity/
  borrowings section, ±1 page) and leaves the rest blank, recorded as `ocr_pending` in
  `data/kb/<stem>/meta.json`. If even that bounded set needs more than `OCR_PAGE_BUDGET`
  pages (env, default 40), the request 422s instead of running it:
  `{ "detail": "scanned PDF: OCR would take ~N min for P pages", "ocr_pages_needed": P }`,
  where `P` is every scanned page in the document (what a full pass would cost), not just
  the bounded subset. Retrying the same call with `ocr=full` OCRs the whole document
  unconditionally, no budget check — an explicit opt-in. Before `/extract` runs, any
  candidate page the locator picked for the section being extracted that is still
  `ocr_pending` is OCR'd individually first, so the model never reads a page bounded
  registration skipped but this extraction actually needs.
- PPTX keeps analyst-review metadata and prior-year/per-year options. Incomplete or
  failed-check maturity splits render as a table. Chart axis IDs are unsigned.
