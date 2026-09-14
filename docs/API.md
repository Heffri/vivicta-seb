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
| `GET`  | `/api/library` | – | `LibraryEntry[]` — bundled annual reports in `data/reports/` (only files present on disk) |
| `POST` | `/api/reports/{report_id}/index` | – | `IndexStatus` — chunk + embed the report into the knowledge base (idempotent, cached on disk). ~10–30 s per report locally |
| `POST` | `/api/ask` | `{ "question": string, "report_ids": string[] }` | `Answer` — RAG over the selected reports (page texts + prior extractions). Indexes on demand if `/index` was not called |
| `GET`  | `/api/kb` | – | `KbEntry[]` — what is in `data/kb/` (one per parsed report: pages indexed, sections extracted) |
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
  indexed: boolean;         // embeddings cached
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
  confidence: number;       // 0..1
};

type Check = {
  name: string;             // from schema.checks[].name
  passed: boolean;
  detail: string;           // human-readable, e.g. "152340 + -88120 = 64220 == 64220"
};

type Extraction = {
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

Every non-null `value` **must** carry a `source`. Backend verifies `source.quote` occurs verbatim
(whitespace-normalised) in the text of `source.page`; if not, it appends a warning and lowers
`confidence`. This is the provenance + anti-hallucination story — do not drop it.

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
    { "key": "revenue", "label": "Revenue", "description": "...", "unit_hint": "currency_millions" }
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

## Bundled report library — `data/reports/`

PDFs are gitignored (large). `data/reports/index.json` is committed and lists them with `company`, `fiscal_year`,
`language`, `source_url`, `tags`. `python data/fetch.py` downloads every entry that is missing. `GET /api/library`
returns index entries whose file exists on disk, with `pages` filled in.

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
- `/ask` retrieves top-k chunks by cosine (+ keyword overlap rerank so exact figures/labels win), prompts `LLM_MODEL` with
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
