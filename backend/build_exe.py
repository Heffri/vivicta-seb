"""Build backend.exe (onedir). From backend/: pip install -r requirements-build.txt, then python build_exe.py.
Output: dist/backend/backend.exe + dist/backend/_internal/ (what's bundled: backend.spec)."""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent


def main() -> None:
    os.chdir(HERE)  # backend.spec's relative paths (app.py, schemas/, fixtures/) are resolved from here
    PyInstaller.__main__.run(["backend.spec", "--noconfirm"])
    exe = HERE / "dist" / "backend" / "backend.exe"
    if not exe.exists():
        print("build finished but dist/backend/backend.exe was not found", file=sys.stderr)
        sys.exit(1)
    size_mb = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file()) / 1_000_000
    print(f"built {exe} ({size_mb:.0f} MB onedir)")


if __name__ == "__main__":
    main()
