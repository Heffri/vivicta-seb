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

## LLM configuration (backend)

Environment variables, read from `backend/.env`:

```
LLM_BASE_URL=http://localhost:11434/v1   # Ollama (OpenAI-compatible). Unset => backend returns the fixture (frontend dev mode)
LLM_MODEL=qwen3:8b
LLM_API_KEY=ollama                       # any non-empty string for Ollama
```

Same variables point at Azure OpenAI / OpenAI / OpenRouter with no code change.
