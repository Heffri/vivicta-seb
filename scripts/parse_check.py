"""Offline parse-quality check over real PDFs: split-row rate and quote regression. No model, no network.

    python scripts/parse_check.py --out docs/acrylic/evidence/v013/before.txt
    python scripts/parse_check.py --quotes --out docs/acrylic/evidence/v013/quote_regression.txt

Default mode (split rate): for every PDF in data/reports/ the top-2 candidate pages per section
(debt_maturity, income_statement -- locate.candidate_pages, same entry point the backend uses) are
scored with the split heuristic: a line holding letters but no digits directly followed by a line
holding digits but no letters is one split -- a row label separated from its figures. The rate is
splits per 100 non-empty lines, per page, per company, per section, and overall.

--quotes mode (quote regression): every source.quote in data/kb/<stem>/extractions/income_statement.json
is re-matched with parse.quote_on_page (the same function extract.py verifies provenance with) against
(a) the cached pages.jsonl text and (b) the PDF re-parsed with the current parse.py. A quote lost on
(a) was already broken when stored; a quote lost on (b) but not on (a) is a parser regression.
--kb <dir> points the mode at another stored KB (e.g. a hardening round's seed dir, whose only
section is debt_maturity); --section picks the section, or "both".

--locate mode (locator non-regression): candidate_pages() per section on (a) the cached pages.jsonl
text vs (b) the re-parsed text; prints both rankings so a changed top page is visible at a glance.

--pages mode (directed page dump): print the current page_text() of named pages, e.g.
--pages ependion_2025:155,ratos_2025:131 --out .../pages-before.txt. Run before and after a parse.py
change so the two dumps line up page for page.

--dump-all mode (full-corpus page dump): one JSON line per page of every PDF in data/reports/,
{"stem", "page", "text"}. Meant to be diffed page-for-page against another run of the same mode --
under a different pymupdf (v049b: 1.27.2.3 vs 1.28.2) or before/after a parse.py change -- without
re-parsing every PDF twice in one process.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import locate, parse  # noqa: E402

SECTIONS = ["debt_maturity", "income_statement"]
PREVIEW = 48  # chars shown per line of a split pair


def splits_in(text: str) -> tuple[int, int, list[tuple[str, str]]]:
    """(non-empty lines, split pairs, the pairs themselves) for one page's text."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    has_alpha = [any(c.isalpha() for c in l) for l in lines]
    has_digit = [any(c.isdigit() for c in l) for l in lines]
    pairs = [(lines[i], lines[i + 1]) for i in range(len(lines) - 1) if has_alpha[i] and not has_digit[i] and has_digit[i + 1] and not has_alpha[i + 1]]
    return len(lines), len(pairs), pairs


def run_splits(out) -> None:
    pdfs = sorted((ROOT / "data" / "reports").glob("*.pdf"))
    schemas = {s: json.loads((ROOT / "backend" / "schemas" / f"{s}.json").read_text("utf-8")) for s in SECTIONS}
    print(f"parse_check split-rate run: PARSER_VERSION={parse.PARSER_VERSION}, {len(pdfs)} PDFs", file=out)
    grand = {s: [0, 0] for s in SECTIONS}  # section -> [splits, lines]
    for pdf in pdfs:
        stem = pdf.stem
        texts = parse.page_texts(pdf)
        print(f"\n== {stem} ({len(texts)}p) ==", file=out)
        for section in SECTIONS:
            pages = locate.candidate_pages(texts, schemas[section], top_n=2)
            print(f"  [{section}] candidates {pages}", file=out)
            st_splits = st_lines = 0
            for page in pages:
                n_lines, n_pairs, pairs = splits_in(texts[page - 1])
                st_splits += n_pairs
                st_lines += n_lines
                print(f"    p.{page:<4} lines={n_lines:<3} splits={n_pairs:<3} rate={100 * n_pairs / max(n_lines, 1):5.1f}%", file=out)
                for a, b in pairs[:6]:
                    print(f"        | {a[:PREVIEW]!r}\n        | {b[:PREVIEW]!r}", file=out)
            print(f"    [{section}] splits={st_splits} lines={st_lines} rate={100 * st_splits / max(st_lines, 1):.2f}%", file=out)
            grand[section][0] += st_splits
            grand[section][1] += st_lines
    print("\n== overall (all candidate pages, splits per 100 non-empty lines) ==", file=out)
    for section in SECTIONS:
        sp, ln = grand[section]
        print(f"  {section:<16} {sp} splits / {ln} lines = {100 * sp / max(ln, 1):.2f}%", file=out)


def run_quotes(out, kb: pathlib.Path, sections: list[str]) -> None:
    pdfs = sorted((ROOT / "data" / "reports").glob("*.pdf"))
    where = kb.name if kb.is_absolute() else kb.relative_to(ROOT)  # name only: an absolute path carries the machine's user name into committed evidence dumps
    print(f"parse_check quote-regression run: PARSER_VERSION={parse.PARSER_VERSION}, {len(pdfs)} PDFs,"
          f" kb={where}, sections={sections}", file=out)
    tot = {"old": [0, 0], "new": [0, 0]}  # [found, total]
    for pdf in pdfs:
        stem = pdf.stem
        n = old_found = new_found = 0
        lost = []
        old_texts = new_texts = None
        for section in sections:
            ext_file = kb / stem / "extractions" / f"{section}.json"
            old_file = kb / stem / "pages.jsonl"
            if not (ext_file.exists() and old_file.exists()):
                continue
            if old_texts is None:
                old_texts = [json.loads(l)["text"] for l in old_file.read_text("utf-8").split("\n") if l]
                new_texts = parse.page_texts(pdf)
            fields = json.loads(ext_file.read_text("utf-8"))["fields"]
            for f in fields:
                src = f.get("source") or {}
                quote, page = src.get("quote") or "", src.get("page")
                if not quote or not isinstance(page, int) or not (1 <= page <= min(len(old_texts), len(new_texts))):
                    continue
                n += 1
                if parse.quote_on_page(quote, old_texts[page - 1]):
                    old_found += 1
                else:
                    lost.append(("old", f"{section}.{f['key']}", page, quote))
                if parse.quote_on_page(quote, new_texts[page - 1]):
                    new_found += 1
                else:
                    lost.append(("new", f"{section}.{f['key']}", page, quote))
        if not n:
            print(f"\n== {stem}: no stored extraction/pages, skipped ==", file=out)
            continue
        tot["old"][0] += old_found
        tot["old"][1] += n
        tot["new"][0] += new_found
        tot["new"][1] += n
        print(f"\n== {stem}: quotes={n} old_found={old_found} new_found={new_found}", file=out)
        for which, key, page, quote in lost:
            print(f"    LOST({which}) {key} p.{page}: {quote[:100]!r}", file=out)
    print("\n== totals ==", file=out)
    for which in ("old", "new"):
        f, n = tot[which]
        print(f"  {which:>4}: {f}/{n} found, {n - f} lost", file=out)


def run_pages(out, spec: str) -> None:
    """Directed dump: the current page_text() of <stem>:<page> pairs, before/after a parse.py change."""
    import pymupdf

    print(f"parse_check directed-pages run: PARSER_VERSION={parse.PARSER_VERSION}", file=out)
    for item in spec.split(","):
        stem, page = item.strip().rsplit(":", 1)
        pdf = ROOT / "data" / "reports" / f"{stem}.pdf"
        with pymupdf.open(pdf) as doc:
            text = parse.page_text(doc[int(page) - 1])
        print(f"\n===== {stem} p.{page} ({len(text)} chars) =====", file=out)
        print(text, file=out)


def run_dump_all(out) -> None:
    """One JSON line per page of every PDF: {"stem", "page", "text"}. Diff two runs of this mode page for
    page (e.g. jq -c '[.stem,.page,.text]' both files then diff) to count and locate every page a pymupdf
    version (or a parse.py change) actually touches, corpus-wide -- not just the directed pages."""
    pdfs = sorted((ROOT / "data" / "reports").glob("*.pdf"))
    for pdf in pdfs:
        for i, text in enumerate(parse.page_texts(pdf), start=1):
            print(json.dumps({"stem": pdf.stem, "page": i, "text": text}), file=out)


def run_locate(out) -> None:
    kb = ROOT / "data" / "kb"
    pdfs = sorted((ROOT / "data" / "reports").glob("*.pdf"))
    schemas = {s: json.loads((ROOT / "backend" / "schemas" / f"{s}.json").read_text("utf-8")) for s in SECTIONS}
    print(f"parse_check locator run: PARSER_VERSION={parse.PARSER_VERSION}, {len(pdfs)} PDFs", file=out)
    changed = 0
    for pdf in pdfs:
        stem = pdf.stem
        old_file = kb / stem / "pages.jsonl"
        if not old_file.exists():
            print(f"\n== {stem}: no cached pages, skipped ==", file=out)
            continue
        old_texts = [json.loads(l)["text"] for l in old_file.read_text("utf-8").split("\n") if l]
        new_texts = parse.page_texts(pdf)
        print(f"\n== {stem} ==", file=out)
        for section in SECTIONS:
            was, now = locate.candidate_pages(old_texts, schemas[section], top_n=3), locate.candidate_pages(new_texts, schemas[section], top_n=3)
            flag = "" if was[:2] == now[:2] else "  <== top-2 changed"
            changed += bool(flag)
            print(f"  [{section}] old {was} -> new {now}{flag}", file=out)
    print(f"\n== {changed} section rankings with a changed top-2 ==", file=out)


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--quotes", action="store_true", help="quote regression instead of split-rate measurement")
    mode.add_argument("--locate", action="store_true", help="locator non-regression instead of split-rate measurement")
    mode.add_argument("--pages", metavar="STEM:PAGE[,STEM:PAGE...]", help="directed dump of the current page_text() of these pages")
    mode.add_argument("--dump-all", action="store_true", help="full-corpus page dump (JSONL), meant to be diffed against another run of the same mode")
    ap.add_argument("--kb", default="data/kb", help="knowledge base to read stored extractions/pages from (quote mode)")
    ap.add_argument("--section", default="income_statement", help="extraction section(s) for quote mode: a name or 'both'")
    ap.add_argument("--out", default="-", help="write the report here ('-' = stdout)")
    a = ap.parse_args()
    sections = SECTIONS if a.section == "both" else [a.section]
    out = open(ROOT / a.out, "w", encoding="utf-8", newline="\n") if a.out != "-" else sys.stdout
    with out:
        run_quotes(out, ROOT / a.kb, sections) if a.quotes else run_locate(out) if a.locate \
            else run_pages(out, a.pages) if a.pages else run_dump_all(out) if a.dump_all else run_splits(out)


if __name__ == "__main__":
    main()
