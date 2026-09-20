#!/usr/bin/env bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

if command -v python3 >/dev/null 2>&1; then
    PYEXE=python3
elif command -v python >/dev/null 2>&1; then
    PYEXE=python
else
    echo "Python was not found on PATH."
    echo "Install Python 3.11 or newer from https://www.python.org/downloads/ and re-run this script."
    exit 1
fi

exec "$PYEXE" scripts/run.py "$@"
