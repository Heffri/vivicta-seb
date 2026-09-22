# Wallenberg FY2025 report-fetch audit

Checked on 22 September 2026 against the local desktop backend and all 35 options returned by Extract → Wallenberg.

**Result: 21 reports available, 13 without a verified public annual-report PDF among the sources checked, and 1 download blocked by its source site.**

## Scope

Each company was sent through the real report-fetch endpoint. Successful reports were checked for an available original PDF and nonempty debt-maturity candidate-page retrieval. Failed options were retried after fixes. Existing saved report editions were retained when their PDF checksums matched. This audit did not run full model extraction for all companies or verify every extracted financial figure.

“Unavailable” means discovery did not locate and validate a downloadable FY2025 annual PDF; it does not prove that a report does not exist. A registry copy, a report obtained directly from the company, or a different fiscal year may be needed. Uploading a PDF remains supported.

Publication policy also matters: the project owner identified Atlas Antibodies AB and Sarnova as companies that do not publish public standalone annual reports. For these companies, missing public PDFs are an expected availability limitation, not necessarily a scraper defect. This is distinct from whether statutory accounts can be obtained from a registry. The directory remains a company list, not a promise of a public report for every company and year.

## Company results

| Company | Result | PDF pages | Source / finding |
| --- | --- | ---: | --- |
| 3 Scandinavia | Unavailable | — | Unrelated Candles Scandinavia reports rejected. |
| ABB | Available | 142 | [Report PDF](https://library.e.abb.com/public/b32991481e8b4418a5c5261c5ff25440/ABB%20Financial%20Report%202025.pdf?x-sign=VUIc2%2FXU0KamNKfZuTAst4Jxc%2FFcjbcqZak4rq88pIrFaq+QhRZpHqLfH81WD9mJ) |
| AstraZeneca | Available | 232 | [Report PDF](https://www.astrazeneca.com/content/dam/az/Investor_Relations/annual-report-2025/pdf/AstraZeneca_AR_2025.pdf) |
| Atlas Antibodies | Unavailable | — | No verified standalone annual PDF found; Investor group material is not its own report. |
| Atlas Copco | Available | 174 | [Report PDF](https://www.atlascopcogroup.com/content/dam/atlas-copco/group/documents/investors/financial-publications/english/20260320-annual-report-2025-incl-sustainability-report-and-corporate-governance-report-copy-of-the-official-ESEF-format.pdf) |
| BraunAbility | Unavailable | — | No verified public FY2025 annual-report PDF found. |
| EQT | Available | 186 | [Report PDF](https://mb.cision.com/Main/87/4324934/3996686.pdf) |
| Electrolux | Available | 186 | [Report PDF](https://mb.cision.com/Main/1853/4309679/3941763.pdf) |
| Electrolux Professional | Available | 204 | [Report PDF](https://storage.mfn.se/f972ee6b-0a78-4b50-9a9c-e9c3490f0153/press-release-as-pdf.pdf) |
| Epiroc | Available | 241 | [Report PDF](https://mb.cision.com/Main/16899/4323601/3992085.pdf) |
| Ericsson | Available | 236 | [Report PDF](https://mb.cision.com/Main/15448/4316310/3963269.pdf) |
| FAM AB | Available | 84 | [Report PDF](https://fam.se/sites/default/files/2026-06/FAM_%C3%85R_2025.pdf) |
| Husqvarna | Available | 134 | [Report PDF](https://www.husqvarnagroup.com/sites/husqvarna/files/pr/202603249629-1.pdf) |
| Höganäs | Available | 118 | [Report PDF](https://www.hoganas.com/globalassets/downloads/corporate/sustainability/sustainabilty-report-2025_3710hog.pdf) |
| IPCO | Unavailable | — | Discovered pages were HTML, not report PDFs. |
| Investor AB | Available | 196 | [Report PDF](https://www.investorab.com/media/mjzjnq4d/investor_ar25_eng.pdf) |
| Kivra | Unavailable | — | Discovered pages were HTML, not report PDFs. |
| Kopparfors Skogar | Available | 48 | [Report PDF](https://kopparfors.se/wp-content/uploads/2026/03/KS_Arsredovisning_2025.pdf) |
| Laborie | Unavailable | — | No verified public FY2025 annual-report PDF found. |
| Munters | Available | 180 | [Report PDF](https://mb.cision.com/Main/15490/4319008/3975210.pdf) |
| Mölnlycke | Available | 168 | [Report PDF](https://www.molnlycke.com/globalassets/global/annual-reports/molnlycke_annual_report_2025-digital.pdf) |
| Nasdaq | Blocked (HTTP 403) | — | Official investor-relations downloads and pages returned HTTP 403. |
| Nefab | Unavailable | — | No group annual PDF verified; Nefab Danmark A/S accounts belong to a different legal entity. |
| Nova Biomedical | Unavailable | — | No verified public FY2025 annual-report PDF found. |
| Permobil | Unavailable | — | The 2025 Year-End Report was rejected because it is not an annual report. |
| Piab | Unavailable | — | No verified public FY2025 annual-report PDF found. |
| SEB | Available | 350 | [Report PDF](https://webapp.sebgroup.com/mb/mblib.nsf/alldocsbyunid/1C740093062958DDC1258DAE003DFAF7/$FILE/SEB_Annual_Report_2025_ENG.pdf) |
| SKF | Available | 163 | [Report PDF](https://cdn.skfmediahub.skf.com/api/public/096ee325b273e74a/pdf_preview_medium/SKF_ASR_2025_ENG_locked_pdf_preview_medium.pdf) |
| Saab | Available | 231 | [Report PDF](https://www.saab.com/globalassets/corporate/corporate-governance/annual-general-meeting/2026/en-post/appendix-4a---annual-and-sustainability-report-2025_new.pdf) |
| Sarnova | Unavailable | — | No standalone annual PDF verified; incorrectly matched Investor report quarantined. |
| Sobi | Available | 187 | [Report PDF](https://www.sobi.com/sites/sobi/files/pr/202603260876-1.pdf) |
| Stora Enso | Available | 225 | [Report PDF](https://mb.cision.com/Main/13589/4306573/3931241.pdf) |
| The Grand Group | Unavailable | — | No verified public FY2025 annual-report PDF found. |
| Vectura | Unavailable | — | Discovered pages were HTML, not report PDFs. |
| Wärtsilä | Available | 235 | [Report PDF](https://www.wartsila.com/docs/default-source/investors/financial-materials/annual-reports/w%C3%A4rtsil%C3%A4-annual-report-2025.pdf?sfvrsn=94090d42_3) |

## Why Atlas Antibodies failed

Discovery did not find a verified downloadable 2025 annual report belonging to Atlas Antibodies AB. Company web pages and parent-company material are insufficient: attaching Investor’s annual report would misidentify the issuer. The application now reports this as report availability, offers manual upload or another year, and exposes source-check reasons when candidates were returned.

## Fixes applied

- Accept Swedish annual-report links with unaccented “Arsredovisning” and correctly recognize combined annual and sustainability reports while retaining interim-report exclusions.
- Try verified report-index URLs before new discovery. Added official FAM, Höganäs, and Kopparfors Skogar FY2025 sources.
- Allow short annual accounts when the issuer, year, annual-report title, income statement, and balance sheet are present; reject brochures and incomplete statements.
- Check cover issuer identity more strictly, preventing parent-company, subsidiary, and similarly named company substitutions. Include collection context and known legal-name aliases in discovery and validation.
- Use UTF-8 in the desktop Python process, fixing Windows console-encoding failures for names such as Mölnlycke and Wärtsilä.
- Distinguish unavailable reports, blocked/failed downloads, and discovery-service failures. Show actionable messages and source-check details in the batch interface.
- Preserve the incorrectly matched Sarnova/Investor PDF and its audit-created knowledge-base entry in the desktop data quarantine rather than keeping it as a successful Sarnova report.

## Validation

- Live roster audit: 35/35 attempted; all 21 available PDFs returned nonempty candidate pages.
- Backend regression suite: 28 tests passed, including issuer checks, short reports, aliases, restoration, and source evidence.
- Existing fetch self-check passed.
- Five report-availability and discovery browser tests passed.
- Frontend production build passed. Targeted lint had only a pre-existing CompanySearch warning.

The reproducible audit command is `backend/.venv/Scripts/python.exe scripts/audit_wallenberg.py --output <audit.json>` with the app running. It performs real downloads/discovery and updates the local cache; it does not run financial model extraction. Use `--retry-failed` to retain successful results.

See [the branch change notes](source-evidence-report-discovery-fixes.md) for implementation scope, deployment requirements, and merge validation.
