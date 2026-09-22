"""Document-grounded reporting periods and audited accounts in registration filings."""
import re

from . import collection

FIELDS = ("document_type", "statement_pages", "source_notice")
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
YEAR = r"(?:19|20)\d{2}"
REGISTRATION = re.compile(r"\bFORM\s+(?:S-[14]|F-[14])(?:/A)?\b|\bPROSPECTUS\b", re.I)
AUDIT = re.compile(r"report of independent (?:registered public accountants?|registered public accounting firm|auditors?)", re.I)


class ValidatedText(str):
    """Keep fetch's text return compatible while carrying verified source metadata."""
    def __new__(cls, text, **metadata):
        instance = super().__new__(cls, text)
        instance.metadata = metadata
        return instance


def declared_year(head):
    """Prefer the document's explicit period to publication dates or comparative figures."""
    flat = " ".join(head.split())
    period = re.search(
        rf"for the (?:fiscal |financial )?year ended\s+(?:{MONTH}\s+\d{{1,2}},?\s+|\d{{1,2}}\s+{MONTH}\s+|)({YEAR})(?:-\d{{2}}-\d{{2}})?\b",
        flat, re.I)
    if period:
        return int(period[1])
    title = r"(?:annual\s+(?:(?:and|&)\s+sustainability\s+)?report|årsredovisning|arsredovisning)"
    # Only a tight title/year pair, not a year somewhere in the contents or shareholder letter.
    before = re.search(rf"^\s*({YEAR})\s+{title}\b", head, re.I | re.M)
    if before:
        return int(before[1])
    match = re.search(rf"{title}\s*[:–—-]?\s*({YEAR})(?:\s*/\s*(\d{{2}}|{YEAR}))?\b", flat, re.I)
    if match:
        end = match[2]
        return (int(end) if len(end) == 4 else int(match[1]) // 100 * 100 + int(end)) if end else int(match[1])
    return None


def historical_accounts(texts, company, year):
    """Verify an issuer-specific audit opinion plus annual balance/income statements.

    Return only the audited section, stopping at another audit or an interim appendix.
    No model's claim, comparative mention, or year on the prospectus cover suffices.
    """
    wanted = collection.identity(company)
    for start, text in enumerate(texts):
        flat = " ".join(text.split())
        heading = AUDIT.search(flat[:450])
        if not heading or not re.search(r"\bwe have audited\b", flat, re.I):
            continue
        opinion = re.search(r"\bwe have audited\b(.{0,1800})", flat, re.I)
        body = opinion[1] if opinion else ""
        # The name must belong to the audit opinion, not another issuer in the filing.
        if not wanted or not re.search(r"\b" + re.escape(wanted) + r"\b", collection.normalize(body)):
            continue
        if not re.search(rf"\b{year}\b", body) or not re.search(r"balance sheets?.*statements? of (?:operations|income|earnings)", body, re.I):
            continue
        end = len(texts)
        for i in range(start + 1, len(texts)):
            opening = " ".join(texts[i].split())[:650]
            if AUDIT.search(opening[:450]) or re.search(r"(?:condensed consolidated|consolidated) (?:financial statements|balance sheets).*unaudited", opening, re.I):
                end = i
                break
            if re.search(r"^\s*(?:Table of Contents\s*)?(?:PART II|SIGNATURES|EXHIBIT INDEX)\b", opening, re.I):
                end = i
                break
        opening_pages = [" ".join(t.split()) for t in texts[start:min(end, start + 12)]]
        def statement(pattern):
            return any(re.search(pattern, t[:1000], re.I) and re.search(rf"\b{year}\b", t[:1800])
                       and not AUDIT.search(t[:450])
                       and "unaudited" not in t[:1000].lower() for t in opening_pages)
        if not statement(r"consolidated balance sheets") or not statement(r"consolidated statements of (?:operations|income|earnings)"):
            continue
        return {"document_type": "registration_statement", "statement_pages": list(range(start + 1, end + 1)),
                "source_notice": f"FY{year} audited accounts from a registration statement/prospectus, not a standalone annual report. Original PDF page numbers are preserved."}
    return None


def extraction_texts(texts, metadata):
    """Mask unrelated prospectus sections while preserving original page indices."""
    if metadata.get("document_type") != "registration_statement":
        return texts
    allowed = set(metadata.get("statement_pages") or [])
    return [text if i in allowed else "" for i, text in enumerate(texts, 1)]
