"""Ensure PyMuPDF's local OCR has the official Tesseract fast language files.

eng.traineddata, swe.traineddata and their Apache-2.0 LICENSE are committed under
data/tessdata (tessdata_fast), so a normal clone already has them and this script is
a no-op. It stays for repair installs (deleted/corrupted files) and any additional
language: name files after their <lang> code and extend the tuple below.
"""
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1] / "data" / "tessdata"
root.mkdir(parents=True, exist_ok=True)
for name in ("eng.traineddata", "swe.traineddata", "LICENSE"):
    path = root / name
    if path.exists():
        print(f"{path}: already present, nothing to download")
        continue
    data = urllib.request.urlopen(f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{name}", timeout=120).read()
    temp = path.with_suffix(".tmp")
    temp.write_bytes(data)
    temp.replace(path)
    print(f"{path}: downloaded")
