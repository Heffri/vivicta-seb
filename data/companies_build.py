"""Build companies.json from Nasdaq's Nordic screener API (main market + First North, Stockholm).
Run: python data/companies_build.py. Share classes (Volvo A/B) collapse to one row, most-traded class kept."""
import json
import re
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
API = "https://api.nasdaq.com/api/nordic/screener/shares?market=STO&tableonly=false&size=1000&category={cat}"
SEGMENTS = [("MAIN_MARKET", "LARGE_CAP", "Large Cap"), ("MAIN_MARKET", "MID_CAP", "Mid Cap"),
            ("MAIN_MARKET", "SMALL_CAP", "Small Cap"), ("FIRST_NORTH", "", "First North")]
CLASS = re.compile(r"\s+(A|B|C|D|R|SDB|Pref)$")  # share-class suffixes


def num(s):  # "1,234" -> 1234.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


def main():
    best = {}
    for cat, seg, label in SEGMENTS:
        req = urllib.request.Request(API.format(cat=cat) + (f"&segment={seg}" if seg else ""), headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.load(r)["data"]["instrumentListing"]["rows"]
        for r in rows:
            name = CLASS.sub("", r["fullName"]).strip()
            key = name.lower()
            if key not in best or num(r["turnover"]) > best[key][0]:
                best[key] = (num(r["turnover"]), {"name": name, "ticker": r["symbol"], "sector": r["sector"] or None,
                                                  "isin": r["isin"] or None, "market": label})
        print(f"{label}: {len(rows)} rows")
    out = sorted((v for _, v in best.values()), key=lambda c: c["name"].lower())
    Path(__file__).with_name("companies.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(out)} companies")


if __name__ == "__main__":
    main()
