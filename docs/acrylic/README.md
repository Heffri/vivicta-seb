# Acrylic branch — notes for the team

What this branch changed, how to run it, and what the backend hardening found along the way — for
whoever picks this up next. Background, if you haven't read it yet: [`README.md`](../../README.md),
[`docs/HANDOFF.md`](../HANDOFF.md) (backend state, decided-today scope), [`docs/API.md`](../API.md)
(the contract), [`DESIGN.md`](DESIGN.md) (the token system everything below is built on).

## What this branch is

The frontend is redone in the UAW "acrylic" glass design language (tokens, rationale, contrast
numbers: [`DESIGN.md`](DESIGN.md)). Alongside it, a batch of backend fixes that don't need a model to
verify — locator, parser, label matching. `main` hasn't moved; nothing here has merged there.

**How a teammate gets it** — three ways, cheapest first:

- **Double-click the Release exe**: download the portable (or Setup) exe from the
  [`desktop-0.3.3` prerelease](https://github.com/Heffri/vivicta-seb/releases) — no Python or Node
  needed (unsigned, so SmartScreen asks: "More info" → "Run anyway"). It starts on fixture/demo data.
- **Clone the repo's `demo` branch and run `run.bat`** (macOS/Linux: `./run.sh`): the first run sets
  up the venv, installs dependencies, builds the frontend and opens the app in your browser — about
  2–4 minutes; later runs take seconds.
- **Real model answers**: in Settings pick the **Codex** or **Claude** provider card and Save — a
  subscription login (`codex login` / `claude login`) is enough, no API key. With no provider
  configured the app stays on fixture data.

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
first run ("More info" → "Run anyway"). The current packaged release is **0.3.3**, built from
`0f2e2bc` (the acrylic tip at package time — it ships everything 0.3.2 did plus v074's
foreign-company annual-report web search (a no-hit directory query offers "Search the web for
'…' FY 2025" under a Codex/Claude provider; the located PDF then registers like any other) and
v076's bucket-column carrying-amount slot):
`Annual Report Parser-0.3.3-portable.exe` (~141.4 MB) and
`Annual Report Parser-Setup-0.3.3.exe` (NSIS, ~141.6 MB) — both attached to the **`desktop-0.3.3`
prerelease** on GitHub Releases, so a teammate can download and double-click without building
anything. [v077](evidence/v077.md) The data
directory (reports, KB, uploads, `backend.log`)
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

**Two-pass page selection** (`EXTRACT_TWO_PASS`, default **off**) is an opt-in `extract()` mode: a
small pass-1 call first asks the model which of the locator's candidate pages actually holds the
target table, then pass-2 extracts from that narrower window instead of every candidate at once —
fewer hallucinations from unrelated pages, one extra model call per extraction. v045's 30-company
`debt_maturity` before/after (Codex `gpt-5.6-terra`) found this a net positive over v043's first
round — 11 of v043's own 13 regressions no longer worse (7 exact recoveries, 4 improvements beyond
the original baseline), full-confidence count up (5→6), only 2 companies worse for narrow, understood
reasons — and recommended flipping the default on for hosted providers. It stays off by default here
because it has only ever been run against Codex/Claude: the local Ollama path (`qwen3:8b`) has never
been validated with it, so flipping the *default* for local models would be an unverified guess, not
a confirmed win. Turn it on with `EXTRACT_TWO_PASS=1` in `backend/.env`, or the desktop Settings
tab's "Two-pass page selection (recommended for hosted models)" toggle on the Codex/Claude/API
endpoint cards (on by default there; Save restarts the backend with it applied) — there is no toggle
on the Local (Ollama) card, which always runs with it off regardless of any previously-saved value.
`GET /api/config` does not report this field (backend untouched by the Settings lane); the status
row's "two-pass on/off" reads the desktop's own last-saved `config.json` instead.
[v043](evidence/v043.md), [v045](evidence/v045.md), [v047](evidence/v047.md)

## Backend hardening

Most of the below calls no model at all — each row is a deterministic pipeline or schema change,
checked against the 102+ reports already parsed into `data/kb/` and/or PDFs fetched for the
purpose. The `debt_maturity` hardening-loop rows are the exception: each round runs
`scripts/random_check.py` against a real model (Codex CLI) to find failures on a random sample,
then — usually — lands a deterministic fix — schema wording/keywords, or an `extract.py` code
change — verified afterwards with no further model calls. Eight rounds so far, seeds 1–8, 77
company draws ([v035](evidence/v035.md), [v037](evidence/v037.md), [v041](evidence/v041.md),
[v048](evidence/v048.md), [v051](evidence/v051.md), [v063](evidence/v063.md),
[v072](evidence/v072.md), [v082](evidence/v082.md); seeds 7 and 8 measured the merged stack and
deliberately landed nothing), and
the failures they chased resolve into four mechanism families, each now with its own deterministic
reader: bucket-shaped rows (`_between_rows`), bucket-shaped columns (`_fill_bucket_columns`),
per-instrument maturity dates (`_date_bucket_derive`), and stated-zero prose sentences
(`zero_if_stated`). `scripts/replay_check.py` (regression — replays stored extractions through
baseline vs. worktree) and `eval/run.py --stored-kb` (scoring against `eval/labels.csv`) are the
loop's two repeatable tools. `python -m pipeline.test_confidence` and `test_parse` are
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
| Opt-in two-pass page selection (`EXTRACT_TWO_PASS=1`, default off — see "Model providers" above), round 2: a longer, boilerplate-stripped pass-1 snippet with schema-keyword lines appended beyond its head; a forced two-page reply (primary + companion, repaired rather than rejected when the model names only one page); the schema's own `description` text reused verbatim as pass-1's steer | v043 (below) found three causes for its own 13 regressions — a starved 400-char snippet, a lost companion page, no schema-specific steer — and left them for the group; this round implements all three and re-runs the same 30 companies | [v045](evidence/v045.md) |
| `debt_maturity.json` gains 26 bucket-label synonyms — spelled-out digit forms (`after five years`, `one to five years`) and Swedish `mellan`/`inom`/`efter`/`över` phrasing — found by reading every debt-maturity page cited across three prior hardening seeds, then corpus-wide false-positive-checked (four risky candidates found and left out) before shipping; zero code changes, zero model calls | Closes the spelled-out/Swedish vocabulary gap directly; two companies (Coor Service Management, Storytel) newly covered cleanly, two more (Ependion, Gentoo Media) confirmed still blocked by an unrelated parser-level column scramble, not vocabulary | [v046](evidence/v046.md) |
| `kb.py`'s `/ask` retrieval goes three-state (`kb.retrieval_mode()`, surfaced as `retrieval` on `/api/config`): **hybrid** = min-max-normalised cosine (0.6) + BM25 (0.4) with `LLM_BASE_URL`; **bm25** = pure Okapi BM25 (in-memory index, no new files, stdlib only) under a codex/claude-only subscription; fixture untouched; `/ask` and `/index` gate on `_llm_configured()` instead of `LLM_BASE_URL` alone | A codex/claude-only desktop setup has no embeddings endpoint, so Ask was fixture-only there; the offline eval (1145 income + 77 debt queries over the stored KB) puts BM25's hit@3 at **87.0%** / **98.7%** vs the old token-share ranking's 41.4% / 59.7%, with hit@1 and hit@8 up too | [v034](evidence/v034.md) |
| `parse.py` rebuilds page text column-aware (`PARSER_VERSION` 3 → 4): an XY-cut on the word-bbox x-projection behind four measured gates (substance, baseline alignment, label-column shape, torn-row pairs), plus block-level chaining of stacked header cells; over 35 real PDFs the split-row rate drops 0.27% → **0.20%** (debt pages) and 0.36% → **0.29%** (income pages), stored `data/kb` quotes 8/8 kept; `pymupdf==1.27.2.3` pinned to the text layer the parser was validated on | v013's baseline merge crosses gutters, so sidebars and side-by-side tables glued into the running text and scrambled rows on two-column report pages | [v049](evidence/v049.md) |
| `extract.py` accepts a report-stated prose no-debt sentence as `total_debt = 0` behind a schema opt-in (`zero_if_stated`): value exactly 0, digit-free quote, verbatim on the cited page, naming the field, negation word from the schema's own list; a replay over all 42 stored seed runs moves exactly one company (Creades, the rule's only corpus candidate) | A correct "the company has no interest-bearing liabilities" sentence has no digits, so the printed-quote gates dropped the model's correctly-sourced 0 as "computed, not read" | [v050](evidence/v050.md) |
| `extract.py`'s row derivations anchor on the nearest year run above the quoted row (was: the page's first header — wrong on multi-table note pages), resolve a repeated year across `Koncernen \| Moderbolaget` column pairs to the Group side when the run names Group before Parent, and `_between_rows` additionally tries the full rows printed directly above the uppermost operand row | MedCap p.101's stacked tables (an ageing table above the note, Group \| Parent year pairs in the note's own header) defeated every derivation window; the 135-company replay moves exactly 2 entries, both the intended medcap_2025 fix | [v052](evidence/v052.md) |
| `scripts/replay_check.py` commits the stored-extraction replay as one repeatable script: every stored KB field list is fed back through baseline and worktree `extract()` (schemas loaded as of the same ref) and value/confidence/evidence/checks are diffed; `--kb/--section/--baseline/--only/--out`; the red control fires — seed4 vs pre-v048 reproduces exactly v048's 2 recorded changes (Intrum, MEKO) | v044/v050/v052 each hand-wrote a one-off replay script (30–60 min each, none committed); this is the capability they converged on, in the shape `label_regression.py` established | [v053](evidence/v053.md) |
| Opt-in quote retry (`EXTRACT_QUOTE_RETRY`, default **off**): when the model's own answer cites a quote not printed on the page it names, **one** follow-up call shows those fields against the cited page's own table rows; a field adopts the reply only when the new quote verifies on the page it names, and a v050-proven stated zero is never retried; 9-company Codex before/after: 1 trigger (MEKO), 0 adoptions, nothing worse | Quote-shaped failures are the one class the offline repairs can't reach; the switch stays off pending a corpus where they reproduce — the mechanism and its offline tests are ready either way | [v054](evidence/v054.md) |
| `kb.search()` returns no hits in bm25 mode when every raw BM25 score is 0 (was: stable cover-page order), and `ask()` then skips the model — a fixed "no passage matches the question's terms" answer, empty citations, an explanatory warning; hybrid untouched; KbView's Embeddings column reads `/api/config.retrieval` and shows a BM25 badge in bm25 mode | Swedish questions against English reports scored a flat 0 and still went to the model (v034's own finding) — the short-circuit saves the call and says why | [v059](evidence/v059.md) |
| `parse.py`'s stacked-header chaining (`_stack_cells`) no longer depends on PyMuPDF's own block grouping: `_merge_baselines` feeds it geometrically grouped short blocks (`_group_blocks` union-find, pairwise `_blocks_link` tests with a new `_LINE_RATIO` height gate, every candidate merge re-checked incrementally against the tabular-shape test); the Ependion p.155 header now chains identically under PyMuPDF 1.27.2.3 and 1.28.2; `PARSER_VERSION` 4 → 5; the `pymupdf==1.27.2.3` pin is **kept** — quote-replay and locate are identical across both versions, but 1.28 still reflows ~17% of the 35-PDF corpus's pages (its block split changed pervasively, e.g. whole tables split into per-column blocks beyond the 3-row grouping cap), reason updated in the requirements comment | v049's acceptance had found the same PDF parse differently per PyMuPDF version: 1.28's finer block splits routed pages to the link-less word-level rebuild, re-scrambling the stacked headers v049 fixed | [v049b](evidence/v049b.md) |
| `debt_maturity` hardening loop, seed 5 (10 Mid Cap companies × 2 passes, plus a targeted fresh-parse rerun of ework/boozt/ependion/medcap under the night's merged fixes): full-confidence 0/10 again; 6/10 confirmed-correct basis, 2/10 wrong table, 2/10 no debt disclosure reached; `extract.py`'s `_between_rows` rescue now also fires at the *second* drop site (a verified two-row quote truncated to its suffix row was dropped as "computed, not read" before any missing-operand rescue looked at it) — MedCap's `due_within_1_year` 102.3@1.0 end to end; corpus replays 117 + 35 companies, 0 changed; 52 of the 60-call cap | Fifth round of the loop, now also measuring whether the merged parse/derivation fixes move the four standing gap companies; names the remaining levers ranked by affected companies (unlabelled-total column sums, stated-zero vocabulary, statement-fill under-counts, locator misses) | [v051](evidence/v051.md) |
| `eval/labels.csv` gains 90 hand-verified `debt_maturity` rows across 27 companies (the four hardening seeds' 34-company universe minus 2 fully-disputed banks and 5 with no reliable printed number), every value re-derived from the raw page text, plus `eval/run.py --stored-kb` offline scoring through the unmodified comparison logic, zero model calls: `total_debt` 25/34 correct where a stored extraction exists, non-null buckets 22/33, null buckets 51/51, pages 45/118 | HANDOFF's open item: an accuracy number that isn't the backend grading itself; reading the pages directly caught two real errors — Bergman & Beving's stored read is its prior-year column, and XANO's "impossible" 8th column is a printed within-1-year subtotal | [v057](evidence/v057.md) |
| v044's present-label guard is scoped to the operands' own table (the row span from the nearest year-header above the anchored operands down to the bottommost one; no provable boundary → the whole-page search, unweakened), with a never-worse fallback to the page-level verdict whenever the scoped zero-fill can't close the identity; plus six month-range bucket synonyms (`6 månader eller mindre`, `6 – 12 månader`, `less than 3 months`, `0-3 months`, `less than 6 months`, `6-12 months`) per the supervisor's ruling; replay: 4 checks flip missing/failed → **passed** (apotea, storytel, nelly, medcap — medcap's `due_within_1_year` restored to 102.3@1.0), income_statement 0 differences, nothing worse | Swedish notes stack several tables per page, so a bucket word printed by a *different* table on the same page kept a true 0 out of the zero-fill and left checks at `missing:` forever | [v058](evidence/v058.md) |
| The column-bucket reader gains: `header_synonyms` (schema, matched only against column headers — `label_regression` proves row-label matching untouched), a debt-row fallback for `_bucket_total_row` (rows labelled "Borrowing"/"Lease liabilities"/… qualify when they read a real bucket header above, narrowed by the model's own total where present, ambiguous → warning not a guess), and within-1-year subtotal-column handling (a printed "summa inom 1 år"/"total within 1 year" column supersedes the finer columns to its left, never double-counts). Ependion closes exactly (583,531 / 167,546 / 415,984, check failed → passed); Ework/XANO correctly still decline (their headers are matrix-transposed across two physical lines, unrecoverable from plain-text rows) and Boozt stays blocked in `_row_amounts`' thousands-grouping ambiguity — all root-caused, none regressed | v035's bucket-as-columns shape where the total row isn't labelled "total" — v051's top-ranked remaining lever; replay 152 companies: 3 changed (the Ependion fix + two warning-count-only Acast diffs), zero worse | [v060](evidence/v060.md) |
| `zero_if_stated` gains its own subject vocabulary — `total_debt.zero_if_stated.subject_terms: ["loan", "loans"]`, read only by `_stated_zero`, never by row matching — closing v051's precisely-bounded gap: Vicore Pharma's and BioGaia's bare-"loan(s)" no-debt sentences now record `total_debt = 0` @ 0.5 with the sentence as provenance; 7 other candidate terms declined after an appearance scan over seed1–5 (each would mint false zeros on real corpus sentences); replay 0 changed everywhere | A correct "the group has no external loans" sentence names its subject with a bare word the schema's phrase-level vocabulary never listed, so the stated zero fell through to the weaker printed-zero path capped at 0.25 | [v062](evidence/v062.md) |
| Desktop package rebuilt as **0.3.1** (`382beff`): every lane merged since 0.3.0 in one exe (v049b's stacked-header parse, v051's second `_between_rows` rescue site, v058's present-label guard + month-range synonyms, v060's bucket-columns reader, v062's stated-zero `subject_terms`, v059/v056's BM25-empty short-circuit + status strip) — double-click acceptance (a)–(h) all pass, driven over CDP against the real packaged exe, never a full-screen capture | Seven backend/frontend lanes had landed since 0.3.0 with no packaged build to show for it | [v061](evidence/v061.md) |
| `debt_maturity` hardening round 6 (seed 6, 10 Mid Cap companies × 2 passes): full confidence 1/10 (CellaVision, pass 1), partial 8/10, failed 1/10 (Scandi Standard — a net-debt movement row, not a sign bug); `due_1_to_5_years.synonyms` gains `within 2-3/4-5 years` (ASCII + en-dash) — safe but no measured effect on its own target (VBG's row still declines on the column-count guard, reclassified to an extract-layer gap); replay 162 same, 0 changed | Measures v049–v062's combined effect on ten fresh companies before landing anything else; first full-confidence company of any hardening round this size (seeds 4 and 5 both ended 0/10) | [v063](evidence/v063.md) |
| `_row_amounts` splits a space-glued Swedish-thousands pair when the header's own column count says so, narrowed to the one case that can't be another table's whole-sum Total row (a nil elsewhere in the same row, exactly one splittable token, split lands exactly on `ncols`); Boozt's `due_within_1_year` now fills to 104 (26+78), matching `eval/labels.csv`'s 441/104/273/63 exactly; replay 2 changed (both Boozt, both the intended fix), income_statement 0 differences | v060 got Boozt's row and header both reading correctly but left one bucket null — the file's own Swedish-thousands regex read "78 273" as one 78,273-column-short number, named out of that lane's own six-function territory | [v064](evidence/v064.md) |
| StatusBar footer refreshes immediately after Settings Save (`App.tsx`/`SettingsView.tsx`, 25+/7− across two files) instead of waiting for a relaunch — the post-save config (or a fresh `/api/config` fetch) is forwarded up to `App`'s state; failure path proven to leave the footer untouched | Closes v061 §6-5's own finding: the footer kept its mount-time provider until the app restarted, even though the "Running now" strip was already correct | [v065](evidence/v065.md) |
| Two bucket-column guards: (a) `_identity_closes` — a model value that already closes an identity check exactly against ≥2 other real (frozen-snapshot) operands survives a column-position correction that would otherwise overwrite it with a wrong-segment 0 (Proact IT's 312,458); (b) `_fill_bucket_columns` never writes from a Total\*/Summa\* row with no total column of its own, and never lends a bucket-column row naming the fiscal year's predecessor to this year's fields (Net Insight). Replay 162 same, 0 changed — XANO/Ework/Bergman & Beving's own standing rejections explicitly re-checked, still declined, not flipped into false writes | v063's own gap findings 2 and 7 — a correct, identity-proven value and a wrong-scope row were both losing to a guess | [v066](evidence/v066.md) |
| `parse.py` rebuilds matrix-transposed two-row table headers by column x-position (`_rebuild_transposed_headers`, new; `PARSER_VERSION` 5 → 6): Ework p.70 and XANO p.84 both print two physical lines where line 1 holds every column's first fragment and line 2 the second — the trigger is a ≥3-bare-amount data row, walked upward to the header lines above it, each phrase matched to its nearest column by right-edge distance, declines untouched on any conflict. Full-corpus before/after (55 PDFs, both pymupdf releases): quotes/locate/split-rate all unchanged, fires correctly on ~300 other pages sampled by hand (15/15 correct); confirms `eval/labels.csv`'s Ework figures were transcribed against the scrambled reading (v060's own dispute) | v060's own finding: Ework/XANO's headers are scrambled two-line-wraps no per-row hit collection can recover column order from — v049/v049b fixed *stacked* two-line headers, this is *transposed* two-line headers, a different shape | [v068](evidence/v068.md) |
| Closes v068's two named schema-side gaps with one general fix, `_drop_nested_hits` (a hit whose span sits entirely inside another, wider hit's own span is one column, not two — not per-company): XANO's `Summa`/`inom 1 år` double-hit inside its own `Summa inom 1 år` subtotal (10 hits → 8) resolves XANO end to end (904,522/51,075/802,669/50,778, check passed, matches labels.csv); Ework's own header_synonym overlap (`3 months` inside `1-3 months`) also dedupes, correctly, to 7 — still short of the row's 8 real columns ("Carrying amount" recognised by nothing), honestly still declined, not forced. `"Due"` (the work order's own instruction) shipped as a case-sensitive `_BUCKET_BOUNDARY` regex instead of a plain `header_synonyms` string — the literal version matched a dozen+ ordinary-prose "due"s on Ework's own surrounding pages ("risk due to assets", "Past due accounts receivable"), confirmed causing two spurious `over`-valve warnings before the fix. `eval/labels.csv`'s Ework rows corrected per v068's column evidence: `due_within_1_year` 154732 → 156409, `due_1_to_5_years` 1677 → **null** (the page prints a dash, not "0"). Replay 162 same, 0 changed; label_regression 739/0/173 (unchanged); `eval/run.py --stored-kb` seed1 26/34→25/34, seed5 8/15→9/15 (a label fix un-crediting/crediting *stored* answers that were only right by coincidence against the old, also-wrong label — not a regression) | v068's own "downstream" section named both gaps read-only, for whoever owns `extract.py`/the schema next | [v069](evidence/v069.md) |
| Desktop package rebuilt as **0.3.2** (`e216fd4`): every lane merged since 0.3.1 in one exe (v064's Boozt thousands-pair split, v066's `_identity_closes` guard + the two `_fill_bucket_columns` valves, v068's transposed-header rebuild — `PARSER_VERSION` 6 confirmed live from the packaged binary's own kb `meta.json`, v069's `_drop_nested_hits` dedup, v065's Settings-save StatusBar refresh) — double-click acceptance (a)–(i) all pass, driven over CDP against the real packaged exe, never a full-screen capture; both artifacts size-flat vs 0.3.1 (portable ~141.4 MB, NSIS ~141.6 MB) | Five backend/frontend lanes had landed since 0.3.1 with no packaged build to show for it | [v071](evidence/v071.md) |
| `debt_maturity` hardening round 7 (seed 7, 7 Mid Cap companies × 2 passes, two-pass 7/7 — two fetches died 500/404 uncounted, one seed1–6 overlap skipped before any call): full confidence 0/7, partial 4/7 (Stillfront, HANZA, KABE, Nederman — values stable across passes except KABE's source-page flip), failed 3/7; **no schema or pipeline change landed** — the round's own finds sort into basis conflicts (Green Landscaping, Sdiptech), values needing guarded derivation from split rows/dated instruments (HANZA, Stillfront, Nederman), and locator/two-pass misses (Meren, KABE); 44 of the 50-call Codex cap spent, 16 of them duplicates after an interrupted driver re-issued in-flight `/extract`s (the server keeps running past a client timeout) → standing driver rule: never reissue — wait for the server-side run to land or reuse the saved pass | Measures v049–v069's combined effect on ten intended fresh companies; names the next levers, all extract/locator-layer, no vocabulary gap left | [v072](evidence/v072.md) |
| `extract.py` gains a third maturity-note shape reader, `_date_bucket_derive` (beside bucket-rows' `_between_rows` and bucket-columns' `_fill_bucket_columns`): **one row per loan/lease, each naming its own due date / year / year-range** — bucketed by exact calendar arithmetic against the balance-sheet date, scoped to a 15-row look-upward window above `total_debt`'s own verified row (a year-range value fires `_year_run`, so v058's operand-table window cuts the note off), repeated-watermark/running-header rows excluded, whole derivation abandoned on a straddling row, adopted **only when the identity check closes exactly** (`±2`) and never overwriting an answered bucket. Proact IT closes (312,458 / 166,153 / null, check failed → passed); HANZA (bucket-column), Stillfront (duration-labelled component rows) and Nederman (date table beyond the window; lease line dateless) correctly decline; label_regression 739/0/173, replay 0 changed, zero model calls | v063's gap 2 and v072's dated-instrument finding are this same shape — a correct per-instrument read has no bucket label anywhere for the row/column mechanisms to key on | [v073](evidence/v073.md) |
| Model web search as the **fourth report source** for foreign/non-directory companies (only when levels 1–3 produce nothing usable and the provider is codex/claude: `llm.web_lookup` → `codex --search exec` / `claude -p --tools WebSearch`, ≤3 candidate PDF links, each tried with its %-decoded twin, through the same download+validation chain; `/api/reports/fetch` accepts any company name + optional `country`/`hint`; Extract's no-hit directory query gains a "Search the web for '…' FY 2025" button, a muted "needs a model provider" hint under fixture/openai): 5 live foreign companies, **4 fetched** (Nestlé 67 p, Siemens 335 p after the decoded-twin fix, Novo Nordisk 137 p, Kone 183 p; Shell the honest failure — an expiring stream URL), a feed hit never reaches the model, a cached report short-circuits everything | The Swedish directory feeds and Nasdaq notices cover Nordic issuers only — every other company had no fetch path at all | [v074](evidence/v074.md) |
| Bucket columns gain a **carrying-amount total slot** beside an ignored undiscounted total (schema: `total_debt.header_synonyms` + new top-level `ignore_header_synonyms`; a carrying/ignore hit survives only on a line that also names a bucket; carrying present on that line demotes its bare Total word to an ignored column; ignored columns count toward the column-count safety valve but are never assigned and never fed to the `over` valve; the prior-year row walk gains a lone-year fallback): Ework's 8-column table now selects its real debt row — `due_within_1_year` null → **156 409 @1.0** by column order (identity closes within ±1 of the carrying total 156 410; the dash buckets stay null at this point), replay 68 debt + 101 income companies, 0 changed | v035's bucket-as-columns shape where the table prints two total-shaped columns (undiscounted + carrying) and the mechanism had one total slot — v069 had left Ework honestly declined rather than risk summing both | [v076](evidence/v076.md) |
| Desktop package rebuilt as **0.3.3** (`0f2e2bc`) and published as the **`desktop-0.3.3` prerelease** on GitHub Releases (portable + Setup, unsigned): v074's foreign-report web search + v076's carrying-amount slot in one double-click exe; double-click acceptance (a)–(k) driven over CDP against the real packaged exe (fixture upload, real KB data, BM25 badge, immediate post-save status-bar refresh, the web-search button asserted visible-and-not-clicked, the `foreign` chip), the codex discovery chain verified live in-exe (`codex-cli 0.153.4 · logged in`), portable ~141.4 MB / NSIS ~141.6 MB, size-flat vs 0.3.2 | Two lanes had landed since 0.3.2 with no packaged build to show for it; the Release is what teammates download instead of building | [v077](evidence/v077.md) |
| A dash printed in the selected row's own bucket column is that bucket's explicit **0** (`printed_nil`, 0 @0.5), behind two gates — the row must print a total, and the row's own real-bucket arithmetic must close within the check's ±2 with the dashes read as 0 (a lone total over dash columns proves a misparsed row, not zero debt; buckets the table prints no column for keep their null): Ework's two dash buckets fill 0, `maturity_sums_to_total` failed → **passed** (156 409 + 0 + 0 vs 156 410), replay 68 + 101 companies, 0 changed | v076's own leftover: the buckets were null only because their column headers are printed, which `_check`'s null-bucket guard treats as unproven — a dash is a printed nil, so the translation lives at the write site, upstream of the check | [v078](evidence/v078.md) |
| One-click launchers `run.bat` / `run.sh` over a stdlib-only `scripts/run.py` (invocation, health-check and process-tree-kill shapes borrowed from `desktop/main.js`): checks Python ≥3.11 / Node ≥18, creates `backend/.venv` + `npm ci` + builds `frontend/dist` only when missing or stale, picks the first free port from 8000, health-checks `GET /api/config`, opens the browser, Ctrl+C kills the tree (verified clean by PID, port closed); README gains a "Quick start" section plus the repo-root-`.env` note: clean-clone first run **156 s**, later runs seconds | Teammate onboarding was a multi-terminal manual sequence (venv, pip, uvicorn, npm, vite) before anyone saw the app | [v079](evidence/v079.md) |
| **Fifth report source**: when levels 1–4 leave only page-shaped leftovers (a model reply naming an IR page, a web hit that served a page, or the guessed IR paths for a dead direct link's own domain), crawl those pages one hop deep (≤8 candidates, 20 s each, 90 s budget), download every harvested PDF through the same validation chain and keep the one with the most pages (`note: "IR page crawl"`); `SEARCH_SYSTEM` now says an IR-page URL is an acceptable answer; follow-up: `_filename_clear` stops `BAD_URL` matching an IR *section* name in the path from rejecting a filename that itself names an annual report (Shell's real PDF was being dropped pre-fetch on `/sustainability/reporting-centre/`): live TotalEnergies 666 p and Nokia 204 p fetched directly; Shell still 404, its failure shape now diagnosed (stale token; JS-rendered pages) | v074's two standing failures — the model sometimes answers with a page instead of a PDF, and its direct links can be stale — plus a shared-filter false positive root-caused on the way | [v080](evidence/v080.md) |
| The fetch gains a **second model ask** and a **complete-report preference**: once every direct-link candidate and the first IR-page crawl have failed, one narrower ask (`IR_PAGE_SYSTEM`: the investor-relations/annual-report *page*, never a PDF, ≤2 URLs) feeds v080's crawler — two model calls max per fetch, by construction; the fourth source now tries all ≤3 candidates and ranks by `(pages ≥ 80, clean filename, page count)`, labelling a surviving summary `model search (codex); summary volume`: the foreign-company tally stands at **6/7 fetched** (Nestlé 67 p, Siemens 335 p, Novo Nordisk 137 p, Kone 183 p, TotalEnergies 666 p, Nokia 204 p) — Nestlé's summary volume now honestly labelled, **Shell still unfetched** (its server-rendered IR pages expose no scrapeable PDF link; traced two levels deeper than v080) | Shell's report lives behind a stale link and a JS-rendered page, Nestlé's best web hit is the summary volume — ask once more, narrowly, and rank whatever does download | [v081](evidence/v081.md) |
| `debt_maturity` hardening round 8 (seed 8, 10 fresh Mid Cap companies × 2 passes, Codex `gpt-5.6-terra`, two-pass selection 10/10): full confidence **0/10, partial 8/10, failed 2/10** (Enity Holding, Modern Times Group); pass1==pass2 value-stable only 3/10; **nothing landed** — the two closeable tables it found (Tången, Instalco) were blocked one layer below schema by `extract.py`'s private `_DEBT_ROW_SYNONYMS`, plus a separate `_row_amounts` token-drop, both flagged with evidence; gap count: locator/two-pass 4, row-label recognition 2, model-level 3, correct ambiguity-decline 1; 40 of the 50-call cap, zero resends (per-company saved-pass reuse before any call) | Measure-first, like seed 7: quantify v073/v076/v078's combined effect on ten fresh companies before landing anything — none of the three newest mechanisms produced a fill on this batch | [v082](evidence/v082.md) |
| Debt-row vocabulary moves to the schema: `_DEBT_ROW_SYNONYMS` (11 words, `extract.py`'s private constant) becomes `total_debt.row_synonyms` byte-identical — the constant is deleted rather than kept as a code default, so debt wording can't silently inject into a future same-shaped schema — plus seed-8's word gaps as exact printed phrases (`"lån kreditinstitut"`, `"liabilities to credit institutions"` as rows; `"mindre än 12 månader"`, `"within 6 months"`, `"mellan 1 och 2 år"` as headers), direction-safe against v060's asset-side bare-`loan` lesson; `backend/README.md` documents the four synonym-shaped keys: Tången closes on the isolated single-year replay (588 199 = 141 734 + 388 979 + 57 486, check **passed**; the real two-year page still declines ambiguous — v084's target), Instalco byte-identical, replay 179 companies 0 changed | v082's Findings 1–2: a genuine closeable table whose row label the private list never matched — and vocabulary belongs in the schema, not in code | [v083](evidence/v083.md) |
| Bucket columns pick the **fiscal-year table** when two years print the same debt row: `_bucket_total_row` narrows duplicate same-labelled candidates by year (via the already-trusted `_bucket_row_prior_year`) *before* `known_total` — exactly one survivor wins outright; more than one still declines exactly as before: Tången's real two-table p.62 closes end to end (588 199 / 141 734 / 388 979 / 57 486, check **passed**, was "2 candidate debt rows … ambiguous, none used"); Byggmax's neither-year-decidable rows still decline (its replay line moves warnings 1 → 0 only), replay 78 companies otherwise 0 changed | v083's own named remaining blocker: Swedish notes stack one table per year under identical row labels, and the ambiguity decline blocked the fix v083 had already unlocked | [v084](evidence/v084.md) |
| The bucket header admits a **second header tier** with no bucket word of its own (v085): an unbroken run of carrying/ignore-bearing lines touching the header joins the read — only when v076's same-line mechanism finds nothing, and only when nothing between the header and the candidate row prints its own amounts (both guards load-bearing, proven by removing each: Instalco's total corrupts 3 122 → 4 802 without the second; Ework/Ependion regress on real prose "carrying amount" sentences without the contiguous-run stop): Instalco's three-line wrapped header now reads 6 keys matching its 6 printed amounts, but the fill is rejected one layer further down by `_fill_bucket_columns`' `over` valve (undiscounted 1–5y 3 209 vs carrying total 3 122) — named with figures for the next lane; replay 179 companies: instalco warnings-only, 0 values moved | v082/v083's Instalco blocker: its column header wraps across three lines and the carrying phrase sits on a bucket-less line, so v076's same-line gate stripped the hit before `has_carry` ever ran | [v085](evidence/v085.md) |

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

Calls the `debt_maturity` pipeline now makes on Kristian's behalf — the first three written into
its field descriptions (and the prompt the model reads), the later ones into schema switches and
code gates, so they're applied consistently — not yet confirmed:

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
- **A report's own prose no-debt sentence proves `total_debt = 0`.** When the report states in
  words that there are no interest-bearing liabilities — a sentence with no digits, found verbatim
  on the cited page, naming the field, carrying a negation word from the schema's own list — we
  record `0` with that sentence as the provenance instead of dropping the field, behind the
  schema's `zero_if_stated` opt-in. We assumed this; confirm it or tell us to flip it (drop the
  field instead). [v050](evidence/v050.md).
- **When a maturity table's year header repeats across Group | Parent column pairs, the Group side
  wins.** If the header run's own row (or the one directly above it) names Group before Parent
  (`Koncernen Moderbolaget`), the first pair is taken as the Group's; Parent named first → the last
  pair; neither word, or no order → still declined as unknowable, exactly as before. We assumed
  this; confirm it or tell us to flip it. [v052](evidence/v052.md).
- **A check's "own table" is the row span between the nearest year-header above its operands and
  its bottommost operand row, and `header_synonyms` match column headers only.** v058's zero-fill
  and v060's bucket-column reading only narrow their search when that boundary is provable from
  the page; when it isn't (no year header above, or a quote the model composed rather than
  copied), the older whole-page behavior applies unchanged. We assumed this conservative default;
  confirm it or tell us to flip it. [v058](evidence/v058.md), [v060](evidence/v060.md).

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
