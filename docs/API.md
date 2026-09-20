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
| `POST` | `/api/reports/fetch` | `{ "company": "<Company.name>", "year": 2025 }` | `Report` — finds the company's annual report for that year on the web, downloads it into the cache (`data/reports/`), registers it like an upload. 10–90 s. `404` with `{detail, tried: string[]}` when nothing usable was found. Cached = instant |
| `GET`  | `/api/library` | – | `LibraryEntry[]` — the report **cache** in `data/reports/` (only files present on disk). Populated by `/fetch`; hand-curated entries also live in `index.json` |
| `POST` | `/api/reports/{report_id}/index` | – | `IndexStatus` — chunk + embed the report into the knowledge base (idempotent, cached on disk). ~10–30 s per report locally |
| `POST` | `/api/ask` | `{ "question": string, "report_ids": string[] }` | `Answer` — RAG over the selected reports (page texts + prior extractions). Indexes on demand if `/index` was not called |
| `GET`  | `/api/kb` | – | `KbEntry[]` — what is in `data/kb/` (one per parsed report: pages indexed, sections extracted) |
| `POST` | `/api/reports/from-library` | `{ "file": "<LibraryEntry.file>" }` | `Report` — registers a bundled report exactly like an upload would. Same file twice = same `report_id` |

Errors: JSON `{ "detail": "message" }` with 4xx/5xx.

## Demo performance and inspection additions

- `/extract` accepts `force?: boolean` (default false). Results include `cached`,
  `model`, `provider`, `created_at`, and `timings` (seconds: parse, locate, model,
  validate, total; plus attempts). Cache identity includes PDF, schema, pipeline,
  model settings and the rendered few-shot prompt. Legacy results remain readable.
- `/api/config` additionally returns `provider`, `embed_base_url`, and `reasoning`.
  `LLM_PROVIDER=codex` uses the logged-in CLI, independently of `LLM_BASE_URL`.
  `EMBED_BASE_URL` and `EMBED_API_KEY` override the embedding connection.
- KB entries additionally contain `status` (ready/missing/outdated/invalid),
  `reason`, `embed_model`, `dimensions`, `chunks`, `page_chunks`, `fact_chunks`, `built_at`.
- `GET /api/knowledge/{stem}/chunks?q=&offset=0&limit=25` returns
  `{items: [{page,start,text,kind}], total, offset, limit}` without vectors.
  It only browses the stored index and never generates embeddings.
- `POST /api/knowledge/{stem}/index` rebuilds the selected index.
- `POST /api/knowledge/{stem}/open` registers a saved report, including uploads,
  and returns `Report`. Missing PDFs return 409.
- `index.json` inside each KB folder records model, dimensions, source fingerprints,
  chunker version and embedding-file hash. Legacy indexes are outdated until rebuilt.
  Cache files are atomically replaced. The demo supports one backend process.

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
  report_id: string | null; // set while the backend has it registered this run
  company: string | null;
  fiscal_year: number | null;
  pages: number;
  sections: string[];       // extractions present, e.g. ["income_statement"]
  indexed: boolean;
  status: 'ready' | 'missing' | 'outdated' | 'invalid';
  reason: string;
  embed_model: string | null;
  dimensions: number | null;
  chunks: number;
  page_chunks: number;
  fact_chunks: number;
  built_at: string | null;
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
  cached?: boolean;
  model?: string;
  provider?: string;
  created_at?: string;
  timings?: { parse: number; locate: number; model: number; validate: number; total: number; attempts: number };
  report_id: string;
  company: string | null;
  fiscal_year: number | null;
  currency: string | null;  // dominant unit in the section
  section: string;          // schema name
  fields: Field[];          // one entry per schema field, in schema order (value null if missing)
  checks: Check[];
  warnings: string[];       // free text, e.g. "revenue: quote not found on page 64"
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

Both CSV and PPTX endpoints accept `?section=<schema name>`. Clients must pass the
displayed section so opening another section cannot change an export. Omitting it
retains the legacy last-opened-section behavior. Saved results return `stale: true`
when their source, pipeline, prompt or model identity differs, plus current load
timings with zero model calls. Invalid saved JSON returns 409 rather than a server error.

PPTX exports include unavailable fields as `Not available`, preserve decimals, and
use a maturity chart only for a complete split with passing checks. Speaker notes
retain borrowing scope, warnings, calculations and all component citations.

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

## Knowledge base — `data/kb/` (RAG + memory)

Every parsed report leaves its data behind as plain files so the corpus grows and the local model gets more context
with every run. Layout, one folder per report:

```
data/kb/<stem>/
  meta.json                 # company, fiscal_year, language, source_url, pages, sha256 of the PDF
  pages.jsonl               # {"page": 1, "text": "..."} per page — the text layer, committed (public data, ~1 MB/report)
  extractions/<section>.json# the Extraction returned by /extract, latest run wins — committed; doubles as eval + few-shot bank
  index.json               # derived model/source manifest, gitignored
  embeddings.jsonl          # {"page", "start", "text", "vec"} per chunk — DERIVED, gitignored, rebuilt by /index
```

- Upload or library registration writes `meta.json` + `pages.jsonl`. `/extract` writes `extractions/<section>.json`.
- `/index` chunks `pages.jsonl` (~800 chars, page-aware) **and** turns each extracted field into a fact chunk
  (`"Atlas Copco FY2025 · Consolidated income statement · Revenue = 176 771 MSEK (p.106)"`), embeds both with `EMBED_MODEL`.
- `/ask` retrieves top-k chunks by cosine (+ keyword overlap rerank so exact figures/labels win), prompts `LLM_MODEL` with
  the chunks labelled `[Company p.N]`, requires verbatim quotes, verifies them on the page — same provenance rule as fields.
- "Gets better over time": `/extract` includes up to 2 prior *checks-passed* extractions of the same section from the KB
  as few-shot examples in the prompt (`FEWSHOT=0` disables). Fine-tuning is out of scope; the KB is the training set if it ever isn't.

## LLM configuration (backend)

Environment variables, read from `backend/.env`:

```
LLM_PROVIDER=codex                     # codex, http, or fixture; auto-detected when unset
LLM_BASE_URL=http://localhost:11434/v1   # HTTP extraction only, not used by codex
LLM_MODEL=gpt-5.6-terra
LLM_REASONING=low
EMBED_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama                       # any non-empty string for Ollama
EMBED_MODEL=bge-m3                       # via the same base URL's /embeddings; multilingual (sv+en). `ollama pull bge-m3`
KB_DIR=../data/kb                        # optional override
```

Same variables point at Azure OpenAI / OpenAI / OpenRouter with no code change.
# Debt evidence and OCR

Debt maturity uses consolidated carrying amounts. Contractual cash flows (including future interest), parent-only schedules, and lease-only schedules are not substitutes. The result includes `debt_scope`, a description of the reported borrowing scope, and `context_source` for the selected note. Missing disaggregation stays null with a warning.

Debt fields may include `components: [{value, source: {page, quote}}]` and `calculation`. The backend verifies every printed component and computes the sum. `source` remains the first component for compatibility. Clients must show the component list for calculated fields. JSON and CSV retain all component evidence. A passed sum check establishes arithmetic consistency, not accounting scope or OCR accuracy.

Scanned or outlined-text pages use local PyMuPDF OCR at 200 DPI when native text is absent. Install English/Swedish data with `python scripts/setup_ocr.py`. Native text pages bypass OCR. Parsed pages are cached under parser version 3. An absent OCR language file returns an actionable error rather than saving empty text.


Retrieval citation validation uses the model response's exact `report` ID, not a
company-name guess. Public citations still return company, fiscal_year and report_id.
A quote must occur in a retrieved excerpt and its source page. Any rejected citation
withholds the answer text. `ocr_settings` in report metadata keys OCR cache reuse.
Explicit knowledge-base Rebuild recomputes vectors; ordinary refresh may reuse them.

Index status may temporarily be `building` while a report is being updated. Listing
returns the last known counts without waiting for the embedding operation.
