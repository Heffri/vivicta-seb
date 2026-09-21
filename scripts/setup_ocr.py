"""Download official Tesseract fast English/Swedish data for PyMuPDF's local OCR."""
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1] / "data" / "tessdata"
root.mkdir(parents=True, exist_ok=True)
for name in ("eng.traineddata", "swe.traineddata", "LICENSE"):
    path = root / name
    if not path.exists():
        data = urllib.request.urlopen(f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{name}", timeout=120).read()
        temp = path.with_suffix(".tmp")
        temp.write_bytes(data)
        temp.replace(path)
    print(path)
