# Debt selection and review layout validation

Validated on 2026-09-21 against baseline `370fb4d`.

AAK's two-pass model selected the borrowing note on PDF pages 169–170, but
post-processing still searched the original top-ranked liquidity/lease pages
145–146 for missing values. The repair now starts from the selected note.
Stacked Group/Parent headings with repeated year pairs are treated as a shared
column header; separate Parent-only sections remain excluded. Missing debt
units can use an explicit report-wide amounts declaration, with its page logged.
Conflicting declarations remain unresolved.

A fresh `gpt-5.6-terra` Codex run (default low reasoning, two-pass enabled,
few-shot examples disabled) selected pages 169–170. Its raw answer contained
current borrowings 4,088, 1–5 years zero, and over five years 390. It left total
and units null. Post-processing derived 4,478 from the same note's current and
non-current subtotals and used the explicit SEK million declaration on page 136.
The maturity check passed: 4,088 + 0 + 390 = 4,478. This borrowing-note scope
excludes separately disclosed leases; it does not establish total debt including
leases or replace human confirmation of definitions.

Validation:

- Dedicated debt regression: selected-page repairs, AAK values and source pages,
  printed zero, both entity column orders, Parent-only rejection, ambiguous units.
- Existing confidence regression suite passed.
- Stored-output replay: 206 replayable extractions unchanged versus baseline;
  absent section combinations and one entry without candidate pages were skipped.
  This is a regression comparison, not fresh model accuracy measurement.
- Nine Edge tests passed: review scrolling at 1440px and 900px, basis review and
  comparison in both themes, shared collection navigation, review grouping,
  Libraries.dev orb themes, stop/retry, citations, and reduced motion without WebGL.
- Frontend production build passed.

The first installed-app extraction exposed an additional PDF parsing issue:
the freshly downloaded PDF's navigation sidebar was merged into financial rows,
so the printed dash was dropped. The parser now separates a navigation rail only
when at least five distinct internal link destinations, a tall left-edge column,
and an empty gutter prove its layout. All text is retained. The parser version
is incremented so locally cached PDFs are reparsed. Synthetic sidebar and normal
table counterexamples, plus the existing parser suite, pass.

The review shell stays fixed to the viewport, with navigation scrolling only the
content pane. The orb uses `thinking-orbs` 0.3.1, replacing the ElevenLabs shader
and Three.js dependency. The installed app must be updated before those changes
are available in its window. Previously cached extractions require re-extraction
to benefit from the debt fixes; reviewed results are protected by the existing API.
