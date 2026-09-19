"""One model call, three backends: openai_compatible (Ollama's native /api/chat, or any real
OpenAI-compatible /v1 -- Azure, OpenAI, OpenRouter, and Anthropic's own /v1 via its OpenAI-compatible
layer), codex_cli (shells out to a local `codex` install non-interactively) and claude_cli (same idea,
`claude -p`), for teammates with a Codex or Claude subscription/API key but no local model and no
OpenAI-compatible endpoint. Moved out of pipeline/extract.py so pipeline/kb.py's ask() can call it
directly too, without importing extract.py just for this.

    LLM_PROVIDER=openai (default; also what an unset LLM_PROVIDER + a set LLM_BASE_URL means) | codex | claude

A Claude subscription has no CLI-free API path (no api.anthropic.com key to put in LLM_BASE_URL the way
Ollama/Azure/OpenAI/OpenRouter work) -- claude_cli is that path. A Claude *API key*, by contrast, needs
no new code here: LLM_PROVIDER=openai + LLM_BASE_URL=https://api.anthropic.com/v1/ + LLM_API_KEY=<key> is
already the openai_compatible path, since Anthropic's API speaks the OpenAI SDK's wire format at that
base URL. See backend/README.md.

Embeddings never come through here (kb.embed() keeps calling an OpenAI-compatible /v1/embeddings
directly): neither Codex nor Claude has an embeddings endpoint, so retrieval for /ask still needs
LLM_BASE_URL pointed at Ollama or a real OpenAI-compatible host even when LLM_PROVIDER=codex/claude
extracts and answers.

Next for a teammate: codex_cli/claude_cli ignore `schema`/`name` -- `codex exec --output-schema <file>`
or claude's `--json-schema` could constrain the reply the way response_format={"json_schema": ...} does
for openai_compatible, but that's untried against the real CLIs and the prompt already asks for strict
JSON, parsed the same way as today either way.

LLM_STRICT_SCHEMA=1 (v121, opt-in) closes that gap: the CLI providers then pass the caller's `schema` on
-- codex exec takes `--output-schema <file>` (the schema written into the call's own -C temp dir), claude
takes `--json-schema <inline JSON>` (its --help shows the schema as a string value, not a file path -- the
one place the two CLIs differ). Parsing is unchanged; the prompt still asks for strict JSON either way.
When the strict call fails (a CLI build without the flag, or any non-zero exit/timeout), chat() falls
back to today's flag-less call with a warnings.warn -- so the switch can only add a retry, never change
a reply that today's code would have gotten. Default (switch unset) is byte-for-byte today's behavior.

web_lookup() (v074) is chat() with the provider's own web-search tool switched on -- fetch.py's fourth
report source. Only the CLI providers have a search tool; an OpenAI-compatible endpoint has none, so
web_lookup raises there instead of quietly answering from the model's memory.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import warnings
from pathlib import Path

from openai import OpenAI

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def provider() -> str:
    p = os.getenv("LLM_PROVIDER") or "openai"
    if p not in ("openai", "codex", "claude"):
        raise ValueError(f"LLM_PROVIDER={p!r} unknown; use 'openai', 'codex' or 'claude'")
    return p


def chat(system: str, user: str, schema: dict, name: str = "response") -> str:
    """One model call -> the reply's raw text. Raises on failure the same way the provider's own
    client already did (a timeout's exception type name contains "timeout" either way, which is what
    extract.extract()'s retry/window-shrink logic keys off; anything else is just some Exception, same
    as an unhandled openai.* error today).

    LLM_STRICT_SCHEMA=1 (v121) hands the CLI providers the caller's `schema` the way _openai_chat has
    always passed it as response_format. Only the *first*, strict attempt carries the flag: any failure
    (RuntimeError from a non-zero exit, or TimeoutExpired) falls back to today's flag-less call with a
    warnings.warn -- so a CLI build without the flag, a rate limit, or a timeout costs one retry and
    degrades to exactly the pre-v121 behavior. The fallback's own failure is what the caller sees."""
    p = provider()
    strict = schema is not None and os.getenv("LLM_STRICT_SCHEMA", "") == "1"
    if p == "codex":
        try:
            content = _codex_chat(system, user, schema=schema if strict else None)
        except (RuntimeError, subprocess.TimeoutExpired):
            if not strict:
                raise
            warnings.warn("LLM_STRICT_SCHEMA: codex exec did not accept --output-schema; retrying without it")
            content = _codex_chat(system, user)
    elif p == "claude":
        try:
            content = _claude_chat(system, user, schema=schema if strict else None)
        except (RuntimeError, subprocess.TimeoutExpired):
            if not strict:
                raise
            warnings.warn("LLM_STRICT_SCHEMA: claude -p did not accept --json-schema; retrying without it")
            content = _claude_chat(system, user)
    else:
        content = _openai_chat(system, user, schema, name)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # qwen3 & co
    return _FENCE.sub("", content)  # fenced anyway (codex/claude answer like a chat assistant, fences and all)? strip


def web_lookup(system: str, user: str, schema: dict, name: str = "web_lookup") -> str:
    """chat() with the provider's own web-search tool switched on: fetch.py's fourth report source
    asks the model for official annual-report PDF links the feeds and the plain web search missed.
    codex gets `--search` (the native Responses web_search tool, no per-call approval); claude gets
    `--tools WebSearch` -- its default `--tools ""` disables every tool, so the allowlist is the
    whole difference. openai_compatible (Ollama & co) has no search tool: raise rather than answer
    from the model's memory -- fetch.py gates on provider() in ("codex", "claude") first anyway.
    Reply post-processing is chat()'s, byte for byte."""
    p = provider()
    if p == "codex":
        content = _codex_chat(system, user, search=True)
    elif p == "claude":
        content = _claude_chat(system, user, tools="WebSearch")
    else:
        raise ValueError(f"{p} has no web-search tool; web_lookup needs LLM_PROVIDER=codex or claude")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # qwen3 & co
    return _FENCE.sub("", content)  # fenced anyway (codex/claude answer like a chat assistant, fences and all)? strip


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
    if os.name == "nt":
        for candidate in roots:
            versions = [p for p in candidate.parent.glob("*/codex.exe") if p.is_file()]
            if versions:
                return str(max(versions, key=lambda p: p.stat().st_mtime))
    raise RuntimeError("codex executable not found (PATH, or the usual OpenAI Codex install dirs); set CODEX_BIN to override")


def _codex_chat(system: str, user: str, search: bool = False, schema: dict | None = None) -> str:
    exe = _codex_executable()
    model, timeout = os.getenv("LLM_MODEL", "gpt-5.6-terra"), float(os.getenv("LLM_TIMEOUT", "120"))
    prompt = f"{system}\n\n{user}"
    with tempfile.TemporaryDirectory(prefix="vivicta-codex-") as cwd:
        out = Path(cwd) / "last-message.txt"  # -o: codex's own answer to "which part of the output is the reply", no event-stream parsing needed
        # --output-schema (v121, opt-in LLM_STRICT_SCHEMA) is an exec flag per `codex exec --help`
        # ("Path to a JSON Schema file describing the model's final response shape"): a FILE path, so
        # the schema goes into the call's own -C temp dir -- inside the read-only sandbox, never the repo.
        schema_arg = []
        if schema is not None:
            sp = Path(cwd) / "response-schema.json"
            sp.write_text(json.dumps(schema), encoding="utf-8")
            schema_arg = ["--output-schema", str(sp)]
        # --search is a top-level codex flag (v074), not an exec one: `codex exec --search` is rejected,
        # `codex --search exec ...` parses. It enables the native Responses web_search tool with no
        # per-call approval, which is all web_lookup() needs.
        cmd = [exe, *(["--search"] if search else []), "exec", "-m", model, "-s", "read-only", "-C", cwd, "--skip-git-repo-check", *schema_arg, "--json", "-o", str(out), "-"]
        p = subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
        if p.returncode != 0 or not out.exists():
            tail = ((p.stdout or "") + "\n" + (p.stderr or ""))[-2000:].strip()
            raise RuntimeError(f"codex exec exited {p.returncode}: {tail}")
        return out.read_text(encoding="utf-8").strip()


# ---- claude_cli: `claude -p`, non-interactive, one prompt in, one reply out ----------------------

def _claude_executable() -> str:
    """CLAUDE_BIN overrides outright; else PATH (bare "claude", so PATHEXT picks up whatever the install left
    there -- a native .exe, or the .cmd/.ps1 shim `npm install -g @anthropic-ai/claude-code` writes). UAW's
    adapter.ts (discoverClaudeLaunch in process-transport.ts) also checks `%APPDATA%\\npm` directly, ahead of
    PATH, for a login PATH an Electron app launched from Explorer would not otherwise inherit; skipped here,
    same as _codex_executable's -- a backend process always inherits a shell's PATH, npm shim included. Else
    `~/.local/bin/claude.exe`, the native installer's default (what this machine's own install uses, and what
    UAW falls back to next). Else the Claude desktop app's own bundled CLI, which UAW's
    discoverManagedClaudeExecutable also falls back to last: newest version directory under
    `%APPDATA%/Claude/claude-code/` that actually contains a claude.exe -- never
    `%LOCALAPPDATA%\\AnthropicClaude`, which UAW's own comment warns is the desktop GUI's claude.exe, not the
    CLI, and "driving it would fail in a way no error message would explain."."""
    override = os.getenv("CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    home_bin = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    if home_bin.is_file():
        return str(home_bin)
    managed = _claude_managed_candidate() if os.name == "nt" else None
    if managed:
        return managed
    raise RuntimeError("claude executable not found (PATH, or the usual Claude Code install dirs); set CLAUDE_BIN to override")


def _claude_managed_candidate() -> str | None:
    """UAW's claudeManagedRoots/discoverManagedClaudeExecutable: an upgrade of the desktop app's bundled CLI
    leaves the previous version behind in its own directory rather than replacing it, so more than one version
    directory existing is normal, not ambiguous (unlike _codex_executable's two candidates) -- the newest one
    that actually contains claude.exe wins. UAW additionally ranks a version directory its regex cannot parse
    last rather than dropping it, and caps the scan at 256 entries; skipped here, since a missing or
    unparseable version directory on this fallback-of-a-fallback just falls through to _claude_executable's
    own RuntimeError instead of stranding a real install."""
    root = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming")) / "Claude" / "claude-code"
    try:
        versions = [d for d in root.iterdir() if d.is_dir()]
    except OSError:
        return None

    def version_key(d: Path):
        try:
            return tuple(int(part) for part in d.name.split("."))
        except ValueError:
            return (-1,)

    for d in sorted(versions, key=version_key, reverse=True):
        candidate = d / "claude.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _claude_chat(system: str, user: str, tools: str = "", schema: dict | None = None) -> str:
    exe = _claude_executable()
    model, timeout = os.getenv("LLM_MODEL", "claude-sonnet-5"), float(os.getenv("LLM_TIMEOUT", "120"))
    prompt = f"{system}\n\n{user}"
    with tempfile.TemporaryDirectory(prefix="vivicta-claude-") as cwd:
        # --tools "" (--help: 'Use "" to disable all tools') leaves the model nothing to call at all -- stronger
        # than --permission-mode plan, which still permits read-only tool calls and exists for an interactive
        # approval loop `-p` never runs. UAW's own CLAUDE_CATALOG_ARGUMENTS (process-transport.ts) reaches for
        # the same "--tools", "" pair to take a headless CLI call down to plain text in, text out. web_lookup()
        # passes "WebSearch" instead (v074): the same flag is the whole allowlist. --output-format
        # json is codex's `--json -o <file>` in one flag: a single JSON object on stdout, reply text in "result"
        # (verified against a real `claude -p` call, 2026-09-16).
        # --json-schema (v121, opt-in LLM_STRICT_SCHEMA), unlike codex's --output-schema, takes the schema
        # itself, not a file path: `claude --help` shows `--json-schema <schema>` with an inline JSON object
        # as its example, so it goes on argv as one element (subprocess list form, no quoting involved).
        schema_arg = ["--json-schema", json.dumps(schema)] if schema is not None else []
        cmd = [exe, "-p", "--output-format", "json", *schema_arg, "--model", model, "--tools", tools, "--no-session-persistence"]
        p = subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
        if p.returncode != 0:
            tail = ((p.stdout or "") + "\n" + (p.stderr or ""))[-2000:].strip()
            raise RuntimeError(f"claude -p exited {p.returncode}: {tail}")
        try:
            reply = json.loads(p.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude -p produced non-JSON output: {p.stdout[-2000:].strip()}") from e
        if reply.get("is_error"):
            raise RuntimeError(f"claude -p reported an error: {json.dumps(reply)[-2000:]}")
        return reply.get("result") or ""
