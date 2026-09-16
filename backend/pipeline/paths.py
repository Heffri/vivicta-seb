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
