"""Mechanism-only replay: extract() on the model-selected pages with the model's values nulled.

    python scripts/mechanism_only.py --kb data/kb --section debt_maturity
    python scripts/mechanism_only.py --variant total                    # only total_debt keeps the model's stored answer
    python scripts/mechanism_only.py --pages locate                     # window from the deterministic locator, not the model's selection
    python scripts/mechanism_only.py --only academedia_2025 --out replay.md --csv fields.csv

The question (reruns of the same model move values, so model variance is the largest residual): if
the model's four answers are thrown away and only extract()'s deterministic mechanisms read the
pages the model picked, what survives?  It measures how much of the accuracy the rules alone carry,
and so how far a "table-first, model-picks-the-page" mode could go.

For every <kb>/<stem>/extractions/<section>.json the stored fields are -- as in scripts/replay_check.py
and scripts/publish_kb.py -- fed back as the model's own answer (MODEL_KEYS only; confidence/evidence
are post-processing output extract() derives itself), then the numbers are stripped: the --variant
mechanism answer keeps each schema field's key and label (the shape the model is handed and answers
through) with value/unit/period/raw_label/source all null; the --variant total answer keeps the stored
total_debt field verbatim (the field the model is best at; the buckets are where the instability lives)
and nulls the rest.  call_llm is stubbed -- zero model calls.  What can still write is exactly the
machinery that fires on null: the statement-spread null fill, _fill_bucket_columns' null fills,
_finer_split_rows, _subtotal_pair_fill, the on-null window family, _stated_zero/printed-nil,
_between_rows, _date_bucket_derive -- each gated as hard as it is in production, so a mechanism-only
hit is a value the rules alone can prove.

The replay window is publish_kb's own construction (imported, not re-derived): the two_pass selection
recorded in the stored warnings -- what the original run received as `pages`, selection first -- UNION
the stored fields' cited pages.  --pages locate swaps it for pipeline.locate.candidate_pages' ranking
(the deterministic locator standing in for the model at page-pick too): the sensitivity check on how
much the result depends on the model's own page choice.

Scored per field against (a) eval/labels.csv through eval/run.py's own values_match/page_match -- the
same predicates -- and (b) the stored record itself (the model+mechanism baseline): same (repr-equal),
lost (stored non-null -> null), found (stored null -> non-null), different (both non-null, unequal).
Per field the run's own warnings are mapped to its writer by scripts/eval_breakdown.py's vocabulary.
Per stem a shape class comes from the STORED record's markers (which repair family the original run
used -- prose-zero > subtotal-pair > finer-rows > bucket-column > window/date/between-rows >
derived-total > rollforward > statement-fill > lease/refused > plain bucket rows), so the mechanism-only
hit rate can be read per company shape.

A null answer has one honest consequence this script does not hide: with no model citation, a
mechanism's page walk is pages[:2] only (the selection), where the stored run also walked the pages the
model itself cited mid-run.  The cited pages still sit in the `pages` list (position 3+), so widening
paths see them; the [:2] walks do not.  That is the table-first world as it would actually run.
"""
import argparse
import copy
import json
import os
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))
os.environ.pop("EXTRACT_TWO_PASS", None)  # the window below already is the recorded selection
os.environ["FEWSHOT"] = "0"  # the rendered prompt is discarded by the stub; skip the fewshot disk scan
from pipeline import extract  # noqa: E402
from pipeline.extract import _identity_parts  # noqa: E402
from pipeline.locate import candidate_pages  # noqa: E402
from publish_kb import load_texts, mask_user_paths, replay_pages  # noqa: E402 -- the same window construction, imported not diverged
from run import load_labels, values_match  # noqa: E402 -- eval/run.py's own scoring predicate, byte-aligned
from eval_breakdown import likely_writer, relevant_warnings  # noqa: E402 -- the established warning-vocabulary mapping

MODEL_KEYS = ("key", "label", "value", "unit", "period", "raw_label", "source")

# Shape of the original stored read, from the repair family its own record names.  First match is the
# primary class; every match is kept as a tag (a stem can be two things).  prose-zero has no warning
# vocabulary -- it is an evidence bit (stated_zero) on a field.
_SHAPE_MARKERS = (
    ("subtotal-pair", re.compile(r"section subtotals on page|current-section Summa")),
    ("finer-rows", re.compile(r"finer-split")),
    ("bucket-column", re.compile(r"by its column order|column reading")),
    ("window-rows", re.compile(r"derived as the sum of")),
    ("date-rows", re.compile(r"sums by maturity date")),
    ("between-rows", re.compile(r"sits between the other rows")),
    ("derived-total", re.compile(r"it is the sum of|sums to")),
    ("rollforward", re.compile(r"roll-forward")),
    ("statement-fill", re.compile(r"filled from page")),
    ("lease-refused", re.compile(r"(?i)refused[^|]*lease|lease[^|]*refused")),
    ("refused-scope", re.compile(r"refused")),
)


def stored_shape(ext: dict, bucket_keys: set[str]) -> tuple[str, list[str]]:
    """(primary, tags): the repair families the stored record's own markers name; default splits by
    whether the stored record holds bucket reads at all -- >=2 non-null buckets is the plain note
    shape (one printed row per bucket, the model's direct read, no repair involved), fewer is a
    total-only shape (a balance-sheet total, a bank's liability rows, a lease table the model
    declined to read buckets from: the buckets were null before any repair)."""
    ws = " | ".join(str(w) for w in ext.get("warnings") or [])
    tags = [name for name, rx in _SHAPE_MARKERS if rx.search(ws)]
    if any("stated_zero" in (f.get("evidence") or []) for f in ext.get("fields", [])):
        tags.insert(0, "prose-zero")
    if not tags:
        nb = sum(1 for f in ext.get("fields", []) if f.get("key") in bucket_keys and f.get("value") is not None)
        return ("bucket-rows" if nb >= 2 else "total-only"), []
    return tags[0], tags[1:]


def model_answer(schema: dict, keep: list[dict]) -> list[dict]:
    """The model-side shape: the kept fields verbatim (MODEL_KEYS), every other schema field holding
    only its key and label -- the numbers are gone, the shape the model answers through is not."""
    kept = {f["key"]: {k: f.get(k) for k in MODEL_KEYS} for f in keep}
    return [kept.get(sf["key"]) or {"key": sf["key"], "label": sf["label"], "value": None, "unit": None,
                                    "period": None, "raw_label": None, "source": None}
            for sf in schema["fields"]]


def replay(answer: list[dict], texts: list[str], pages: list[int], schema: dict, report_meta: dict) -> dict:
    # fresh deep copy per call: extract() mutates the model answer's source dicts in place
    # (src["quote"] = verified) -- a stored field must enter every run pristine (replay_check's reason).
    extract.call_llm = lambda *a, **k: {"fields": copy.deepcopy(answer)}
    return extract.extract(texts, pages, schema, report_meta)


def field_of(ext: dict, key: str) -> dict | None:
    return next((f for f in ext.get("fields", []) if f.get("key") == key), None)


def label_verdict(row: dict, field: dict | None) -> str:
    """ok / null-ok / wrong / missed / spurious -- against eval/run.py's own predicate."""
    got = field.get("value") if field else None
    if values_match(row["expected_value"], got):
        return "null-ok" if str(row["expected_value"]).strip().lower() == "null" else "ok"
    if got is None:
        return "missed"
    return "spurious" if str(row["expected_value"]).strip().lower() == "null" else "wrong"


def stored_verdict(stored_field: dict | None, run_field: dict | None) -> str:
    """same / lost / found / different / absent (neither side read anything)."""
    sv = stored_field.get("value") if stored_field else None
    rv = run_field.get("value") if run_field else None
    if sv is None and rv is None:
        return "absent"
    if rv is None:
        return "lost"
    if sv is None:
        return "found"
    return "same" if repr(sv) == repr(rv) else "different"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Swedish labels on a GBK console
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", action="append", help="KB directory to walk (repeatable; default data/kb)")
    ap.add_argument("--section", action="append", help="section to replay (repeatable; default debt_maturity)")
    ap.add_argument("--variant", action="append", choices=("mechanism", "total"),
                    help="model answer to replay (repeatable; default both)")
    ap.add_argument("--pages", choices=("window", "locate"), default="window",
                    help="window=the stored two_pass selection UNION cited pages (publish_kb's, default); "
                         "locate=candidate_pages' own ranking -- the locator standing in for the model")
    ap.add_argument("--labels", default=str(ROOT / "eval" / "labels.csv"))
    ap.add_argument("--only", help="comma-separated stem filter (default: every stem)")
    ap.add_argument("--out", help="write the per-stem report here too (UTF-8, LF)")
    ap.add_argument("--csv", help="write the per-(stem, side, field) table here (UTF-8, LF)")
    a = ap.parse_args()
    a.section = a.section or ["debt_maturity"]
    a.variant = a.variant or ["mechanism", "total"]
    kb_dirs = [pathlib.Path(p).resolve() for p in a.kb] if a.kb else [ROOT / "data" / "kb"]
    only = {s.strip() for s in a.only.split(",")} if a.only else None

    label_rows = [r for r in load_labels(a.labels) if r["section"] in a.section]
    by_stem_labels: dict[tuple[str, str], dict[str, dict]] = {}
    for r in label_rows:
        stem = r["report_file"][:-4] if r["report_file"].lower().endswith(".pdf") else r["report_file"]
        by_stem_labels.setdefault((stem, r["section"]), {})[r["key"]] = r
    label_counts = Counter(r["key"] for r in label_rows)

    lines = [f"mechanism_only: sections {a.section}, pages {a.pages}, variants {a.variant}; "
             f"extract() with the model's values nulled, zero model calls"]
    lines += [f"  kb: {x}" for x in kb_dirs]
    lines += [f"  labels: {len(label_rows)} rows over "
              + ", ".join(f"{k} {v}" for k, v in sorted(label_counts.items()))]
    csv_rows: list[list] = []
    skipped: list[tuple[str, str]] = []
    sides = ["stored"] + a.variant
    summary = {name: {"ok_f": 0, "n_f": 0, "ok_c": 0, "n_c": 0, "nonnull": 0, "fields": 0} for name in sides}
    classes: Counter = Counter()          # (variant, ok-both | stored-only | mech-only | both-wrong)
    finds = {name: [] for name in a.variant}    # per variant: field instances variant ok, stored not ok
    regressions = {name: [] for name in a.variant}  # stored ok, variant read a wrong number
    drops = {name: [] for name in a.variant}    # stored ok, variant null
    flips = {name: [] for name in a.variant}    # companies: variant all-labeled-ok, stored not
    by_shape: dict[str, dict[str, Counter]] = {}   # shape -> side -> counters

    for kb_dir in kb_dirs:
        for stem_dir in sorted(kb_dir.iterdir()):
            if not stem_dir.is_dir() or (only and stem_dir.name not in only):
                continue
            for section in a.section:
                label = f"{kb_dir.name}/{stem_dir.name}"
                lrows = by_stem_labels.get((stem_dir.name, section))
                ext_path = stem_dir / "extractions" / f"{section}.json"
                schema_path = ROOT / "backend" / "schemas" / f"{section}.json"
                if not ext_path.exists() or not schema_path.exists():
                    continue
                ext = json.loads(ext_path.read_text(encoding="utf-8"))
                if not isinstance(ext, dict) or not isinstance(ext.get("fields"), list):
                    continue
                meta_path = stem_dir / "meta.json"
                if not meta_path.exists():
                    skipped.append((label, "no meta.json"))
                    continue
                meta = json.loads(meta_path.read_text("utf-8"))
                schema = json.loads(schema_path.read_text("utf-8"))
                texts = load_texts(stem_dir)
                if texts is None:
                    skipped.append((label, "no pages.jsonl"))
                    continue
                pages = replay_pages(ext) if a.pages == "window" else candidate_pages(texts, schema)
                if not pages:
                    skipped.append((label, "no candidate pages derivable"))
                    continue
                ident = _identity_parts(schema)
                shape, tags = stored_shape(ext, set(ident[1]) if ident else set())
                st = by_shape.setdefault(shape, {name: Counter() for name in sides})
                total_key = ident[0] if ident else None
                keep_total = [f for f in ext["fields"] if f["key"] == total_key and f.get("value") is not None] \
                    if total_key else []
                report_meta = {"stem": stem_dir.name, "company": meta.get("company"),
                               "fiscal_year": meta.get("fiscal_year"), "currency": meta.get("currency")}

                runs: dict[str, dict] = {"stored": ext}
                for name in a.variant:
                    answer = model_answer(schema, keep_total if name == "total" else [])
                    runs[name] = replay(answer, texts, pages, schema, report_meta)

                lines.append(f"  {label}  shape={shape}{'/' + ','.join(tags[1:]) if len(tags) > 1 else ''}"
                             f"  window={pages[:2]}  labels={len(lrows) if lrows else 0}")
                ok_company: dict[str, bool | None] = {}
                for name in sides:
                    ext_r = runs[name]
                    n_ok = n_sc = n_nonnull = 0
                    for key, lrow in (lrows or {}).items():
                        fld = field_of(ext_r, key)
                        verd = label_verdict(lrow, fld)
                        ok = verd in ("ok", "null-ok")
                        n_ok += ok
                        n_sc += 1
                        n_nonnull += fld is not None and fld.get("value") is not None
                        st[name]["ok_f"] += ok
                        st[name]["n_f"] += 1
                        if name != "stored":
                            sv = label_verdict(lrow, field_of(ext, key))
                            s_ok = sv in ("ok", "null-ok")
                            cls = ("ok-both" if ok and s_ok else "mech-only" if ok else
                                   "stored-only" if s_ok else "both-wrong")
                            classes[(name, cls)] += 1
                            if cls == "mech-only":
                                finds[name].append(f"{label} {key}: mechanism {fld.get('value')!r}"
                                                   f" (label {lrow['expected_value']}, stored "
                                                   f"{(field_of(ext, key) or {}).get('value')!r})")
                            if s_ok and not ok:
                                (regressions[name] if fld is not None and fld.get("value") is not None
                                 else drops[name]).append(
                                    f"{label} {key}: stored {(field_of(ext, key) or {}).get('value')!r}"
                                    f" (label {lrow['expected_value']}), variant "
                                    + (f"{fld.get('value')!r}" if fld is not None and fld.get("value") is not None
                                       else "null"))
                            csv_rows.append([stem_dir.name, section, shape, name, key, lrow["expected_value"],
                                             lrow.get("expected_page", ""), (field_of(ext, key) or {}).get("value"),
                                             ((field_of(ext, key) or {}).get("source") or {}).get("page"),
                                             fld.get("value"), (fld.get("source") or {}).get("page"),
                                             "|".join(fld.get("evidence") or []), likely_writer(relevant_warnings(ext_r, key)),
                                             verd, stored_verdict(field_of(ext, key), fld)])
                    if lrows:
                        summary[name]["n_c"] += 1
                        summary[name]["ok_c"] += n_ok == len(lrows)
                        summary[name]["n_f"] += n_sc
                        summary[name]["ok_f"] += n_ok
                        st[name]["n_c"] += 1
                        st[name]["ok_c"] += n_ok == len(lrows)
                        ok_company[name] = n_ok == len(lrows)
                    summary[name]["fields"] += len(ext_r.get("fields", []))
                    summary[name]["nonnull"] += sum(f.get("value") is not None for f in ext_r.get("fields", []))
                    vals = " ".join(f"{f['key']}={f['value']!r}" for f in ext_r.get("fields", []))
                    lines.append(f"    {name:<10} {vals}   labels {n_ok}/{n_sc}  non-null {n_nonnull}")
                    if name != "stored":
                        def writer_of(fld: dict) -> str:
                            # the zero paths write no distinctive warning (stated-zero's "kept on the
                            # report's own words" maps to "warning (unmapped)"); their evidence bits
                            # name them, so name them from that
                            if "stated_zero" in (fld.get("evidence") or []):
                                return "_stated_zero"
                            if "printed_nil" in (fld.get("evidence") or []):
                                return "_model_zero_on_dash_row"
                            return likely_writer(relevant_warnings(ext_r, fld["key"]))
                        writers = {f["key"]: writer_of(f) for f in ext_r["fields"] if f.get("value") is not None}
                        writers = {k: w for k, w in writers.items() if w != "model"}
                        if writers:
                            lines.append(f"             writers: {', '.join(f'{k}={w}' for k, w in writers.items())}")
                        for w in ext_r.get("warnings") or []:
                            lines.append(f"             ! {mask_user_paths(w)}")
                for name in a.variant:
                    if ok_company.get(name) and ok_company.get("stored") is False:
                        flips[name].append(label)

    lines.append("")
    lines.append("summary (scored against labels; fields = labeled field instances, companies = all labeled keys right)")
    for name in sides:
        s = summary[name]
        lines.append(f"  {name:<10} fields {s['ok_f']}/{s['n_f']}  companies {s['ok_c']}/{s['n_c']}"
                     f"  non-null {s['nonnull']}/{s['fields']}")
    lines.append("")
    lines.append("field classes per labeled field instance (variant vs the stored record)")
    for name in a.variant:
        lines.append(f"  {name}: ok-both {classes[(name, 'ok-both')]}  stored-only {classes[(name, 'stored-only')]}"
                     f"  mech-only {classes[(name, 'mech-only')]}  both-wrong {classes[(name, 'both-wrong')]}")
    lines.append("")
    for name in a.variant:
        lines.append(f"companies the {name} variant turns right over a wrong stored record: "
                     + (f"{len(flips[name])}: {', '.join(flips[name])}" if flips[name] else "none"))
        lines.append(f"field instances the {name} variant reads right over a wrong stored record: "
                     + (f"{len(finds[name])}" if finds[name] else "none"))
        lines += [f"  {r}" for r in finds[name]]
        lines.append(f"field instances the stored record reads right that the {name} variant would lose: "
                     f"{len(drops[name])} null + {len(regressions[name])} wrong")
        lines += [f"  {r}" for r in regressions[name]]
    lines.append("")
    lines.append(f"hit rate by stored shape (primary class; {a.variant[0]} variant vs stored)")
    lines.append(f"  {'shape':<15}{'stems':>6} | {'fields stored':>13} | {'fields mech':>11} | "
                 f"{'companies stored':>16} | {'companies mech':>14}")
    for shape, st in sorted(by_shape.items(), key=lambda kv: -kv[1]["stored"]["n_c"]):
        m, s = st[a.variant[0]], st["stored"]
        lines.append(f"  {shape:<15}{s['n_c']:>6} | {s['ok_f']:>6}/{m['n_f']:<6} | {m['ok_f']:>6}/{m['n_f']:<4} | "
                     f"{s['ok_c']:>9}/{s['n_c']:<6} | {m['ok_c']:>8}/{m['n_c']}")
    report = "\n".join(lines) + "\n"
    if skipped:
        report += "not replayable:\n" + "".join(f"  {s}: {why}\n" for s, why in skipped)
    print(report, end="")
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
    if a.csv:
        pathlib.Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        head = ["stem", "section", "shape", "side", "key", "label_value", "label_page",
                "stored_value", "stored_page", "run_value", "run_page", "run_evidence", "run_writer",
                "run_vs_label", "run_vs_stored"]
        with open(a.csv, "w", encoding="utf-8", newline="\n") as f:
            f.write(",".join(head) + "\n")
            for row in csv_rows:
                f.write(",".join("" if x is None else str(x).replace(",", ";") for x in row) + "\n")


if __name__ == "__main__":
    main()
