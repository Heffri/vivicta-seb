# m03 — historical-report discovery merge and year-safety evidence

## Scope and merge result

Merged `team/codex/historical-report-discovery-fixes` (`4c94188`) into the then-current
Acrylic tree, then merged the latest Acrylic delivery (`44fdd64`, committed OCR language
resources). The historical branch's report-period verification, archive/listing discovery,
manual browser download path, registration-statement scope, and KB refresh changes are present.

The four textual conflicts were resolved additively:

- `backend/app.py`: retain bounded OCR and bilingual-twin candidate recovery, while masking
  registration-statement pages to their verified audited-account range before candidate discovery
  and after an OCR top-up.
- `UploadView.tsx`, `BatchProgress.tsx`, and `useBatch.ts`: retain **Extract again** and
  section-reset behavior alongside the new browser **Download and continue** flow.

## Old fiscal years — red then green

The teammate implementation correctly adds the historical-year prompt, explicit fiscal-period
parsing, audited registration-statement fallback, and exact-year saved discovery. It did **not**
block one remaining silent wrong-year path: its `_period_re()` still accepted an unattached body
phrase such as `In fiscal year 2023`.

A focused regression was added to `pipeline.test_fetch` before changing the implementation. It
served a 2026 report whose body merely said `In fiscal year 2023`; the pre-fix route accepted it
and published it successfully for a 2023 request. The test failed at:

```text
AssertionError: a buried bare fiscal-year phrase must not publish a wrong-year report
```

The final `_year_ok()` accepts a bare fiscal-year phrase only if it is immediately followed by an
ISO-style month/day date continuation. Full written date-range forms are unchanged. The regression
also verifies that a rejected PDF writes its precise reason to the `verify` job event, and that a
valid `financial year 2023-04-01-2024-03-31` period remains accepted.

After the change, the same route rejected the stray-year report with:

```text
2023 not on the first 3 pages and no accounting period for it
```

The six live-provider probes requested in the late recording timebox were not completed before the
handoff. The deterministic regression exactly reproduces the previously silent publish condition;
no real-provider claim is made here.

## Debt comparison

| Item | Existing Acrylic behavior | Historical branch behavior | Retained result |
| --- | --- | --- | --- |
| v186 | Parent-note continuation and lease-only schedule predicates | No overlapping predicate edit | Existing guards and tests retained. |
| w203 | Debt schema synonym coverage and sweep fixtures | No overlap | Existing schema/tests retained. |
| w208 | NVIDIA/AMD/Volvo guarded readers | No overlap | Existing readers and tests retained. |
| w209 | Bounded OCR, including exact Swedish-twin ranking | `app.py` period masking could overlap candidate text | Both: bounded OCR remains, and historical filings locate only verified account pages. |
| w210 | Section reset and Extract again | Browser download/retry state touches the same batch components | Both actions remain, with their state kept independent. |

## Existing feature retention

Static integration assertions and the required backend gates confirm all ten named retained paths:
three-way batch concurrency/reset, Extract again, saved-first/force-web discovery, app-level search
trace, KB poll stop/backoff, types, bounded OCR recovery, and the retained debt guards/readers.

## Verification

- Red: focused `pipeline.test_fetch` regression failed before the bare-period guard.
- Green: focused `pipeline.test_fetch` passed after the guard; it includes the new job-trace and
  dated-period counterexample.
- Backend: 19 self-check modules passed: 13 `pipeline.*` modules plus six root modules.
- `npm run build`: passed.
- `npm run lint`: exit 0 with 13 pre-existing advisory warnings.
- Per the recording fast path, no full browser suite or live-provider comparison was run.

## Reference

The UAW demo tree was inventoried for report/history/discovery and acrylic implementation patterns.
Its acrylic token file remains the visual reference; no applicable report-discovery code was copied.