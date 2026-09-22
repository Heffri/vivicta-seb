# Historical report discovery: merge handoff

Branch: `codex/historical-report-discovery-fixes`

Base: `abf5355` from main. This branch contains the local follow-up fixes described below. Earlier Ask evidence formatting, keyword/number highlighting, and annotated PDF downloads are already in the base. Publishing this branch does not merge or push main.

## Changes included

- **Historical years:** the year selector supports 1900 through the current calendar year and defaults to the last completed year. Discovery asks the configured model for the fiscal year, searches archives and issuer-hosted alternatives, and supplies failed candidate URLs and validation reasons to follow-up searches.
- **Archive navigation:** recognize 10-K, 20-F and 40-F links, including numeric PDF filenames with useful accessibility labels, nearby filing-row text or year headings. Follow financial-results and filing archives when an old PDF URL returns a listing page. These rules apply across companies without hardcoded AMD or Circle URLs.
- **Correct-year verification:** explicit fiscal-year declarations take precedence over incidental publication and comparative years. A FY2023 report cannot pass as FY2024 merely because it was filed in 2024.
- **Audited historical accounts:** allow a registration statement/prospectus when the requested issuer and year are verified in an audit opinion and annual financial statements. Clearly disclose that it is not a standalone annual report. Persist the verified section and restrict extraction and Ask retrieval to it while preserving original PDF page numbers and the full original source. Reusing one filing for multiple years retains separate report identities.
- **Registry listings:** verify company identity, year and report-download action in the listing HTML. Recheck cached listings and continue looking for downloadable alternatives. Distinguish a verified listing requiring manual access from an unsuccessful lookup or a download error; failure to find a report does not establish that the company never publishes one.
- **Private holdings:** remove the blanket discovery block based on parent-report mappings. Seek each company's own accounts while retaining issuer checks that reject a parent's report as a substitute.
- **Desktop downloads:** open a dedicated report browser so the user can complete the site's normal download process. Capture and validate the PDF, import it with OCR when needed, and resume extraction. Validate issuer/year, enforce size limits, clean temporary downloads, and handle cancellation and errors. Package the new browser module with the desktop app.
- **Knowledge base:** refresh after new reports arrive, expose a manual refresh action, and keep its collection filter independent of Extract with a clear way to show all saved reports.
- **Main integration:** retain main's workspace layout, search progress, saved-first discovery, bounded OCR/retry, atomic PDF publishing and stable desktop ports while resolving overlaps with these local fixes.

## Verification

The final historical-report changes passed 61 focused backend tests, the fetch self-check, 16 runtime tests, KB/global-Ask checks, a frontend production build, and 12 browser tests covering historical years, availability and discovery. The preceding main integration also passed 17 browser tests and 11 desktop tests covering report downloads, packaging and ports. The existing frontend large-bundle warning remains.

Live discovery used the app's configured `codex / gpt-5.6-terra` without supplying known source URLs:

| Request | Verified result |
|---|---|
| AMD 2023 | 175-page FY2023 10-K; income-statement candidates start at original PDF page 57 |
| AMD 2022 | 121-page annual report |
| CRCL 2024 | 354-page final IPO prospectus; audited annual accounts scoped to original PDF pages 276–327, with the alternative document type disclosed |
| Grand Group 2025 | Website download/import of a 15-page scanned report, OCR and extraction completed |

Cached AMD 2024/2025 and Circle 2025 reports also passed revised validation. Circle's persisted historical scope was checked after backend restart, and its Ask chunks remained within the verified section.

## Known limits for review

Live AMD 2023 and Circle 2024 income-statement extraction reached the correct year and pages, but the existing two-run majority merger returned most monetary fields as null when runs disagreed; EPS agreed. That separate extraction/merge issue remains unresolved. Grand Group's tested debt section did not supply the requested debt fields. Discovery success does not imply every requested financial field is present or extracted.

Website restrictions, unavailable reports and model/search failures remain possible. Historical audited-account detection is conservative; the app should report uncertainty rather than substitute the wrong company or year. Downloaded PDFs, credentials, caches and runtime logs are excluded from this branch.

See [the detailed development notes](source-evidence-report-discovery-fixes.md) and [API contracts](API.md) for implementation and validation history.
