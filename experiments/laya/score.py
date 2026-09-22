#!/usr/bin/env python
"""Score predictions.json against split.json: naive always-"applicable" baseline vs. Laya,
at threshold 0.5 and at a threshold picked on the train split only, honestly held out on test.

Prints a full report to stdout; also writes experiments/laya/results.json with the numbers so
FINDINGS.md can quote them exactly.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def confusion(rows, pred_fn):
    """Binary confusion counts with "not_applicable" as the positive class (the interesting,
    minority one) -- pred_fn(row) -> "applicable" | "not_applicable"."""
    tp = fp = tn = fn = 0
    for r in rows:
        actual_na = r["target"] == "not_applicable"
        pred_na = pred_fn(r) == "not_applicable"
        if actual_na and pred_na:
            tp += 1
        elif not actual_na and pred_na:
            fp += 1
        elif not actual_na and not pred_na:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def metrics(rows, pred_fn):
    tp, fp, tn, fn = confusion(rows, pred_fn)
    n = tp + fp + tn + fn
    acc = (tp + tn) / n if n else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) else None
    return dict(n=n, tp=tp, fp=fp, tn=tn, fn=fn, accuracy=acc, precision_na=precision,
                recall_na=recall, f1_na=f1)


def fmt(m):
    def p(x, pct=True):
        if x is None:
            return "n/a (no predicted not_applicable)"
        return f"{100*x:.1f}%" if pct else f"{x:.3f}"
    return (f"n={m['n']}  accuracy={p(m['accuracy'])}  "
            f"[tp={m['tp']} fp={m['fp']} tn={m['tn']} fn={m['fn']}]  "
            f"precision(not_applicable)={p(m['precision_na'])}  "
            f"recall(not_applicable)={p(m['recall_na'])}")


def best_threshold(rows, metric="f1_na"):
    """Sweep thresholds over the observed train probabilities only; pick the one maximizing
    `metric` on the TRAIN split (ties broken toward the higher threshold => fewer false positives).
    Never looks at test rows."""
    candidates = sorted({r["prob_applicable"] for r in rows} | {0.5})
    best = (0.5, None)
    for th in candidates:
        pred_fn = lambda r, th=th: "not_applicable" if r["prob_applicable"] < th else "applicable"
        m = metrics(rows, pred_fn)
        score = m[metric] if m[metric] is not None else -1
        if best[1] is None or score > best[1]:
            best = (th, score)
    return best[0]


def main():
    split = load("split.json")
    preds = load("predictions.json")
    train_rows = [r for r in preds if r["stem"] in split["train_stems"]]
    test_rows = [r for r in preds if r["stem"] in split["test_stems"]]
    assert len(train_rows) + len(test_rows) == len(preds)

    naive = lambda r: "applicable"  # always predict applicable
    thresh05 = lambda r: "not_applicable" if r["prob_applicable"] < 0.5 else "applicable"

    th_star = best_threshold(train_rows, metric="f1_na")

    def thresh_star(r):
        return "not_applicable" if r["prob_applicable"] < th_star else "applicable"

    report = {
        "split": {"train_n": len(train_rows), "test_n": len(test_rows),
                  "train_reports": len(split["train_stems"]), "test_reports": len(split["test_stems"]),
                  "seed": split["seed"], "test_fraction": split["test_fraction"]},
        "train_calibrated_threshold": th_star,
        "test": {
            "naive_always_applicable": metrics(test_rows, naive),
            "laya_threshold_0.5": metrics(test_rows, thresh05),
            "laya_train_calibrated_threshold": metrics(test_rows, thresh_star),
        },
        "train_diagnostic_only": {
            "naive_always_applicable": metrics(train_rows, naive),
            "laya_threshold_0.5": metrics(train_rows, thresh05),
        },
    }

    print(f"train: {len(train_rows)} rows / {len(split['train_stems'])} reports   "
          f"test: {len(test_rows)} rows / {len(split['test_stems'])} reports   seed={split['seed']}")
    print(f"train-calibrated threshold (max F1 on not_applicable, train only): {th_star:.3f}\n")

    print("=== TEST SPLIT (the only numbers that count) ===")
    print("naive always-'applicable' baseline:")
    print("  " + fmt(report["test"]["naive_always_applicable"]))
    print("Laya zero-shot, default threshold 0.5:")
    print("  " + fmt(report["test"]["laya_threshold_0.5"]))
    print(f"Laya zero-shot, threshold calibrated on train ({th_star:.3f}):")
    print("  " + fmt(report["test"]["laya_train_calibrated_threshold"]))

    print("\n=== train split (diagnostic only, not the reported number) ===")
    print("naive: " + fmt(report["train_diagnostic_only"]["naive_always_applicable"]))
    print("Laya @0.5: " + fmt(report["train_diagnostic_only"]["laya_threshold_0.5"]))

    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
