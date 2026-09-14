"""Knowledge base on disk: data/kb/<stem>/ (layout in docs/API.md, "Knowledge base").

Plain files, no DB: meta.json + pages.jsonl (committed), extractions/<section>.json (committed,
doubles as few-shot bank), embeddings.jsonl (derived, gitignored). Pure-Python cosine: ~1000
chunks x 1024 dims per report, math.sumprod makes that a few ms -- numpy not worth the dep.

    python -m pipeline.kb build                      # meta+pages+embeddings for every bundled report on disk
    python -m pipeline.kb atlas_copco_2025 "What was the revenue?"

Next for a teammate: (1) hybrid BM25 instead of the token-share rerank; (2) embed the page
*before/after* a hit for table context; (3) invalidate embeddings.jsonl when EMBED_MODEL changes.
"""
import hashlib
import json
import math
import os
import re
import time
from heapq import nlargest
from pathlib import Path

from openai import OpenAI

from .parse import normalize_ws

HERE = Path(__file__).resolve().parent.parent  # backend/
CHUNK, OVERLAP, BATCH = 800, 100, 64
ASK_SYSTEM = ("You answer questions about annual reports using ONLY the excerpts. Each excerpt is labelled "
              "[Company FY p.N]. Cite every number/claim inline as [Company p.N]. For each citation also give a short "
              "verbatim quote from that excerpt. If the excerpts do not contain the answer, say so — never guess.")
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {
            "type": "object",
            "properties": {"company": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["company", "page", "quote"], "additionalProperties": False}},
    },
    "required": ["answer", "citations"], "additionalProperties": False,
}
_dot = getattr(math, "sumprod", lambda a, b: sum(x * y for x, y in zip(a, b)))  # 3.12+; fallback for older venvs
_vecs: dict[str, tuple[float, list[dict]]] = {}   # stem -> (embeddings.jsonl mtime, rows)
_pages_cache: dict[str, tuple[float, dict[int, str]]] = {}


def kb_dir() -> Path:  # function, not constant: app.py calls load_dotenv() after importing us
    return (HERE / os.getenv("KB_DIR", "../data/kb")).resolve()


def embed_model() -> str:
    return os.getenv("EMBED_MODEL", "bge-m3")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _meta(stem: str) -> dict:
    p = kb_dir() / stem / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _pages(stem: str) -> dict[int, str]:
    p = kb_dir() / stem / "pages.jsonl"
    mtime = p.stat().st_mtime
    if stem not in _pages_cache or _pages_cache[stem][0] != mtime:
        rows = (json.loads(l) for l in p.read_text(encoding="utf-8").split('\n') if l)  # not splitlines(): page text may hold U+2028
        _pages_cache[stem] = (mtime, {r["page"]: r["text"] for r in rows})
    return _pages_cache[stem][1]


# ---- writing -------------------------------------------------------------------------------

def save_report(stem: str, meta: dict, texts: list[str]) -> Path:
    """meta.json + pages.jsonl; no-op when the PDF's sha256 is already there."""
    d = kb_dir() / stem
    if _meta(stem).get("sha256") == meta.get("sha256") and (d / "pages.jsonl").exists():
        return d
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(d / "pages.jsonl", "w", encoding="utf-8") as f:
        for i, t in enumerate(texts, 1):
            f.write(json.dumps({"page": i, "text": t}, ensure_ascii=False) + "\n")
    return d


def save_extraction(stem: str, section: str, extraction: dict) -> Path:
    p = kb_dir() / stem / "extractions" / f"{section}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ---- chunking ------------------------------------------------------------------------------

def _windows(text: str, size=CHUNK, overlap=OVERLAP) -> list[tuple[int, str]]:
    """(start, text) windows of <= size chars on whitespace boundaries, ~overlap chars shared."""
    toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    out, i = [], 0
    while i < len(toks):
        start, j = toks[i][0], i
        while j + 1 < len(toks) and toks[j + 1][1] - start <= size:
            j += 1
        end = toks[j][1]
        out.append((start, text[start:end]))
        if j + 1 >= len(toks):
            break
        k = j + 1
        while k - 1 > i and toks[k - 1][0] >= end - overlap:
            k -= 1
        i = k
    return out


def _fmt(v) -> str:
    return f"{v:,}".replace(",", " ") if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _title(section: str) -> str:
    p = HERE / "schemas" / f"{section}.json"
    return json.loads(p.read_text(encoding="utf-8")).get("title", section) if p.exists() else section


def chunks(stem: str) -> list[dict]:
    """Page windows + one fact chunk per extracted field (page = the field's source page)."""
    out = [{"page": n, "start": s, "text": t} for n, text in sorted(_pages(stem).items()) for s, t in _windows(text)]
    meta = _meta(stem)
    who = f"{meta.get('company') or stem} FY{meta.get('fiscal_year') or '?'}"
    for p in sorted((kb_dir() / stem / "extractions").glob("*.json")):
        x = json.loads(p.read_text(encoding="utf-8"))
        title = _title(x.get("section") or p.stem)
        for f in x.get("fields", []):
            if f.get("value") is None or not f.get("source"):
                continue
            page, quote = f["source"].get("page"), f["source"].get("quote") or ""
            # sentence-ish wording embeds ~0.03 cosine closer to questions than "Label = value (p.N)" alone
            text = f"{who} · {title} (p.{page}): {f['label']} {f.get('period') or ''} = {_fmt(f['value'])} {f.get('unit') or ''}, printed as \"{f.get('raw_label') or f['label']}\"."
            if quote and quote != f.get("raw_label"):
                text += f' Verbatim: "{quote}"'  # so a citation quoting this chunk still exists on the page
            out.append({"page": page, "start": -1, "text": text})  # start -1 = fact, not a page offset
    return out


# ---- embeddings ----------------------------------------------------------------------------

def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(_dot(v, v)) or 1.0
    return [round(x / n, 6) for x in v]


def embed(texts: list[str]) -> list[list[float]]:
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.getenv("LLM_API_KEY") or "none")
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        resp = client.embeddings.create(model=embed_model(), input=texts[i:i + BATCH])
        out += [_unit(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]
    return out


def _rows(stem: str) -> list[dict]:
    p = kb_dir() / stem / "embeddings.jsonl"
    mtime = p.stat().st_mtime
    if stem not in _vecs or _vecs[stem][0] != mtime:
        _vecs[stem] = (mtime, [json.loads(l) for l in p.read_text(encoding="utf-8").split('\n') if l])
    return _vecs[stem][1]


def index(stem: str, force=False) -> dict:
    """Build embeddings.jsonl unless it is newer than pages.jsonl and every extraction."""
    d = kb_dir() / stem
    emb = d / "embeddings.jsonl"
    deps = [d / "pages.jsonl", *(d / "extractions").glob("*.json")]
    if not force and emb.exists() and emb.stat().st_mtime >= max(x.stat().st_mtime for x in deps):
        return {"chunks": len(_rows(stem)), "embed_model": embed_model(), "cached": True}
    t0 = time.time()
    rows = chunks(stem)
    old = {r["text"]: r["vec"] for r in _rows(stem)} if emb.exists() else {}  # reuse: a new extraction only adds facts
    todo = [r["text"] for r in rows if r["text"] not in old]
    fresh = dict(zip(todo, embed(todo)))
    for r in rows:
        r["vec"] = old.get(r["text"]) or fresh[r["text"]]
    tmp = emb.with_suffix(f".{os.getpid()}.tmp")  # per-process name: two backends indexing the same stem never share a temp file
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, emb)  # atomic: a second backend on the same KB_DIR never reads a half-written file
    _vecs.pop(stem, None)
    print(f"[kb] index {stem}: {len(rows)} chunks ({len(todo)} embedded) in {time.time() - t0:.1f}s")
    return {"chunks": len(rows), "embed_model": embed_model(), "cached": False}


# ---- retrieval -----------------------------------------------------------------------------

STOP = frozenset("what was were the and which that this with for from how much many are did does has have page "
                 "vad var och det den som för hur mycket till med av på är vilken vilket sida".split())


def _tokens(s: str) -> set[str]:
    """Content tokens: split at digit/letter edges (FY2025 -> 2025, p.106 -> 106), drop stop words so
    "what was the" does not reward prose; 7-char prefix ≈ stemmer (revenue/revenues, rörelseresultat/-et).
    # ponytail: BM25 would do this properly"""
    return {t[:7] for t in re.findall(r"\d+|[^\W\d_]+", s.lower()) if len(t) > 2 and t not in STOP}


def search(stems: list[str], query: str, k=8) -> list[dict]:
    """cosine + 0.15 * share of query tokens in the chunk, so exact figures/labels beat paraphrases."""
    q, qt = embed([query])[0], _tokens(query)
    scored = []
    for stem in stems:
        index(stem)
        for r in _rows(stem):
            share = len(qt & _tokens(r["text"])) / len(qt) if qt else 0
            scored.append((_dot(q, r["vec"]) + 0.15 * share, stem, r, share))
    top = nlargest(k, scored, key=lambda x: x[0])
    seen = {id(x[2]) for x in top}
    for stem in stems:  # ponytail: the 2 best label-matching extraction facts per report always ride along (~150 chars
        # each) -- otherwise "compare operating profit" fills k with prose/segment figures and misses the statement
        facts = (x for x in scored if x[1] == stem and x[2]["start"] == -1 and x[3] > 0)
        top += [x for x in nlargest(2, facts, key=lambda x: x[0]) if id(x[2]) not in seen]
    return [{"stem": s, "page": r["page"], "text": r["text"], "score": round(sc, 4)}
            for sc, s, r, _ in sorted(top, key=lambda x: -x[0])]


def _norm_name(s: str) -> str:
    return re.sub(r"\W+", " ", re.sub(r"\bfy ?\d{4}\b|\bp\.? ?\d+\b", "", s.lower())).strip()


def ask(stems: list[str], question: str, k=8, ids: dict[str, str] | None = None) -> dict:
    """Answer dict per docs/API.md. ids maps stem -> report_id (defaults to the stem)."""
    from .extract import call_llm  # lazy: extract imports us for few-shot
    ids = ids or {}
    metas = {s: _meta(s) for s in stems}
    label = {s: f"{m.get('company') or s} FY{m.get('fiscal_year') or '?'}" for s, m in metas.items()}
    hits = search(stems, question, k)
    user = (f"Question: {question}\n\nQuotes must be copied character for character from one excerpt (a line break may become a "
            f"space; keep note numbers and every token between label and figure).\n\nExcerpts:\n"
            + "\n\n".join(f"[{label[h['stem']]} p.{h['page']}]\n{h['text']}" for h in hits))
    warnings: list[str] = []
    try:
        raw = call_llm(ASK_SYSTEM, user, ANSWER_SCHEMA, "answer")
    except Exception as e:  # ponytail: no retry, same as extract
        raw, warnings = {"answer": "", "citations": []}, [f"llm: {type(e).__name__}: {e}"]

    by_name = sorted(((_norm_name(metas[s].get("company") or s), s) for s in stems), key=lambda x: -len(x[0]))
    citations, seen = [], set()
    for c in raw.get("citations") or []:
        if not isinstance(c, dict):
            continue
        name, page, quote = str(c.get("company") or ""), c.get("page"), str(c.get("quote") or "")
        n = _norm_name(name)
        stem = next((s for cn, s in by_name if cn == n), None) or next((s for cn, s in by_name if cn and (cn in n or n in cn)), None) \
            or (stems[0] if len(stems) == 1 else None)
        if stem is None:
            warnings.append(f"citation dropped: {name} p.{page} unknown company")
            continue
        if not isinstance(page, int) or not quote or normalize_ws(quote) not in normalize_ws(_pages(stem).get(page, "")):
            warnings.append(f"citation dropped: {name} p.{page} quote not found")
            continue
        if (stem, page, quote) in seen:
            continue
        seen.add((stem, page, quote))
        score = max((h["score"] for h in hits if h["stem"] == stem and h["page"] == page), default=0)
        citations.append({"report_id": ids.get(stem, stem), "company": metas[stem].get("company"), "fiscal_year": metas[stem].get("fiscal_year"),
                          "page": page, "quote": quote, "score": round(min(score, 1.0), 3)})
    return {"question": question, "answer": raw.get("answer") or "", "citations": citations, "warnings": warnings,
            "model": os.getenv("LLM_MODEL", "")}


# ---- listing / few-shot --------------------------------------------------------------------

def entries() -> list[dict]:
    """KbEntry[] minus report_id (app.py fills it from its registry)."""
    out = []
    for d in sorted(p for p in kb_dir().glob("*") if (p / "meta.json").exists()):
        m = _meta(d.name)
        out.append({"stem": d.name, "report_id": None, "company": m.get("company"), "fiscal_year": m.get("fiscal_year"),
                    "pages": m.get("pages", 0), "sections": sorted(p.stem for p in (d / "extractions").glob("*.json")),
                    "indexed": (d / "embeddings.jsonl").exists()})
    return out


def fewshot_examples(section: str, exclude_stem: str | None, n: int) -> list[dict]:
    """Up to n prior extractions of `section` from other stems with all checks passed and no warnings,
    compacted to {company, fields: [{key, raw_label, value, unit, period, page}]}."""
    out = []
    for p in sorted(kb_dir().glob(f"*/extractions/{section}.json")):
        stem = p.parent.parent.name
        if stem == exclude_stem or len(out) >= n:
            continue
        x = json.loads(p.read_text(encoding="utf-8"))
        if x.get("warnings") or not all(c.get("passed") for c in x.get("checks", [])):
            continue
        out.append({"company": x.get("company") or stem, "fields": [
            {"key": f["key"], "raw_label": f.get("raw_label"), "value": f["value"], "unit": f.get("unit"),
             "period": f.get("period"), "page": (f.get("source") or {}).get("page")}
            for f in x.get("fields", []) if f.get("value") is not None]})
    return out


# ---- CLI -----------------------------------------------------------------------------------

def build() -> None:
    """meta + pages + embeddings for every data/reports/index.json entry present on disk."""
    from .parse import page_texts
    lib = HERE.parent / "data" / "reports"
    for e in json.loads((lib / "index.json").read_text(encoding="utf-8")):
        pdf = lib / e["file"]
        if not pdf.exists():
            continue
        stem, t0 = pdf.stem, time.time()
        texts = page_texts(pdf)
        meta = {k: e.get(k) for k in ("company", "fiscal_year", "language", "source_url")} | {"pages": len(texts), "sha256": sha256(pdf.read_bytes()), "filename": e["file"]}
        save_report(stem, meta, texts)
        print(f"[kb] {stem}: {len(texts)} pages saved in {time.time() - t0:.1f}s; index -> {index(stem)}")


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
    if sys.argv[1:] == ["build"]:
        build()
    else:
        stem, question = sys.argv[1], sys.argv[2]
        t0 = time.time()
        print(json.dumps(ask([stem], question), ensure_ascii=False, indent=2), f"\n[{time.time() - t0:.1f}s]")
