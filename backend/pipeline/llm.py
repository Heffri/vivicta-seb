"""One model call, two backends: openai_compatible (Ollama's native /api/chat, or any real
OpenAI-compatible /v1 -- Azure, OpenAI, OpenRouter) and codex_cli (shells out to a local `codex`
install non-interactively, for teammates with a Codex subscription/API key but no local model and
no OpenAI-compatible endpoint). Moved out of pipeline/extract.py so pipeline/kb.py's ask() can call
it directly too, without importing extract.py just for this.

    LLM_PROVIDER=openai (default; also what an unset LLM_PROVIDER + a set LLM_BASE_URL means) | codex

Embeddings never come through here (kb.embed() keeps calling an OpenAI-compatible /v1/embeddings
directly): codex has no embeddings endpoint, so retrieval for /ask still needs LLM_BASE_URL pointed
at Ollama or a real OpenAI-compatible host even when LLM_PROVIDER=codex extracts and answers.

Next for a teammate: codex_cli ignores `schema`/`name` -- `codex exec --output-schema <file>` could
constrain the reply the way response_format={"json_schema": ...} does for openai_compatible, but
that's untried against the real CLI and the prompt already asks for strict JSON, parsed the same way
as today either way.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from openai import OpenAI

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def provider() -> str:
    p = os.getenv("LLM_PROVIDER") or "openai"
    if p not in ("openai", "codex"):
        raise ValueError(f"LLM_PROVIDER={p!r} unknown; use 'openai' or 'codex'")
    return p


def chat(system: str, user: str, schema: dict, name: str = "response") -> str:
    """One model call -> the reply's raw text. Raises on failure the same way the provider's own
    client already did (a timeout's exception type name contains "timeout" either way, which is what
    extract.extract()'s retry/window-shrink logic keys off; anything else is just some Exception, same
    as an unhandled openai.* error today)."""
    content = _codex_chat(system, user) if provider() == "codex" else _openai_chat(system, user, schema, name)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # qwen3 & co
    return _FENCE.sub("", content)  # fenced anyway (codex answers like a chat assistant, fences and all)? strip


# ---- openai_compatible: Ollama native /api/chat, or any OpenAI-compatible /v1 --------------------

def _openai_chat(system: str, user: str, schema: dict, name: str) -> str:
    base, timeout = os.environ["LLM_BASE_URL"], float(os.getenv("LLM_TIMEOUT", "120"))  # a local 8b model that answers in 30-40 s and is still going after two minutes is stuck
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if re.search(r":11434/v1/?$", base):
        # Ollama's native API: think=false makes qwen3 answer in ~35 s instead of ~100 s. Its OpenAI-compatible /v1 ignores
        # both the think option and the "/no_think" soft switch, and the model then reasons for a minute before the JSON.
        body = {"model": os.environ["LLM_MODEL"], "stream": False, "think": os.getenv("LLM_THINK", "0") == "1", "format": schema,
                "options": {"temperature": 0, "num_ctx": int(os.getenv("LLM_NUM_CTX", "16384"))}, "messages": messages}
        req = urllib.request.Request(base.rsplit("/v1", 1)[0] + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["message"]["content"]
    client = OpenAI(base_url=base, api_key=os.getenv("LLM_API_KEY") or "none", timeout=timeout, max_retries=0)  # any OpenAI-compatible endpoint (Azure, OpenAI, a hosted model for the demo)
    resp = client.chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0, messages=messages,
                                          response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}})
    return resp.choices[0].message.content or ""


# ---- codex_cli: `codex exec`, non-interactive, one prompt in, one reply out ----------------------

def _codex_executable() -> str:
    """CODEX_BIN overrides outright; else PATH (bare "codex", so PATHEXT picks up the .cmd/.ps1 shim an
    `npm install -g` writes -- an explicit "codex.exe" would not); else the two directories a Windows
    Codex install has actually been seen in (`AppData/Local/OpenAI/Codex/bin`, or with an extra
    `Programs` segment for a different installer/version). A desktop app also tries `%APPDATA%\\npm`
    directly, ahead of these two, for a login PATH it would not otherwise inherit; skipped here, a
    backend process always inherits a shell's PATH."""
    override = os.getenv("CODEX_BIN")
    if override:
        return override
    found = shutil.which("codex")
    if found:
        return found
    roots = [Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe",
             Path.home() / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"] if os.name == "nt" \
        else [Path.home() / ".codex" / "bin" / "codex"]
    for candidate in roots:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("codex executable not found (PATH, or the usual OpenAI Codex install dirs); set CODEX_BIN to override")


def _codex_chat(system: str, user: str) -> str:
    exe = _codex_executable()
    model, timeout = os.getenv("LLM_MODEL", "gpt-5.6-terra"), float(os.getenv("LLM_TIMEOUT", "120"))
    prompt = f"{system}\n\n{user}"
    with tempfile.TemporaryDirectory(prefix="vivicta-codex-") as cwd:
        out = Path(cwd) / "last-message.txt"  # -o: codex's own answer to "which part of the output is the reply", no event-stream parsing needed
        cmd = [exe, "exec", "-m", model, "-s", "read-only", "-C", cwd, "--skip-git-repo-check", "--json", "-o", str(out), "-"]
        p = subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
        if p.returncode != 0 or not out.exists():
            tail = ((p.stdout or "") + "\n" + (p.stderr or ""))[-2000:].strip()
            raise RuntimeError(f"codex exec exited {p.returncode}: {tail}")
        return out.read_text(encoding="utf-8").strip()
