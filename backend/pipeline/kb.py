"""Knowledge base on disk: data/kb/<stem>/ (layout in docs/API.md, "Knowledge base").

Plain files, no DB: meta.json + pages.jsonl (committed), extractions/<section>.json (committed,
doubles as few-shot bank), embeddings.jsonl (derived, gitignored). Pure-Python cosine: ~1000
chunks x 1024 dims per report, math.sumprod makes that a few ms -- numpy not worth the dep.

    python -m pipeline.kb build                      # meta+pages+embeddings for every bundled report on disk
    python -m pipeline.kb atlas_copco_2025 "What was the revenue?"

Next for a teammate: evaluate BM25 instead of the token-share rerank and neighbouring-page
context. Index manifests validate model, dimensions, source content and chunk settings.
"""
import hashlib
import json
import math
import os
import re
import time
import tempfile
import threading
from datetime import datetime, timezone
from heapq import nlargest
from pathlib import Path

from openai import OpenAI

from . import runtime

HERE = Path(__file__).resolve().parent.parent  # backend/
CHUNK, OVERLAP, BATCH = 800, 100, 64
ASK_SYSTEM = ("You answer questions about annual reports using ONLY the excerpts. Each excerpt is labelled "
              "[Company FY p.N]. Cite every number/claim inline as [Company FY p.N]. For each citation also give a short "
              "verbatim quote from that excerpt. Return its exact report ID, not its company name. "
              "If the excerpts do not contain the answer, say so — never guess.")
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {
            "type": "object",
            "properties": {"report": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["report", "page", "quote"], "additionalProperties": False}},
    },
    "required": ["answer", "citations"], "additionalProperties": False,
}
_dot = getattr(math, "sumprod", lambda a, b: sum(x * y for x, y in zip(a, b)))  # 3.12+; fallback for older venvs
_vecs: dict[str, tuple[float, list[dict]]] = {}   # stem -> (embeddings.jsonl mtime, rows)
_pages_cache: dict[str, tuple[float, dict[int, str]]] = {}
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
_status_cache = {}
CHUNKER_VERSION = 2  # facts require verified evidence; derived sums stay in source pages


def report_lock(stem, operation="index"):
    with _locks_guard:
        return _locks.setdefault((str(kb_dir() / stem), operation), threading.RLock())


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def embed_base_url():
    return os.getenv("EMBED_BASE_URL") or os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1"


def cached_texts(stem, digest):
    from .parse import PARSER_VERSION, ocr_settings
    meta = _meta(stem)
    legacy_ocr = {"language": "eng+swe", "tessdata": str((HERE.parent / "data/tessdata").resolve())}
    if (meta.get("sha256") == digest and meta.get("parser") == PARSER_VERSION
            and meta.get("ocr_settings", legacy_ocr) == ocr_settings()):
        try:
            pages = _pages(stem)
            if len(pages) == meta.get("pages") and sorted(pages) == list(range(1, len(pages) + 1)):
                return [pages[n] for n in sorted(pages)]
        except (OSError, ValueError, KeyError):
            pass
    return None


def load_texts(stem, path, digest):
    """Use the same OCR provenance/cache behavior for uploads, library, reopen and CLI."""
    from .parse import page_texts, ocr_settings
    texts = cached_texts(stem, digest)
    parsing = {"ocr_pages": _meta(stem).get("ocr_pages", []), "ocr_settings": ocr_settings()}
    if texts is None:
        texts = page_texts(path, parsing)
    return texts, parsing


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
    key, mtime = str(p), (p.stat().st_mtime_ns, p.stat().st_size)
    if key not in _pages_cache or _pages_cache[key][0] != mtime:
        rows = (json.loads(l) for l in p.read_text(encoding="utf-8").split('\n') if l)  # not splitlines(): page text may hold U+2028
        _pages_cache[key] = (mtime, {r["page"]: r["text"] for r in rows})
    return _pages_cache[key][1]


# ---- writing -------------------------------------------------------------------------------

def save_report(stem: str, meta: dict, texts: list[str]) -> Path:
    """meta.json + pages.jsonl; no-op when the PDF's sha256 is already there."""
    with report_lock(stem):
        d = kb_dir() / stem
        from .parse import PARSER_VERSION
        meta = {**meta, "parser": PARSER_VERSION}
        if cached_texts(stem, meta["sha256"]) is not None:
            if _meta(stem) != meta:
                atomic_write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
            return d
        atomic_write(d / "pages.jsonl", "".join(json.dumps({"page": i, "text": t}, ensure_ascii=False) + "\n" for i, t in enumerate(texts, 1)))
        atomic_write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
        return d


def save_extraction(stem: str, section: str, extraction: dict) -> Path:
    p = kb_dir() / stem / "extractions" / f"{section}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with report_lock(stem):
        atomic_write(p, json.dumps(extraction, ensure_ascii=False, indent=2))
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
    from .extract import _value_in_quote
    from .maturity import verified_source
    pages = _pages(stem)
    texts = [pages[n] for n in sorted(pages)]
    out = [{"page": n, "start": s, "text": t} for n, text in sorted(pages.items()) for s, t in _windows(text)]
    meta = _meta(stem)
    who = f"{meta.get('company') or stem} FY{meta.get('fiscal_year') or '?'}"
    for p in sorted((kb_dir() / stem / "extractions").glob("*.json")):
        try:
            x = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(x, dict) or not isinstance(x.get("fields"), list):
                continue
        except (OSError, ValueError):
            continue  # broken saved facts must not prevent indexing source pages
        if any(not c.get("passed") and not c.get("detail", "").startswith("missing:") for c in x.get("checks", [])):
            continue
        if x.get("section") == "debt_maturity" and not x.get("context_source"):
            continue  # legacy debt extractions did not distinguish leases/parent-company scopes
        title = _title(x.get("section") or p.stem)
        for f in x.get("fields", []):
            if (f.get("value") is None or f.get("confidence", 0) < 0.7
                    or (meta.get("fiscal_year") and str(f.get("period")) != str(meta["fiscal_year"]))
                    or len(f.get("components", [])) > 1 or not verified_source(f.get("source"), texts, pages)):
                continue
            page, quote = f["source"].get("page"), f["source"].get("quote") or ""
            if not _value_in_quote(f["value"], quote):
                continue  # a computed amount cannot be cited as printed on its first component's page
            # sentence-ish wording embeds ~0.03 cosine closer to questions than "Label = value (p.N)" alone
            text = f"{who} · {title} (p.{page}): {f['label']} {f.get('period') or ''} = {_fmt(f['value'])} {f.get('unit') or ''}, printed as \"{f.get('raw_label') or f['label']}\"."
            if quote and quote != f.get("raw_label"):
                text += f' Verbatim: "{quote}"'  # so a citation quoting this chunk still exists on the page
            out.append({"page": page, "start": -1, "text": text})  # start -1 = fact, not a page offset
    return out


# ---- embeddings ----------------------------------------------------------------------------

def _unit(v: list[float]) -> list[float]:
    if not v or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in v) or not any(v):
        raise ValueError("Embedding endpoint returned an invalid vector")
    n = math.sqrt(_dot(v, v)) or 1.0
    return [round(x / n, 6) for x in v]


def embed(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    with OpenAI(base_url=embed_base_url(), api_key=os.getenv("EMBED_API_KEY") or os.getenv("LLM_API_KEY") or "none",
                timeout=float(os.getenv("EMBED_TIMEOUT", "120")), max_retries=0) as client:
        for i in range(0, len(texts), BATCH):
            batch = texts[i:i + BATCH]
            resp = client.embeddings.create(model=embed_model(), input=batch)
            data = sorted(resp.data, key=lambda d: d.index)
            if [d.index for d in data] != list(range(len(batch))):
                raise ValueError("Embedding endpoint returned an incomplete batch")
            out += [_unit(d.embedding) for d in data]
    return out


def _rows(stem: str) -> list[dict]:
    p = kb_dir() / stem / "embeddings.jsonl"
    key, mtime = str(p), (p.stat().st_mtime_ns, p.stat().st_size)
    if key not in _vecs or _vecs[key][0] != mtime:
        _vecs[key] = (mtime, [json.loads(l) for l in p.read_text(encoding="utf-8").split('\n') if l])
    return _vecs[key][1]


def index_dependencies(stem):
    d = kb_dir() / stem
    paths = [d / "meta.json", d / "pages.jsonl", *sorted((d / "extractions").glob("*.json"))]
    return {str(p.relative_to(d)): sha256(p.read_bytes()) for p in paths}


def embedding_identity():
    return {"embed_model": embed_model(), "provider": embed_base_url(), "chunker": CHUNKER_VERSION,
            "chunk_size": CHUNK, "overlap": OVERLAP}


def validate_rows(rows, dimensions):
    if not isinstance(dimensions, int) or dimensions <= 0:
        raise ValueError("Invalid vector dimensions")
    for row in rows:
        v = row["vec"]
        if (len(v) != dimensions or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in v)
                or not 0.98 < _dot(v, v) < 1.02 or not isinstance(row["text"], str)
                or not isinstance(row["page"], int) or row["page"] < 1
                or not isinstance(row["start"], int) or row["start"] < -1):
            raise ValueError("Invalid embedding row")


def index_status(stem):
    """Hash/validate once per file revision; repeated listings only stat the dependencies."""
    guard = report_lock(stem)
    if not guard.acquire(blocking=False):
        previous = _status_cache.get(str(kb_dir() / stem), (None, {}))[1]
        return {"embed_model": None, "dimensions": None, "chunks": 0, "page_chunks": 0,
                "fact_chunks": 0, "built_at": None, **previous,
                "status": "building", "reason": "Report update in progress"}
    try:
        d = kb_dir() / stem
        paths = [d / n for n in ("meta.json", "pages.jsonl", "embeddings.jsonl", "index.json")]
        paths += sorted((d / "extractions").glob("*.json"))
        signature = (fingerprint(embedding_identity()), tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.exists()))
        key = str(d)
        if key not in _status_cache or _status_cache[key][0] != signature:
            _status_cache[key] = (signature, _index_status(stem))
        return dict(_status_cache[key][1])
    finally:
        guard.release()


def _index_status(stem):
    with report_lock(stem):
        d = kb_dir() / stem
        status = {"status": "missing", "reason": "No embeddings built", "embed_model": None,
                  "dimensions": None, "chunks": 0, "page_chunks": 0, "fact_chunks": 0, "built_at": None}
        if not (d / "embeddings.jsonl").exists():
            return status
        if not (d / "index.json").exists():
            return status | {"status": "outdated", "reason": "Legacy index has no model metadata; rebuild required"}
        try:
            m = json.loads((d / "index.json").read_text(encoding="utf-8"))
            status.update({k: m[k] for k in ("embed_model", "dimensions", "chunks", "page_chunks", "fact_chunks", "built_at")})
            if sha256((d / "embeddings.jsonl").read_bytes()) != m["content_sha256"]:
                raise ValueError("Embedding file does not match its manifest")
            rows = _rows(stem)
            validate_rows(rows, m["dimensions"])
            if len(rows) != m["chunks"]:
                raise ValueError("Chunk count does not match manifest")
            if any(m.get(k) != v for k, v in embedding_identity().items()) or m["sources"] != index_dependencies(stem):
                return status | {"status": "outdated", "reason": "Model, sources or chunk settings changed"}
            return status | {"status": "ready", "reason": "Index matches current sources and model"}
        except (OSError, ValueError, KeyError, TypeError) as e:
            return status | {"status": "invalid", "reason": str(e)}


def index(stem: str, force=False) -> dict:
    """One-process demo: serialize each report and never reuse incompatible vectors."""
    with report_lock(stem):
        d = kb_dir() / stem
        status = index_status(stem)
        if not force and status["status"] == "ready":
            return status | {"cached": True}
        identity, sources = embedding_identity(), index_dependencies(stem)
        old = {}
        if not force and status["status"] in {"ready", "outdated"} and (d / "index.json").exists():
            m = json.loads((d / "index.json").read_text(encoding="utf-8"))
            if all(m.get(k) == v for k, v in identity.items()):
                old = {r["text"]: r["vec"] for r in _rows(stem)}
        rows = chunks(stem)
        if not rows:
            raise ValueError("Report contains no indexable text. A scanned PDF requires OCR.")
        todo = list(dict.fromkeys(r["text"] for r in rows if r["text"] not in old))
        vectors = embed(todo) if todo else []
        if len(vectors) != len(todo):
            raise ValueError("Embedding endpoint returned the wrong number of vectors")
        fresh = dict(zip(todo, vectors))
        for r in rows:
            r["vec"] = old.get(r["text"]) or fresh[r["text"]]
        dimensions = len(rows[0]["vec"]) if rows else 0
        validate_rows(rows, dimensions)
        if sources != index_dependencies(stem):
            raise ValueError("Report changed during indexing; retry")
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        manifest = {**identity, "sources": sources, "dimensions": dimensions, "chunks": len(rows),
                    "page_chunks": sum(r["start"] >= 0 for r in rows), "fact_chunks": sum(r["start"] == -1 for r in rows),
                    "built_at": datetime.now(timezone.utc).isoformat(), "content_sha256": sha256(content.encode())}
        # Publish data first. A crash between replacements yields an invalid index, never a false cache hit.
        embedding_path = d / "embeddings.jsonl"
        previous = embedding_path.read_text(encoding="utf-8") if embedding_path.exists() else None
        try:
            atomic_write(embedding_path, content)
            atomic_write(d / "index.json", json.dumps(manifest, indent=2))
        except OSError:
            if previous is None:
                embedding_path.unlink(missing_ok=True)
            else:
                atomic_write(embedding_path, previous)
            raise
        _vecs.pop(str(d / "embeddings.jsonl"), None)
        return index_status(stem) | {"cached": False}


def inspect_chunks(stem, query="", offset=0, limit=25):
    with report_lock(stem):
        path = kb_dir() / stem / "embeddings.jsonl"
        rows = _rows(stem) if path.exists() else []
        hits = [{k: r[k] for k in ("page", "start", "text")} | {"kind": "fact" if r["start"] == -1 else "page"}
                for r in rows if query.casefold() in r["text"].casefold()]
        return {"items": hits[offset:offset + limit], "total": len(hits), "offset": offset, "limit": limit}


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
        with report_lock(stem):
            index(stem)
            rows = _rows(stem)
        if any(len(r["vec"]) != len(q) for r in rows):
            raise ValueError("Query and index vector dimensions differ; rebuild the index")
        for r in rows:
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


def ask(stems: list[str], question: str, k=8, ids: dict[str, str] | None = None) -> dict:
    """Answer dict per docs/API.md. ids maps stem -> report_id (defaults to the stem)."""
    from .extract import call_llm  # lazy: extract imports us for few-shot
    ids = ids or {}
    metas = {s: _meta(s) for s in stems}
    label = {s: f"{m.get('company') or s} FY{m.get('fiscal_year') or '?'}" for s, m in metas.items()}
    hits = search(stems, question, k)
    user = (f"Question: {question}\n\nQuotes must be copied character for character from one excerpt (a line break may become a "
            f"space; keep note numbers and every token between label and figure).\n\nExcerpts:\n"
            + "\n\n".join(f"[report ID: {h['stem']}; {label[h['stem']]} p.{h['page']}]\n{h['text']}" for h in hits))
    warnings: list[str] = []
    try:
        raw = call_llm(ASK_SYSTEM, user, ANSWER_SCHEMA, "answer")
        if not isinstance(raw, dict) or not isinstance(raw.get("answer"), str) or not isinstance(raw.get("citations"), list):
            raise ValueError("Answer response must contain answer text and a citations array")
    except Exception as e:  # ponytail: no retry, same as extract
        raw, warnings = {"answer": "", "citations": []}, [f"llm: {type(e).__name__}: {e}"]

    citations, seen = [], set()
    for c in raw.get("citations") or []:
        if not isinstance(c, dict):
            warnings.append("citation dropped: malformed citation")
            continue
        stem, page, quote = c.get("report"), c.get("page"), c.get("quote")
        if not isinstance(stem, str) or stem not in metas:
            warnings.append(f"citation dropped: unknown report ID {stem!r}")
            continue
        norm = lambda text: re.sub(r"\s+", " ", text).strip()
        if (type(page) is not int or not isinstance(quote, str) or not quote.strip()
                or norm(quote) not in norm(_pages(stem).get(page, ""))
                or not any(h["stem"] == stem and h["page"] == page and norm(quote) in norm(h["text"]) for h in hits)):
            warnings.append(f"citation dropped: {stem} p.{page} quote not in the retrieved source")
            continue
        if (stem, page, quote) in seen:
            continue
        seen.add((stem, page, quote))
        score = max((h["score"] for h in hits if h["stem"] == stem and h["page"] == page), default=0)
        citations.append({"report_id": ids.get(stem, stem), "company": metas[stem].get("company"), "fiscal_year": metas[stem].get("fiscal_year"),
                          "page": page, "quote": quote, "score": round(min(score, 1.0), 3)})
    answer = raw.get("answer") or ""
    if any(w.startswith("citation dropped:") for w in warnings):
        answer = "Answer withheld because its citations could not all be verified. Try a more specific question."
    elif answer and not citations:
        warnings.append("No source citations were verified for this answer.")
    return {"question": question, "answer": answer, "citations": citations, "warnings": warnings,
            "model": runtime.model()}


# ---- listing / few-shot --------------------------------------------------------------------

def entries() -> list[dict]:
    """KbEntry[] minus report_id (app.py fills it from its registry)."""
    out = []
    for d in sorted(p for p in kb_dir().glob("*") if (p / "meta.json").exists()):
        m = _meta(d.name)
        out.append({"stem": d.name, "report_id": None, "company": m.get("company"), "fiscal_year": m.get("fiscal_year"),
                    "pages": m.get("pages", 0), "sections": sorted(p.stem for p in (d / "extractions").glob("*.json")),
                    **index_status(d.name)})
        out[-1]["indexed"] = out[-1]["status"] == "ready"
    return out


def fewshot_examples(section: str, exclude_stem: str | None, n: int) -> list[dict]:
    """Up to n prior extractions of `section` from other stems with all checks passed and no warnings,
    compacted to {company, fields: [{key, raw_label, value, unit, period, page}]}."""
    out = []
    for p in sorted(kb_dir().glob(f"*/extractions/{section}.json")):
        stem = p.parent.parent.name
        if stem == exclude_stem or len(out) >= n:
            continue
        try:
            x = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(x, dict) or not isinstance(x.get("fields"), list):
                continue
        except (OSError, ValueError):
            continue
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
    lib = HERE.parent / "data" / "reports"
    for e in json.loads((lib / "index.json").read_text(encoding="utf-8")):
        pdf = lib / e["file"]
        if not pdf.exists():
            continue
        stem, t0 = pdf.stem, time.time()
        digest = sha256(pdf.read_bytes())
        texts, parsing = load_texts(stem, pdf, digest)
        meta = {k: e.get(k) for k in ("company", "fiscal_year", "language", "source_url")} | {"pages": len(texts), "sha256": digest, "filename": e["file"]}
        save_report(stem, meta | parsing, texts)
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
