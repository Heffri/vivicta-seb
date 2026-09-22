# Wallenberg FY2025 report-fetch audit

Checked on 22 September 2026 against the local desktop backend and all 35 options returned by Extract → Wallenberg.

**Updated result: 22 PDFs available, 5 verified report listings awaiting download, 4 inconclusive searches, and 4 download/access failures.** The registry follow-up retried all 14 initially unsuccessful options, retaining the original 21 PDFs. A subsequent desktop browser-download test obtained and validated The Grand Group's 15-page scanned FY2025 report. Other registry listings have not yet been tested through that new download flow.

## Scope

Each company was sent through the real report-fetch endpoint. Successful reports were checked for an available original PDF and nonempty debt-maturity candidate-page retrieval. Failed options were retried after fixes. Existing saved report editions were retained when their PDF checksums matched. This audit did not run full model extraction for all companies or verify every extracted financial figure.

“Unavailable” means discovery did not locate and validate a downloadable FY2025 annual PDF; it does not prove that a report does not exist. A registry copy, a report obtained directly from the company, or a different fiscal year may be needed. Uploading a PDF remains supported.

Publication policy also matters: some companies do not publish standalone reports on their own websites, while statutory accounts may be available through registry services. The directory remains a company list, not a promise of a direct PDF for every company and year. Do not infer non-publication from a failed search.

**Registry follow-up:** broader live discovery on 22 September 2026 verified FY2025 annual-account listings for both [The Grand Group AB](https://www.hitta.se/f%C3%B6retagsinformation/-/5563029650) and [Atlas Antibodies AB](https://www.hitta.se/f%C3%B6retagsinformation/atlas+antibodies+ab/5566828082). The desktop now offers **Download and continue** for browser-only sources. The Grand Group's actual PDF was subsequently downloaded through Hitta's normal button, OCR-read on all 15 pages, issuer/year validated, and registered with its original bytes intact. Its debt extraction resumed automatically. Atlas Antibodies remains a verified listing without a tested PDF import. This corrects the earlier assumption that Atlas Antibodies had no public annual accounts.

## Company results

| Company | Result | PDF pages | Source / finding |
| --- | --- | ---: | --- |
| 3 Scandinavia | Not found automatically | — | Discovery did not verify a FY2025 PDF or listing; publication status remains unknown. |
| ABB | Available | 142 | [Report PDF](https://library.e.abb.com/public/b32991481e8b4418a5c5261c5ff25440/ABB%20Financial%20Report%202025.pdf?x-sign=VUIc2%2FXU0KamNKfZuTAst4Jxc%2FFcjbcqZak4rq88pIrFaq+QhRZpHqLfH81WD9mJ) |
| AstraZeneca | Available | 232 | [Report PDF](https://www.astrazeneca.com/content/dam/az/Investor_Relations/annual-report-2025/pdf/AstraZeneca_AR_2025.pdf) |
| Atlas Antibodies | Listed; manual download | — | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/atlas+antibodies+ab/5566828082); PDF contents not yet verified. |
| Atlas Copco | Available | 174 | [Report PDF](https://www.atlascopcogroup.com/content/dam/atlas-copco/group/documents/investors/financial-publications/english/20260320-annual-report-2025-incl-sustainability-report-and-corporate-governance-report-copy-of-the-official-ESEF-format.pdf) |
| BraunAbility | Not found automatically | — | Discovery did not verify a FY2025 PDF or listing; publication status remains unknown. |
| EQT | Available | 186 | [Report PDF](https://mb.cision.com/Main/87/4324934/3996686.pdf) |
| Electrolux | Available | 186 | [Report PDF](https://mb.cision.com/Main/1853/4309679/3941763.pdf) |
| Electrolux Professional | Available | 204 | [Report PDF](https://storage.mfn.se/f972ee6b-0a78-4b50-9a9c-e9c3490f0153/press-release-as-pdf.pdf) |
| Epiroc | Available | 241 | [Report PDF](https://mb.cision.com/Main/16899/4323601/3992085.pdf) |
| Ericsson | Available | 236 | [Report PDF](https://mb.cision.com/Main/15448/4316310/3963269.pdf) |
| FAM AB | Available | 84 | [Report PDF](https://fam.se/sites/default/files/2026-06/FAM_%C3%85R_2025.pdf) |
| Husqvarna | Available | 134 | [Report PDF](https://www.husqvarnagroup.com/sites/husqvarna/files/pr/202603249629-1.pdf) |
| Höganäs | Available | 118 | [Report PDF](https://www.hoganas.com/globalassets/downloads/corporate/sustainability/sustainabilty-report-2025_3710hog.pdf) |
| IPCO | Not found automatically | — | Discovery did not verify a FY2025 PDF or listing; publication status remains unknown. |
| Investor AB | Available | 196 | [Report PDF](https://www.investorab.com/media/mjzjnq4d/investor_ar25_eng.pdf) |
| Kivra | Listed; manual download | — | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/kivra%2Bab/5568402266); PDF contents not yet verified. |
| Kopparfors Skogar | Available | 48 | [Report PDF](https://kopparfors.se/wp-content/uploads/2026/03/KS_Arsredovisning_2025.pdf) |
| Laborie | Not found automatically | — | Discovery did not verify a FY2025 PDF or listing; publication status remains unknown. |
| Munters | Available | 180 | [Report PDF](https://mb.cision.com/Main/15490/4319008/3975210.pdf) |
| Mölnlycke | Available | 168 | [Report PDF](https://www.molnlycke.com/globalassets/global/annual-reports/molnlycke_annual_report_2025-digital.pdf) |
| Nasdaq | Download/access failure | — | Source requests failed or were blocked; no PDF or listing verified. This does not establish publication status. |
| Nefab | Listed; manual download | — | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/nefab%2Bab/5562268143); PDF contents not yet verified. |
| Nova Biomedical | Download/access failure | — | Source requests failed or were blocked; no PDF or listing verified. This does not establish publication status. |
| Permobil | Download/access failure | — | Source requests failed or were blocked; no PDF or listing verified. This does not establish publication status. |
| Piab | Listed; manual download | — | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/piab%2Bgroup%2Bab/5591562599); PDF contents not yet verified. |
| SEB | Available | 350 | [Report PDF](https://webapp.sebgroup.com/mb/mblib.nsf/alldocsbyunid/1C740093062958DDC1258DAE003DFAF7/$FILE/SEB_Annual_Report_2025_ENG.pdf) |
| SKF | Available | 163 | [Report PDF](https://cdn.skfmediahub.skf.com/api/public/096ee325b273e74a/pdf_preview_medium/SKF_ASR_2025_ENG_locked_pdf_preview_medium.pdf) |
| Saab | Available | 231 | [Report PDF](https://www.saab.com/globalassets/corporate/corporate-governance/annual-general-meeting/2026/en-post/appendix-4a---annual-and-sustainability-report-2025_new.pdf) |
| Sarnova | Download/access failure | — | Source requests failed or were blocked; no PDF or listing verified. This does not establish publication status. |
| Sobi | Available | 187 | [Report PDF](https://www.sobi.com/sites/sobi/files/pr/202603260876-1.pdf) |
| Stora Enso | Available | 225 | [Report PDF](https://mb.cision.com/Main/13589/4306573/3931241.pdf) |
| The Grand Group | Available via desktop browser download | 15 | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/-/5563029650); real PDF downloaded, OCR on all 15 pages, issuer/year validated. |
| Vectura | Listed; manual download | — | [FY2025 report listing](https://www.hitta.se/f%C3%B6retagsinformation/vectura%2Bfastigheter%20ab/5569030587); PDF contents not yet verified. |
| Wärtsilä | Available | 235 | [Report PDF](https://www.wartsila.com/docs/default-source/investors/financial-materials/annual-reports/w%C3%A4rtsil%C3%A4-annual-report-2025.pdf?sfvrsn=94090d42_3) |

The registry follow-up also verified Kivra, Nefab, Piab, and Vectura. Eight final API checks, including legal-name variants for Atlas Antibodies and The Grand Group, each returned one source link after a fresh HTML check in 0.4–3.7 seconds. Source URLs are cached locally and revalidated; report contents are not inferred from a listing.

The later desktop Grand Group test completed `/import-download` and `/extract` with HTTP 200 and showed **Done**. Its borrowing maturity fields were null: the retrieved schedule on page 10 was explicitly operating leases, and the borrowing extractor refused to substitute those amounts. Completion verifies download/OCR/extraction execution, not that every requested section exists. Original PDF SHA-256: `fc96ae5753e020bf667fc165d1e808b0a457ed42740e4cae00904c61329af3cc`.

## Why Atlas Antibodies failed

The initial discovery restricted sources to issuer/official filing pages and did not find Atlas Antibodies AB's registry listing. The broader follow-up found its 2025 statutory accounts on Hitta. The application now identifies this as a verified listing needing a manual download, rather than an unknown publication status. Company web pages and parent-company material are insufficient as financial sources: attaching Investor’s annual report would misidentify the issuer.

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
- Backend regression suite: 49 tests passed, including issuer checks, short reports, aliases, browser imports/OCR, restoration, and source evidence.
- Existing fetch self-check passed.
- Ten report-availability and discovery browser tests passed, including generic registry listings, download/resume, cancellation, wrong-issuer rejection, and clearing source links on retry. Six desktop download lifecycle/isolation tests and the packaging check passed.
- Frontend production build passed. Targeted lint had only a pre-existing CompanySearch warning.

The reproducible audit command is `backend/.venv/Scripts/python.exe scripts/audit_wallenberg.py --output <audit.json>` with the app running. It performs real downloads/discovery and updates the local cache; it does not run financial model extraction. Use `--retry-failed` to retain successful results.

See [the branch change notes](source-evidence-report-discovery-fixes.md) for implementation scope, deployment requirements, and merge validation.
