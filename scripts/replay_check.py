"""Replay stored KB extractions through extract() -- baseline code vs worktree code, zero model calls.

    python scripts/replay_check.py --baseline <git-ref>             # income_statement, data/kb
    python scripts/replay_check.py --section debt_maturity --section income_statement --baseline <git-ref>
    python scripts/replay_check.py --kb <dir> --kb <dir> --baseline <git-ref> --only stem1,stem2 --out <file>

For every <kb>/<stem>/extractions/<section>.json the stored fields are fed back as the model's own
answer -- the model-side shape extract() consumes (key/label/value/unit/period/raw_label/source; the
post-processing-added confidence/evidence stripped, extract() derives both itself) -- page texts come
from the same directory's pages.jsonl, report_meta from meta.json. Every company runs through BOTH
extract.py as of --baseline (loaded off `git show`, the same mechanism scripts/label_regression.py
uses; the matching baseline schemas/<section>.json goes with it) and the worktree's own, on identical
inputs -- so any replay-setup choice below hits both sides equally and only the change under test can
move a value. Stored fields are post-processing OUTPUT: a field the original run dropped is stored
null with no source and replays as null on both sides (raw model answers are not stored), so a replay
proves a change cannot move what is on disk; it does not re-enact the original run's model behaviour.

Candidate pages (extract()'s `pages` argument), first rule that fits: a top-level "pages" or
"candidate_pages" int list in the stored json (no stored file carries one today); else the candidate
list recorded in a "two_pass: ... selected from candidates [...]" warning -- what the original run
received as `pages`; else the deduped sorted set of the stored fields' source.page (the cited pages).
With EXTRACT_TWO_PASS off the replay's window is that list's first two pages, which for a two-pass
run whose selection was not its first two candidates differs from the original window -- equally on
both sides, and never against a stored-value comparison (none is made).

The default --baseline, origin/acrylic, no longer exists in this repository: pass --baseline
explicitly.

Compared per field: value (by repr, so 5 vs 5.0 shows), confidence, the evidence set; per check:
passed + detail up to the first " | " (the "missing: <field>" prefix, or the check's own text); and
the warnings count. --out writes the report as a UTF-8/LF file sized for pasting into an evidence doc.
"""
import argparse
import copy
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import extract as cur  # noqa: E402

os.environ.pop("EXTRACT_TWO_PASS", None)  # the stub would fail pass-1's page pick and add an equal warning on both sides; off = one call
os.environ["FEWSHOT"] = "0"  # the rendered prompt is discarded by the stub; skip the fewshot disk scan

MODEL_KEYS = ("key", "label", "value", "unit", "period", "raw_label", "source")
_TWO_PASS_CANDIDATES = re.compile(r"two_pass: page \[[\d, ]*\] selected from candidates \[([\d, ]*)\]")


def git_show(ref: str, path: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def load_baseline(ref: str):
    """extract.py as of a git ref, imported as pipeline._replay_baseline_extract (package-relative imports intact)."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="replay_check_")) / "_replay_baseline_extract.py"
    tmp.write_text(git_show(ref, "backend/pipeline/extract.py"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pipeline._replay_baseline_extract", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_texts(stem_dir: pathlib.Path) -> list[str] | None:
    """pages.jsonl -> texts indexed by page-1; None when the file is missing or has no page lines.
    Split on '\\n', not splitlines(): page text may hold U+2028, which splitlines() breaks apart
    (the same rule as pipeline.kb._pages, the only reader these files were written for)."""
    p = stem_dir / "pages.jsonl"
    if not p.exists():
        return None
    texts: list[str] = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        d = json.loads(line)
        n = d.get("page")
        if isinstance(n, int) and n >= 1:
            while len(texts) < n:
                texts.append("")
            texts[n - 1] = d.get("text") or ""
    return texts or None


def candidate_pages(ext: dict) -> list[int] | None:
    for k in ("pages", "candidate_pages"):  # recorded candidates, if a store format ever carries them
        v = ext.get(k)
        if isinstance(v, list) and v and all(isinstance(p, int) and not isinstance(p, bool) for p in v):
            return v
    for w in ext.get("warnings") or []:  # the original run's own `pages` argument, recorded by a two-pass run
        m = _TWO_PASS_CANDIDATES.search(str(w))
        if m and m.group(1).strip():
            return [int(p) for p in m.group(1).split(",")]
    cited = sorted({f["source"]["page"] for f in ext.get("fields", [])
                    if isinstance(f.get("source"), dict) and isinstance(f["source"].get("page"), int)
                    and not isinstance(f["source"]["page"], bool)})
    return cited or None


def model_answer(ext: dict) -> list[dict]:
    """The stored fields as the model-side shape: no confidence (the model's own is ignored anyway),
    no evidence (post-processing's own record), nothing else added back."""
    return [{k: f.get(k) for k in MODEL_KEYS} for f in ext.get("fields", [])]


def replay(mod, texts: list[str], pages: list[int], schema: dict, meta: dict, answer: list[dict]) -> dict:
    # fresh deep copy per call: extract() mutates the model answer's source dicts in place
    # (src["quote"] = verified), and a stored answer must enter every run pristine, exactly
    # like the fresh model output the real pipeline hands it -- otherwise the second run on the
    # same company replays the first run's post-processing, not the change under test.
    mod.call_llm = lambda *a, **k: {"fields": copy.deepcopy(answer)}
    return mod.extract(texts, pages, schema, meta)


def field_sig(f: dict | None) -> tuple:
    if f is None:
        return ("<absent>", "", ())
    return (repr(f.get("value")), repr(f.get("confidence")), tuple(sorted(f.get("evidence") or [])))


def check_sig(c: dict) -> tuple:
    return (bool(c.get("passed")), c.get("detail", "").split(" | ")[0])


def compare(a: dict, b: dict) -> list[str]:
    """Human-readable before -> after lines for everything this replay compares; [] when same."""
    diffs = []
    fa = {f["key"]: f for f in a["fields"]}
    fb = {f["key"]: f for f in b["fields"]}
    for key in [f["key"] for f in a["fields"]] + [k for k in fb if k not in fa]:
        x, y = fa.get(key), fb.get(key)
        if field_sig(x) != field_sig(y):
            show = lambda f, get: repr(get(f)) if f is not None else "<absent>"  # noqa: E731
            diffs.append(f"    {key}: value {show(x, lambda f: f.get('value'))} -> {show(y, lambda f: f.get('value'))}"
                         f"; confidence {show(x, lambda f: f.get('confidence'))} -> {show(y, lambda f: f.get('confidence'))}"
                         f"; evidence {show(x, lambda f: sorted(f.get('evidence') or []))} -> {show(y, lambda f: sorted(f.get('evidence') or []))}")
    if len(a["checks"]) != len(b["checks"]):
        diffs.append(f"    checks: {len(a['checks'])} -> {len(b['checks'])}")
    for ca, cb in zip(a["checks"], b["checks"]):
        if check_sig(ca) != check_sig(cb) or ca.get("name") != cb.get("name"):
            diffs.append(f"    check {ca.get('name')}: passed={check_sig(ca)[0]} detail={check_sig(ca)[1]!r}"
                         f" -> passed={check_sig(cb)[0]} detail={check_sig(cb)[1]!r}")
    if len(a["warnings"]) != len(b["warnings"]):
        diffs.append(f"    warnings: {len(a['warnings'])} -> {len(b['warnings'])}")
    return diffs


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Swedish labels on a GBK console
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", action="append", help="KB directory to walk (repeatable; default data/kb)")
    ap.add_argument("--section", action="append",
                    help="extraction section to replay (repeatable; default income_statement)")
    ap.add_argument("--baseline", default="origin/acrylic", help="git ref providing the old extract.py + schemas")
    ap.add_argument("--only", help="comma-separated stem filter (default: every stem)")
    ap.add_argument("--out", help="write the report here too (UTF-8, LF)")
    a = ap.parse_args()
    a.section = a.section or ["income_statement"]
    kb_dirs = [pathlib.Path(p).resolve() for p in a.kb] if a.kb else [ROOT / "data" / "kb"]
    only = {s.strip() for s in a.only.split(",")} if a.only else None

    old = load_baseline(a.baseline)
    new_schemas = {s: json.loads((ROOT / "backend" / "schemas" / f"{s}.json").read_text("utf-8"))
                   for s in a.section if (ROOT / "backend" / "schemas" / f"{s}.json").exists()}
    old_schemas: dict[str, dict] = {}
    for s in list(new_schemas):  # both sides need a schema: the schema is part of the code state being compared
        try:
            old_schemas[s] = json.loads(git_show(a.baseline, f"backend/schemas/{s}.json"))
        except subprocess.CalledProcessError:
            print(f"replay_check: skipping {s}: no schemas/{s}.json at {a.baseline}", file=sys.stderr)
            del new_schemas[s]
    a.section = [s for s in a.section if s in old_schemas]
    if not a.section:
        ap.error("no section with a schema both at the baseline and in the worktree")

    lines = [f"replay_check: baseline {a.baseline}, sections {a.section}, worktree extract.py; "
             f"stored fields fed back as the model answer, zero model calls"]
    lines += [f"  kb: {d}" for d in kb_dirs]
    totals = {"companies": 0, "same": 0, "changed": 0}
    skipped: list[tuple[str, str]] = []
    for kb_dir in kb_dirs:
        for stem_dir in sorted(kb_dir.iterdir()):
            if not stem_dir.is_dir() or (only and stem_dir.name not in only):
                continue
            for section in a.section:
                label = f"{kb_dir.name}/{stem_dir.name}"
                ext_path = stem_dir / "extractions" / f"{section}.json"
                if not ext_path.exists():
                    skipped.append((label, f"no {section}"))
                    continue
                try:
                    ext = json.loads(ext_path.read_text("utf-8"))
                except (ValueError, OSError):
                    skipped.append((label, "unrecognized shape (unreadable json)"))
                    continue
                if not isinstance(ext, dict) or not isinstance(ext.get("fields"), list):
                    skipped.append((label, "unrecognized shape (no fields list)"))
                    continue
                meta_path = stem_dir / "meta.json"
                if not meta_path.exists():
                    skipped.append((label, "no meta.json"))
                    continue
                meta = json.loads(meta_path.read_text("utf-8"))
                texts = load_texts(stem_dir)
                if texts is None:
                    skipped.append((label, "no pages.jsonl"))
                    continue
                pages = candidate_pages(ext)
                if pages is None:
                    skipped.append((label, "no candidate pages derivable"))
                    continue
                report_meta = {"stem": stem_dir.name, "company": meta.get("company"),
                               "fiscal_year": meta.get("fiscal_year"), "currency": meta.get("currency")}
                answer = model_answer(ext)
                was = replay(old, texts, pages, old_schemas[section], report_meta, answer)
                now = replay(cur, texts, pages, new_schemas[section], report_meta, answer)
                totals["companies"] += 1
                diffs = compare(was, now)
                if diffs:
                    totals["changed"] += 1
                    lines.append(f"  {label:<44} {section:<16} CHANGED")
                    lines += diffs
                else:
                    totals["same"] += 1
                    lines.append(f"  {label:<44} {section:<16} same")
    lines.append(f"\ntotals: companies={totals['companies']} same={totals['same']} "
                 f"changed={totals['changed']} not_replayable={len(skipped)}")
    for label, reason in skipped:
        lines.append(f"  not replayable: {label}: {reason}")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)


if __name__ == "__main__":
    main()
