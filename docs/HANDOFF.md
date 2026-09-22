# Handoff — Boyu & Chen (backend pipeline)

> Historical record, written 2026-09-15 to hand the `debt_maturity` work to two teammates. Every
> task on its to-do list has since shipped, and the counts below describe the repository as it
> stood that day.

Written 2026-09-15 by Sebastijan, right after the SEB/Kristian meeting. Read this, then [`README.md`](../README.md) for run instructions and [`docs/API.md`](API.md) for shapes. Ask on Discord.

## Where we are

Everything runs locally, end to end, on a real model (Ollama `qwen3:8b`, embeddings `bge-m3`):

```
company name → fetch.py finds + downloads the annual report (MFN / Nasdaq / web)
            → parse.py (PDF → text per page)
            → locate.py (schema keywords → candidate pages, no LLM)
            → extract.py (LLM → fields, each with page + verbatim quote → provenance check → arithmetic checks → confidence)
            → JSON / CSV / PPTX export, RAG "Ask" over the knowledge base
```

- 114 annual reports cached in `data/reports/` (PDFs gitignored, `index.json` committed), 102 of them in `data/kb/`.
- `income_statement` is hardened: 10/10 random untuned Large Cap companies at full confidence (`random_check.py --seed 14`). It was the placeholder section while we waited for the scope; ~25 commits of parser fixes came out of that loop.
- Confidence has a definition: [`docs/CONFIDENCE.md`](CONFIDENCE.md). Seven evidence checks per field; 1.0 means the quote is on the page, the value is in the quote, arithmetic holds, etc. Not a model vibe.

## Scope — decided today with Kristian

**Section:** the debt maturity note — total interest-bearing debt and *when it falls due*. Kristian calls it "Note 20"; the number varies by issuer, the content doesn't (borrowings / upplåning / räntebärande skulder + a maturity table).

**Descope, explicitly:** amounts only. No interest rates, no covenants, no currency split, no fair values.

**Output he wants:** one PowerPoint slide per company — total debt + a bar chart of the maturity buckets.

**Company universe:** Nasdaq Stockholm Main Market, **Mid Cap**, excluding insurance, real-estate companies and SEB itself. That is 107 of the 132 Mid Cap names in `data/companies.json` (25 Real Estate removed; there is no insurance sector in the dataset and none of the 18 Mid Cap Financials are insurers). Reproduce the list:

```bash
python -c "import json; d=json.load(open('data/companies.json',encoding='utf-8')); print('\n'.join(sorted(c['name'] for c in d if c['market']=='Mid Cap' and c['sector']!='Real Estate')))"
```

**Shipped for this scope (commit `cd6ebe1`):**
- [`backend/schemas/debt_maturity.json`](../backend/schemas/debt_maturity.json) — fields `total_debt`, `due_within_1_year`, `due_1_to_5_years`, `due_after_5_years`; one identity check that the buckets sum to the total.
- [`backend/pipeline/ppt.py`](../backend/pipeline/ppt.py) + `GET /api/reports/{id}/extraction.pptx` — bar chart when the fields look like maturity buckets, a plain table for any other section. Export PPTX button in the UI.
- Tested on **one** company (Ericsson: 32 703 = 3 538 + 29 165, no >5y bucket in its note — correct null). That is the whole test coverage. Which brings us to:

## Your job: make `debt_maturity` as solid as `income_statement`, on the Mid Cap universe

Same loop that got the income statement to 10/10. One person drives seeds, the other fixes — swap when it gets boring.

```bash
# backend on :8000 with Ollama, from the repo root
PYTHONIOENCODING=utf-8 python scripts/random_check.py --n 10 --seed 1 --section debt_maturity --market "Mid Cap"
```

For every company that is not at full confidence, in this order:

1. **Was it the locator?** Backend log prints `candidate pages [..]`. Open the PDF at those pages. Wrong pages → add keywords / `exclude_keywords` to the schema. Zero code.
2. **Was it the label?** Right page, wrong or null value → the bucket label in that report isn't in `synonyms`. Add it to the schema. Zero code.
3. **Was it the parser?** Right page, right label, wrong number → `extract.py`. Fix the *pattern*, not the company (look at the git log for the style: every commit names the company that exposed it and the general rule that fixed it). No `if company == ...`, ever.
4. `cd backend && python -m pipeline.test_confidence`, replay a few earlier companies so you didn't regress, commit as `schema: ...` or `extract: ...`, push, next seed.

Task 0, before any of that: `random_check.py` can't exclude sectors yet (`--market` is a substring match on the market field, line ~42). Add `--exclude-sector "Real Estate"` — three lines — so the draw is the real universe.

### What will be different from the income statement (expect these)

- **Bucket boundaries vary.** IFRS 7 standard is `<1y / 1–5y / >5y`, but you'll see `1–2y / 2–5y`, per calendar year (`2026, 2027, 2028, later`), or only `current / non-current`. The schema tells the model to sum finer splits into 1–5y — verify it does; if it's unreliable, add explicit fields for the finer splits and derive 1–5y in a check instead of trusting the model to add.
- **Two tables on one page.** The liquidity-risk note often prints *contractual undiscounted cash flows* (including future interest) next to *carrying amounts*. Different totals. We want the one that sums to the balance-sheet borrowings. Make the locator/description prefer it; a check against a `total_debt` that isn't on the balance sheet would catch the wrong pick.
- **Leases (IFRS 16).** Some issuers include lease liabilities in "interest-bearing liabilities", some don't. Decide once, write it into the schema `description`, apply it everywhere. Ask Kristian which one he wants if it matters to him (open question below).
- **Financials in the universe** (Hoist, Intrum, Norion Bank, Morrow Bank, Avarda…): their "borrowings" notes are structured differently (deposits, issued securities). Lower priority — industrials first, they're most of the 107.
- **Null buckets are normal.** Ericsson has no >5y row. The UI then shows the check as failed with `missing: due_after_5_years`, while confidence scoring treats a missing operand as n/a (`extract.py` ~line 479). Net effect: the sum is never actually verified for such companies. If it's common, make the check tolerate null buckets as 0 so the slide's total is checked.
- **The slide is only as good as the extraction.** `ppt.py` skips null buckets and prints whatever `total_debt` says. If you change field keys, update `BUCKET_ORDER` / `BUCKET_LABELS` in `ppt.py` — that is the only coupling.

## Map of the backend

| File | Lines | What | Entry point |
|---|---|---|---|
| `app.py` | ~300 | FastAPI routes, in-memory report store | `uvicorn app:app --port 8000` |
| `pipeline/fetch.py` | 325 | company name + year → PDF in `data/reports/` | `python -m pipeline.fetch "Boliden" 2025` |
| `pipeline/parse.py` | 93 | PDF → text per page | — |
| `pipeline/locate.py` | 74 | keywords → candidate pages | — |
| `pipeline/extract.py` | 846 | the parser: prompt, provenance, repairs, checks, confidence | `python -m pipeline.test_confidence` |
| `pipeline/kb.py` | 329 | `data/kb/` knowledge base + embeddings + RAG | `python -m pipeline.kb build` |
| `pipeline/ppt.py` | 90 | Extraction → one-slide .pptx | — |
| `schemas/*.json` | — | one file per section; **the prompt is generated from it** | `GET /api/schemas` |
| `scripts/random_check.py` | — | the hardening loop | see above |
| `eval/run.py` + `labels.csv` | — | labelled accuracy (Sara's) | `python eval/run.py` |

Each `pipeline/*.py` module docstring ends with a "Next for a teammate" list — those are real, considered next steps, not filler. `extract.py`'s first one (two-pass: pick the page, then extract from it alone) is the biggest single quality lever left.

## Rules that are not negotiable

- **Every number carries `source.page` + `source.quote`, and the backend verifies the quote is on the page.** That is the product. A field without a verified source is dropped, not shown.
- **Schema first, code second.** If a fix can be a synonym or a keyword, it is a synonym or a keyword.
- **General patterns only.** No company-specific branches. The git log is the style guide.
- **`main` always runs.** Small commits, `area: what` messages, push often. No long-lived branches during the hack.
- **Local model.** Everything must work on Ollama `qwen3:8b`; the OpenAI-compatible env vars can point at a hosted model for the final demo if quality demands it, but don't develop against one.
- **Never bypass DuckDuckGo's bot challenge** in `fetch.py`. Feeds first, web as fallback, and if the web says no, it's no.
- `# ponytail:` comments mark deliberate shortcuts and name the upgrade path. Keep the habit.

## Also open (lower priority)

- Octave Intelligence can't be fetched — IPO'd May 2026, no FY2025 report exists. Not a bug. Skip it.
- `parse.py`: plain `get_text()` loses table structure; `find_tables()` / blocks sorted by (y, x) would help both locating and quote matching. Debt notes are pure tables — this might matter more here than it did for the income statement.
- `locate.py`: parse the table of contents and boost the page it names. Would make "Note 20" literally usable as a hint.
- Sara: `eval/labels.csv` has a `section` column — label `debt_maturity` for ~10 Mid Cap reports so `eval/run.py` gives us a number to show Björn that isn't the backend grading itself.

## Open questions for Kristian / SEB (Sebastijan owns, but shout if a fix depends on the answer)

- Carrying amount or contractual (undiscounted) maturities? (Decides which table we read.)
- Lease liabilities in or out of "debt"?
- His bucket structure — is `<1y / 1–5y / >5y` what he puts on his own slides, or does he want per-year?
- Prior year alongside current, or current only?
- Where does the slide go today — deck template we should match?

## Who does what

| | |
|---|---|
| Boyu, Chen | `debt_maturity` hardening loop above; `extract.py` / schema / `locate.py` |
| Sebastijan | frontend, API contract, demo, SEB contact, `ppt.py` layout once Kristian's template is known |
| Sara | `eval/labels.csv` for `debt_maturity`, `eval/run.py` |
