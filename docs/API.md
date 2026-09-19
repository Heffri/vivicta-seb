# API contract — backend ⇄ frontend

Frontend and backend are built in parallel against this document. Change it here first, then code.
Backend runs on `http://localhost:8000`, frontend dev server proxies `/api` to it.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET`  | `/api/schemas` | – | `Schema[]` (section definitions, see below) |
| `POST` | `/api/reports` | `multipart/form-data`, field `file` = PDF | `Report` |
| `GET`  | `/api/reports/{report_id}` | – | `Report` |
| `POST` | `/api/reports/{report_id}/extract` | `{ "section": "<schema name>" }` | `Extraction` (synchronous; may take up to ~60 s with a local model) |
| `GET`  | `/api/reports/{report_id}/pages/{n}.png` | – | PNG of page `n` (1-based), ~150 dpi. 404 if out of range |
| `GET`  | `/api/reports/{report_id}/extraction.csv` | – | last extraction for this report as CSV (one row per field). 404 if none |
| `GET`  | `/api/reports/{report_id}/pdf` | – | the PDF itself, `Content-Disposition: inline`, so `<iframe src=".../pdf#page=64">` opens the browser's own viewer on that page |
| `GET`  | `/api/companies?q=<text>` | – | `Company[]` — the listed-company directory (`data/companies.json`, Nasdaq Stockholm), filtered by name/ticker substring; max 50. Empty `q` = first 50 |
| `POST` | `/api/reports/fetch` | `{ "company": "<Company.name>", "year": 2025, "country"?, "hint"? }` | `Report` — finds the company's annual report for that year on the web, downloads it into the cache (`data/reports/`), registers it like an upload. 10–90 s. Any company name is accepted — not just directory entries; `country`/`hint` are optional context for the model search (v074). `404` with `{detail, tried: string[]}` when nothing usable was found (a failed model search says so in `detail`). Cached = instant |
| `GET`  | `/api/library` | – | `LibraryEntry[]` — the report **cache** in `data/reports/` (only files present on disk). Populated by `/fetch`; hand-curated entries also live in `index.json` |
| `POST` | `/api/reports/{report_id}/index` | – | `IndexStatus` — chunk + embed the report into the knowledge base (idempotent, cached on disk). ~10–30 s per report locally |
| `POST` | `/api/ask` | `{ "question": string, "report_ids"?: string[], "report_stems"?: string[] }` | `Answer` — omit both scopes to search all saved reports. Explicit scopes must be non-empty and mutually exclusive; unknown entries fail rather than widening the search. Global retrieval uses BM25 with bounded context, without embedding the entire library |
| `GET`  | `/api/kb` | – | `KbEntry[]` — what is in `data/kb/` (one per parsed report: pages indexed, sections extracted) |
| `GET` | `/api/kb/{stem}/pages/{page}` | – | `{ page: number, text: string }` — saved page text, available even without the PDF; exact known stem and valid page required |
| `GET` | `/api/kb/{stem}/{section}` | – | Saved `Extraction`, no model call, available without the original PDF |
| `GET`  | `/api/config` | – | `{ model, embed_model, base_url, llm, provider, retrieval, maturity_basis }` — what the backend runs with; `retrieval` is `"hybrid"` (cosine+BM25) \| `"bm25"` (keyword-only, e.g. codex/claude subscription with no embeddings endpoint) \| `"fixture"`; `maturity_basis` (v089) is `"carrying"` (default) \| `"undiscounted"`, from env `DEBT_BASIS` |
| `POST` | `/api/reports/from-library` | `{ "file": "<LibraryEntry.file>" }` | `Report` — registers a bundled report exactly like an upload would. Same file twice = same `report_id` |

Errors: JSON `{ "detail": "message" }` with 4xx/5xx.

## Types

```ts
type Report = {
  report_id: string;        // opaque id, use in later calls
  filename: string;
  pages: number;
  company?: string | null;  // best-effort guess from first pages, may be null
  fiscal_year?: number | null;
};

type Company = {
  name: string;             // as listed, e.g. "Sandvik AB"
  ticker: string;           // "SAND"
  sector: string | null;    // ICB sector text
  isin: string | null;
  cached_years: number[];   // years already present in the report cache, e.g. [2025]
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
};

type Source = {
  page: number;             // 1-based page in the uploaded PDF
  quote: string;            // verbatim text from that page that supports the value
};

type Field = {
  key: string;              // canonical key from the schema, e.g. "revenue"
  label: string;            // human label from the schema
  value: number | string | null;  // null = not found
  unit: string | null;      // "MSEK", "SEK", "%", ...
  period: string | null;    // "2025", "2024", "2025-Q4"
  raw_label: string | null; // the label as printed in the report, e.g. "Intäkter"
  source: Source | null;
  confidence: number;       // 0..1, computed from evidence by the backend — see docs/CONFIDENCE.md. Never the model's opinion.
  evidence: string[];       // satisfied evidence codes, e.g. ["quote_on_page","value_in_quote","arith_ok"]; 1.0 <=> all seven present
};

type Check = {
  name: string;             // from schema.checks[].name
  passed: boolean;
  detail: string;           // human-readable, e.g. "152340 + -88120 = 64220 == 64220"
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

Header: `report_id,company,fiscal_year,section,key,label,value,unit,period,raw_label,page,quote,confidence`
One row per field. UTF-8, comma-separated, quotes escaped per RFC 4180.

## Company directory + on-demand report fetching

Reports are **not** bundled. `data/companies.json` (committed, built by `python data/companies_build.py` from the
Nasdaq Stockholm listed-companies list) is the directory the picker searches. Picking a company + year calls
`POST /api/reports/fetch`, which runs `backend/pipeline/fetch.py`: search the web for that company's annual report
for that year (press-release feeds first — MFN / Cision attachments — then a web search restricted to PDFs), download
the first candidate that is a real PDF with a text layer and > 40 pages, save it as `data/reports/<slug>_<year>.pdf`
and append a manifest entry to `data/reports/index.json` (`file, company, fiscal_year, language, source_url,
tags: ["fetched"], fetched_at`). `data/reports/` is therefore a cache: gitignored PDFs, committed manifest.
`GET /api/library` lists the cache; `python data/fetch.py` re-downloads manifest entries that are missing.

**Foreign companies (v074).** The directory is Swedish-listed only, but `/api/reports/fetch` accepts any name.
`fetch.py` tries four sources in order — MFN/Cision feeds, Nasdaq notices, the DuckDuckGo web search — and, only
when all three found nothing usable *and* the backend runs on a CLI provider (`LLM_PROVIDER=codex|claude`), asks
the model itself for links, via its own web-search tool (`codex --search exec`, `claude -p --tools WebSearch`):
at most 3 direct URLs to the official annual-report PDF on the issuer's investor-relations site or a regulatory
repository (no ESEF zips, quarterly or sustainability reports), or — failing a direct link — the issuer's IR/
annual-report page URL itself. Every candidate from every source passes the same validation; the first survivor
registers with `note: "model search (<provider>)"` and `tags: ["fetched", "foreign"]`.
With an OpenAI-compatible or no provider the fourth level never runs and the 404 keeps its usual shape (a model
search that errored — unavailable CLI, unparseable reply — says so in `detail`). `country`/`hint` in the request
body only feed that search's prompt.

**Fifth source (v080).** Only once all four sources above fail: `fetch.py` crawls whatever page-shaped leftovers
those attempts produced (a model reply naming an IR page instead of a PDF, a web-search hit that served a page, or
the guessed IR path for the domain of a direct link that 404d), one hop deep, harvesting `.pdf` links that pass
the same validation gate. Unlike the other four sources, this one downloads every harvested candidate (budget:
90 s total, ≤8 candidates, 20 s each) and keeps the one with the most pages rather than the first that validates,
so a page linking both a summary volume and the full report resolves to the full report. The survivor registers
with `note: "IR page crawl"` and `tags: ["fetched", "foreign"]`.

## Knowledge base — `data/kb/` (RAG + memory)

Every parsed report leaves its data behind as plain files so the corpus grows and the local model gets more context
with every run. Layout, one folder per report:

```
data/kb/<stem>/
  meta.json                 # company, fiscal_year, language, source_url, pages, sha256 of the PDF
  pages.jsonl               # {"page": 1, "text": "..."} per page — the text layer, committed (public data, ~1 MB/report)
  extractions/<section>.json# the Extraction returned by /extract, latest run wins — committed; doubles as eval + few-shot bank
  embeddings.jsonl          # {"page", "start", "text", "vec"} per chunk — DERIVED, gitignored, rebuilt by /index
```

- Upload or library registration writes `meta.json` + `pages.jsonl`. `/extract` writes `extractions/<section>.json`.
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
`POST /api/reports/{report_id}/review` accepts `section`, `key`, `expected` (the complete field last read), `decision` (`confirmed`, `corrected`, `unresolved`), `reviewer` (self-reported name), `note`, and optional `value`, `unit`, `period` for corrections. Returns the updated Extraction. Requires a saved extraction. Stale fields return 409. Reviews persist inside each field as `human_review` and append-only `review_history` with the previous field snapshot and a UTC timestamp. Corrections retain source provenance, clear the changed field's automated evidence, and mark calculation checks `stale: true`. Review does not certify automated checks. Re-extraction of a reviewed section is rejected (409) to prevent loss of reviews. JSON export includes the full history; CSV includes current review status, name, time, and note.


### Wallenberg collection and opt-in PDFs
The desktop UI requests `collection_name=wallenberg` on GET `/api/companies`, `/api/library`, and `/api/kb`. The API's `all` scope remains available and existing data is retained. The roster is defined in `pipeline/collection.py`, sourced from Investor and FAM, and shipped as application code. It is a curated holdings collection, not an exhaustive ownership graph. Global Ask sends the visible collection's report stems explicitly.
POST `/api/reports/fetch` defaults `download_pdf` to false. It reuses saved text or an existing PDF and returns 409 if neither exists, without making a web request. Only `download_pdf: true` permits a download. POST `/api/reports/{id}/extract` accepts `reuse_saved: true` to return the saved extraction before calling a model, preserving human reviews. A new extraction can use saved page text without a PDF.


### Analyst workbench
Extractions gain optional `basis`, `basis_history`, `check_history`, `issues`, and derived `ready`. Basis records entity, consolidation, period, currency, scale, source page, restatement status and (debt only) debt basis, leases and bucket mapping. Values are analyst-confirmed, never inferred as confirmed from legacy data. GET `/api/review-queue` returns unresolved issues for the Wallenberg collection. POST `/api/reports/{id}/basis` accepts section, expected basis, values, reviewer and note, returning the updated extraction. Existing field reviews recalculate deterministic checks and archive previous checks. GET `/api/kb/{stem}/{section}/comparison?previous_stem=...` returns compatible saved-report deltas or reasons why unavailable. Exports accept optional section and previous_stem to bind the exact statement and comparison. Missing values never implicitly become zero. No endpoint in this workflow downloads PDFs.


`basis` is `{values: Record<string,string>, reviewer, note, at}`. Shared value keys: `entity`, `consolidation`, `period`, `currency`, `scale`, `source`, `restatement`. Debt adds `debt_basis`, `leases`, `bucket_mapping`. Empty values remain unknown. Basis review accepts `{section, expected: previousBasisOrEmptyObject, values, reviewer, note}` and rejects stale snapshots with 409. `basis_history` records each prior basis. `check_history` records previous checks when recalculation changes them.

Checks include `status: passed|failed|unavailable`. Reconciliation requires every operand to be explicit and use the same nonempty unit and period. Source evidence remains distinct from arithmetic and human review. `issues` contains `{kind: basis|field|check, key, detail}`. `ready` requires no unresolved issues, including missing figures even when a human confirmed their absence. Queue entries add `report: KbEntry` and `section`.

Comparison responses include saved `candidates`, `previous_stem`, `current_year`, `previous_year`, `reasons`, and per-field `rows` with current/previous values, delta, percent, sign-change flag, sources and human reviews. Missing immediate prior years and duplicate sources require explicit selection. Definitions must be confirmed and compatible before calculating changes. Period formats must match after replacing each fiscal year. A zero previous value gives a null percentage, never infinity. Alternate intervals and declared restatements remain explicit. Export query parameters `section` and `previous_stem` select the saved statement and comparison, regardless of the last statement opened.

### Prior-year maturity metadata and the PPTX second series (v091)
`GET /api/reports/{report_id}/extraction.pptx` additionally accepts `prior_year=1`: the maturity chart gains a second, fainter series named `FY<n-1>` beside the current one (plus a legend naming both). The flag is ignored — the slide renders exactly as before — when the extraction carries no `prior_year` or the parameter is absent. The two deterministic sources are: a maturity table printing one row per bucket under year columns (the prior year is the prior-year column of the same rows), and one printing buckets as columns under stacked per-year blocks (the prior year is the same-labelled row of the FY-1 block, read with the same column keys). Date-per-instrument notes and model-only answers never produce a prior year.

`GET /api/reports/{report_id}/extraction.pptx` also accepts `per_year=1` (v109): when the extraction carries `buckets_by_year`, the maturity chart's three bucket categories are replaced by the report's own calendar-year columns, one "Debt due" series of the printed years (labels as printed). The flag is ignored — the slide renders exactly the three buckets — when the extraction carries no `buckets_by_year` or the parameter is absent; when both `per_year=1` and `prior_year=1` are sent, the year series wins (a year series and a bucket series answer two different questions). See "Per-year maturity metadata (`buckets_by_year`)" in `backend/README.md`.
