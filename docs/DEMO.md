# DEMO — the three-minute walkthrough, frozen

One script the whole team can rehearse from: which version to demo, which saved debt records to
open, what to say, and what not to promise. Everything here reads off the repository itself —
zero model calls to set up, and the main show is **stored real results**, not a live inference.

## Version lock (update this section before demo day)

| What | Value |
|---|---|
| Branch / commit demoed | acrylic demo rehearsal: commit `0dff6d1` (the following commit adds evidence/docs only; re-run `git rev-parse --short=7 HEAD` after a final fetch and use the delivered branch) |
| Windows installer feed | [`desktop-demo`](https://github.com/Heffri/vivicta-seb/releases/tag/desktop-demo) (auto-updating, CI-built from the team `demo` branch) — install the Setup exe once; it updates itself. [`desktop-main`](https://github.com/Heffri/vivicta-seb/releases/tag/desktop-main) is the equivalent feed for `main` |
| Not the installer? | Clone the repo and run `run.bat` (Windows) or `./run.sh` (macOS/Linux) — first run ~2–4 min, later runs seconds |
| The old portable exe | `desktop-0.3.4` (portable/Setup zip) **cannot update itself** — do not demo from it; use the auto-updating installer above or a fresh `run.bat` checkout |
| Data shipped | `data/kb/` (206 saved reports, 105 with a stored `debt_maturity` extraction) ships with the repo and inside the installer's bundled data. **No PDFs ship** — they are gitignored and the installer bundles none |

## The two saved samples (and one honest incomplete case)

All three open from **Knowledge base** with **Collection → All**, zero model calls, and — because a
saved report opens without the PDF (only page images need it) — fully offline. Their
verification chips read "Needs review": no human has confirmed the basis yet, so present them as
**Draft**, never as analyst-approved.

| | Karnell Group (`karnell_2025`) | XANO Industri (`xano_industri_2025`) | Ericsson (`ericsson_2025`) |
|---|---|---|---|
| Report | FY2025, English, 116 pages | FY2025, Swedish, 164 pages | FY2025, English, 236 pages |
| Debt note | Note 20, **page 106** | Note (borrowings), **page 84** | page 65 |
| Total borrowings | **397.2 MSEK** | **904,522 TSEK** | **32,703 MSEK** |
| Due within 1 year | 43.5 MSEK | 51,075 TSEK | 3,538 MSEK |
| Due 1–5 years | 353.7 MSEK | 802,669 TSEK | **null — not printed** |
| Due after 5 years | 0 (derived, check proves it) | 50,778 TSEK | **null — not printed** |
| Sum check | passed (43.5 + 353.7 + 0 = 397.2) | passed (51,075 + 802,669 + 50,778 = 904,522) | unclosed — `missing: due_1_to_5_years`, shown as such |
| PDF bundled? | **No** (public source: `storage.mfn.se` link in `data/kb/karnell_2025/meta.json`) | **No** (`mb.cision.com` link in its meta.json) | No |

Karnell is the primary sample (English, closes exactly, its derived 0 demonstrates the
"explicit zero, proven by arithmetic" story). XANO is the Swedish-language second sample with all
four buckets actually printed. Ericsson is the honest-incomplete case: a real report with no
>5-year bucket — the two nulls are **"not printed in this report"**, not zero, and the app shows
the check as unclosed instead of pretending it passed.

**Page images:** with no PDF on disk, the record opens, every value, quote, check, review and the
PPTX/CSV export work; only the page-image/PDF view is absent (the UI says to fetch the PDF from
Extract). For page images on stage, download the PDF once from the `source_url` in the entry's
`meta.json`, drop it in `data/reports/` as `<stem>.pdf`, and reopen — Karnell's note 20 then
renders on page 106.

## The three-minute script

The main show is stored real results. A live fresh extraction is an **encore**, never the main line — if it is demoed at all, it comes
after everything below has already succeeded.

- **0:00–0:20 — the goal.** "This is not a chatbot over PDFs. It turns a borrowings note into
  reviewable, deliverable analyst material: every number carries the page it came from and the
  sentence it was read from." On the first **Extract** screen, click **Open a real debt sample**;
  it opens the saved Karnell record directly. Say so up front: *this extraction is saved from an
  earlier run — pre-extracted, not happening live.* The equivalent manual route is **Knowledge
  base → Collection: All → search "karnell" → Open**.
- **0:20–1:00 — the evidence chain.** In Results, click the **Due 1–5 years** row: the source panel
  shows **page 106** and the verbatim quote `Liabilities to credit institutions 43.5 353.7 - 397.2`
  with the value highlighted. Open **Maturity profile** and point at the chart, then open **Checks & review** and point at the check: 43.5 + 353.7 + 0 =
  397.2, the identity closes — and the 0 is explicit because the table prints a `>3 years` column
  with a dash, proven by the arithmetic, not guessed. Name the basis: carrying amount, MSEK,
  group — and say the caveat: *a verified quote means we read the report faithfully, not that the
  report is right.*
- **1:00–1:35 — a real incomplete case.** Open **Ericsson**. Two real figures, two nulls. "The
  report prints no >5-year bucket. We show 'not read / not printed' — **null is not zero**, and a
  non-current split is not a 1–5-year bucket." Open **Checks & review** and show the check row saying `missing: due_1_to_5_years`
  — the app refuses to bless an identity it cannot prove, and that is the deliverable: an honest
  to-do for an analyst, not a fabricated table.
- **1:35–2:15 — a real human confirmation.** In Results, pick a figure, open **Review <figure>** under the table, then walk the form:
  check the source, enter a name, save the decision — the original value and previous decisions
  stay in the history. Leave the record **Draft** afterwards (or use a sample you genuinely
  reviewed before stage); never imply review mass-confirms everything.
- **2:15–2:40 — the deliverable.** **Export** → **Export PPTX**: one slide — totals, buckets, the source page
  numbers on it, Draft/ready status and the open items visible. Mention CSV/JSON as the downstream
  system interface in one sentence; do not narrate the tech stack.
- **2:40–3:00 — the numbers and the boundary.** "The stored library of 105 saved debt extractions
  scores 327/367 (89.1%) on hand-verified values and 263/313 (84.0%) on cited pages — reproducible
  offline with `python eval/run.py --stored-kb data/kb`, zero model calls. That is the *curated*
  library; first-pass extraction without labels scores lower (see the Accuracy section in the
  README)." Leave **Ask** and the company map for Q&A — do not let them eat the main line.

## Demo-day hardening checklist

- **Closed loop on a clean userData.** Rehearse once with `--user-data-dir <fresh dir>` (the
  packaged exe honors it; create the directory first and quote it — an unquoted path with spaces
  makes the exe exit silently). Confirm: open Karnell → bucket → page/quote → review → export →
  close → reopen, everything still there.
- **Offline-readable.** Kill the network and redo the Karnell walkthrough. Saved text, quotes,
  checks, review and export need nothing remote. Page images need the PDF already on disk —
  download it the day before; do not plan to fetch it on stage.
- **No dependence on web search or full-report OCR.** Do not demo the foreign-company web fetch or
  any scanned report. Saab's English PDF has no text layer — its OCR pass took **506 seconds**;
  never on stage.
- **OCR languages ship with the app.** `desktop/scripts/prepare-resources.js` copies an existing
  developer `data/tessdata` or downloads the official fast English/Swedish files while packaging,
  then places them in `resources/tessdata`. A clean installed app does not need repository scripts.
- **One redistributable real PDF, prepared.** Karnell's is a public `storage.mfn.se` link recorded
  in its own `meta.json`. Download it once, verify the sha256 against the meta, keep it on the demo
  machine and a spare stick. Other companies are fine as saved text.
- **Pre-warm everything you will click.** Saved results open from cache in milliseconds; if you
  want one *live* extraction as an encore, pick a known-stable one (Atlas Copco:
  34,899 = 6,471 + 16,025 + 12,403 on page 135) and run it once before the audience arrives so the
  cached repeat is the fallback.
- **Settings before stage.** Provider "Test" should show the CLI logged in — or stay deliberately
  in fixture mode and say so; fixture output is a fictional company ("Nordic Industrials AB
  (fictional fixture)") and must be labelled as demo data, never passed off as a real extraction.
  Keep `EXTRACT_MERGE_RUNS=off` for the encore (union/majority doubles the wait). Ask on BM25 alone
  is fine; only hybrid retrieval needs an embeddings endpoint indexed in advance.
- **Collection on stage.** The KB page defaults to the Wallenberg collection; switch to **All**
  (or pre-filter) before the audience sees it, so nobody thinks the Mid Cap companies are missing.
- **Package sanity, if demoing the installer.** Launch the packaged exe once the morning of,
  hit `GET /api/kb` / open a KB record, confirm the window survives (a fresh single-instance lock
  conflict closes the second copy silently).

## Measured rehearsal (2026-09-22 · package build / acrylic `0dff6d1` · isolated Windows package copy)

This is a fixture-mode rehearsal of an isolated unpacked package, freshly refreshed from the listed
acrylic commit and launched with a new quoted `--user-data-dir` whose path contains a space. No
model call was made. The shared package was not changed. The clean first start returned 206 bundled
saved reports; the close/reopen result later contains 207 because the Atlas fixture-upload result is
stored in that user-data directory.

| Step | Time | Result |
|---|---:|---|
| First start → `/api/kb` | 11.33 s | 206 saved reports. |
| Extract landing → **Open a real debt sample** | 0.137 s | Karnell Group's stored debt result; no extraction/model request. |
| Select Karnell **Due 1–5 years** → source | 0.097 s | Page 106 with highlighted `Liabilities to credit institutions 43.5 353.7 - 397.2`. Saved page text is present; the original PDF is not bundled. |
| KB → All → Ependion → **Due after 5 years** | 0.206 s | **Not printed in this report**, visibly distinct from zero, on page 155. |
| Confirm Ependion total borrowings | ≤1.1 s UI run | Review saved against page 155: `Borrowing 167,546 35,636 380,348 583,531`. |
| KB **Export all** CSV | 0.266 s | HTTP 200, 26,507 bytes, 105 parsed data rows. Quoted source fields can contain line breaks. |
| KB **Export all** PPTX | 1.805 s | HTTP 200, 536,326 bytes; opened by `python-pptx` with 110 slides. |
| Compare Karnell + Ependion → all maturity wall | 0.295 s + 0.202 s | 0/105 comparable, 105 basis-unconfirmed, 13 missing totals and 49 missing `<1y`; it is not a credit judgment. |
| Wallenberg directory: Sarnova | 0.153 s | Per the rehearsal ruling, Extract's company directory showed `Private company — reported inside Investor AB's annual report (Patricia Industries)` and opened Investor AB at page 41, with no `/discover`, `/fetch`, or `/extract` request. Company map's private-member column treatment is out of scope. |
| Atlas Copco exact upload | 9.1 s | Fixture batch row visibly **Done**; figures remain clearly labelled demo data. |
| Close → reopen → `/api/kb` | close 0.11 s; reopen 2.99 s | HTTP 200 / 207 records. Renderer re-observed **All companies**, light tone, and Ependion's saved `Human confirmed` / `Demo rehearsal` review. |

The package, backend, and dedicated debug port were closed after verification. The supporting visual
evidence is recorded in `docs/acrylic/evidence/w206.md` (five renderer captures).

## What we cannot promise (say none of these on stage)

- **The identity check closing ≠ the basis is right.** 43.5 + 353.7 + 0 = 397.2 proves arithmetic
  on the table we read — it does not prove that table is the borrowing note Kristian means
  (carrying vs undiscounted, leases in or out are recorded assumptions, pending his confirmation).
- **null ≠ 0.** A missing bucket is "not printed / not read". We never fill it with zero —
  Ericsson's nulls stay null.
- **A verified quote ≠ the annual report is correct.** We prove we read the report faithfully; the
  report itself can be inconsistent — two such cases (Green Landscaping, Volati) are documented in
  our own labels.
- **Confidence is not an accuracy probability** — it is a 0–1 score over named evidence checks
  (quote on page, value in quote, arithmetic, units). See `docs/CONFIDENCE.md`.
- **89.1% is the curated library's score, not a first-pass or market rate.** The 105 labelled
  companies were used repeatedly to debug the pipeline; the stored library is republished under a
  "nothing loses on the labels" gate. First-pass numbers are lower and are reported separately.
- **Fixture/demo mode output is fictional.** Without a configured model, uploads return a canned
  fictional company. It is for UI walks only.
- **No interest rates, covenants, currency splits or fair values** — out of the agreed scope
  (amounts and maturities only), and no credit-rating or refinancing-risk conclusions come out of
  this tool.
