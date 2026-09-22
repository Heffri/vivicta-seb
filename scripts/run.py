"""One-click dev launcher: sets up and runs the Annual Report Parser from a clean clone.

    python scripts/run.py [--reinstall]

Checks Python/Node versions, creates backend/.venv and installs backend/requirements.txt on first
run (skipped if already there), runs `npm ci` and `npm run build` for the frontend on first run or
when frontend/dist is missing/stale (skipped otherwise), then starts the backend as a single process
that also serves the built frontend (FRONTEND_DIST) on one port -- same origin, no proxy, no CORS --
and opens it in a browser. Ctrl+C stops it and kills the backend process it started.

Wrapped by run.bat (Windows) / run.sh (mac/Linux) at the repo root -- see README.md "Install / run".
--reinstall recreates backend/.venv and frontend/node_modules and rebuilds frontend/dist.

Model provider: unset by default -> the backend answers with fixture data (no model calls, ever from
this script). Add a .env file at the repo root (same variables as backend/.env.example, e.g.
LLM_PROVIDER=codex/claude, or LLM_BASE_URL+LLM_API_KEY for an OpenAI-compatible endpoint) to point it
at a real model -- python-dotenv's own upward search from backend/app.py finds it there once
backend/.env itself doesn't exist, no extra wiring needed here.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 18
DEFAULT_PORT = 8000
PORT_TRIES = 20
HEALTH_TIMEOUT = 60.0

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = BACKEND_DIR / ".venv"
NODE_MODULES = FRONTEND_DIR / "node_modules"
DIST_DIR = FRONTEND_DIR / "dist"

FRONTEND_SOURCE_FILES = ("package.json", "vite.config.ts", "index.html", "tsconfig.json", "tsconfig.app.json", "components.json")


def log(msg: str) -> None:
    print(f"[run] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"[run] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / "Scripts" / "python.exe" if os.name == "nt" else venv_dir / "bin" / "python"


def check_python_version() -> None:
    if sys.version_info[:2] < MIN_PYTHON:
        have = f"{sys.version_info.major}.{sys.version_info.minor}"
        fail(
            f"Python {have} found; this project needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer. "
            "Install it from https://www.python.org/downloads/ and re-run this script."
        )


def check_node() -> tuple[str, str]:
    node = shutil.which("node")
    if not node:
        fail("Node.js was not found on PATH. Install Node 18 or newer from https://nodejs.org/ and re-run this script.")
    try:
        out = subprocess.run([node, "--version"], capture_output=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    except Exception as exc:
        fail(f"could not run 'node --version' ({exc}). Install Node 18 or newer from https://nodejs.org/ and re-run this script.")
    major_text = out.lstrip("v").split(".", 1)[0]
    major = int(major_text) if major_text.isdigit() else 0
    if major < MIN_NODE_MAJOR:
        fail(f"Node {out} found; this project needs Node {MIN_NODE_MAJOR}+. Install it from https://nodejs.org/ and re-run this script.")
    return node, out


def find_npm() -> str:
    npm = shutil.which("npm")
    if not npm:
        fail("npm was not found on PATH (it ships with Node.js). Install Node 18+ from https://nodejs.org/ and re-run this script.")
    return npm


def run_step(cmd: list[str], cwd: Path, use_shell: bool = False) -> None:
    log(f"$ {' '.join(cmd)}  (in {cwd.relative_to(ROOT)}/)")
    result = subprocess.run(cmd, cwd=str(cwd), shell=use_shell)
    if result.returncode != 0:
        fail(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


def newest_mtime(root: Path) -> float:
    newest = 0.0
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
    return newest


def dist_is_stale() -> bool:
    if not (DIST_DIR / "index.html").exists():
        return True
    src_mtime = newest_mtime(FRONTEND_DIR / "src")
    for name in FRONTEND_SOURCE_FILES:
        f = FRONTEND_DIR / name
        if f.exists():
            src_mtime = max(src_mtime, f.stat().st_mtime)
    return src_mtime > newest_mtime(DIST_DIR)


def ensure_backend(system_python: str, reinstall: bool) -> Path:
    if reinstall and VENV_DIR.exists():
        log("--reinstall: removing backend/.venv")
        shutil.rmtree(VENV_DIR)
    vpy = venv_python(VENV_DIR)
    if vpy.exists():
        log("backend/.venv found, skipping install (use --reinstall to force)")
        return vpy
    log("backend/.venv not found, creating it ...")
    run_step([system_python, "-m", "venv", str(VENV_DIR)], cwd=BACKEND_DIR)
    log("installing backend dependencies ...")
    run_step([str(vpy), "-m", "pip", "install", "-r", "requirements.txt"], cwd=BACKEND_DIR)
    return vpy


def ensure_frontend(npm: str, reinstall: bool) -> None:
    windows_shell = os.name == "nt"  # npm[.cmd] is a shim on Windows; CreateProcess needs a shell to run it (see desktop/main.js)
    if reinstall:
        if NODE_MODULES.exists():
            log("--reinstall: removing frontend/node_modules")
            shutil.rmtree(NODE_MODULES)
        if DIST_DIR.exists():
            log("--reinstall: removing frontend/dist")
            shutil.rmtree(DIST_DIR)
    if NODE_MODULES.exists():
        log("frontend/node_modules found, skipping npm ci (use --reinstall to force)")
    else:
        log("frontend/node_modules not found, running npm ci ...")
        run_step([npm, "ci"], cwd=FRONTEND_DIR, use_shell=windows_shell)
    if dist_is_stale():
        log("frontend/dist missing or older than the source, building ...")
        run_step([npm, "run", "build"], cwd=FRONTEND_DIR, use_shell=windows_shell)
    else:
        log("frontend/dist found and up to date, skipping build")


def find_open_port(start: int, tries: int) -> int:
    port = start
    for _ in range(tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    fail(f"could not find a free port in {start}..{start + tries - 1}")


def note_env_status() -> None:
    if (ROOT / ".env").exists():
        log("found .env in the repo root -- it configures the model provider.")
    else:
        log("no .env in the repo root -> fixture mode (canned demo data, no model calls).")
        log("to use a real model: add a .env file here, e.g. LLM_PROVIDER=codex (or claude), or")
        log("LLM_PROVIDER=openai + LLM_BASE_URL + LLM_API_KEY. See README.md / backend/README.md.")
        log("Or, in the desktop build, use the Settings tab to pick a provider.")


def wait_for_health(port: int, proc: subprocess.Popen) -> bool:
    url = f"http://127.0.0.1:{port}/api/config"
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def print_mode_banner(port: int) -> None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=3) as resp:
            cfg = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return  # best-effort only; wait_for_health() already confirmed the backend is up
    if cfg.get("llm"):
        log(f"model provider: {cfg.get('provider')} (model: {cfg.get('model')}) -- extraction and Ask call it for real.")
    else:
        log("no model configured -> fixture mode (canned demo data, no model calls).")


def start_backend(vpy: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["FRONTEND_DIST"] = str(DIST_DIR)  # single-port hosting: backend serves the built frontend too (app.py)
    kwargs = {} if os.name == "nt" else {"start_new_session": True}  # POSIX: own process group, so kill_process_tree() can killpg it alone
    return subprocess.Popen(
        [str(vpy), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(BACKEND_DIR),
        env=env,
        **kwargs,
    )


def kill_process_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/pid", str(proc.pid), "/t", "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reinstall", action="store_true", help="recreate backend/.venv and frontend/node_modules, rebuild frontend/dist, then continue")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    check_python_version()
    node, node_version = check_node()
    npm = find_npm()
    log(f"repo: {ROOT}")
    log(f"python {sys.version.split()[0]}, node {node_version}, npm at {npm}")

    note_env_status()

    already_set_up = venv_python(VENV_DIR).exists() and NODE_MODULES.exists() and not dist_is_stale()
    if args.reinstall or not already_set_up:
        log("first run can take 2-4 minutes (venv + pip install + npm ci + build); later runs take a few seconds.")

    vpy = ensure_backend(sys.executable, args.reinstall)
    ensure_frontend(npm, args.reinstall)

    port = find_open_port(DEFAULT_PORT, PORT_TRIES)
    if port != DEFAULT_PORT:
        log(f"port {DEFAULT_PORT} is busy, using {port} instead")

    log(f"starting the backend on 127.0.0.1:{port} (serving the built frontend from the same port) ...")
    proc = start_backend(vpy, port)
    try:
        if not wait_for_health(port, proc):
            fail(f"the backend did not respond on :{port} within {int(HEALTH_TIMEOUT)}s; see the output above for errors.")
        print_mode_banner(port)
        url = f"http://127.0.0.1:{port}/"
        log(f"ready: {url}")
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            log(f"could not open a browser automatically -- open {url} manually.")
        log("press Ctrl+C to stop.")
        return proc.wait()
    except KeyboardInterrupt:
        log("Ctrl+C received, stopping ...")
        return 0
    finally:
        kill_process_tree(proc)


if __name__ == "__main__":
    sys.exit(main())
