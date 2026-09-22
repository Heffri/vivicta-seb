# Laya (`convaiinnovations/laya-multilingual`) on "applicable vs not applicable" fields

## TL;DR

**Laya does not earn its keep on this task.** Zero-shot, at its own default decision
threshold, it is indistinguishable from (very slightly worse than) always guessing "applicable":
79.6% vs the 80.6% naive baseline on held-out test reports. Calibrating a decision threshold on
the train split -- the one adaptation short of full fine-tuning that's feasible on a laptop CPU --
makes it *worse* (69.9% accuracy) because there is no real train-to-test-transferable signal to
calibrate: on the test split, the model's raw P(applicable) is on average *higher* for the
fields that are actually not-applicable (0.965) than for the fields that are actually applicable
(0.946). That is not "weak signal in the right direction" -- it is noise, and if anything points
the wrong way. Full RLCD fine-tuning (the model's own documented path to real accuracy on a new
typed-decisions task) needs a 2xT4 GPU box and ~4-5 hours per the project's own notebook; that
was out of scope for this hackathon's compute/time budget, so this is a zero-shot-plus-threshold
result, not a fine-tuned one. Take the numbers below as "zero-shot Laya isn't useful here", not
as "Laya can't be made useful here" -- those are different claims and only the first one was
tested.

## Setup

- Model: `convaiinnovations/laya-multilingual` (mmBERT-base backbone + decision head, 322M
  params, 614MB `model.safetensors`), downloaded via `laya.load()` from the Hugging Face Hub --
  clean download, no login required. One Windows-specific fix was needed: `huggingface_hub`
  tries to symlink its cache, which fails without Developer Mode/admin
  (`OSError: [WinError 1314]`) -- worked around with `HF_HUB_DISABLE_SYMLINKS=1`.
- Isolated venv at `experiments/laya/.venv` (CPU-only `torch==2.14.0+cpu`, `laya`, `transformers`,
  `huggingface_hub`). Model cache lives in `experiments/laya/.hf_cache` (not committed). No GPU on
  this machine -- everything ran on CPU, ~2.0-2.3s/forward-pass for a single `noul` question with
  ~700-800 tokens of state text (the model card's own GPU number is 32.8ms; CPU is the
  ~65x-slower path its own README warns about).
- `backend/.venv`, `eval/labels.csv`, and git were not touched. Everything lives under
  `experiments/laya/`.

## Adaptation approach

Laya's own README frames it as a "typed-decision" model: give it a state (text/JSON) and typed
questions, get typed answers with probabilities in one forward pass -- a `noul` question is
exactly a calibrated-probability boolean ("does the report state a value for this field?"). That
is the natural fit for "applicable vs not applicable" and is what the model card's own quickstart
uses, so that's what was tried, via the direct single-model SDK (`laya.load(...)`,
`agent.predict(state, questions)`).

For every one of the 367 scoreable label rows in `eval/labels.csv` (see below), one `noul`
question was built:

- **state** (`{"body": ...}`): the report's own text near where the field would appear --
  reused, read-only, the *actual* candidate-page picker the extraction pipeline uses
  (`backend/pipeline/locate.candidate_pages`, keyword/heading/table-density scoring, no LLM), run
  against the already-parsed `data/kb/<stem>/pages.jsonl` text for that report+section. Capped to
  ~3200 chars (~700-800 tokens) to fit the model's 1024-token window after the question budget.
- **question**: "Does the report state a value for the line item '{field label}' (schema key:
  {key})? Answer true if... false if the report's structure does not include this line item at
  all." plus up to 8 synonyms from the schema (`backend/schemas/income_statement.json` /
  `debt_maturity.json`). The full schema field *description* text was deliberately left out --
  some run 100+ words and would have crowded out the report text itself within the 256-token
  instruction budget; the task asked for key + label/synonyms + report text, not the full schema
  prose.

The only "adaptation" beyond prompting was picking a decision threshold for
P(applicable) on the **train split only**, then freezing it for test -- the cheap, explicitly
model-card-sanctioned move ("[base checkpoints] ship uncalibrated... over-confident... refit [a
threshold] on held-out data"). No gradient step, no fine-tuning: full RLCD fine-tuning is a
separate, much larger undertaking (see TL;DR) that this hackathon's time/compute budget did not
allow.

## Eval set

Built from `eval/labels.csv` directly (`experiments/laya/build_dataset.py`): `expected_value ==
"null"` (case-insensitive) -> target `not_applicable`; every other row (a number, always) ->
`applicable`. The 3 `nordic_industrials_2025.pdf` placeholder rows were dropped -- no
`data/kb/nordic_industrials_2025` directory exists, consistent with `eval/README.md` calling
them out as examples that "never score." That leaves **367 rows across 117 reports**: **55
not_applicable (15.0%) / 312 applicable (85.0%)** -- the ~85% naive baseline the task description
anticipated.

**Split** (`experiments/laya/make_split.py`, seed `20260922`): by **report**, not by row --
several label rows from the same report share the same context text, so a row-level split would
leak identical context between train and test. Reports were stratified on "has >=1
not_applicable row" (32/117 reports do) before a 70/30 split, so both sides get minority-class
reports:

| split | reports | rows | not_applicable | applicable | naive accuracy |
|---|---|---|---|---|---|
| train | 81 | 264 | 35 (13.3%) | 229 | 86.7% |
| test  | 36 | 103 | 20 (19.4%) | 83  | **80.6%** |

The test split's naive baseline (80.6%) differs from the overall 85.0% simply because of which
reports landed in it by chance of the stratified draw -- not cherry-picked, and reported as-is.

## Results (test split -- the only numbers that count)

| method | accuracy | precision (not_applicable) | recall (not_applicable) | tp / fp / tn / fn |
|---|---|---|---|---|
| naive, always "applicable" | 80.6% | n/a (predicts nothing as not_applicable) | 0.0% | 0/0/83/20 |
| Laya zero-shot, threshold 0.5 | 79.6% | 0.0% | 0.0% | 0/1/82/20 |
| Laya zero-shot, threshold calibrated on train (0.912) | 69.9% | 17.6% | 15.0% | 3/14/69/17 |

At the model's own default 0.5 cut, Laya is **worse than the naive baseline** (79.6% vs 80.6%) --
it predicted `not_applicable` exactly once across all 103 test rows, and that one call was wrong.
Functionally it is the naive baseline plus one extra mistake.

Sweeping the decision threshold on train to maximize F1 on the minority class lands at 0.912
(predict `not_applicable` whenever P(applicable) < 0.912 -- i.e., almost always, since the model
is extremely skewed toward "true"). Applied to test, this trades a lot of accuracy (80.6% ->
69.9%) for a recall of only 15.0% (3 of 20 actual not_applicable rows caught) at 17.6% precision
(3 of 17 `not_applicable` predictions were right). With n=20 in the positive class, "3 true
positives" is not a number to build confidence on either way -- the split is small and the
minority class is thin; this result would move a lot with a different seed.

## Why: no separating signal, badly miscalibrated

```
                    mean P(applicable)   median   n
test / applicable        0.946           0.978    83
test / not_applicable    0.965           0.992    20   <- HIGHER, not lower
train / applicable       0.911           0.953   229
train / not_applicable   0.884           0.911    35   <- lower here (what the threshold overfit to)
```

Not only is there no usable separation on held-out reports -- the fields that are actually
*not* applicable score a **higher** average P(applicable) than the ones that are. Whatever
weak, backwards-on-test pattern exists on train (0.911 vs 0.884, which is what the 0.912
threshold latched onto) does not generalize. Overall, 245/367 predictions across the whole
dataset landed in the 0.9-1.0 probability bucket -- the model is confidently saying "yes,
applicable" almost regardless of input, matching its own model card's stated limits ("ships
uncalibrated... mean confidence 0.75-0.83 against much lower accuracy" and "near chance on
typed-decisions zero-shot... treat Laya as a fast base to specialise, not a zero-shot decision
engine").

## Bottom line

On this specific task, with zero-shot prompting (the only adaptation this hackathon's CPU-only,
time-boxed setup could run), Laya-multilingual does not beat, and briefly does worse than, the
trivial always-"applicable" baseline, and has no usable train-to-test signal to calibrate a
threshold from. This matches what the model's own documentation predicts for an unfine-tuned
typed-decisions task, not a contradiction of it. A properly fine-tuned Laya checkpoint (its
documented path: build a task dataset, RLCD-train on a GPU for hours) might do better, but that
is a different, untested claim -- this write-up reports only what was actually run: **zero-shot
Laya is not useful for applicable/not-applicable field classification on this report set, full
stop.**

## Files

- `build_dataset.py` -- builds `dataset.json` from `eval/labels.csv` + `data/kb/*/pages.jsonl` (read-only reuse of `backend/pipeline/locate.py`)
- `make_split.py` -- report-level stratified train/test split -> `split.json`
- `run_laya.py` -- runs the model, one `noul` question per row -> `predictions.json`
- `score.py` -- naive baseline + threshold-0.5 + train-calibrated-threshold metrics -> `results.json`
