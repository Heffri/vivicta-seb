# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for backend.exe (onedir: fast cold start, easy to inspect/patch).
Build via `python build_exe.py` from backend/ (wraps `pyinstaller backend.spec`), or directly:
`pyinstaller backend.spec`. Output: dist/backend/backend.exe + dist/backend/_internal/.

Bundles schemas/ + fixtures/ as read-only resources -- pipeline/paths.py's resource_dir() finds them
via sys._MEIPASS at runtime. Never bundles data/: the desktop shell (see docs/acrylic/evidence/v030.md)
points ARP_DATA_DIR at a per-user folder it copies data/companies.json, data/reports/index.json, and
data/kb/ into instead.
"""
from PyInstaller.utils.hooks import collect_data_files

hidden_imports = [
    # uvicorn resolves its loop/protocol implementations by dotted-string import at runtime (see the explicit
    # loop="asyncio", http="h11", ws="none" passed to uvicorn.run() in app.py:main), invisible to static analysis
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "multipart",  # python-multipart's import name; UploadFile parsing
    "dotenv",
    "pptx",
    "openai",
]

datas = [
    ("schemas", "schemas"),
    ("fixtures", "fixtures"),
]
datas += collect_data_files("pymupdf")  # font/ICC resources pymupdf ships as package data
datas += collect_data_files("pptx")     # default.pptx template python-pptx builds new decks from

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # keep a real stdout/stderr: the desktop shell manages/hides the window itself
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="backend",
)
