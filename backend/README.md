# backend

```sh
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # mac/linux: .venv/bin/pip
cp .env.example .env         # leave the LLM_* lines commented to get fixture responses (frontend dev mode)
.venv/Scripts/uvicorn app:app --reload --port 8000

python ../data/fetch.py                                                                          # once: download the bundled reports (data/reports/index.json)
curl http://localhost:8000/api/library                                                           # -> LibraryEntry[] (only files on disk)
curl -X POST -H 'content-type: application/json' -d '{"file":"atlas_copco_2025.pdf"}' http://localhost:8000/api/reports/from-library  # -> same Report shape as an upload, id "lib-atlas_copco_2025"
curl -F file=@report.pdf http://localhost:8000/api/reports                                       # -> {"report_id": "...", ...}
curl -X POST -H 'content-type: application/json' -d '{"section":"income_statement"}' http://localhost:8000/api/reports/<id>/extract
curl http://localhost:8000/api/reports/<id>/extraction.csv
curl -o out.pdf http://localhost:8000/api/reports/<id>/pdf                                       # inline PDF, Range-capable (browser viewer, #page=N)
curl -X POST http://localhost:8000/api/reports/<id>/index                                        # chunk + embed into the KB (cached; /ask does it on demand)
curl -X POST -H 'content-type: application/json' -d '{"question":"Revenue 2025?","report_ids":["<id>"]}' http://localhost:8000/api/ask  # -> Answer with verified citations
curl http://localhost:8000/api/kb                                                                # what is in data/kb/
python -m pipeline.kb build                                                                      # once: meta + pages + embeddings for every bundled report on disk
```

Knowledge base (`pipeline/kb.py`, layout in `docs/API.md`): every parsed report lands in `data/kb/<stem>/` as
`meta.json` + `pages.jsonl` (committed), `/extract` adds `extractions/<section>.json` (committed), `/index` derives
`embeddings.jsonl` (gitignored, `EMBED_MODEL`, default `bge-m3`) from ~800-char page windows plus one fact chunk per
extracted field. `/ask` = cosine + keyword rerank over the selected reports, then `LLM_MODEL` answers with `[Company p.N]`
citations whose quotes are verified against the page text (unverified ones are dropped with a warning). `/extract` shows
the model up to `FEWSHOT` (default 2) checks-passed extractions of the same section from *other* reports, so the mapping
"Skatt" -> `income_tax` improves as the KB grows; `FEWSHOT=0` turns that off.

Contract: [`docs/API.md`](../docs/API.md). Add a section = drop a file in `schemas/`, no code.

Where to start hacking: `pipeline/parse.py` (PDF -> page texts, table-aware text would help),
`pipeline/locate.py` (keyword scoring -> which pages), `pipeline/extract.py` (prompt in
`SYSTEM_PROMPT_TEMPLATE`, provenance check, arithmetic checks), `pipeline/kb.py` (chunking, retrieval, /ask prompt).
Each module's docstring says what to do next.

## Codex CLI provider (`LLM_PROVIDER=codex`)

Every model call goes through `pipeline/llm.py`'s `chat()` now; `extract.py` and `kb.py`'s `ask()` call it
instead of talking to `openai.OpenAI` directly. Two backends: `openai_compatible` (today's Ollama / Azure /
OpenAI / OpenRouter path -- `LLM_BASE_URL` + `LLM_MODEL`, unchanged) and `codex_cli`, for a teammate with a
Codex subscription/API key but no local model and no OpenAI-compatible endpoint to point `LLM_BASE_URL` at:

```
# in backend/.env:
LLM_PROVIDER=codex
LLM_MODEL=gpt-5.6-terra           # -m passed to `codex exec`; this is the default if unset
# CODEX_BIN=C:\path\to\codex.exe  # only needed if `codex` isn't on PATH
```

`codex_cli` shells out to `codex exec -m <model> -s read-only -C <fresh empty temp dir> --skip-git-repo-check
--json -o <temp file> -`, piping `system` + `user` over stdin (`codex exec` has no separate system-role
concept) and reading the reply from `-o`/`--output-last-message`. The Codex CLI manages its own login
(`codex login`); this backend never reads or writes its credentials. A timeout or a non-zero `codex exec`
exit raises the same way an `openai.*` call failing already does, so `extract.py`'s retry/window-shrink logic
is untouched.

**Embeddings never go through Codex.** `kb.embed()` always calls an OpenAI-compatible `/v1/embeddings`
directly, so `/ask`'s retrieval still needs `LLM_BASE_URL` pointed at Ollama or a real OpenAI-compatible host
even with `LLM_PROVIDER=codex` -- Codex then only serves `/extract` and `/ask`'s answer generation. Without
`LLM_BASE_URL`, `POST /api/reports/{id}/extract` stays in fixture mode regardless of `LLM_PROVIDER` (its gate
in `app.py` checks only `LLM_BASE_URL`), so a Codex-only setup today also needs some placeholder
`LLM_BASE_URL` set just to clear that gate.

Test: `python -m pipeline.test_llm` -- a fake `codex.cmd` + Python script replays discovery, a fenced reply,
a non-zero exit and a timeout, no network or real Codex install needed.

## Checks

- `python ../scripts/smoke_api.py` — every endpoint in `docs/API.md` against a running backend (`--llm` adds extract/index/ask,
  `--fetch "Alfa Laval"` fetches a report live). Run before pushing backend changes.
- `python -m pipeline.test_confidence` — the evidence scoring in [`docs/CONFIDENCE.md`](../docs/CONFIDENCE.md).
- `python ../eval/run.py` — accuracy + mean confidence against `eval/labels.csv` (needs Ollama; ~1 min per report).
- Company + year in the UI calls `POST /api/reports/fetch`: MFN news feed first, DuckDuckGo PDF search as fallback; the PDF must
  be > 40 pages, have a text layer, and mention the company and the year in its first 20 pages. Cached in `data/reports/`.
