"""Publish seed-hardening KB entries into data/kb -- meta.json + pages.jsonl + extractions/<section>.json.

    python scripts/publish_kb.py --kb <seed1-kb> --kb <seed2-kb> ...     # later --kb overrides earlier
    python scripts/publish_kb.py --kb <dir> --dry-run                    # decide, print, write nothing

Why: the hardening rounds' per-company results (seeds 1-8, Mid Cap universe) live only in shared
seed directories; this copies the best run per stem into the committed KB so the KB view, Compare,
Ask (BM25 over pages.jsonl) and `eval/run.py --stored-kb data/kb` all see them. The replay mechanism
is scripts/replay_check.py's: the stored fields are fed back as the model's own answer (MODEL_KEYS
only -- confidence/evidence are post-processing output, extract() derives both itself) through the
WORKTREE's current extract(), with call_llm stubbed -- zero model calls.

Replay window = the two_pass selection recorded in the stored warnings (what the original run's
window was; replay_check's "candidates' first two" would lose it) UNION the pages the stored fields
cite. Selected pages come first so extract()'s pages[:2] is the original window.

Per field, replayed vs stored: a value lost (non-null -> null) or a confidence drop publishes the
STORED extraction instead; otherwise the replayed one -- current code is published only when it is
no worse than what the seed stored. Both cases keep the stored warnings (with the user segment of
any user-profile path masked -- a stored provider-error warning can quote a whole failed command
line) and append one "published: ..." line naming the seed and how the entry was produced. The
extract.py hash is the sha256 of the file that produced the replay -- not HEAD -- so a re-run from
a moved HEAD with unchanged extract.py still writes byte-identical files (idempotency; seeds 9/10
will re-run this).

Not copied: PDFs (gitignored), embeddings.jsonl (derived). An existing data/kb/<stem> whose
meta.json sha256 differs from the seed's is skipped and listed, never overwritten.
"""
import argparse
import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("EXTRACT_TWO_PASS", None)  # the window below already is the recorded selection
os.environ["FEWSHOT"] = "0"  # the rendered prompt is discarded by the stub; skip the fewshot disk scan
from pipeline import extract  # noqa: E402

MODEL_KEYS = ("key", "label", "value", "unit", "period", "raw_label", "source")
_TWO_PASS_SELECTED = re.compile(r"two_pass: page \[([\d, ]*)\] selected from candidates \[")
_SEED_NO = re.compile(r"seed(\d+)-kb")
_USER_PATH = re.compile(r"(?i)([A-Z]:\\+Users\\+)[^\\'\"\]]+")
CONF_EPS = 1e-9  # confidences are round(x, 3); the epsilon only guards float repr noise


def mask_user_paths(text: str) -> str:
    """A stored provider-error warning can quote the whole failed command line, user-profile paths
    included -- machine-identifying, and the published KB must not carry it. The user segment of a
    `X:\\Users\\<segment>` path is replaced generically (the script never spells any name out);
    the rest of the path and the error survive. Stillfront's stored seed-7 timeout warning is the
    one case in the corpus."""
    return _USER_PATH.sub(lambda m: m.group(1) + "<user>", str(text))


def extract_py_sha() -> str:
    return hashlib.sha256((ROOT / "backend" / "pipeline" / "extract.py").read_bytes()).hexdigest()[:8]


def load_texts(stem_dir: pathlib.Path) -> list[str] | None:
    """pages.jsonl -> texts indexed by page-1; None when missing or empty. Split on '\n', not
    splitlines(): page text may hold U+2028 (same rule as pipeline.kb._pages and replay_check)."""
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


def replay_pages(ext: dict) -> list[int]:
    """The two_pass-selected pages first (the original run's own window), then the stored fields'
    cited pages; deduped, order preserved."""
    pages: list[int] = []
    for w in ext.get("warnings") or []:
        m = _TWO_PASS_SELECTED.search(str(w))
        if m and m.group(1).strip():
            pages += [int(p) for p in m.group(1).split(",")]
            break
    for f in ext.get("fields", []):
        src = f.get("source") or {}
        p = src.get("page") if isinstance(src, dict) else None
        if isinstance(p, int) and not isinstance(p, bool) and p >= 1:
            pages.append(p)
    return list(dict.fromkeys(pages))


def replay(ext: dict, texts: list[str], pages: list[int], schema: dict, meta: dict, report_id) -> dict:
    answer = [{k: f.get(k) for k in MODEL_KEYS} for f in ext["fields"]]
    # fresh deep copy per call: extract() mutates the model answer's source dicts in place
    # (src["quote"] = verified) -- same reason replay_check deep-copies inside the stub
    extract.call_llm = lambda *a, **k: {"fields": copy.deepcopy(answer)}
    report_meta = {"stem": meta.get("stem"), "report_id": report_id, "company": meta.get("company"),
                   "fiscal_year": meta.get("fiscal_year"), "currency": meta.get("currency")}
    return extract.extract(texts, pages, schema, report_meta)


def compare_fields(stored: dict, replayed: dict) -> tuple[list[str], list[str]]:
    """(reasons the replay is worse, fields where the replay differs favourably). Worse = a field
    that had a value now null, or a confidence drop; that publishes the stored extraction. Anything
    else -- null -> value, a confidence gain, or both fields reading different values (repr
    compared, so 5 vs 5.0 shows) -- publishes the replay and is listed; equal everywhere is "same"."""
    worse: list[str] = []
    better: list[str] = []
    sf = {f["key"]: f for f in stored["fields"]}
    rf = {f["key"]: f for f in replayed["fields"]}
    for key, s in sf.items():
        r = rf.get(key) or {}
        sv, rv = s.get("value"), r.get("value")
        sc = s.get("confidence") or 0.0
        rc = r.get("confidence") or 0.0
        if sv is not None and rv is None:
            worse.append(f"{key}: value {sv!r} -> null")
        elif rc < sc - CONF_EPS:
            worse.append(f"{key}: confidence {sc} -> {rc}")
        elif sv is not None and rv is not None and repr(rv) != repr(sv):
            # both read a value but they differ: current code wins (the stored run keeps only a
            # null-loss or a confidence drop), but the change must show, never hide inside "same"
            better.append(f"{key}: value {sv!r} -> {rv!r}")
        elif rv is not None and sv is None:
            better.append(f"{key}: null -> {rv!r}")
        elif rv == sv and rc > sc + CONF_EPS:
            better.append(f"{key}: confidence {sc} -> {rc}")
    return worse, better


def write_extraction(target: pathlib.Path, section: str, payload: dict) -> None:
    p = target / "extractions" / f"{section}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:  # LF: the .gitattributes form of the blob
        f.write(json.dumps(payload, ensure_ascii=False, indent=2))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Swedish labels on a GBK console
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", action="append", required=True,
                    help="seed KB directory to publish from (repeatable; later overrides earlier)")
    ap.add_argument("--section", action="append", default=None,
                    help="extraction section to publish (repeatable; default debt_maturity)")
    ap.add_argument("--dry-run", action="store_true", help="decide and print, write nothing")
    a = ap.parse_args()
    a.section = a.section or ["debt_maturity"]

    target_root = ROOT / "data" / "kb"
    sha8 = extract_py_sha()

    # best run per stem: walk the --kb dirs in order, later dirs override earlier ones
    pick: dict[str, tuple[str, pathlib.Path]] = {}
    for kb in a.kb:
        kb_path = pathlib.Path(kb)
        tag = _SEED_NO.search(kb_path.name)
        tag = tag.group(1) if tag else kb_path.name
        for ext_path in sorted(kb_path.glob(f"*/extractions/*.json")):
            if ext_path.stem in a.section:
                pick[ext_path.parent.parent.name] = (tag, ext_path.parent.parent)

    lines = [f"publish_kb -> data/kb, sections {a.section}, replay via extract.py @ {sha8}"
             f"{' [dry-run]' if a.dry_run else ''}"]
    rows, skipped, published = [], [], 0
    for stem in sorted(pick):
        tag, src = pick[stem]
        target = target_root / stem
        try:
            src_meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            skipped.append((stem, tag, f"unreadable meta.json ({type(e).__name__})"))
            continue
        if not (src / "pages.jsonl").exists():
            skipped.append((stem, tag, "no pages.jsonl"))
            continue

        if (target / "meta.json").exists():  # published before (or built from a PDF here): sha decides
            try:
                dst_sha = json.loads((target / "meta.json").read_text(encoding="utf-8")).get("sha256")
            except (ValueError, OSError):
                dst_sha = None
            if dst_sha != src_meta.get("sha256"):
                skipped.append((stem, tag, f"sha256 differs (data/kb has {str(dst_sha)[:12]}, source {str(src_meta.get('sha256'))[:12]})"))
                continue
            fresh = False
        else:
            fresh = True

        for section in a.section:
            ext_path = src / "extractions" / f"{section}.json"
            try:
                stored = json.loads(ext_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                skipped.append((stem, tag, f"unreadable {section}.json"))
                continue
            if not isinstance(stored, dict) or not isinstance(stored.get("fields"), list):
                skipped.append((stem, tag, f"{section}.json: no fields list"))
                continue

            texts = load_texts(src)
            pages = replay_pages(stored)
            replayable = texts is not None and bool(pages)
            if replayable:
                schema_path = ROOT / "backend" / "schemas" / f"{section}.json"
                if not schema_path.exists():
                    skipped.append((stem, tag, f"no schemas/{section}.json in the worktree"))
                    continue
                schema = json.loads(schema_path.read_text("utf-8"))
                replayed = replay(stored, texts, pages, schema, src_meta, stored.get("report_id"))
                worse, better = compare_fields(stored, replayed)
            else:
                worse, better = [], []
                replayed = None

            if replayed is not None and not worse:
                payload = replayed
                mode = "same" if not better else "better"
                note = "; ".join(better)
            else:
                payload = stored
                mode = "stored"
                note = ("replay not possible: "
                        + ("no pages.jsonl" if texts is None else "no candidate pages derivable")
                        if replayed is None else "; ".join(worse))
            payload = {**payload, "warnings": [mask_user_paths(w) for w in stored.get("warnings") or []]
                       + [f"published: seed{tag} run replayed with extract.py @ {sha8}" if mode != "stored"
                          else f"published: seed{tag} run as stored"]}

            if not a.dry_run:
                if fresh:
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src / "meta.json", target / "meta.json")
                    shutil.copyfile(src / "pages.jsonl", target / "pages.jsonl")
                write_extraction(target, section, payload)
            published += 1
            nn = sum(f.get("value") is not None for f in payload["fields"])
            chk = "; ".join(f"{c.get('name')}:{'pass' if c.get('passed') else 'fail'}"
                            for c in payload.get("checks", []))
            rows.append((stem, tag, mode, note, f"{nn}/{len(payload['fields'])}", chk or "-"))

    width = max((len(r[0]) for r in rows), default=0)
    for stem, tag, mode, note, nn, chk in rows:
        lines.append(f"  {stem:<{width}}  seed{tag:<3} {mode:<6} {nn:<4} {chk:<28} {note}")
    for stem, tag, why in skipped:
        lines.append(f"  SKIPPED {stem:<{width}}  seed{tag:<3} {why}")
    lines.append(f"totals: published={published} skipped={len(skipped)}"
                 f"{' (dry-run: nothing written)' if a.dry_run else ''}")
    report = "\n".join(lines) + "\n"
    print(report, end="")


if __name__ == "__main__":
    main()
