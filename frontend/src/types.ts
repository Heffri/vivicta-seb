// Copied verbatim from docs/API.md — change it there first, then here.

export type Report = {
  report_id: string;        // opaque id, use in later calls
  filename: string;
  pages: number;
  company?: string | null;  // best-effort guess from first pages, may be null
  fiscal_year?: number | null;
  document_type?: "registration_statement";
  statement_pages?: number[];
  source_notice?: string;
  ocr_pages?: number[];     // 1-based pages this registration actually OCR'd (empty for a text-layer PDF)
};

export type Company = {
  name: string;             // as listed, e.g. "Sandvik AB"
  ticker: string;           // "SAND"
  sector: string | null;    // ICB sector text
  isin: string | null;
  cached_years: number[];   // years already present in the report cache, e.g. [2025]
  // Curated private holdings are disclosed in this parent report, not fetchable as an issuer PDF.
  // `report_page` is the parent report's relevant portfolio section when saved page text can find it.
  no_standalone_report?: boolean;
  reports_in?: string;
  collection_group?: string;
  report_stem?: string | null;
  report_page?: number | null;
};

export type Candidate = {          // one entity POST /api/reports/discover proposes; identity fields are model-reported unless saved
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

export type Discovery = {
  candidates: Candidate[];
  note: string | null;
  source?: 'saved' | 'web';
  skipped_web_search?: boolean;
};

export type JobEvent = { t: number; stage: string; text: string; data?: Record<string, unknown> };
// data: download carries { bytes, total: number | null }; model_search carries { queries: string[] } and/or
// { candidates / urls }, whichever the stage produced — see docs/API.md's Progress tracking section
export type Job = {                // GET /api/jobs/{job_id}
  job_id: string;
  stage: string;             // directory | mfn | nasdaq | ddg | model_search | ir_page | download | verify | done | failed
  started: number;           // unix seconds
  updated: number;
  done: boolean;
  error: string | null;      // the failed event's own text; null until then
  events: JobEvent[];
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
  stem?: string;            // saved report source for text-only citations
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
  text_available?: boolean; // false for empty saved page text; optional for older backends
  figures_available?: boolean; // at least one non-null extracted field
  stem: string;             // data/kb/<stem>/, = report filename without .pdf
  report_id: string | null; // stable ID, restored after restart
  company: string | null;
  fiscal_year: number | null;
  pages: number;
  sections: string[];       // extractions present, e.g. ["income_statement"]
  indexed: boolean;         // embeddings cached
  status: 'ready' | 'missing' | 'outdated' | 'invalid' | 'building';
  reason: string;
  embed_model: string | null;
  dimensions: number | null;
  chunks: number;
  page_chunks: number;
  fact_chunks: number;
  built_at: string | null;
  sector: string | null;
  pdf_available: boolean;
  reported_members?: { name: string; collection_group: string }[]; // curated private holdings covered inside this parent report
};

export type Source = {
  page: number;             // 1-based page in the uploaded PDF
  quote: string;            // verbatim text from that page that supports the value, or a proven reason why a null cannot be mapped
};

export type MissingReasonDisclosed = {
  span: string;             // original report interval, never a standard bucket label invented by the parser
  amount: number | null;    // amount printed for that interval; null only when the row has no safely-readable amount
  unit: string | null;      // printed/inherited table unit when known
  page: number;
  quote: string;            // verbatim row carrying the disclosed amount
};

export type MissingReason = {
  code: 'absent_in_table' | 'offgrid_span' | 'noncurrent_only' | 'lease_table_only' | 'parent_only' | 'straddle' | 'not_found';
  detail: string;           // human-readable fact established by the existing extraction guard; never model-generated prose
  page?: number;
  quote?: string;
  disclosed?: MissingReasonDisclosed[]; // original off-grid intervals/amounts, never substituted into a standard bucket
};

export type ReviewComponent = { value: number; page: number; quote: string; label: string };
export type HumanReview = { decision: 'confirmed' | 'corrected' | 'unresolved'; reviewer: string; note: string; at: string; source_verified?: boolean };
export type Field = {
  human_review?: HumanReview;
  review_history?: (HumanReview & { previous: Omit<Field, 'review_history'> })[];
  key: string;              // canonical key from the schema, e.g. "revenue"
  label: string;            // human label from the schema
  value: number | string | null;  // null = not found, or (with "absent_in_table" evidence) not printed in this report
  unit: string | null;      // "MSEK", "SEK", "%", ...
  period: string | null;    // "2025", "2024", "2025-Q4"
  raw_label: string | null; // the label as printed in the report, e.g. "Intäkter"
  source: Source | null;
  missing_reason?: MissingReason; // debt_maturity only; present only while this field's value is null. It explains a known absence/refusal without changing the field, check, or standard-bucket semantics.
  components?: ReviewComponent[]; // individually cited human-review inputs whose exact sum is this value
  confidence: number;       // 0..1, computed from evidence by the backend — see docs/CONFIDENCE.md. Never the model's opinion.
  evidence: string[];       // satisfied evidence codes, e.g. ["quote_on_page","value_in_quote","arith_ok"]; 1.0 <=> all seven present; "absent_in_table" = the maturity table prints no column for this window (value stays null, source quotes the header row, the identity counts it as 0)
};

// An analyst-directed /fill response is deliberately not an Extraction: it contains only a
// candidate for one currently-empty field, and must be accepted through the ordinary review form.
export type FieldFill = { candidate: Field | null; warnings: string[] };

export type Check = {
  status?: "passed" | "failed" | "unavailable";
  stale?: boolean;
  name: string;             // from schema.checks[].name
  passed: boolean;
  detail: string;           // human-readable, e.g. "152340 + -88120 = 64220 == 64220"
};

export type Basis = { values: Record<string, string>; reviewer: string; note: string; at: string };
// Deterministic, source-backed form hints. They are not analyst confirmation and do not
// contribute to `ready`; a missing key is deliberately still unknown.
export type BasisSuggestion = { key: string; value: string; source: Source | 'report metadata' };
export type ReviewIssue = { kind: 'basis' | 'field' | 'check'; key: string; detail: string };
export type Comparison = { candidates: KbEntry[]; previous_stem?: string; current_year?: number; previous_year?: number; reasons: string[]; restatement?: Record<string, string>; rows: { key: string; label: string; current: Field['value']; previous: Field['value']; delta: number | null; percent: number | null; sign_change: boolean; reason: string }[] };
export type QueueIssue = ReviewIssue & { report: KbEntry; section: string };
// GET /api/kb/maturity-wall — deterministic upcoming-maturities list over a saved collection.
// No FX conversion: `total`/`due_within_1_year` carry the printed unit unless both fields share a
// recognised currency at different scales (MSEK vs TSEK), in which case both are shown at the coarser
// scale. `share` (due_within_1_year / total) is 0..1, or null when it cannot be computed (a missing
// value, an unrecognised/mismatched currency, or a zero total). `comparable` is false whenever the
// basis is unconfirmed, either field lacks verified evidence, or the currencies do not match — `share`
// can still be present in that case; `reason` explains why (or, if comparable, a soft note like "No
// debt outstanding.").
export type MaturityAmount = { value: number | null; unit: string | null };
export type MaturityWallRow = {
  stem: string; report_id: string | null; company: string | null; fiscal_year: number | null;
  total: MaturityAmount; due_within_1_year: MaturityAmount;
  share: number | null;
  basis_confirmed: boolean;
  consolidation: string | null; debt_basis: string | null; leases: string | null;
  review_status: string;
  comparable: boolean;
  reason: string;
  // The data/companies.json sector (null when the company is not in the universe file) and
  // whether the buckets are complete: the stored identity check passed AND total AND <1y present.
  sector: string | null;
  complete: boolean;
};
// The same wall aggregated per sector. median/min/max only count complete companies' shares
// (a missing bucket is never back-filled with 0); all three are null until one company completes.
export type MaturityWallSector = {
  sector: string | null; companies: number; complete: number;
  median_share: number | null; min: number | null; max: number | null;
};
export type MaturityWall = {
  rows: MaturityWallRow[];
  coverage: { total: number; comparable: number; missing_total: number; missing_w1y: number; basis_unconfirmed: number };
  sectors: MaturityWallSector[];
};
// The prior fiscal year's own figures, read deterministically from the same table as the
// current year (identity-gated on explicit values) — absent entirely when they could not be.
export type PriorYear = {
  fiscal_year: number;
  fields: Record<string, { value: number; source: Source | null }>; // one entry per readable field (a bucket the prior-year table never prints is absent)
  check: { passed: boolean; detail: string };
};
// The report's own calendar-year maturity columns (the years must sum to total_debt within
// the identity check's own tolerance) — absent entirely when the report prints named buckets
// instead, or the year columns cannot be read deterministically.
export type BucketsByYear = {
  basis: 'carrying' | 'undiscounted'; // the same maturity basis total_debt + the buckets were read on
  years: { label: string; value: number; source: Source | null }[]; // one per printed column, label as printed ("2026" … "Later")
};
export type Extraction = {
  cached?: boolean;
  stale?: boolean;
  model?: string;
  timings?: { total?: number; attempts?: number; model?: number };
  basis?: Basis;
  basis_suggestions?: BasisSuggestion[];
  basis_history?: (Basis & { previous: Partial<Basis> })[];
  check_history?: unknown[];
  issues?: ReviewIssue[];   // field + check tasks for a human; ready = no issues
  basis_issues?: ReviewIssue[]; // basis definitions still to confirm; never block ready
  basis_suggested?: Record<string, string>; // prefill for the basis form, read from the extraction; never saved by the backend
  not_reported?: string[];  // schema-optional fields the report does not print (null, not zero, not a task)
  ready?: boolean;
  report_id: string;
  stem?: string;            // saved source, provided when opening the knowledge base
  pdf_available?: boolean; // false means use saved page text instead of the PDF
  company: string | null;
  fiscal_year: number | null;
  currency: string | null;  // dominant unit in the section
  section: string;          // schema name
  maturity_basis?: 'carrying' | 'undiscounted'; // debt_maturity only: which maturity table total_debt + the buckets were read from (env DEBT_BASIS)
  prior_year?: PriorYear;   // debt_maturity only: FY-1 alongside FY for the maturity chart
  buckets_by_year?: BucketsByYear; // debt_maturity only: the report's own calendar-year columns for the maturity chart
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

export type ChunkPage = {
  items: { page: number; start: number; text: string; kind: 'page' | 'fact' }[];
  total: number; offset: number; limit: number;
};
