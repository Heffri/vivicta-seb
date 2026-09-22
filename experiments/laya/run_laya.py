#!/usr/bin/env python
"""Run convaiinnovations/laya-multilingual zero-shot on the applicable-vs-not-applicable task.

Adaptation approach (per the model's own README/model card): Laya is a "typed-decision" model --
give it a state dict and typed questions, it returns typed answers with calibrated-ish
probabilities in one forward pass. For a fresh binary task the model card's own quickstart pattern
is a single `noul` (boolean-probability) question per item, so that's what this script does: one
noul question per label row, phrased around the field's key/label/synonyms from the schema, with
"body" = the report's own text near where the field would appear (context_text from
build_dataset.py, picked by the real pipeline's candidate-page locator).

Full RLCD fine-tuning (the model's documented path to real accuracy on a new typed-decisions task)
needs the project's own Kaggle notebook, 2xT4 GPUs and ~4-5 hours for ~30k questions -- not
reproducible against a 367-row dataset on a laptop CPU in a hackathon's time budget. What *is*
cheap and is explicitly sanctioned by the model's own "Honest limits" section ("[base checkpoints
are] near chance ... zero-shot"; calibration should be "refit ... on held-out data") is picking a
decision threshold on the raw noul probability using the train split, then freezing it for test.
That's the only "adaptation" this script does beyond prompting -- there is no gradient step
anywhere in this file.

Usage: .venv/Scripts/python.exe experiments/laya/run_laya.py
Writes experiments/laya/predictions.json: [{..every dataset.json field.., "prob_applicable": float}]
"""
import json
import os
import sys
import time

os.environ.setdefault("USE_TF", "0")  # avoid the TF-probe deadlock the model card warns about
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("HF_HOME", os.path.join(HERE, ".hf_cache"))  # keep the 614MB checkpoint inside experiments/laya
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")  # Windows without dev mode/admin can't symlink the HF cache
DATASET_PATH = os.path.join(HERE, "dataset.json")
OUT_PATH = os.path.join(HERE, "predictions.json")

MAX_SYNONYMS_IN_PROMPT = 8


def build_instructions(row):
    # Order matters: the decision head's instructions get truncated to whatever token budget is
    # left after the (tiny) true/false option markers -- see build_sequence in laya/common.py. Put
    # the question + the true/false answer criteria first so they always survive truncation; the
    # synonym list (least essential, and sometimes long for debt_maturity fields) goes last so it
    # is what gets cut if the field's label/key pushes past the budget. field_description is
    # intentionally left out -- some schema descriptions run to 100+ words, which would crowd out
    # the report text itself; the task calls for key + label/synonyms + report text, not the full
    # schema prose.
    syn = row["synonyms"][:MAX_SYNONYMS_IN_PROMPT]
    syn_txt = f" Synonyms/labels this line item may appear under: {', '.join(syn)}." if syn else ""
    return (
        f"Annual report excerpt ({row['section'].replace('_', ' ')}). Does the report state a value "
        f"for the line item '{row['field_label']}' (schema key: {row['key']})? Answer true if this "
        f"report's own statement/table prints such a line (including a zero/nil value stated in "
        f"words); answer false if the report's structure does not include this line item at all."
        f"{syn_txt}"
    )


def main():
    import laya

    with open(DATASET_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    print(f"loading convaiinnovations/laya-multilingual ...", flush=True)
    t0 = time.time()
    agent = laya.load("convaiinnovations/laya-multilingual")
    print(f"loaded in {time.time()-t0:.1f}s", flush=True)

    out = []
    t0 = time.time()
    for i, row in enumerate(rows):
        state = {"body": row["context_text"]}
        questions = {
            "applicable": {
                "type": "noul",
                "instructions": build_instructions(row),
            }
        }
        result = agent.predict(state, questions)
        prob = result["answers"]["applicable"]["noul"]
        out.append({**row, "prob_applicable": prob})
        if (i + 1) % 25 == 0 or i + 1 == len(rows):
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(rows)} rows, {elapsed:.1f}s elapsed, "
                  f"{elapsed/(i+1)*1000:.0f} ms/row", flush=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
