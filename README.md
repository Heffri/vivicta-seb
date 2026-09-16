# Annual Report Parser — SEB challenge, Vivicta Finance & Insurance AI Hackathon 2026

PDF annual report in → structured, **source-linked** data out → JSON/CSV for downstream banking systems. Web UI on top.

Challenge owner: Kimberly Lejonö, Co-Head CIB Data & AI Hub, SEB. Full brief + meeting notes: [`docs/CHALLENGE.md`](docs/CHALLENGE.md).

## The one idea to keep

Every extracted number carries `source.page` + `source.quote`, and the backend checks the quote really exists on that page.
That is what makes this a bank tool and not a chatbot. Don't drop it.

## Layout

```
backend/    FastAPI + PyMuPDF + OpenAI-compatible LLM client (Ollama locally)   ← Chen, Boyu
frontend/   Vite + React 19 + Tailwind 4 + shadcn/ui                            ← Sebastijan
eval/       labels.csv + run.py → accuracy number                               ← Sara
docs/       API contract, challenge notes, prep for SEB meetings
data/reports/  bundled annual reports: index.json committed, PDFs gitignored -> `python data/fetch.py`
```

The handshake between frontend and backend is [`docs/API.md`](docs/API.md). Change it there first.

## Run it

Backend (terminal 1):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    mac/linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # leave LLM_BASE_URL unset → returns the fixture (UI dev mode)
uvicorn app:app --reload --port 8000
```

Reports (once): `python data/fetch.py` downloads the six bundled annual reports listed in `data/reports/index.json`
(Atlas Copco, Investor, Saab en/sv, SEB, SKF — ~130 MB). They show up in `GET /api/library` and in the UI's library picker.

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173, proxies /api → :8000
```

Real extraction with a local model:

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

Extraction and Ask's answers then run on Codex/Claude; Ask's retrieval still needs `LLM_BASE_URL` (Ollama/OpenAI-compatible) — see `backend/README.md`.

Accuracy:

```bash
python eval/run.py --dry-run       # scores the fixture, no backend needed
python eval/run.py                 # runs the real pipeline over data/reports + eval/labels.csv
python scripts/random_check.py --n 10 --seed 1   # fetches 10 untuned Large Cap reports; how many parse at full confidence
```

## How a section works

One JSON file per report section in `backend/schemas/` — fields, sv+en locator keywords, arithmetic checks.
The prompt is generated from it. **Adding a section = adding a file.** `debt_maturity.json` is the scoped section
(total interest-bearing debt + maturity buckets, decided with SEB's end-user Kristian on 15 Sept; output is a one-slide
PPTX per company via `GET /api/reports/{id}/extraction.pptx`). `income_statement.json` was the placeholder we hardened
the parser on. Current state and next steps for the backend team: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Pipeline (backend/pipeline)

```
parse.py    PDF → text per page
locate.py   schema keywords → candidate pages          (deterministic, no LLM)
extract.py  candidate pages + schema → LLM (JSON schema) → fields
            → provenance check (quote ∈ page text)
            → arithmetic checks from schema
```

Deferred until a demo breaks without it: ESEF/iXBRL cross-check, vision fallback for scanned tables, async jobs, DB, auth, multi-report compare.
