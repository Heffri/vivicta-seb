#!/usr/bin/env python
"""Report-level train/test split of experiments/laya/dataset.json.

Splitting by report (stem), not by row: several label rows from the same report share the same
context_text (built per report+section), so a row-level split would leak identical context
between train and test. 32/117 reports contain at least one "not_applicable" row; the other 85
are all-"applicable". Stratifying the split on that (has_na) flag keeps both the train split
(used only to pick a decision threshold on Laya's raw probability -- no gradient fine-tuning) and
the test split (the only split any accuracy number is reported on) supplied with a mix of
the minority class instead of risking a test split with zero not_applicable reports.

Deterministic (fixed seed), so the split is reproducible and can be printed in FINDINGS.md.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(HERE, "dataset.json")
OUT_PATH = os.path.join(HERE, "split.json")
SEED = 20260922
TEST_FRACTION = 0.30


def main():
    with open(DATASET_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    stems = sorted({r["stem"] for r in rows})
    na_stems = sorted({r["stem"] for r in rows if r["target"] == "not_applicable"})
    plain_stems = sorted(set(stems) - set(na_stems))

    rng = random.Random(SEED)
    rng.shuffle(na_stems)
    rng.shuffle(plain_stems)

    def split(lst):
        k = round(len(lst) * TEST_FRACTION)
        return lst[k:], lst[:k]  # train, test

    na_train, na_test = split(na_stems)
    plain_train, plain_test = split(plain_stems)

    train_stems = set(na_train) | set(plain_train)
    test_stems = set(na_test) | set(plain_test)
    assert not (train_stems & test_stems)
    assert train_stems | test_stems == set(stems)

    train_rows = [r for r in rows if r["stem"] in train_stems]
    test_rows = [r for r in rows if r["stem"] in test_stems]

    def summarize(name, rs, sts):
        na = sum(1 for r in rs if r["target"] == "not_applicable")
        print(f"{name}: {len(sts)} reports, {len(rs)} rows, {na} not_applicable "
              f"({100*na/len(rs):.1f}%), {len(rs)-na} applicable")

    summarize("train", train_rows, train_stems)
    summarize("test", test_rows, test_stems)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "seed": SEED,
            "test_fraction": TEST_FRACTION,
            "train_stems": sorted(train_stems),
            "test_stems": sorted(test_stems),
        }, f, indent=1)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
