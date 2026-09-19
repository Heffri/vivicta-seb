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
`embeddings.jsonl` (gitignored, `EMBED_MODEL`, default `bge-m3`, first line records which model built it -- a model
switch rebuilds it wholesale) from ~800-char page windows plus one fact chunk per extracted field. `/ask` retrieval is
three-state (`kb.retrieval_mode()`, surfaced on `/api/config` as `retrieval`): **hybrid** = min-max-normalised cosine +
BM25 (0.6/0.4) when `LLM_BASE_URL` provides embeddings; **bm25** = pure Okapi BM25 (k1=1.5, b=0.75, in-memory index,
no files written) under a codex/claude-only subscription, which has no embeddings endpoint -- Ask is real there too;
**fixture** = no model at all. Both real states keep the ride-along of the 2 best label-matching extraction facts per
report, and `LLM_MODEL` answers with `[Company p.N]` citations whose quotes are verified against the page text
(unverified ones are dropped with a warning). `/extract` shows the model up to `FEWSHOT` (default 2) checks-passed
extractions of the same section from *other* reports, so the mapping "Skatt" -> `income_tax` improves as the KB grows;
`FEWSHOT=0` turns that off.

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
directly. Since v034 that no longer blocks a Codex-only setup: with `LLM_PROVIDER=codex` and no `LLM_BASE_URL`,
`/ask`'s retrieval runs pure BM25 (`kb.retrieval_mode()` -> `"bm25"`, nothing embedded, `embeddings.jsonl` never
written) and `/extract`, `/ask`'s answer generation both run on Codex. Pointing `LLM_BASE_URL` at Ollama or a real
OpenAI-compatible host additionally buys hybrid cosine+BM25 retrieval and `/index` embeddings.

Test: `python -m pipeline.test_llm` -- a fake `codex.cmd` + Python script replays discovery, a fenced reply,
a non-zero exit and a timeout, no network or real Codex install needed.

## Claude CLI provider (`LLM_PROVIDER=claude`)

Same idea as the Codex path above, for a teammate with a Claude subscription (not an API key) and no local
model or OpenAI-compatible endpoint:

```
# in backend/.env:
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-5           # --model passed to `claude -p`; this is the default if unset
                                     # (claude-opus-5, claude-haiku-4-5-20251001 also work)
# CLAUDE_BIN=C:\path\to\claude.exe  # only needed if `claude` isn't on PATH
```

`claude_cli` shells out to `claude -p --output-format json --model <model> --tools "" --no-session-persistence`,
piping `system` + `user` over stdin (same as Codex -- no separate system-role concept in a one-shot `-p` call)
and reading the reply from the JSON reply's `result` field. `--tools ""` (`claude --help`: 'Use "" to disable
all tools') leaves the model nothing to call at all; UAW's own `CLAUDE_CATALOG_ARGUMENTS`
(`process-transport.ts`, private reference repo) reaches for the same pair to take a headless call down to plain text in, text out --
stronger than `--permission-mode plan`, which still permits read-only tool calls and exists for an interactive
approval loop `-p` never runs. Executable discovery order also follows UAW's `discoverClaudeLaunch`: `CLAUDE_BIN`,
then PATH (bare `claude`, so PATHEXT finds an npm shim too -- a backend process inherits a shell's PATH already,
so unlike UAW's Electron app there is no separate `%APPDATA%\npm` check), then `~/.local/bin/claude.exe` (the
native installer's default), then the Claude desktop app's own bundled CLI under
`%APPDATA%\Claude\claude-code\<newest version>\claude.exe` -- never `%LOCALAPPDATA%\AnthropicClaude`, which is
the desktop GUI's own `claude.exe`, not the CLI. The Claude CLI manages its own login; this backend never reads
or writes its credentials. A timeout, a non-zero `claude -p` exit, or a reply with `is_error: true` all raise
the same way a Codex or `openai.*` failure already does.

**A Claude API key does not need `LLM_PROVIDER=claude`.** That provider is the CLI/subscription path only,
mirroring Codex; a teammate with an Anthropic API key instead points the *existing* `openai_compatible` path at
Anthropic's own OpenAI SDK-compatible endpoint -- no new code:

```
# in backend/.env:
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.anthropic.com/v1/
LLM_API_KEY=<your Anthropic API key>
LLM_MODEL=claude-sonnet-5
```

Confirmed against Anthropic's own OpenAI SDK compatibility docs (platform.claude.com/docs/en/cli-sdks-libraries/
libraries/openai-sdk, fetched 2026-09-16) rather than a live call -- this environment has a Claude Code
subscription, not a separate Anthropic API key, and the point of this lane's call budget is exercising the real
`claude_cli` path above, not minting a new billable credential to spend a call on this one instead. Two things
to know before relying on it:

- **`response_format` (the `json_schema`/`strict` mode `_openai_chat()` sends) is silently ignored** by
  Anthropic's compatibility layer -- Anthropic's docs say so explicitly ("For JSON output, use Structured
  Outputs with the native Claude API"). The model still answers -- `extract.py`'s system prompt already asks
  for compact, schema-shaped JSON in plain language, the same way it does for `codex_cli`/`claude_cli`, neither
  of which gets strict-schema enforcement either -- but nothing here *guarantees* the reply parses, unlike a
  real OpenAI/Azure/Ollama endpoint honoring `response_format` today.
- `temperature=0` (what `_openai_chat()` sends) is within Anthropic's supported 0..1 range, and the model name
  goes through as-is (`claude-sonnet-5`, `claude-opus-5`, `claude-haiku-4-5-20251001`) -- both unremarkable, no
  action needed.

**Embeddings never go through Claude either**, for the same reason as Codex: `kb.embed()` always calls an
OpenAI-compatible `/v1/embeddings` directly. As with Codex, a Claude-only setup still gets a real `/ask` -- its
retrieval runs pure BM25 without `LLM_BASE_URL` (`kb.retrieval_mode()` -> `"bm25"`); a base URL upgrades retrieval to
hybrid cosine+BM25.

Test: `python -m pipeline.test_llm` -- a fake `claude.cmd` + Python script replays discovery, stdin,
`--output-format json` parsing, fence stripping, `is_error: true`, a non-zero exit and a timeout, no network or
real Claude Code install needed.

## Model web search for report fetching (v074)

The report cache used to only know how to find Swedish issuers. `pipeline/fetch.py` now has a fourth source for
the rest of the world: when the MFN/Cision feeds, the Nasdaq notices and the DuckDuckGo search all come up empty
(the norm for foreign companies -- the Swedish feeds never carry them, and DuckDuckGo bot-blocks this backend),
and the provider is `LLM_PROVIDER=codex` or `claude`, `llm.web_lookup()` makes the same one-shot CLI call as
`chat()` with the provider's web-search tool switched on:

- codex: `codex --search exec ...` -- `--search` is a *top-level* flag (enables the native Responses
  `web_search` tool, no per-call approval); `codex exec --search` is rejected.
- claude: `claude -p --tools WebSearch ...` -- `chat()`'s `--tools ""` disables every tool, so the allowlist
  is the whole difference.

The model is asked for at most 3 direct URLs to the official annual-report PDF on the issuer's investor-relations
site or a regulatory repository (no ESEF zips, quarterly, sustainability or governance reports) -- or, failing a
direct link, the issuer's IR/annual-report page URL itself. Every candidate then runs fetch's regular validation
-- real PDF, text layer, > 40 pages, issuer token + fiscal year in the first 20 pages -- and the first survivor is
registered with `note: "model search (<provider>)"` and `tags: ["fetched", "foreign"]`. An OpenAI-compatible
provider has no search tool: `web_lookup()` raises rather than answer from memory, `fetch.websearch_provider()`
keeps such a backend on the three plain sources, and a model search that errors (CLI unavailable, unparseable
reply) is reported in `/api/reports/fetch`'s usual 404 `detail`. The endpoint takes optional `country`/`hint`
fields that only feed this search's prompt.

**Fifth source (v080): crawling a page-shaped leftover.** When every direct candidate from all four sources above
still fails -- because a model reply names the issuer's IR page instead of a PDF, a web-search hit served a page,
or a direct link 404s outright (Shell's own asset-store URLs expire) -- `fetch.py` crawls whatever page-shaped
candidates those attempts left behind: the page itself (or, for a dead direct link, the guessed IR path for its
own domain, the same guesses the stub-notice fallback above already makes), plus one hop into a same-domain
reports/investor-relations sub-page when the page itself carries no PDF link. Every `.pdf` link found still passes
the same IS_AR/BAD_URL/NOT_REPORT gate and the same download+validate chain as every other source, and -- unlike
every earlier source (first validated survivor wins) -- this one downloads every harvested candidate within a
90-second budget (at most 8, 20 s each) and keeps the one with the most pages, since the page linking a summary
volume often links the full report right next to it (Nestlé's Annual Review vs. its actual Annual Report). The
winner is registered with `note: "IR page crawl"` and `tags: ["fetched", "foreign"]`.

Test: `python -m pipeline.test_fetch` -- a scripted `web_lookup` stand-in and a loopback http server serving a
handful of generated PDFs and static HTML pages; no CLI, no model call, no external network.

## Two-pass page selection (`EXTRACT_TWO_PASS`)

Opt-in, default **off**: `EXTRACT_TWO_PASS=1` makes `extract()` run a small pass-1 call that asks the
model which locator candidate page holds the target table before pass-2 extracts from that narrower
window, instead of every candidate page at once (`_select_pages` in `pipeline/extract.py`). v045's
30-company `debt_maturity` before/after (Codex `gpt-5.6-terra`) found this a net positive over v043's
first round -- 11 of 13 regressions no longer worse, only 2 still worse for narrow, understood reasons
-- and recommended flipping the default on for hosted providers; kept off here pending the group's
call, and specifically because it has never been run against a local Ollama model, only Codex/Claude.
The desktop Settings tab's Codex/Claude/API-endpoint cards carry a matching toggle (on by default)
that writes this same env var on Save; there is no toggle for Local Ollama, which always runs with it
off. See `pipeline/extract.py`'s own module docstring and `docs/acrylic/evidence/v043.md`/`v045.md`.

## Quote retry (`EXTRACT_QUOTE_RETRY`)

Opt-in, default **off**: `EXTRACT_QUOTE_RETRY=1` adds one follow-up call after the extraction call
when the model's own answer cites a quote that is not printed verbatim on the page it names. The
follow-up (`_quote_retry` in `pipeline/extract.py`) shows each such field's key, label and earlier
value plus the cited page's own table rows (`_page_rows`, numbered; a page over
`QUOTE_RETRY_MAX_ROWS` rows is filtered to the rows matching a field's value or one of its synonyms,
±2 rows of context) and asks the model to copy the printed row character for character -- or answer
null when no printed row states the figure. A field adopts the reply only when the new quote
verifies on the page it names (`quote_on_page`), so a null, missing or still-unverifiable reply
keeps the first answer: the retry can never leave a field worse than the single call. A 0 already
proven by the report's own words (`_stated_zero`, v050) is not retried -- the sentence is the
provenance, and a row list could only talk the model out of it. v054's 9-company Codex
before/after (`docs/acrylic/evidence/v054.md`): 1 trigger in 9 (MEKO), no adoption (the true row is
torn apart by a two-column layout in the text layer -- the `parse.py` defect HANDOFF's "Next" names),
nothing worse, nothing improved, so it stays off pending a corpus where quote-shaped failures
reproduce; the switch and its offline tests are ready either way.

## debt_maturity's four synonym-shaped schema keys (v083)

`schemas/debt_maturity.json` carries four differently-scoped word lists; picking the wrong one silently
does nothing (a v046/v060 split, deliberate, not an oversight) or, worse, loosens the wrong match. Which
`extract.py` code path reads each one, per field or per schema:

- **`fields[].synonyms`** -- row-*label* matching, read everywhere a printed row is checked against a field
  (`_label_known`, used by scoring, the "own row" fill, `_stated_zero`'s subject check, ...). This is the one
  list that can match a field's *direct* statement row. A month/day-range header fragment ("within 12 months")
  never belongs here -- see `header_synonyms`.
- **`fields[].header_synonyms`** -- *column-header* wording for a bucket-as-columns table (one row, several
  maturity buckets side by side, e.g. Cloetta's "Total 197 22 1,377 9 1,605" under "< 1 year / 1-2 years / 2-5
  years / > 5 years / Total"), read only by `_bucket_synonym_hits`/`_bucket_header`, never by `_label_known`.
  Lets a header say "within 12 months" without that phrase ever being allowed to match a *row label* (which
  would wrongly claim a "within 12 months ..." prose sentence as a field's own row). `total_debt`'s own
  `header_synonyms` are carrying-amount wording ("carrying amount", "redovisat värde") that mark which header
  column is the table's real total when a bare Total/Summa word competes with it on the same line (v076).
- **`total_debt.row_synonyms`** (v083; formerly a private `_DEBT_ROW_SYNONYMS` list inside `extract.py`) --
  `_bucket_total_row`'s own fallback for picking a bucket-as-columns table's *grand-total row* when no row is a
  `total_debt` synonym and no row is a bare Total/Totalt/Summa either (Ependion's bucket row is labelled just
  "Borrowing", Boozt's just "Lease liabilities"). Never used for direct field-row matching -- a row still needs
  its own real bucket header above it, with a column count matching its own printed amounts, before it is
  trusted. Keep additions direction-safe and phrase-exact: bare `"loan"`/`"loans"`/`"lån"` are deliberately
  excluded (v060 Finding 2 -- a bank's own *asset*-side "Loans to credit institutions" prefix-matched bare
  "loan" and outranked the real debt row); `"bank loans"` and v083's `"lån kreditinstitut"` stay because they
  are exact phrases that do not also prefix a lending-direction row like "Lån till kreditinstitut" ("till" =
  "to" breaks the prefix). Only `total_debt` has this key -- the three bucket fields don't need their own,
  since they are never the table's total row.
- **`ignore_header_synonyms`** (schema top-level, not per-field; v076) -- header wording that is a real,
  counted table column but must never be assigned to a bucket or the total (a liquidity-risk note's
  undiscounted contractual-cash-flow total printed beside the carrying-amount column, e.g. "Total contractual
  cash flows", "total undiscounted"). Read by `_bucket_synonym_hits`/`_bucket_header` only, tagged `_ignore`,
  dropped by `_bucket_assign` -- present in the column count so the real columns still line up, absent from
  every field's own value.

## Maturity basis (`DEBT_BASIS`) -- v089

Default **carrying**: debt_maturity reads the borrowings note's carrying-amount table, exactly as every
round since v028 has (the total that ties to the balance sheet; a liquidity note's undiscounted total is
counted as a column and ignored -- the v076 split above). `DEBT_BASIS=undiscounted` flips the basis to the
liquidity-risk note's contractual undiscounted cash flows: the same bucket columns are read the same way,
but the two total-shaped word groups swap roles -- `ignore_header_synonyms` wording becomes the total slot
(total_debt = the contractual cash-flow total, future interest included, so Instalco's buckets summing to
3,209 against a carrying total of 3,122 is no longer an over-valve rejection but the report's own read) and
`total_debt`'s carrying `header_synonyms` become the ignored column. The identity check then closes against
the undiscounted total by construction. The prompt follows the basis: the schema carries a
`description_undiscounted` beside its `description` (schema top level and `total_debt`), and
`system_prompt` picks the one matching `debt_basis()`; anything but `undiscounted` in the env reads
`carrying`, so a typo can never flip it. Every extraction reports the basis it was read on in its
top-level `maturity_basis` field (v089 named it `basis`; the 2026-09-18 merge renamed it, because
Sebastijan's analyst-confirmed `basis` object owns that key), and `GET /api/config` mirrors the live
value as `maturity_basis`. The desktop
Settings cards carry the matching two-choice control that writes this env var on Save. See
`pipeline/extract.py`'s `debt_basis()` and `docs/acrylic/evidence/v089.md`.

## Prior-year maturity metadata (`prior_year`) -- v091

debt_maturity extractions may carry a top-level `prior_year` object: the prior fiscal year's own
`total_debt` + bucket figures, each with the prior year's printed row as its source, plus the identity
check re-run on those values. It is never a model answer and never crosses tables — it is a
deterministic re-read of the same table the current year came from, on the same basis: either the
prior-year *column* of the same bucket rows (MedCap's year-column table), or the same-labelled row of
the prior year's own stacked block read with the same column keys (Tången's and Ework's two-table
pages, where `_bucket_row_prior_year` proves the year). The key is written only when `total_debt` and
at least two buckets were read and they close `maturity_sums_to_total` within the check's own ±2 on
**explicit** values (the shipped `require_explicit_values` rule, applied to FY-1: a bucket whose
prior-year figure the table does not print is absent from the fields and named in the check detail,
never zero-filled). Date-per-instrument notes (Proact) and model-only answers produce no prior year.
`GET .../extraction.pptx?prior_year=1` adds the second, fainter `FY<n-1>` chart series when the
extraction carries one; the UI's "Show prior year" switch (MaturityChart) follows the same flag. See
`pipeline/extract.py`'s `_prior_year_fill()` and `docs/acrylic/evidence/v091.md`.

## Publishing hardening results into `data/kb` (`scripts/publish_kb.py`) -- v093

    python scripts/publish_kb.py --kb <seed1-kb> ... --kb <seedN-kb> [--section debt_maturity] [--dry-run]

Copies the debt-maturity hardening rounds' stored results into `data/kb`. Per stem the `--kb`
directories are walked in the order given and a later one overrides an earlier one — list them
`seed1…seedN` and the highest seed that has the stem wins. `data/kb/<stem>/` missing → `meta.json` +
`pages.jsonl` are copied byte for byte; same-PDF-sha stems get only the extraction written;
different-sha stems are skipped and listed, never overwritten. Every extraction is **replay-gated**:
the stored fields are fed back through the *current* `extract()` as if the model had just answered
(no model call — the `scripts/replay_check.py` mechanism), and the replayed output is published only
where it is no worse than stored — never a lost value, never a lower confidence; the original
warnings are kept plus one `published:` line. Idempotent: run twice, nothing changes. At v093
`data/kb` carried the 72 seed-1–8 entries plus 12 more (seed 9 + Avarda/Linc) published with the
same script — 186 companies, 85 of them with a `debt_maturity` extraction. To fold in a future seed,
append its directory and re-run; the full per-stem table (what replayed better, what was kept as
stored and why) is in `docs/acrylic/evidence/v093.md`. Since v093 the same script has republished
the committed `data/kb` after every landed mechanism (the `data: republish` commits — 84 Mid Cap
debt entries after v095/v096, the seed-10 publish, v101's sign normalization, v102's Ambea year fix,
v104's Svedbergs finer-split sums; the publish gate clamps stored confidences at 1.0): `data/kb`
now carries 196 companies, 95 of them with a `debt_maturity` extraction, and `eval/run.py
--stored-kb data/kb` scores values 257/327 (78.6%) / pages 200/327 (61.2%) over the 327 scored
label rows.

## Checks

- `python ../scripts/smoke_api.py` — every endpoint in `docs/API.md` against a running backend (`--llm` adds extract/index/ask,
  `--fetch "Alfa Laval"` fetches a report live). Run before pushing backend changes.
- `python -m pipeline.test_confidence` — the evidence scoring in [`docs/CONFIDENCE.md`](../docs/CONFIDENCE.md).
- `python -m pipeline.test_parse`, `python -m pipeline.test_kb`, `python -m pipeline.test_paths` — table-row
  reconstruction, KB save idempotency, and dev-tree-vs-frozen path resolution self-checks.
- `python ../eval/run.py` — accuracy + mean confidence against `eval/labels.csv` (needs Ollama; ~1 min per report).
- Company + year in the UI calls `POST /api/reports/fetch`: MFN news feed first, DuckDuckGo PDF search as fallback; the PDF must
  be > 40 pages, have a text layer, and mention the company and the year in its first 20 pages. Cached in `data/reports/`.

## Desktop build (PyInstaller)

All filesystem paths go through `pipeline/paths.py` (dev tree vs. frozen onedir build, see its module docstring).
Two roots: `resource_dir()` (read-only, bundled: `schemas/`, `fixtures/`) and `data_dir()` (read-write: reports
cache, KB, uploads, `backend.log` — `ARP_DATA_DIR` if set, else `data/` next to the repo root in dev or next to
the exe when frozen).

```sh
pip install -r requirements-build.txt        # adds pyinstaller on top of requirements.txt
python build_exe.py                          # -> dist/backend/backend.exe (onedir; ~106 MB, ~2-6 s cold start)

set ARP_DATA_DIR=C:\path\to\user\data        # companies.json, reports/, kb/, uploads/, backend.log all live here
set FRONTEND_DIST=C:\path\to\frontend\dist   # optional: serve the built frontend from / (SPA fallback to index.html); unset -> no static route at all
dist\backend\backend.exe --port 8000 --host 127.0.0.1
```

- `ARP_DATA_DIR` unset in the packaged exe defaults to a `data/` folder next to `backend.exe` (portable-app style);
  in the dev tree it defaults to `<repo>/data`, unchanged from before this existed.
- `KB_DIR` keeps its pre-existing standalone meaning (resolved against `resource_dir()`, independent of
  `ARP_DATA_DIR`) for backward compatibility with the documented `.env` override.
- The desktop shell is expected to copy `data/companies.json`, `data/reports/index.json`, and `data/kb/` into
  `ARP_DATA_DIR` once (and any cached report PDFs it wants pre-seeded) — `backend.exe` never bundles `data/` itself.
- Logs go to stdout and `<data_dir>/backend.log` (rotated at 5 MB, 3 backups); this mirrors the existing
  `print()`-based diagnostics too, not just uvicorn's own request log, so a console-less run still leaves a trail.
- `backend.spec` bundles `schemas/` + `fixtures/` as data and pins hidden imports uvicorn needs for its dynamic
  loop/protocol imports (`app.py` forces `loop="asyncio", http="h11", ws="none"` so only those concrete
  implementations need to be listed), plus `pymupdf`/`pptx` package data PyInstaller's static analysis can't see
  on its own. A PyInstaller `tzdata` hidden-import warning is expected and harmless (nothing here does named-zone
  `zoneinfo` conversion).
