# Acrylic branch — notes for the team

What this branch changed, how to run it, and what the backend hardening found along the way — for
whoever picks this up next. Background, if you haven't read it yet: [`README.md`](../../README.md),
[`docs/HANDOFF.md`](../HANDOFF.md) (backend state, decided-today scope), [`docs/API.md`](../API.md)
(the contract), [`DESIGN.md`](DESIGN.md) (the token system everything below is built on).

## What this branch is

The frontend is redone in the UAW "acrylic" glass design language (tokens, rationale, contrast
numbers: [`DESIGN.md`](DESIGN.md)). Alongside it, a batch of backend fixes that don't need a model to
verify — locator, parser, label matching. `main` hasn't moved; nothing here has merged there.

**Running it** (full version in the root [`README.md`](../../README.md)):

- **Fixture mode**: copy `backend/.env.example` to `backend/.env`, leave every `LLM_*` unset.
  `POST /extract` then returns the canned `backend/fixtures/sample_extraction.json` for anything — no
  Ollama, no GPU. Good enough for the whole UI except real per-report data.
- **Real data**: drop a PDF into `data/reports/` (gitignored), named `<company>_<year>.pdf`.
  `atlas_copco_2025.pdf` is the one most of this branch was screenshotted against — its
  `data/kb/atlas_copco_2025/` entry already exists, so Knowledge base → Atlas Copco → income_statement
  is a real extraction, real page images, real citations, zero inference.
- **Tone**: the toggle in the rail footer flips `<html data-tone>` between the dark default and
  `"light"`, persisted to `localStorage`. No `.dark` class anywhere, no OS dark-mode hook.
- **Screenshots** below came from a plain `npm run dev` plus a browser, both tones, 1440×900 unless
  noted — see [`frontend/README.md`](../../frontend/README.md) for the dev-server command itself,
  nothing else to set up.

## Frontend

**Design in one paragraph**: one glass pane, not a stack of them. The whole shell (titlebar + rail +
stage + status bar) is a single blurred `.glass` surface over a wallpaper gradient; everything inside
it — cards, tables, badges — is a flat, translucent step of `--bg-1..4`, no per-component blur. The one
exception is floating popovers (`SelectContent`): they render outside the window pane, so they keep
their own thin glass. Dark is the default (`:root`), light is `[data-tone="light"]` — there's no
`.dark` class. Full token table and contrast numbers: [`DESIGN.md`](DESIGN.md).

| View | What changed | Evidence |
|---|---|---|
| Shell (titlebar, rail, status bar, tone toggle) | Rebuilt on the token system; the 5-tab rail folds to icons ≤900px; tone choice persists across reloads | [v001](evidence/v001.md) |
| Extract (`UploadView`) | One pane, three faces (directory search / cached reports / upload) side by side ≥1280px, single column ≤900px; cached reports out of a collapsed `<details>`, open by default; busy state dims the faces but keeps the action bar live; faces widened and the cached-card grid fills its face ≥1280px; the upload face's title no longer wraps mid-word at narrow widths (the hint drops to its own line instead); drag/drop and the file picker now accept several PDFs at once — staged as a list with per-file remove, deduped by name+size, appended rather than replaced on a second drop (the one row here where view logic changed: `file` state became `files[]`) | [v002](evidence/v002.md), [v010 §4](evidence/v010.md), [v015 §4](evidence/v015.md), [v021](evidence/v021.md) |
| Results (`ResultsView`, `FieldsTable`, `SourcePanel`, `StatusCards`) | Split into 5 files; selected row gets an accent left edge; the PDF/Image toggle is a segmented control; the quote block highlights the matched value inline (verified on 34/34 real cases); debt sections get a `MaturityChart` card (pure SVG, driven by field keys not the section name), mounted as the first row above the table; the no-`onBack` header eyebrow deduped from the titlebar's own text to the view name ("Results") — the `onBack` breadcrumb state is untouched | [v003](evidence/v003.md), [v009](evidence/v009.md), [v010 §3](evidence/v010.md), [v015 §3](evidence/v015.md) |
| Compare | "Field" column is sticky; each report header is a small card tile; checks/failed badges use the real status-token variants instead of hardcoded colors; the header eyebrow deduped to "Comparison"; a failed column's error cell gains a one-line next step ("fetch the PDF from Extract's directory search, then open it here again"); debt-maturity sections gain a per-column mini-bar (same bucket rule and identity check as Results' `MaturityChart`, never recomputed — only the sliver's pixel width is local arithmetic; a danger sliver, or a ring outline when there's no room to draw one, on a failed sum-to-total check) | [v004](evidence/v004.md), [v015 §2–3](evidence/v015.md), [v020](evidence/v020.md) |
| Ask | Pulled out of `App.tsx` into `AskView`; citation chips get a stronger hover; example questions are badge "chips" | [v004](evidence/v004.md) |
| Knowledge base (`KbView`) | Filter box (case-insensitive, shows `n / 102`, doesn't disturb an existing selection); sticky table header; accent row selection; a 409 ("PDF not cached") now tells you to fetch it from Extract first; rows without a cached PDF get a muted "no PDF" badge and a disabled Open button/checkbox with a tooltip; the header count splits into "n reports · m with PDF"; a "With PDF only" toggle filters the table, and degrades to a disabled no-op rather than a false filter if the library call hasn't resolved | [v005](evidence/v005.md), [v010 §5](evidence/v010.md), [v019](evidence/v019.md) |
| Cross-cutting | Hardcoded emerald/amber/red replaced by `--success`/`--warning`/`--danger` tokens everywhere; wallpaper redone as a two-glow gradient so the glass reads as glass, not flat fill; focus rings, hover/active steps, disabled state, `Select`/`Table` interaction states unified; shared `LoadingLine`/`ErrorBlock` rolled out to Extract, Ask and Knowledge base (Results/Compare's error surfaces are per-cell, not view-level, so left as-is); shell rail + tone toggle got the same focus ring; the same outline-ring recipe extended to the directory-search input, the KB filter input, the Results PDF/Image segmented toggle, and the Ask textarea | [v006](evidence/v006.md) (incl. v006b), [v010](evidence/v010.md), [v015 §1](evidence/v015.md) |

**Screenshots** — the closest thing to a full walkthrough, one pair per tab, `evidence/v010/`, 1440×900:

| Tab | Dark | Light |
|---|---|---|
| Extract | [dark](evidence/v010/extract-dark.png) | [light](evidence/v010/extract-light.png) |
| Results — income_statement (real data, no chart) | [dark](evidence/v010/results-income-dark.png) | [light](evidence/v010/results-income-light.png) |
| Results — debt_maturity (chart) | [dark](evidence/v010/results-debt-dark.png) | [light](evidence/v010/results-debt-light.png) |
| Compare | [dark](evidence/v010/compare-dark.png) | [light](evidence/v010/compare-light.png) |
| Ask | [dark](evidence/v010/ask-dark.png) | [light](evidence/v010/ask-light.png) |
| Knowledge base | [dark](evidence/v010/kb-dark.png) | [light](evidence/v010/kb-light.png) |
| KB, PDF not cached (409) | [dark](evidence/v010/kb-409-dark.png) | [light](evidence/v010/kb-409-light.png) |

Three panes changed enough after v010 that its shot of them is stale; these replace just that pane, the
rest of the table above still holds:

| Tab / feature | Dark | Light |
|---|---|---|
| Extract — multi-file drop staged | [dark](evidence/v021/dropzone-two-files-dark.png) | [light](evidence/v021/dropzone-two-files-light.png) |
| Compare — debt-maturity mini-bars | [dark](evidence/v020/bars-dark.png) | [light](evidence/v020/bars-light.png) |
| Knowledge base — PDF availability + "With PDF only" | [dark](evidence/v019/kb-a-full-dark.png) | [light](evidence/v019/kb-a-full-light.png) |

Narrower layouts, individual interaction states (focus rings, busy, drag) and the earlier per-view
passes are in `evidence/v001/` through `evidence/v009/`, plus `evidence/v015/` (the focus-ring pass),
`evidence/v019/`, `evidence/v020/` and `evidence/v021/` (bonus states beyond the pair linked above —
mismatch/zoom crops, the Compare landing shot, the fallback-library state).

**New primitives in `components/ui/`**: `input.tsx` (text input), `segmented.tsx` (the PDF/Image-style
toggle), `state.tsx` (`LoadingLine`, `ErrorBlock` — the shared busy/error shapes). `Table` takes an
optional `containerClassName` now — its wrapper div is hardcoded `overflow-x-auto`, which silently
defeats `position: sticky` headers in a bounded box; pass e.g.
`containerClassName="max-h-[70vh] overflow-y-auto"` rather than reaching in from outside. `Badge`
gained `success`/`warning`/`danger` variants alongside the originals.

**Unchanged**: `api.ts`, `types.ts`, the API contract, and every view's actual logic — state machines,
fetch order, prop signatures — with one exception: v021 turned Extract's upload state from a single
`File | null` into `files: File[]` so a drop can stage more than one PDF (still no router, no state
library, no new dependency). Every other piece of evidence above says the same thing: "logic change:
none." This was a restyle, not a rewrite.

## Desktop app

A double-click Windows app, not just a browser tab: an Electron shell (`desktop/`) around the same
frontend, launching a PyInstaller-built `backend.exe` instead of a dev `uvicorn` process. Dev mode
starts the venv backend, `frontend`'s own dev server, and the Electron window in sequence, each
gated on a health check; packaged mode bundles `backend.exe` + `frontend/dist` and serves both from
the same origin — the backend itself hosts the static frontend at `/` and the API at `/api`, no
proxy or CORS involved. [v029](evidence/v029.md), [v030](evidence/v030.md), [v032](evidence/v032.md)

On Windows 11 the window paints with real OS acrylic material (`backgroundMaterial: 'acrylic'`,
confirmed live via a logged `acrylic material: true` check; Windows 10 and earlier degrade to an
opaque window — implemented, not testable on this branch's machines). The custom titlebar (no
native chrome) is draggable and supports double-click-to-maximize/restore, verified at the Windows
message level (`WM_NCHITTEST`/`WM_NCLBUTTONDBLCLK` against the real window). `npm run dist`
produces two unsigned packages, portable and NSIS — unsigned means Windows SmartScreen warns on
first run ("More info" → "Run anyway"). The data directory (reports, KB, uploads, `backend.log`)
lives under the user's own `app.getPath('userData')/data`, seeded once from the bundled repo data
on first launch and left alone on later launches/upgrades; first launch has no model provider
configured, so it defaults to demo/fixture mode until Settings picks one (see "Model providers"
below). [v029](evidence/v029.md), [v038](evidence/v038.md), [v032](evidence/v032.md)

**Build** (full detail: [`desktop/README.md`](../../desktop/README.md)):

```powershell
cd backend  && python build_exe.py     # -> backend/dist/backend/backend.exe (PyInstaller onedir)
cd frontend && npm run build           # -> frontend/dist
cd desktop  && npm run dist            # -> desktop/dist/*.exe (portable + nsis, both unsigned)
```

## Model providers

Four ways to answer `/extract` and `/ask`, selected by `LLM_PROVIDER` (`backend/.env` or the
desktop Settings tab) — **Local Ollama**, an **OpenAI-compatible endpoint** (OpenAI/Azure/
OpenRouter, or Anthropic's own OpenAI-compatible endpoint with an API key), **Codex CLI**, and
**Claude CLI**:

| Provider | `LLM_PROVIDER` | Env | Auth |
|---|---|---|---|
| Local Ollama | unset (default) | `LLM_BASE_URL=http://127.0.0.1:11434/v1`, `LLM_MODEL` (e.g. `qwen3:8b`) | none |
| API endpoint (OpenAI/Azure/OpenRouter/Anthropic-compatible) | unset (default) | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | API key |
| Codex CLI | `codex` | `LLM_MODEL` (default `gpt-5.6-terra`), optional `CODEX_BIN` | `codex login` (subscription/API key); no `LLM_BASE_URL` needed |
| Claude CLI | `claude` | `LLM_MODEL` (default `claude-sonnet-5`), optional `CLAUDE_BIN` | `claude login` (subscription); no `LLM_BASE_URL` needed |

Nothing set at all (no `LLM_BASE_URL`, no `LLM_PROVIDER`) means fixture/demo mode — no model call,
canned data. The desktop Settings tab (browser tabs get a read-only mirror) turns this into four
provider cards plus a text link back to demo mode; Save writes `<userData>/config.json` (API key in
plaintext, never logged) and restarts the backend on the same port with the matching env.
[v031](evidence/v031.md), [v033](evidence/v033.md), [v039](evidence/v039.md)

**Embeddings are the one thing that never follows `LLM_PROVIDER`** — `/index` and `/ask`'s retrieval
always call an OpenAI-compatible `/v1/embeddings` endpoint directly, so both still need
`LLM_BASE_URL` pointed at Ollama or a real endpoint even when extraction itself runs on Codex or
Claude. [v031](evidence/v031.md), [v039](evidence/v039.md)

Both CLI providers were checked end-to-end against the same real Atlas Copco `income_statement`
extraction the local-model baseline used: Codex (`gpt-5.6-terra`) matched **9/9** fields, 0
warnings; Claude (`claude-sonnet-5`) matched **9/9** fields, 0 warnings — same values, same
citations, same pages, both on the first attempt. [v031](evidence/v031.md), [v039](evidence/v039.md)

## Backend hardening

Most of the below calls no model at all — each row is a deterministic pipeline or schema change,
checked against the 102+ reports already parsed into `data/kb/` and/or PDFs fetched for the
purpose. The four `debt_maturity` hardening-loop rows are the exception: each runs
`scripts/random_check.py` against a real model (Codex CLI) to find failures on a random sample,
then lands a deterministic fix — schema wording/keywords, or an `extract.py` code change — verified
afterwards with no further model calls. `python -m pipeline.test_confidence` and `test_parse` are
green throughout — see "How to verify".

| Change | Why | Evidence |
|---|---|---|
| `scripts/random_check.py --exclude-sector`; `locate.py` table-of-contents matching (`toc_targets`: front-matter pages, then widened to note-index pages document-wide; folio-offset alignment; +5 score boost for a TOC-named page) + schema `toc_keywords`. Three follow-ups tried and reverted: schema `exclude_keywords`, a neighbour-page score bonus, and a schema-level `title_keywords` list that narrows which words count as a heading hit. | HANDOFF's Task 0 (`random_check` couldn't exclude sectors yet) and its "Next for a teammate" #1 (use the table of contents as a locator hint). | [v008](evidence/v008.md), [v017](evidence/v017.md) |
| `debt_maturity.json`'s `maturity_sums_to_total` check gains `null_as_zero` on the three bucket fields (not `total_debt`); `extract.py` now scores a listed-null operand as 0 once at least one sibling bucket is real. | HANDOFF: "Null buckets are normal" — Ericsson's real, correct extraction (32 703 = 3 538 + 29 165, no >5y row) was failing the identity check, so the total was never actually verified. | [v011](evidence/v011.md) |
| Three spots in `extract.py` — `_label_known`; `_row_label` (was truncating at the first digit) plus `_statement_row`'s exact-match set; the sum-repair's `own_syns` — now compare the schema synonym through the same cleanup as the printed label, not verbatim. New `scripts/label_regression.py` makes the check repeatable. | A synonym with a digit in it (`"1-5 years"`) could never match a cleaned label (`"1-5years"`, digits glue to neighbours) — every debt-maturity bucket synonym has a digit, so a correctly-read bucket row still capped at 0.9 confidence, or (for `_statement_row`) couldn't be found as a row at all. | [v011 §v011b](evidence/v011.md), [v012](evidence/v012.md), [v014](evidence/v014.md) |
| `parse.py`'s `page_text()`: block-local baseline merge joins a row's label and figures back together when the text layer split them onto separate lines inside one PyMuPDF block; word-level rebuild as a fallback; pure-prose pages untouched, byte for byte. `PARSER_VERSION` 2 → 3 — existing `data/kb` needs `python -m pipeline.kb build` to pick this up (not run by this branch). New `backend/pipeline/test_parse.py`, `scripts/parse_check.py`. | HANDOFF called this out directly: plain `get_text()` loses table structure, likely to matter more for debt notes (pure tables) than it did for the income statement. | [v013](evidence/v013.md) |
| `_clean_label` strips a footnote marker — a glued superscript digit, or a bare `digit)` — sitting directly against a currency/unit token, right before the existing currency/unit strip runs. | Same normalization-asymmetry family as the row above, one step later: a footnote glued to a bare currency word with no space (`"SEK1)"`) survived cleanup while the same label without the footnote didn't, per v014's own Findings note. | [v018](evidence/v018.md) |
| `_clean_label` also strips magnitude-prefixed currency/unit tokens (`MSEK`, `TSEK`, `KSEK`, `kSEK`, `MEUR`, bracketed or not). | The unit regex only matched bare unit words, so `"Revenue, MSEK"` and `"Revenue"` cleaned to different strings; found by v018, fixed the same way. 739/739 stored labels unchanged. | [v023](evidence/v023.md) |
| `debt_maturity` hardening loop, seed 1 (`random_check.py --seed 1`, Mid Cap, Codex `gpt-5.6-terra`): 3/10 already correct (no note to extract, or already full confidence), 1/10 a known locator gap left alone (bare "maturity" keyword, already tried and reverted in v017), 2/10 fixed by schema-keyword-only changes (NCAB's locator ranking, Apotea's `total_debt` label), 4/10 hit a new gap — a maturity note that prints its buckets as *columns of one row* instead of separate rows, which every existing `extract.py` repair assumes | First seed of a repeated hardening pass on the section SEB actually scoped; surfaces failure modes the earlier locator/label lanes hadn't hit | [v035](evidence/v035.md) |
| `extract.py` gains a general column-bucket reader — schema-driven off the identity check's own total/parts fields, not company-specific — that fills a null or overrides a disagreeing model answer from a qualifying page's row/column layout, declining rather than guessing when a row's column count doesn't match its header | Fixes the shape v035 found: 1 of its 4 gap companies (Cloetta, all 4 fields lift); the other 3 (XANO, Ework, Bergman & Beving) verified by hand to have a scrambled header or a genuine two-basis mismatch, and correctly still decline | [v036](evidence/v036.md) |
| `debt_maturity` hardening loop, seed 2 (`random_check.py --seed 2`, Codex `gpt-5.6-terra`): full-confidence count unchanged at 1/10; 3 schema commits (a Swedish current/non-current label, Swedish digit-form bucket splits, broadened finer-split wording) shipped but moved no confidence number in this seed — 7/10 blocked by the report's own bucket granularity or basis not matching the schema's ask (or a locator miss on the real page), not a keyword gap; 2/10 are real `extract.py` bugs precisely diagnosed but left for a separate change | Second seed of the same loop, to see whether v036's fix generalized and what the next-largest failure mode is | [v037](evidence/v037.md) |
| `extract.py`: the column-bucket mechanism now rejects a whole row's column reading — not just one field — if any bucket value exceeds the row's own total past the check's rounding tolerance (Acast, which had been reading a stale prior-year row); `_derived_value`'s neighbour-sum repair no longer requires a row's label to be a *known* schema synonym before treating it as the model's own row, only that the value is literally quoted and the model's own label names that row (Nelly, whose correct current-portion answer was being overwritten by a current+non-current sum) | Fixes v037's two precisely-diagnosed bugs, both offline, zero model calls | [v040](evidence/v040.md) |

**A single before/after model call is not proof.** v037 re-ran its own 10 companies a second time
with no code change and watched two confidence numbers move anyway (Humana up, Storytel down) —
this model's run-to-run variance is large enough that a lone before/after pair can look like a fix
or a regression when it's neither. Verify anything below a full pass with a repeated-trial (n≥3)
check before trusting a small confidence delta. [v037](evidence/v037.md)

Numbers behind the table: the TOC pass found a table-of-contents target for `debt_maturity` in 0/102
reports scanning only the front matter, 2/102 once the scan widened to the whole document (0 top-1
ranking changes either way); `income_statement` went 10/102 → 11/102 hits, also 0 top-1 changes, and
the 101 already-stored source pages stayed in the top 2 throughout. All three follow-up locator
experiments were net negative: `exclude_keywords` flipped 21 companies' top-1 page (2 better, 16 worse,
3 neutral); the neighbour-page bonus flipped 8 (radius 2) or 6 (radius 1), almost all regressions either
way; the schema-level `title_keywords` heading gate flipped 12/101 (2 reports tied at 0 candidates
either side, excluded from the count) — 4 better, 7 worse, 1 neutral. All three fail for the same
underlying reason: for several issuers (aq, seb, swedbank, sca, essity) the one real maturity table sits
on the page titled "Liquidity risk," while for others (aak, alvotech, asmodee, volvo_car) that identical
title marks a narrative or pointer page instead — no fixed heading-keyword list can split them, so all
three experiments reverted and the current locator stays TOC-only. The label-normalization fixes: a
full-KB regression over 101 `income_statement` files first found 735/736 verdicts identical, one inert
change (ssab_2025); closing the label-side footnote-glue gap above fixed that one too — the same check
is now 739/739 identical across `income_statement` and `debt_maturity` combined, 0 changed. Correctly-read
bucket rows now score confidence 1.0 instead of capping at 0.9. The parser fix: split-row rate (a label
torn from its own figures) over 10 real PDFs went from 12.14% → 0.24% on debt-relevant pages and 20.42% →
0.19% on income pages, with all 76 previously-verified `income_statement` quotes (+3/3 debt) still
matching after the re-parse.

## Contract gaps we noticed, not fixed

- **Opening a KB report rewrites tracked files.** Reading an extraction whose PDF is on disk makes the
  backend rewrite `data/kb/<stem>/{meta.json,pages.jsonl}` as a side effect of its re-registration path
  — hit repeatedly while screenshotting Atlas Copco, always had to be `git restore`d before committing.
  [v001](evidence/v001.md), [v003](evidence/v003.md), [v005](evidence/v005.md),
  [v006](evidence/v006.md), [v009](evidence/v009.md), [v010](evidence/v010.md).
- **Fixture `/extract` ignores the section and the file.** In fixture mode, `POST /extract` returns the
  same canned extraction regardless of `report_id`, the requested section, or which PDF was actually
  uploaded — reconfirmed on a multi-file upload, where every column in the batch renders identically.
  Fine for UI work, but fixture mode alone can't distinguish per-section or per-report behavior.
  [v004](evidence/v004.md), [v021](evidence/v021.md).
- **A check's `identity` flag doesn't reach the API.** The schema marks `maturity_sums_to_total` as
  `"identity": true`; the extraction response's `Check` drops it, so the frontend has to find "the"
  identity check by matching its name string instead. [v009](evidence/v009.md).
- **`BUCKET_ORDER` / `BUCKET_LABELS` are defined twice.** Once in `backend/pipeline/ppt.py`, once in
  `frontend/src/components/results/MaturityChart.tsx` — HANDOFF's note that `ppt.py` is "the only
  coupling" for bucket keys is now a coupling between two files. [v009](evidence/v009.md).
- **KB open fails whole, not per-field, when the PDF isn't on disk.** A stem whose PDF isn't in
  `data/reports/` 409s the entire open, not just the page images — right now only Atlas Copco is
  openable offline. [v003](evidence/v003.md).

## Assumptions to confirm with Kristian / SEB

Three calls the `debt_maturity` schema now makes on Kristian's behalf, written into its field
descriptions (and the prompt the model reads) so they're applied consistently — not yet confirmed:

- **Carrying amount, not contractual undiscounted maturities.** We assumed the table whose total
  reconciles to interest-bearing borrowings on the balance sheet, never the liquidity-risk note's
  undiscounted cash-flow table (includes future interest); the locator alone can't tell them apart.
  We assumed this; confirm it or tell us to flip it. [v008](evidence/v008.md), [v028](evidence/v028.md).
- **Lease liabilities (IFRS 16) follow the report's own convention.** `total_debt` includes them only
  if the report's own note already does — we never add or remove leases ourselves. We assumed this;
  confirm it or tell us to flip it. [v028](evidence/v028.md).
- **A missing bucket (e.g. no `>5y` row) counts as 0 in the sum check**, not a check failure. We
  assumed this; confirm it or tell us to flip it (fail the check instead).
  [v011](evidence/v011.md), [v028](evidence/v028.md).
- **A report's own finer bucket splits (e.g. `1-2y`/`2-5y`, or nothing finer than a plain
  current/non-current split) get summed into our three buckets, not kept as their own fields.** The
  schema tells the model to add a report's own finer columns into `due_within_1_year`/
  `due_1_to_5_years`/`due_after_5_years`, and (since v036/v040) `extract.py`'s column-bucket reader
  does the same arithmetic deterministically off the page where it can. We assumed a 3-bucket shape
  is what's wanted downstream; confirm it, or tell us to add the finer buckets as their own schema
  fields instead — that would also mean touching `ppt.py`'s `BUCKET_ORDER`/`BUCKET_LABELS` and the
  frontend's maturity charts, not just the schema.
  [v035](evidence/v035.md), [v036](evidence/v036.md), [v037](evidence/v037.md).

## How to verify

```bash
cd frontend && npm run build && npm run lint       # tsc -b + vite build, then oxlint
cd frontend && npm run e2e                         # Playwright end-to-end pass
cd backend  && python -m pipeline.test_confidence  # extract.py's evidence/confidence scoring
cd backend  && python -m pipeline.test_parse       # parse.py's row-merge behavior
cd backend  && python -m pipeline.test_kb          # kb.save_report idempotency self-check
cd backend  && python -m pipeline.test_paths       # dev-tree-vs-frozen path resolution self-check
cd backend  && python -m pipeline.test_llm         # codex_cli/claude_cli discovery + round-trip self-check
```

Three offline, read-only scripts (repo root `scripts/`, no model calls, nothing started):

- `python scripts/locate_check.py --section debt_maturity [--only <substr>] [--top 5]` — each
  company's top candidate pages for a section, straight from `data/kb/*/pages.jsonl`, plus a crude
  "looks like the note" marker (a triage aid, not a score).
- `python scripts/label_regression.py [--schema income_statement] [--schema debt_maturity] [--baseline <git ref>]`
  — walks every stored KB extraction, compares label-matching verdicts between a baseline `extract.py`
  (default `origin/acrylic`) and the current one.
- `python scripts/parse_check.py [--out <file>] [--quotes] [--locate]` — split-row rate over every PDF
  in `data/reports/` by default; `--quotes` re-checks stored quotes against a fresh re-parse;
  `--locate` compares locator rankings before/after.
