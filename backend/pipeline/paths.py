"""The one place that resolves data/resource paths, dev tree or PyInstaller onedir build alike.

Two roots:
  resource_dir() -- read-only, bundled with the app: schemas/, fixtures/. backend/ in dev,
                    sys._MEIPASS (the onedir build's _internal/) when frozen.
  data_dir()     -- read-write, per-install: reports cache, KB, uploads, backend.log. ARP_DATA_DIR
                    if set, else a `data/` folder next to the repo root (dev) or next to the exe
                    (frozen) -- resource_dir().parent plays both roles.

KB_DIR keeps its pre-existing standalone meaning (a path resolved against resource_dir(), not
data_dir()) for backward compatibility with the documented .env override.
"""
import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent  # backend/


def schemas_dir() -> Path:
    return resource_dir() / "schemas"


def fixture_path() -> Path:
    return resource_dir() / "fixtures" / "sample_extraction.json"


def data_dir() -> Path:
    env = os.getenv("ARP_DATA_DIR")
    if env:
        return Path(env).resolve()
    return (resource_dir().parent / "data").resolve()


def tessdata_dir() -> Path:
    """Tesseract language files, in explicit-override -> package -> writable-data order.

    The desktop bundle places them at ``resources/tessdata``.  A frozen backend lives two
    directories below that (``resources/backend/_internal``), while source checkouts keep the
    optional developer copy under ``data/tessdata``. That copy is committed to the
    repository (tessdata_fast, Apache-2.0), so in a source checkout the writable candidate below
    *is* the repo's own language packs -- no download step. The explicit override is
    authoritative; an automatic package candidate only wins when it contains every requested
    language file: an incomplete bundled copy must not hide a complete one already in
    writable user data.
    """
    env = Path(os.environ["TESSDATA_PREFIX"]).resolve() if os.getenv("TESSDATA_PREFIX") else None
    if env is not None:  # a user-supplied override remains authoritative, including for diagnostics
        return env
    bundled = None
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = resource_dir().parent.parent / "tessdata"
    writable = (data_dir() / "tessdata").resolve()
    languages = [lang for lang in os.getenv("OCR_LANGUAGE", "eng+swe").split("+") if lang]
    candidates = [candidate.resolve() for candidate in (bundled, writable) if candidate is not None]
    for candidate in candidates:
        if all((candidate / f"{language}.traineddata").is_file() for language in languages):
            return candidate
    # Keep the old diagnostic target when no usable copy exists: an explicit override remains the
    # path named in the missing-files error; otherwise writable data is where setup/repair installs.
    return writable


def reports_dir() -> Path:
    return data_dir() / "reports"


def companies_path() -> Path:
    return data_dir() / "companies.json"


def kb_dir() -> Path:
    env = os.getenv("KB_DIR")
    if env:
        return (resource_dir() / env).resolve()
    return (data_dir() / "kb").resolve()


def uploads_dir() -> Path:
    d = data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d
