"""Run: python scripts/check_codex_discovery.py (Windows, Python + Node only)."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Load only discovery: no OpenAI dependency or Electron window needed.
source = ast.parse((ROOT / "backend/pipeline/llm.py").read_text(encoding="utf-8"))
function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "_codex_executable")
import shutil
namespace = {"os": os, "Path": Path, "shutil": shutil}
exec(compile(ast.Module(body=[function], type_ignores=[]), "llm.py", "exec"), namespace)

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    bin_dir = home / "AppData/Local/OpenAI/Codex/bin"
    old = bin_dir / "old/codex.exe"
    newest = bin_dir / "new/codex.exe"
    for file, timestamp in [(old, 1000), (newest, 2000)]:
        file.parent.mkdir(parents=True)
        file.touch()
        os.utime(file, (timestamp, timestamp))
    (bin_dir / "incomplete").mkdir()
    with patch.dict(os.environ, {"CODEX_BIN": ""}), patch.object(Path, "home", return_value=home), patch.object(shutil, "which", return_value=None):
        assert namespace["_codex_executable"]() == str(newest)
        flat = bin_dir / "codex.exe"
        flat.touch()
        assert namespace["_codex_executable"]() == str(flat)
        flat.unlink()
        with patch.dict(os.environ, {"CODEX_BIN": "explicit-override"}):
            assert namespace["_codex_executable"]() == "explicit-override"
        with patch.object(shutil, "which", return_value="from-path"):
            assert namespace["_codex_executable"]() == "from-path"
    subprocess.run(["node", "-e", r"""
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const assert = require('node:assert/strict')
const source = fs.readFileSync(process.argv[1], 'utf8')
const start = source.indexOf('function codexExecutable() {')
const end = source.indexOf('function runCapture(', start)
let onPath = null
const context = { fs, path, isWindows: true, process: {env: {}},
  app: {getPath: () => process.argv[2]}, findOnPath: () => onPath }
vm.createContext(context)
vm.runInContext(source.slice(start, end), context)
assert.equal(context.codexExecutable(), process.argv[3])
const flat = path.join(path.dirname(path.dirname(process.argv[3])), 'codex.exe')
fs.writeFileSync(flat, '')
assert.equal(context.codexExecutable(), flat)
fs.unlinkSync(flat)
onPath = 'from-path'
assert.equal(context.codexExecutable(), 'from-path')
context.process.env.CODEX_BIN = 'explicit-override'
assert.equal(context.codexExecutable(), 'explicit-override')
""", str(ROOT / "desktop/main.js"), str(home), str(newest)], check=True)
print("Codex discovery passed for desktop and backend: versioned, flat, PATH, override.")
