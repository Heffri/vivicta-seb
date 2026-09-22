# Annual Report Parser — SEB challenge, Vivicta Finance & Insurance AI Hackathon 2026

An annual report's debt note in → **analyst material with sources** out: total interest-bearing
debt and when it falls due, every figure carrying the page it came from and the verbatim sentence
it was read from, exportable as PPTX/CSV/JSON for downstream banking systems. Web UI and a
double-click Windows app on top.

The hackathon concluded on 2026-09-22; this repository is the finished entry, not an active
project. The code is left as it was demoed — the app runs, and the saved library and the accuracy
evaluation both reproduce offline with no model calls.

Scope decided with SEB's end user (Kristian, 15 Sept): the **debt maturity note** — one slide per
company, Nasdaq Stockholm Mid Cap. Challenge owner: Kimberly Lejonö, Co-Head CIB Data & AI Hub,
SEB. Full brief, meeting notes and the team: [`docs/CHALLENGE.md`](docs/CHALLENGE.md).

| ① Open a saved report | ② Click a figure — buckets + page | ③ The source: quote on the page |
|---|---|---|
| ![Knowledge base: search karnell, Open](docs/acrylic/evidence/v167/step1-kb-open-karnell.png) | ![Results: four debt buckets with checks](docs/acrylic/evidence/v167/step2-buckets.png) | ![Source panel: page 106, quote highlighted](docs/acrylic/evidence/v167/step3-source-page-quote.png) |

*The saved Karnell Group FY2025 debt record, captured on the fixture backend — no model configured
(dark tone, 1440×900); the page image in ③ comes from the PDF fetched onto that machine.*

## Try it in one minute — no model, no download

The repo ships 206 saved reports; 105 carry a stored `debt_maturity` extraction. Start the app by
any entry point below, open **Knowledge base** → search `karnell` →
**Open** → click a figure: page number, verbatim quote, the sum check, review and PPTX/CSV export
all work offline, zero model calls. (Only page *images* need the PDF on disk.) The full demo
script — the two bundled samples, a three-minute line-by-line, and the demo-day checklist — is
[`docs/DEMO.md`](docs/DEMO.md).

## Install / run — three entry points

1. **Windows installer** (double-click, no toolchain): grab the Setup exe from the
   [latest release](https://github.com/Heffri/vivicta-seb/releases/latest), or download it
   directly — [`annual-report-parser-main-setup.exe`](https://github.com/Heffri/vivicta-seb/releases/latest/download/annual-report-parser-main-setup.exe),
   a permanent link that always serves the newest build. Open to anyone, no login. CI rebuilds it from every push to `main`, so that link is always the current `main`;
   the app checks for updates on startup and applies them on exit. Everything it needs ships
   inside the installer — the Python backend and its dependencies, the Electron runtime, the
   frontend, the 206-report saved library and the OCR language data — so there is nothing to
   install alongside it (~165 MB). Unsigned, so SmartScreen asks: "More info" → "Run anyway".
   Starts on fixture (demo) data; pick a real provider in Settings. The
   [`desktop-demo`](https://github.com/Heffri/vivicta-seb/releases/tag/desktop-demo) prerelease
   is the frozen demo-day build, and the old portable `desktop-0.3.4` zip cannot update itself —
   prefer the latest release. Details: [`desktop/README.md`](desktop/README.md).
2. **`run.bat` (Windows) / `./run.sh` (macOS/Linux)** from a clone of this repo: first run sets up
   a Python venv, installs dependencies, builds the frontend, and opens the app in your browser on
   one port — about 2–4 minutes; later runs take seconds. Ctrl+C stops it (on Windows,
   `Terminate batch job (Y/N)?` is `cmd.exe`'s own prompt for any batch file — answer `Y`).
3. **From source, piece by piece** — backend venv + `uvicorn`, frontend dev server with `/api`
   proxy: see "Run it" below.

Docs: the API contract is [`docs/API.md`](docs/API.md); the accuracy numbers and their caveats are
[`docs/ACCURACY.md`](docs/ACCURACY.md); the per-change evidence archive (all of it merged into
`main`) is [`docs/acrylic/README.md`](docs/acrylic/README.md); backend state is
[`docs/HANDOFF.md`](docs/HANDOFF.md).

## The one idea to keep

Every extracted number carries `source.page` + `source.quote`, and the backend checks the quote really exists on that page.
That is what makes this a bank tool and not a chatbot. Don't drop it.

## Layout

```
backend/       FastAPI + PyMuPDF + OpenAI-compatible LLM client (Ollama locally)
frontend/      Vite + React 19 + Tailwind 4 + shadcn/ui
desktop/       Electron shell: packaged Windows app, auto-update, data sync
eval/          labels.csv + run.py → accuracy number
scripts/       standalone checks and audits (eval_breakdown, random_check, publish_kb, ...)
experiments/   the two alternatives that were benchmarked and ruled out (Laya, Docling)
docs/          API contract, accuracy, challenge notes, prep for SEB meetings
data/kb/       saved reports: metadata, page text, extractions, reviews — committed
data/reports/  bundled annual reports: index.json committed, PDFs gitignored -> `python data/fetch.py`
.github/       one workflow: tests, then builds and publishes the Windows installer
```

The handshake between frontend and backend is [`docs/API.md`](docs/API.md). Change it there first.

## Run it

`run.bat` / `run.sh` (entry point 2 above) does all of this in one step and serves frontend +
backend on a single port. To run each piece by hand instead (e.g. to use `--reload` while editing):

Backend (terminal 1):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    mac/linux: source .venv/bin/activate
pip install -r requirements.txt    # pymupdf is pinned — see below
cp .env.example .env               # leave LLM_BASE_URL unset → returns the fixture (UI dev mode)
uvicorn app:app --reload --port 8000
```

`pymupdf` is pinned to 1.27.2.3 because 1.28.2 splits text blocks differently and reflows about 17%
of the 35-report test corpus's pages; the pin keeps the text layer this parser was validated on.
`backend/requirements.txt` carries the detail.

Reports (once): `python data/fetch.py` downloads the annual reports listed in `data/reports/index.json`
(Atlas Copco, Investor, Saab en/sv, SEB, SKF and the rest; ~130 MB). They show up in
`GET /api/library` and in the UI's library picker. None of this is needed for the saved-KB
walkthrough above; PDFs are only required for page images and *new* live extractions.

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173, proxies /api → :8000
```

Real extraction with a local model (using `run.bat`/`run.sh`? put the same lines in a `.env` file in
the repo root instead of `backend/.env` — either is picked up; `backend/.env` wins if both exist):

```bash
ollama pull qwen3:8b               # or qwen2.5:14b / qwen3:14b if you have ≥12 GB VRAM
# in backend/.env:
#   LLM_BASE_URL=http://localhost:11434/v1
#   LLM_MODEL=qwen3:8b
#   LLM_API_KEY=ollama
```

Same three variables point at Azure OpenAI / OpenAI / OpenRouter — no code change.

Or with the Codex CLI instead of a model endpoint (no local model; uses a Codex subscription/API key):

```bash
# in backend/.env:
#   LLM_PROVIDER=codex
#   LLM_MODEL=gpt-5.6-terra   # -m passed to `codex exec`; the CLI must be installed and already logged in
```

Or with the Claude Code CLI, same idea, for a Claude subscription (a Claude *API key* instead needs no CLI —
`LLM_PROVIDER=openai` + `LLM_BASE_URL=https://api.anthropic.com/v1/` + `LLM_API_KEY` already works):

```bash
# in backend/.env:
#   LLM_PROVIDER=claude
#   LLM_MODEL=claude-sonnet-5   # --model passed to `claude -p`; the CLI must be installed and already logged in
```

Extraction and Ask's answers then run on Codex/Claude — no base URL needed; without one, Ask's retrieval
falls back to keyword search (BM25), and an `LLM_BASE_URL` (Ollama/OpenAI-compatible) upgrades it to hybrid
embeddings+BM25 — see `backend/README.md`.

## Accuracy

```bash
python eval/run.py --stored-kb data/kb --no-fail   # zero model calls, offline, reproducible
```

Against the hand-verified labels in `eval/labels.csv`: values **328/368 (89.1%)**, cited pages
**263/313 (84.0%)**. The scoped debt section on its own is **232/272 (85.3%)** values and
**171/221 (77.4%)** pages, scoring 272 of the 276 labelled debt rows — the headline is pulled up by
the income section, and the debt number is the honest one for the scoped section.

The caveat that matters most: those 106 labelled companies were used repeatedly to debug and tune
this pipeline, so none of these numbers is an out-of-the-box market-accuracy claim, and we do not
present them as one. Blind held-out samples, first-extraction batches, what the 40 debt misses
actually are, and the alternatives that were benchmarked and ruled out are all in
[`docs/ACCURACY.md`](docs/ACCURACY.md).

## Checks

There is no test framework: each test module is a script that asserts and prints. 22 Python
modules, run from `backend/` with the venv active —

```bash
python -m pipeline.test_locate     # the 13 modules under backend/pipeline/, run as modules
python test_collection.py          # the 9 modules at backend/, run as scripts
```

— and 5 Node modules for the desktop shell: `node --test` from `desktop/` after `npm ci`. In
`frontend/`, `npm run build` type-checks and builds and `npm run lint` runs oxlint.

`.github/workflows/desktop.yml` runs a subset on every push and pull request to `main` — ten of the
Python modules and `desktop/updates.test.js` — then builds and publishes the Windows installer.

## Desktop app

A double-click Windows app instead of a browser tab — same frontend, a packaged `backend.exe`, real
OS acrylic material on Windows 11. Install it from the [latest
release](https://github.com/Heffri/vivicta-seb/releases/latest) — self-contained and auto-updating,
rebuilt from every push to `main` — or build it from `desktop/`:
[`desktop/README.md`](desktop/README.md).

## The saved library (`data/kb/`)

`data/kb/` is a committed cache: report metadata, source page text, saved extractions and reviews,
which the app opens without re-extracting. Every surface shows all of it — there is no scope to
pick and nothing that can hide a saved report, so two installations with the same `data/` show the
same reports. Ask lists saved text, nonempty extracted figures and downloaded PDFs separately, and excludes catalog
entries with no readable page text. In Extract, typing a company name and pressing Enter has the
connected model resolve the text to concrete companies — "intel" becomes Intel Corporation
(NASDAQ: INTC) — shown as cards with ticker, country and the report it found; **Use this company**
downloads that PDF and extracts it. Saved reports come first; feeds and traditional search are
fallbacks.

PDFs, private uploads (`up-*`), credentials, logs, raw runs and derived embeddings are gitignored
and stay local. This repository is public and holds only reports and review notes intended for it.
`node scripts/sync-team-data.js` (try `--dry-run` first) copies results between an installed
desktop app and a checkout; keep the app closed while it runs, and it reports conflicting edits or
differing source PDFs rather than overwriting them.

## How a section works

One JSON file per report section in `backend/schemas/` — fields, sv+en locator keywords, arithmetic checks.
The prompt is generated from it. **Adding a section = adding a file.** `debt_maturity.json` is the scoped section
(total interest-bearing debt + maturity buckets, decided with SEB's end-user Kristian on 15 Sept; output is a one-slide
PPTX per company via `GET /api/reports/{id}/extraction.pptx`). `income_statement.json` was the placeholder the parser
was hardened on. Backend state at handoff: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Pipeline (backend/pipeline)

```
parse.py    PDF → text per page
locate.py   schema keywords → candidate pages          (deterministic, no LLM)
extract.py  candidate pages + schema → LLM (JSON schema) → fields
            → provenance check (quote ∈ page text)
            → arithmetic checks from schema
```

Out of scope, and never built: ESEF/iXBRL cross-check, a full vision fallback for scanned tables
(selective page OCR for text-less PDFs does ship — see [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)),
async jobs, a database, auth. Multi-report compare did get built: the Compare tab puts saved
extractions side by side, including the KB entries.
