# Source evidence and report discovery fixes

Original branch: `codex/source-evidence-report-discovery-fixes`

Latest follow-up branch: `codex/historical-report-discovery-fixes`. See the [current merge handoff](historical-report-discovery-handoff.md) for the final scope, validation and remaining limitations. The sections below retain the development history.

This branch makes Ask citations readable and traceable to the correct original PDF, and fixes shared download/discovery failures across the Wallenberg directory. It is prepared for review and a later merge; it does not release or merge a final version.

## Ask source presentation

- Replace the unstructured source-text panel with a dedicated evidence panel containing the supporting passage, color legend, original-page preview, readable text, and highlighted PDF views.
- Reconstruct recognizable year and maturity columns into tables, including inline rows and note columns. Preserve source wording, figures, and offsets; keep ambiguous layouts as text instead of guessing columns.
- Highlight cited keywords in blue and supporting figures in amber. Scroll the readable source toward the cited passage.
- Apply the same report-derived logic across companies. ABB is a regression example, not a hardcoded rendering rule.
- Keep useful evidence visible when saved text, page images, or exact PDF matches are unavailable. Ignore stale responses when switching citations.

## Original PDF evidence and downloads

- Add `GET /api/reports/{report_id}/pages/{n}/evidence` for page coordinates of matched keywords and figures.
- Extend `GET /api/reports/{report_id}/pdf` with a page and citation quotes to return the full report with PDF highlight annotations on the cited page. Original cached bytes are unchanged.
- Prefer exact passages; for split table text, anchor amounts to the matching label's row. Avoid highlighting unrelated repetitions, partial numeric matches, or bare numbers without context.
- Account for rotated pages and enforce quote-count/length and page limits.
- Expose **Open original PDF**, **Download original PDF** when missing, and **Download highlighted PDF** in Ask. Clarify that citation page numbers refer to PDF-viewer pages.

## Restore the correct saved edition

- Add `POST /api/kb/{stem}/pdf` to download the original saved source URL and verify its SHA-256 before attaching it to existing evidence.
- Treat a mismatched cached PDF as unavailable. Reject a different publisher edition rather than silently changing citation page numbers.
- Restore files atomically and preserve a displaced PDF under `reports/replaced/`. Exclude that local backup directory from Git.
- Keep saved page text, extractions, and reviews usable when the original download is unavailable. Upload-only sources require the original PDF to be uploaded again.
- Publish library registration state only after parsing and persistence succeed, allowing retries after a parsing failure.
- This addresses the ABB case where a different report bundle did not match the saved financial report and its page-55 citation.

## Report discovery and validation

- Recognize unaccented Swedish annual-report filenames and combined annual/sustainability reports without allowing interim statements, standalone topic reports, or meeting notices through solely on filename matches.
- Validate shorter annual accounts using issuer, year, annual-report title, income statement, and balance sheet instead of rejecting every document of 40 pages or fewer.
- Check cover identity and known legal-name aliases; reject parent-company reports, different subsidiaries, and similarly named businesses. Supply Wallenberg holding context to discovery.
- Add aliases for Vectura Fastigheter and Hi3G Scandinavia.
- Prefer verified report-index URLs before fresh discovery. Add official FY2025 sources for FAM, Höganäs, and Kopparfors Skogar.
- Preserve per-source rejection and download reasons. Return distinct `report_unavailable`, `download_failed`, and `search_unavailable` error codes.
- Show report-availability and download-specific guidance, source-check details, and retry actions in Extract.
- Set UTF-8 for the desktop Python process so logging names such as Mölnlycke and Wärtsilä cannot crash an otherwise successful request on Windows.

## Publication limits and live audit

Some companies do not publish standalone annual reports on their own websites, while registry accounts may still be available. The follow-up found FY2025 accounts listed for Atlas Antibodies AB and The Grand Group AB on Hitta. A failed PDF search must not be presented as evidence of non-publication. Registry accounts and parent-group reporting remain separate sources, and the directory does not guarantee a direct PDF download for every company and year.

The FY2025 audit attempted all 35 Wallenberg options: **21 original PDFs available with nonempty debt-maturity candidate pages, 13 without a verified public standalone annual PDF, and Nasdaq blocked by HTTP 403**. These are report-fetch and candidate-page checks, not full financial extraction for every company. See [all company results and sources](wallenberg-report-audit-2025.md).

The incorrectly matched Sarnova/Investor report created during the local audit was moved to a local quarantine. That cache repair is not a repository migration and is not shipped as report data.

## General registry-listing follow-up

- Expand both model discovery and the traditional fallback to reputable registry/company-information pages for any company, without company-specific availability rules or URLs.
- Inspect fetched HTML for the requested issuer in its title/heading and an annual-report/year label next to a download action. A model claim, a parent-page mention, or another year's accounts cannot establish a listing.
- Follow ordinary HTTP download endpoints even without `.pdf`, including single-quoted and HTML-escaped links, and keep the same PDF validation before registration.
- Return `409 report_listed` with source URL, year, title, and evidence when a listing is verified but no PDF can be downloaded and validated. Do not send listing HTML to extraction. Deduplicate source links.
- Remember verified listing URLs across legal-name aliases and recheck the live page on every reuse. Removed listings are not treated as confirmed; newly accessible PDFs can be downloaded without another model search.
- Show **Report listed — manual download needed** and an **Open report listing** link. A genuinely inconclusive search shows **Report not found automatically**, without claiming the report is unpublished.
- Use the source site's normal browser process for JavaScript verification, sign-in, or paid access. This change does not bypass those requirements or automatically download protected registry files.
- The full follow-up retained 21 successful PDF checks and retried all 14 other Wallenberg options: 6 verified manual-download listings, 4 inconclusive searches, and 4 download/access failures. Live checks found FY2025 listings for The Grand Group AB, Atlas Antibodies AB, Kivra, Nefab, Piab, and Vectura. Regression tests also cover unrelated synthetic companies, aliases, earlier fiscal years, wrong-issuer PDFs, stale retry links, and the API response.

## Validation and merge checklist

### Desktop browser-download follow-up (local, not yet published)

- Remove the cached-listing early exit: a verified listing without a PDF no longer prevents searching alternative sources on retry.
- Fix the desktop dead end caused by its blanket new-window blocking: listed reports now offer **Download and continue**, opening a dedicated sandboxed report browser without the local application's preload or settings access.
- Capture a PDF downloaded through the site's normal flow, validate its requested issuer/year and annual-accounts content, then resume the original batch item and section. The browser window remains user-operated for download buttons and any CAPTCHA; protected access is not bypassed.
- Add `/api/reports/import-download` with a 50 MB limit, provenance, content-addressed filenames, and identical-file reuse. Invalid PDFs never reach extraction; existing editions and reviews are preserved. Cancellation leaves the item ready to retry.
- The live Grand Group download exposed scanned statutory accounts: imports now run the local parser/OCR before issuer/year validation, reuse those parsed pages during registration, and preserve the original PDF bytes and OCR provenance. The same checks apply to every company.
- Live desktop verification completed for The Grand Group FY2025: 15 scanned pages imported and debt extraction returned HTTP 200 / **Done**. Borrowing maturity figures were null because the matching schedule was lease-only; those figures were correctly not substituted for borrowing maturities. Other listed companies have generic regression coverage but have not all been downloaded through the new browser flow.
- Add backend import/retry regressions, desktop download lifecycle and isolation tests, packaging coverage, and UI success/cancellation/wrong-issuer tests. Web-only clients retain manual download/upload.

Validation performed for this work:

- 49 backend regression tests covering report discovery, registry listings, browser imports including scanned accounts, source restoration, and PDF evidence.
- Existing `pipeline.test_fetch` self-check.
- 11 source-document unit tests covering table reconstruction and highlighting.
- 10 Ask source browser tests and 10 report-availability/discovery browser tests.
- 6 desktop download tests plus the desktop packaging test.
- Frontend TypeScript/production build and whitespace checks.

Commands, from their respective project directories:

```text
# backend
.venv/Scripts/python.exe -m unittest test_download_import test_report_listing test_fetch_coverage test_source_restore test_source_evidence -q
.venv/Scripts/python.exe -m pipeline.test_fetch

# frontend (Node 24; frontend/backend running for browser tests)
node --test src/components/ask/sourceDocument.test.ts
npm run e2e -- ask-source.spec.ts report-availability.spec.ts ai-discovery.spec.ts
npm run build

# desktop
node --test report-browser.test.js packaging.test.js
```

The reproducible live audit is `backend/.venv/Scripts/python.exe scripts/audit_wallenberg.py --output <audit.json>`. It performs real discovery/downloads and updates the local cache; it does not run financial model extraction. `--retry-failed` preserves successful results.

Before merging into the final version:

1. Integrate with the latest target branch and resolve overlaps in `backend/app.py`, the fetch pipeline, Ask, and the batch UI. The fixes were developed from commit `4b95dc0`; the target has newer changes.
2. Rerun the focused checks above against the merged tree, then verify an available report, a missing-original-PDF citation, and an unavailable-company result in the desktop app.
3. Build the frontend and restart the desktop backend to load the Python encoding configuration. Image-only reports need the OCR language files, which are committed under `data/tessdata` (tessdata_fast, Apache-2.0) since w214; `python scripts/setup_ocr.py` remains as the repair fallback.
4. Keep API credentials, downloaded PDFs, runtime caches, local quarantine files, and audit logs out of the release commit. Source URLs and the audit summary are included.

Knowledge-base refresh/filter UI edits in `App.tsx`, `KbView.tsx`, `useCollection.ts`, and `kb-new-reports.spec.ts` were outside the original branch's commit and are included in the latest follow-up branch.


## Local integration with main — 2026-09-22

Updated this branch from `6ee95e0` to `origin/main` at `abf5355` (110 commits) by fast-forward; main already contained the published fixes. Restored the newer uncommitted work from the retained `before-main-update-2026-09-22-local-fixes` stash. No new commit or push was made.

Resolved eight overlapping files while preserving local registry discovery, browser download/import with OCR, source evidence, and independent knowledge-base collection/refresh behavior. Retained main's workspace layout, search progress, saved-first discovery, bounded OCR and full-OCR retry, atomic PDF publishing, and stable desktop ports.

A semantic conflict also required resolution: main treated 13 private holdings as having no standalone report and blocked discovery, including Grand Group and Atlas Antibodies. Parent-report context remains available to the company map, but does not block any company's own report lookup. Issuer validation rejects a PDF explicitly titled as the parent report even when subsidiary names appear repeatedly. API documentation and regression checks reflect this behavior.

Validation: frontend production build; 49 focused backend regression tests; 16 runtime tests; collection, fetch, parse and job self-checks; 17 browser tests covering downloads, availability, new KB reports, discovery and search progress; 11 desktop tests covering downloads, packaging and stable ports. All passed. Build retains the existing large-JavaScript-chunk warning. This integration did not repeat live external website downloads or model extraction.


## Historical-year discovery — local follow-up, 2026-09-22

- Removed the 2023–2025-only UI picker. Years now range from 1900 through the current calendar year; the default follows the last completed calendar year.
- Search prompts use fiscal rather than filing/publication year, direct the selected model to historical archives and issuer-hosted alternatives, and permit explicitly labeled registration statements with audited historical accounts. Failed URLs/rejection reasons inform the archive follow-up.
- Archive crawling now reads aria-label/title attributes, small filing-row context, and year headings. It recognizes 10-K/20-F/40-F and follows financial-results/filings/archive links when a stale PDF URL returns HTML. No AMD/Circle URL or company-specific year rule was added to production code.
- An explicit report title/fiscal-year-ended declaration overrides incidental publication/comparative years. AMD's FY2023 10-K now fails a FY2024 validation request.
- Registration statements require the requested issuer in an auditor's opinion plus audited annual balance-sheet and income-statement pages for the selected year. The verified section is persisted as original PDF page numbers, bounded before another audit/interim appendix. Extraction and Ask retrieval use that section; source inspection retains the full original PDF. The alternative document type is visibly disclosed and survives reload. Importing the same filing for two audited years does not reuse the wrong year's report ID.

Live verification used the app's configured `codex / gpt-5.6-terra`, without supplying source URLs:

| Query | Result |
|---|---|
| AMD 2023 | Discovered/downloaded 175-page FY2023 10-K; 52 seconds including discovery; income-statement candidates start at original PDF p57 |
| CRCL 2024 | Discovered/downloaded 354-page final IPO prospectus; 63 seconds including discovery; audited accounts verified on original PDF pp276–327; income statement p280 |
| AMD 2022 | Discovered/downloaded 121-page annual report; 54 seconds including discovery |

AMD 2024/2025 and Circle 2025 cached PDFs still pass the revised validation. Live income-statement extraction for AMD 2023 and Circle 2024 reached the correct year and source pages. The existing majority merger returned most monetary fields as null because the two runs disagreed (EPS agreed); this separate extraction/merge limitation was not hidden or bypassed. Successful discovery does not mean every figure was extracted.

Validation: focused historical-period/import/listing/source tests, fetch self-check, runtime tests, KB/global-Ask checks, frontend production build, and 12 browser tests including the older-year picker and alternative-source notice. Existing large-bundle warning remains. Source-site access restrictions and model/search failures remain possible and are reported separately; a failed lookup never proves non-publication. These changes are included in the latest follow-up branch.
