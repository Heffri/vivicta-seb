"""Self-check for the provider abstraction (pipeline/llm.py). A fake `codex` executable stands in for
the real CLI -- a .cmd shim plus a Python script that replays FAKE_CODEX_MODE -- so this needs no
network and no Codex install. Run: python -m pipeline.test_llm"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import llm

SCHEMA = {"type": "object", "properties": {"fields": {"type": "array"}}, "required": ["fields"]}
REPLY = {"fields": [{"key": "revenue", "value": 1}]}

_IMPL = '''
import json
import os
import sys
import time


def after(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


args = sys.argv[1:]
stdin_text = sys.stdin.read()
debug = os.environ.get("FAKE_CODEX_DEBUG")
if debug:
    with open(debug, "w", encoding="utf-8") as f:
        json.dump({"args": args, "stdin": stdin_text}, f)
print(json.dumps({"type": "session_configured"}))  # a real --json event; unparsed here, -o carries the reply
mode = os.environ.get("FAKE_CODEX_MODE", "ok")
if mode == "timeout":
    time.sleep(5)
    sys.exit(0)
if mode == "nonzero":
    sys.stderr.write("codex: 429 Too Many Requests\\n")
    sys.exit(1)
out = after(args, "-o")
reply = os.environ.get("FAKE_CODEX_REPLY", "{}")
if mode == "fenced":
    reply = "```json\\n" + reply + "\\n```"
if out:
    with open(out, "w", encoding="utf-8") as f:
        f.write(reply)
print(json.dumps({"type": "task_complete"}))
'''


def _fake_codex(dir: Path) -> Path:
    """codex.cmd -> this Python's own interpreter running fake_codex_impl.py -- the same shape a real
    `npm install -g` produces on Windows, which is why pipeline.llm's discovery looks for a bare
    "codex" on PATH rather than "codex.exe"."""
    impl = dir / "fake_codex_impl.py"
    impl.write_text(_IMPL, encoding="utf-8")
    shim = dir / "codex.cmd"
    shim.write_text(f'@echo off\n"{sys.executable}" "{impl}" %*\n', encoding="ascii")
    return shim


def demo():
    env_keys = ("CODEX_BIN", "LLM_PROVIDER", "LLM_MODEL", "LLM_TIMEOUT", "PATH",
                "FAKE_CODEX_MODE", "FAKE_CODEX_REPLY", "FAKE_CODEX_DEBUG")
    saved = {k: os.environ.get(k) for k in env_keys}
    try:
        with tempfile.TemporaryDirectory(prefix="test-llm-") as tmpdir:
            tmp = Path(tmpdir)
            shim = _fake_codex(tmp)
            debug = tmp / "debug.json"
            os.environ.update(LLM_PROVIDER="codex", LLM_MODEL="test-model-1", CODEX_BIN=str(shim),
                               FAKE_CODEX_MODE="ok", FAKE_CODEX_REPLY=json.dumps(REPLY), FAKE_CODEX_DEBUG=str(debug))

            # CODEX_BIN + happy path: the reply round-trips, and the CLI got the flags/prompt we intend
            content = llm.chat("system prompt text", "user prompt text", SCHEMA, "extraction")
            assert json.loads(content) == REPLY, content
            call = json.loads(debug.read_text(encoding="utf-8"))
            args = call["args"]
            assert args[args.index("-m") + 1] == "test-model-1", args
            assert args[args.index("-s") + 1] == "read-only", args
            assert "-C" in args and "--skip-git-repo-check" in args and "--json" in args, args
            assert args[-1] == "-", args  # prompt goes over stdin, never argv
            assert "system prompt text" in call["stdin"] and "user prompt text" in call["stdin"], call["stdin"]

            # discovery: CODEX_BIN unset, found on PATH instead (prepended, so it wins over any real
            # codex install already on this machine's PATH)
            del os.environ["CODEX_BIN"]
            os.environ["PATH"] = str(tmp) + os.pathsep + os.environ.get("PATH", "")
            assert json.loads(llm.chat("s", "u", SCHEMA)) == REPLY
            os.environ["CODEX_BIN"] = str(shim)  # back to the unambiguous seam for what follows

            # a fenced reply (```json ... ```) is stripped before it reaches json.loads
            os.environ["FAKE_CODEX_MODE"] = "fenced"
            assert json.loads(llm.chat("s", "u", SCHEMA)) == REPLY

            # a non-zero exit raises, with whatever the CLI said on stderr (here, a 429) in the message
            os.environ["FAKE_CODEX_MODE"] = "nonzero"
            try:
                llm.chat("s", "u", SCHEMA)
                assert False, "expected a non-zero codex exec exit to raise"
            except RuntimeError as e:
                assert "429" in str(e), e

            # a hung codex process times out; the exception type's name still says "timeout" (it's
            # subprocess.TimeoutExpired), which is what extract.extract()'s window-shrink retry keys off
            os.environ["FAKE_CODEX_MODE"], os.environ["LLM_TIMEOUT"] = "timeout", "1"
            try:
                llm.chat("s", "u", SCHEMA)
                assert False, "expected a hung codex exec to time out"
            except subprocess.TimeoutExpired as e:
                assert "timeout" in type(e).__name__.lower(), type(e).__name__

        # LLM_PROVIDER is validated at the boundary, not left to fail deep inside a provider call
        os.environ["LLM_PROVIDER"] = "not-a-provider"
        try:
            llm.provider()
            assert False, "expected an unknown LLM_PROVIDER to raise"
        except ValueError:
            pass
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("llm self-check ok")


if __name__ == "__main__":
    demo()
