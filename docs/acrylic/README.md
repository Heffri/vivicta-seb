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

## Backend (model-free hardening)

Nothing below calls a model. Each row is a deterministic pipeline or schema change, checked against
the 102 reports already parsed into `data/kb/` and/or PDFs fetched for the purpose.
`python -m pipeline.test_confidence` and `test_parse` are green throughout — see "How to verify".

| Change | Why | Evidence |
|---|---|---|
| `scripts/random_check.py --exclude-sector`; `locate.py` table-of-contents matching (`toc_targets`: front-matter pages, then widened to note-index pages document-wide; folio-offset alignment; +5 score boost for a TOC-named page) + schema `toc_keywords`. Three follow-ups tried and reverted: schema `exclude_keywords`, a neighbour-page score bonus, and a schema-level `title_keywords` list that narrows which words count as a heading hit. | HANDOFF's Task 0 (`random_check` couldn't exclude sectors yet) and its "Next for a teammate" #1 (use the table of contents as a locator hint). | [v008](evidence/v008.md), [v017](evidence/v017.md) |
| `debt_maturity.json`'s `maturity_sums_to_total` check gains `null_as_zero` on the three bucket fields (not `total_debt`); `extract.py` now scores a listed-null operand as 0 once at least one sibling bucket is real. | HANDOFF: "Null buckets are normal" — Ericsson's real, correct extraction (32 703 = 3 538 + 29 165, no >5y row) was failing the identity check, so the total was never actually verified. | [v011](evidence/v011.md) |
| Three spots in `extract.py` — `_label_known`; `_row_label` (was truncating at the first digit) plus `_statement_row`'s exact-match set; the sum-repair's `own_syns` — now compare the schema synonym through the same cleanup as the printed label, not verbatim. New `scripts/label_regression.py` makes the check repeatable. | A synonym with a digit in it (`"1-5 years"`) could never match a cleaned label (`"1-5years"`, digits glue to neighbours) — every debt-maturity bucket synonym has a digit, so a correctly-read bucket row still capped at 0.9 confidence, or (for `_statement_row`) couldn't be found as a row at all. | [v011 §v011b](evidence/v011.md), [v012](evidence/v012.md), [v014](evidence/v014.md) |
| `parse.py`'s `page_text()`: block-local baseline merge joins a row's label and figures back together when the text layer split them onto separate lines inside one PyMuPDF block; word-level rebuild as a fallback; pure-prose pages untouched, byte for byte. `PARSER_VERSION` 2 → 3 — existing `data/kb` needs `python -m pipeline.kb build` to pick this up (not run by this branch). New `backend/pipeline/test_parse.py`, `scripts/parse_check.py`. | HANDOFF called this out directly: plain `get_text()` loses table structure, likely to matter more for debt notes (pure tables) than it did for the income statement. | [v013](evidence/v013.md) |
| `_clean_label` strips a footnote marker — a glued superscript digit, or a bare `digit)` — sitting directly against a currency/unit token, right before the existing currency/unit strip runs. | Same normalization-asymmetry family as the row above, one step later: a footnote glued to a bare currency word with no space (`"SEK1)"`) survived cleanup while the same label without the footnote didn't, per v014's own Findings note. | [v018](evidence/v018.md) |

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
- **`_clean_label` never strips a magnitude-prefixed currency/unit token.** The regex only matches bare
  unit words (`\bSEK\b` can't match inside `MSEK`), so `MSEK`/`TSEK`/`KSEK`/`MEUR` survive cleanup
  untouched, footnote glued to them or not. Dormant today — no schema synonym contains a
  magnitude-prefixed unit — but it's the same normalization-asymmetry class as the label/synonym fixes
  in the backend table above. [v018](evidence/v018.md).

## Open questions for Kristian / SEB

- **Carrying amount or contractual (undiscounted) maturities?** HANDOFF already asks this; what we
  found says it can't be settled from the locator alone. When a report prints both a borrowings note
  and a liquidity-risk note with its own maturity table, keyword weighting trades one off against the
  other — an attempt to prefer borrowings-note pages improved 2 companies' top pick and hurt 16 others.
  Whichever table is correct, the fix likely belongs on the extraction/arithmetic side (check the
  picked table's total against the balance-sheet borrowings figure), not the locator.
  [v008](evidence/v008.md).
- **Is "a missing bucket counts as 0" the right call?** We made that assumption — a report with no
  `>5y` row treats that bucket as 0 in the sum check — because HANDOFF says null buckets are normal,
  but it's our assumption, not a confirmed one. Worth a sentence from Kristian if a missing bucket
  should instead fail the check rather than pass it. [v011](evidence/v011.md).

## How to verify

```bash
cd frontend && npm run build && npm run lint       # tsc -b + vite build, then oxlint
cd backend  && python -m pipeline.test_confidence  # extract.py's evidence/confidence scoring
cd backend  && python -m pipeline.test_parse       # parse.py's row-merge behavior
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
