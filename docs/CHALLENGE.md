# The challenge

**AI-Powered Annual Report Parser** — SEB, Kimberly Lejonö (Co-Head CIB Data & AI Hub)

> Corporate annual reports contain valuable business and financial information, but extracting relevant insights
> from large, unstructured PDF documents is often a manual and time-consuming process. This creates a bottleneck
> for downstream analysis and decision-making.
>
> **Your challenge:** Build a PoC for an AI-powered annual report parser that extracts key financial, strategic, and
> market insights from corporate reports and converts them into structured data. The solution should include a web
> interface and produce outputs that can be easily consumed by downstream banking systems.

Organised by 2Hero, sponsors Vivicta + Microsoft.

## Intro call with SEB — 2026-09-10 (condensed)

Condensed from memory + transcript. The verified, timestamped record is [docs/meetings/2026-09-10-seb-intro.md](meetings/2026-09-10-seb-intro.md) — where the two differ, the minutes win.

### People

| SEB side | Role | Cares about |
|---|---|---|
| Kimberly Lejonö | Co-head CIB Data & AI Hub; tech manager CIB Credits | Owns the case. Real problem they will build regardless. |
| Björn | Consultant in the Hub, agentic AI daily | **Structured + validated** output. Not "PDF into LLM and hope". |
| Pontus | Global Banking, business development | Brings end-user **Kristian** who consumes one specific note. |
| Jesper | Sopra consultant, AI platform | Bank drowns in unstructured PDFs generally → is the technique generalisable? |
| Sebastian F, Isabel | SEB / Sopra devs (agentic since Nov / Apr) | Observing. SEB will *try* to be on site for hack day + final. |

Our team: Sebastijan B (lead, frontend), Sinji Chen (backend), Borg (backend), Sara (eval/testing).

### Problem as they described it

- No central solution in the bank. Today: download from company website or email subscription → upload somewhere internal → copy/paste into whatever downstream tool. Zero automation, no shared solution.
- Many CIB AI use cases need annual-report data as an input datapoint. It's the unstructured bottleneck.
- Data is a mix of **text and numbers**. The same concept is presented differently across companies (table in one, prose in another, different labels, sv/en). Needs "intelligence" to map equivalents onto one schema. (They mentioned naming rules that "not everyone follows yet" — our reading: ESEF/XBRL.)
- Annual reports are the slow track; quarterly/monthly is another speed. We focus on annual.

### Scope guidance

- **Don't do the whole report.** Pick one section/note → unstructured → structured → visualised the way the end-user wants.
- Kristian meeting **Tue 2026-09-15 10:00–11:00** (Björn sends a Teams booking; Kristian's attendance was likely but not final on the call): we watch how he uses the data today. Exact scope is worked out after that, with SEB helping keep it small.
- Homework: read a few annual reports from the Wallenberg sphere (ABB, AstraZeneca, Atlas Copco, Saab, SEB were named; we added Investor, Ericsson, Electrolux, SKF ourselves).

### Constraints / freedoms

- Stack: free choice. Public data → cloud LLMs fine. We go local-first (Ollama) anyway; the OpenAI-compatible client swaps to hosted with env vars.
- Input: **PDF only**. Not Excel/CSV — PDFs are the trusted source.
- No sensitive data. Only GDPR item is board-member names. A future in-house version would be C2-classified — irrelevant now.
- Comms: Discord (Pontus and Kristian opt out — meetings with them go via Teams bookings). SEB will try to be on-site at hack day + final.

## Prep for Kristian, Tue 15 Sept 10:00

Bring 3–5 PDFs already skimmed (see `data/reports/`). Ask:

1. Which note / section exactly? Page reference in one report we both have open.
2. Which fields, in his words. Get the full list, then ask which 3 matter most.
3. Where do the numbers go today? Excel? Credit memo template? A system name? → tells us the export shape.
4. How many companies per year, how many years back, how often re-done?
5. Does he compare to prior year / peers? (→ compare view or not)
6. Which error hurts most: a wrong number, a missing number, or a number from the wrong period/entity?
7. Swedish, English, or both? Any IFRS vs local-GAAP differences that bite?
8. What would make him trust an automated number? (Probably: see the page. That's our provenance pane — show it.)

Same evening: write `backend/schemas/<his_note>.json` and 5 label rows in `eval/labels.csv`.
