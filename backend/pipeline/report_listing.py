"""Read report listings from HTML without executing a site's download scripts.

A listing is evidence of availability, not a validated PDF. Require the requested
issuer in the page title/heading and a report/year label beside a download action.
"""
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from . import collection

REPORT = r"(?:annual\s+(?:(?:and\s+sustainability|financial)\s+)?(?:reports?|accounts)|[åa]rsredovisning(?:ar)?|[åa]rsrapport(?:er)?|Form\s+10-K)"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)
    hidden: bool = False

    def text(self):
        if self.hidden:
            return ""
        return " ".join(p.text() if isinstance(p, Node) else p for p in self.parts).strip()

    def actions(self):
        if self.hidden:
            return False
        label = self.text() if self.tag in {"a", "button", "input"} else ""
        download = bool(re.search(rf"download|ladda ner|h[äa]mta|(?:open|view|get)\s+(?:report|accounts)|{REPORT}", label, re.I))
        if self.tag == "a":
            download = download or ".pdf" in (self.attrs.get("href") or "").lower() or "download" in self.attrs or self.attrs.get("type") == "application/pdf"
        return download or any(p.actions() for p in self.parts if isinstance(p, Node))


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        node.hidden = self.stack[-1].hidden or tag in {"script", "style", "template", "noscript"} or "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true"
        self.stack[-1].parts.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].parts.append(data)


def http_url(base, href):
    try:
        url = urljoin(base, href)
        parsed = urlsplit(url)
    except (ValueError, TypeError):
        return None
    return url if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password else None


def issuer_heading(text, company):
    # Full heading segments only: mentioning a holding in a parent's body is insufficient.
    key = collection.identity(company)
    for part in re.split(r"\s+[|–—-]\s+|\s*[|]\s*", text):
        part = re.sub(rf"^(?:{REPORT}|financial reports?|reports)\s+(?:for\s+)?|\s+(?:{REPORT}|financial reports?|reports)$", "", part, flags=re.I).strip()
        if key and collection.identity(part) == key:
            return True
    return False


def inspect(url, html, company, year):
    """Return a verified HTML listing, or None; model claims alone never qualify."""
    if not http_url(url, url):
        return None
    document = Document(html)
    headings = [re.sub(r"\s+", " ", n.text()) for n in document.nodes if n.tag in {"h1", "title"}]
    if not any(issuer_heading(text, company) for text in headings):
        return None
    report_year = re.compile(rf"(?:{REPORT})\s*(?:for\s+)?(?:FY\s*)?[:–—-]?\s*{year}(?!\d)|(?<!\d){year}\s*[:–—-]?\s*(?:{REPORT})", re.I)
    for node in document.nodes:
        if node.tag not in {"a", "button", "li", "tr", "div", "section", "p", "article"}:
            continue
        text = re.sub(r"\s+", " ", node.text())
        if len(text) > 400 or not node.actions() or not (match := report_year.search(text)):
            continue
        if re.search(r"will\s+(?:be\s+)?publish|coming soon|not (?:yet )?available|unavailable|kommer att|publiceras|ej tillg[äa]nglig|interim|sustainability report|h[åa]llbarhetsrapport", text, re.I):
            continue
        return {"url": url, "company": company, "fiscal_year": year, "title": match.group(0),
                "evidence": text[:400], "access": "manual_download"}
    return None
