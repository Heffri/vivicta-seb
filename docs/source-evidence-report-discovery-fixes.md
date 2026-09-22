# Source evidence and report discovery fixes

Branch: `codex/source-evidence-report-discovery-fixes`

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

Some companies do not publish public standalone annual reports. The project owner specifically identified Atlas Antibodies AB and Sarnova. Their missing public PDFs should be understood as a publication limitation, not automatically a scraper defect; registry accounts and parent-group reporting are separate sources. The directory does not guarantee that every company has a downloadable annual report for every year.

The FY2025 audit attempted all 35 Wallenberg options: **21 original PDFs available with nonempty debt-maturity candidate pages, 13 without a verified public standalone annual PDF, and Nasdaq blocked by HTTP 403**. These are report-fetch and candidate-page checks, not full financial extraction for every company. See [all company results and sources](wallenberg-report-audit-2025.md).

The incorrectly matched Sarnova/Investor report created during the local audit was moved to a local quarantine. That cache repair is not a repository migration and is not shipped as report data.

## Validation and merge checklist

Validation performed for this work:

- 28 backend regression tests covering report discovery, source restoration, and PDF evidence.
- Existing `pipeline.test_fetch` self-check.
- 11 source-document unit tests covering table reconstruction and highlighting.
- 10 Ask source browser tests and 5 report-availability/discovery browser tests.
- Frontend TypeScript/production build and whitespace checks.

Commands, from their respective project directories:

```text
# backend
.venv/Scripts/python.exe -m unittest test_fetch_coverage test_source_restore test_source_evidence -q
.venv/Scripts/python.exe -m pipeline.test_fetch

# frontend (Node 24; frontend/backend running for browser tests)
node --test src/components/ask/sourceDocument.test.ts
npm run e2e -- ask-source.spec.ts report-availability.spec.ts ai-discovery.spec.ts
npm run build
```

The reproducible live audit is `backend/.venv/Scripts/python.exe scripts/audit_wallenberg.py --output <audit.json>`. It performs real discovery/downloads and updates the local cache; it does not run financial model extraction. `--retry-failed` preserves successful results.

Before merging into the final version:

1. Integrate with the latest target branch and resolve overlaps in `backend/app.py`, the fetch pipeline, Ask, and the batch UI. The fixes were developed from commit `4b95dc0`; the target has newer changes.
2. Rerun the focused checks above against the merged tree, then verify an available report, a missing-original-PDF citation, and an unavailable-company result in the desktop app.
3. Build the frontend and restart the desktop backend to load the Python encoding configuration. Image-only reports require OCR language files installed with `python scripts/setup_ocr.py`; those downloaded files are not committed.
4. Keep API credentials, downloaded PDFs, runtime caches, local quarantine files, and audit logs out of the release commit. Source URLs and the audit summary are included.

Separate uncommitted knowledge-base refresh/filter UI edits in `App.tsx`, `KbView.tsx`, `useCollection.ts`, and `kb-new-reports.spec.ts` are outside this branch's commit.
