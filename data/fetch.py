"""Download the bundled annual reports listed in reports/index.json (PDFs are gitignored). Run once after clone."""
import json
import urllib.request
from pathlib import Path

REPORTS = Path(__file__).parent / "reports"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

for entry in json.loads((REPORTS / "index.json").read_text(encoding="utf-8")):
    dest = REPORTS / entry["file"]
    if dest.exists():
        print(f"skip  {dest.name} ({dest.stat().st_size // 1_000_000} MB, exists)")
        continue
    try:
        req = urllib.request.Request(entry["source_url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        print(f"ok    {dest.name} ({dest.stat().st_size // 1_000_000} MB)")
    except Exception as e:  # keep going, teammates can grab the rest by hand
        print(f"FAIL  {dest.name}: {e}")
