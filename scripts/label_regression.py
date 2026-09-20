"""Offline label-synonym regression over the stored KB extractions. No model, no network, read-only.

    python scripts/label_regression.py                                 # income_statement, old = origin/acrylic
    python scripts/label_regression.py --schema debt_maturity
    python scripts/label_regression.py --schema income_statement --schema debt_maturity --baseline <git ref>

For every field of every data/kb/<stem>/extractions/<schema>.json whose key exists in the matching
backend/schemas/<schema>.json and which carries a source.quote and a raw_label, four verdicts are
compared between the baseline code and the current code:

    row_label          _row_label(source.quote)                    -- the printed label behind the quote
    label_known        _label_known(raw_label, sf)                 -- the scoring / verification predicate
    own_row_exact      _clean_label(_row_label(quote)) in syns     -- extract()'s own-row detection feeding own_syns
    own_syns_contains  any(syn in _clean_label(_row_label(quote)) for syn in syns)
                       -- the part-row containment gate inside _derived_value, evaluated on the field's
                          own row as the stand-in part row

where syns is the call site's synonym set: the baseline builds it verbatim ({s.lower()}), the current
code cleans it ({_clean_label(s), non-empty}).

--baseline loads extract.py AS OF that git ref (via `git show`) into a throwaway module in the
pipeline package namespace, so its relative imports resolve to the current parse/locate; the default
baseline is origin/acrylic. Verdicts are pure predicates -- nothing is written, data/ is untouched.
"""
import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import extract as cur  # noqa: E402


def load_baseline(ref: str):
    """extract.py as of a git ref, imported as pipeline._baseline_extract (package-relative imports intact)."""
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:backend/pipeline/extract.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="label_regression_")) / "_baseline_extract.py"
    tmp.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pipeline._baseline_extract", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def syns(sf: dict, mod) -> set:
    """The call site's own_syns set: verbatim-lowered (baseline) vs cleaned non-empty (current)."""
    if mod is cur:
        return {c for s in sf.get("synonyms", []) if (c := mod._clean_label(s))}
    return {s.lower() for s in sf.get("synonyms", [])}


def verdicts(mod, f: dict, sf: dict) -> dict:
    src = f.get("source") or {}
    quote, rl = src.get("quote") or "", f.get("raw_label")
    label = mod._row_label(quote)
    clean = mod._clean_label(label)
    syn = syns(sf, mod)
    return {"row_label": label,
            "label_known": mod._label_known(rl, sf),
            "own_row_exact": clean in syn,
            "own_syns_contains": any(s in clean for s in syn)}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Swedish synonyms on a GBK console
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="append",
                    help="extraction schema to walk (repeatable; default income_statement)")
    ap.add_argument("--baseline", default="origin/acrylic", help="git ref providing the old extract.py")
    a = ap.parse_args()
    a.schema = a.schema or ["income_statement"]
    old = load_baseline(a.baseline)
    schemas = {s: json.loads((ROOT / "backend" / "schemas" / f"{s}.json").read_text("utf-8"))
               for s in a.schema if (ROOT / "backend" / "schemas" / f"{s}.json").exists()}
    keys = {s: {g["key"]: g for g in schemas[s]["fields"]} for s in schemas}
    print(f"label_regression: baseline {a.baseline}, schemas {sorted(schemas)}, "
          f"CURRENT PARSER {'extract.py@worktree'}")
    total = {"identical": 0, "changed": 0, "skipped": 0}
    for stem_dir in sorted((ROOT / "data" / "kb").iterdir()):
        for schema, sf_all in keys.items():
            ext = stem_dir / "extractions" / f"{schema}.json"
            if not (stem_dir.is_dir() and ext.exists()):
                continue
            same = changed = skipped = 0
            details = []
            for f in json.loads(ext.read_text("utf-8"))["fields"]:
                src = f.get("source") or {}
                if not src.get("quote") or not f.get("raw_label") or f["key"] not in sf_all:
                    skipped += 1  # both implementations answer by construction; nothing to compare
                    continue
                sf = sf_all[f["key"]]
                was, now = verdicts(old, f, sf), verdicts(cur, f, sf)
                if was == now:
                    same += 1
                else:
                    changed += 1
                    diff = [k for k in was if was[k] != now[k]]
                    details.append(f"    CHANGED[{'+'.join(diff)}] {f['key']}: old={ {k: was[k] for k in diff} } "
                                   f"new={ {k: now[k] for k in diff} } raw_label={f['raw_label']!r} quote={src['quote'][:90]!r}")
            total["identical"] += same
            total["changed"] += changed
            total["skipped"] += skipped
            if same or changed or skipped:
                print(f"  {stem_dir.name:<28} {schema:<16} identical={same:<3} changed={changed:<3} skipped={skipped}")
            details and print("\n".join(details))
    print(f"\ntotals: identical={total['identical']} changed={total['changed']} skipped={total['skipped']}")
    for schema, schema_json in schemas.items():  # the census: which synonyms the cleaning even can move
        moved = [(g["key"], s, cur._clean_label(s)) for g in schema_json["fields"] for s in g.get("synonyms", [])
                 if cur._clean_label(s) != s.lower()]
        emptied = [(g["key"], s) for g in schema_json["fields"] for s in g.get("synonyms", []) if not cur._clean_label(s)]
        print(f"synonyms whose cleaned form differs from verbatim ({schema}): {len(moved)}; cleaned to empty: {len(emptied)}")
        for k, s, c in moved:
            print(f"    ({k}, {s!r}, {c!r})")


if __name__ == "__main__":
    main()
