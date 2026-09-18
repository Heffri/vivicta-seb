// Copied verbatim from docs/API.md — change it there first, then here.

export type Report = {
  report_id: string;        // opaque id, use in later calls
  filename: string;
  pages: number;
  company?: string | null;  // best-effort guess from first pages, may be null
  fiscal_year?: number | null;
};

export type Company = {
  name: string;             // as listed, e.g. "Sandvik AB"
  ticker: string;           // "SAND"
  sector: string | null;    // ICB sector text
  isin: string | null;
  cached_years: number[];   // years already present in the report cache, e.g. [2025]
};

export type LibraryEntry = {
  file: string;             // basename in data/reports/, e.g. "atlas_copco_2025.pdf"; key for from-library
  company: string;          // display name, curated in data/reports/index.json
  fiscal_year: number;
  language: 'en' | 'sv';
  pages: number;
  source_url: string | null;
  tags: string[];           // collections, e.g. ["wallenberg", "industrials"]; UI offers each tag as a one-click set
  note?: string | null;     // e.g. "image-only PDF, no text layer"
};

export type IndexStatus = { report_id: string; chunks: number; embed_model: string; cached: boolean };

export type Citation = {
  report_id: string;
  company: string | null;
  fiscal_year: number | null;
  page: number;
  quote: string;            // verbatim, verified against the page text like Field.source (unverified => dropped from citations, warning added)
  score: number;            // retrieval similarity 0..1, for the UI only
};

export type Answer = {
  question: string;
  answer: string;           // markdown; cites as [Company p.N]
  citations: Citation[];
  warnings: string[];
  model: string;
};

export type KbEntry = {
  stem: string;             // data/kb/<stem>/, = report filename without .pdf
  report_id: string | null; // set while the backend has it registered this run
  company: string | null;
  fiscal_year: number | null;
  pages: number;
  sections: string[];       // extractions present, e.g. ["income_statement"]
  indexed: boolean;         // embeddings cached
};

export type Source = {
  page: number;             // 1-based page in the uploaded PDF
  quote: string;            // verbatim text from that page that supports the value
};

export type Field = {
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

export type Check = {
  name: string;             // from schema.checks[].name
  passed: boolean;
  detail: string;           // human-readable, e.g. "152340 + -88120 = 64220 == 64220"
};

export type Extraction = {
  report_id: string;
  company: string | null;
  fiscal_year: number | null;
  currency: string | null;  // dominant unit in the section
  section: string;          // schema name
  basis?: 'carrying' | 'undiscounted'; // v089, debt_maturity only: which maturity table total_debt + the buckets were read from
  fields: Field[];          // one entry per schema field, in schema order (value null if missing)
  checks: Check[];
  warnings: string[];       // free text, e.g. "revenue: quote not found on page 64"
};

// GET /api/schemas returns backend/schemas/*.json as-is. Only what the UI reads is typed.
export type Schema = {
  name: string;             // used in POST /extract { section }
  title: string;
  description?: string;
};

// Frontend-only: one queued report after extraction. Exactly one of extraction / error is set.
export type Result = {
  label: string;            // company display name (library) or filename (upload)
  sectionTitle: string;
  extraction?: Extraction;
  error?: string;
};
