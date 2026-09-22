"""In-memory progress trail for a long-running discover/fetch call. A job_id is a frontend-
generated uuid, optional on every request; step() is a no-op without one, so fetch.py/llm.py never
need a None-check before calling it. One process, one dict -- matches how `reports`/`extractions` in
app.py already assume a single uvicorn worker; nothing here persists across a restart.

GET /api/jobs/{job_id} (app.py) polls this table; the frontend does so every 1.5 s while a search or
fetch is running. A job past JOB_TTL_SECONDS since its last event is swept lazily (on the next step()
or get() from any job, not a background thread) so an abandoned job_id does not leak forever."""
import threading
import time

JOB_TTL_SECONDS = 3600
# Fixed vocabulary, the same one the frontend builds against: directory/mfn/nasdaq/ddg lookups, the
# connected model's own web search, following an IR page it names, a PDF download's byte progress,
# fiscal-year/issuer verification, then a terminal done or failed.
STAGES = ("directory", "mfn", "nasdaq", "ddg", "model_search", "ir_page", "download", "verify", "done", "failed")

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _sweep(now: float) -> None:
    for job_id in [jid for jid, job in _jobs.items() if now - job["updated"] > JOB_TTL_SECONDS]:
        del _jobs[job_id]


def step(job_id: "str | None", stage: str, text: str, **data) -> None:
    """Append one progress event. A no-op when job_id is falsy -- every call site passes it straight
    through from an optional request field without a None-check. `data` (e.g. download's bytes/total)
    rides on the event only, never flattened onto the job itself."""
    if not job_id:
        return
    now = time.time()
    with _lock:
        _sweep(now)
        job = _jobs.setdefault(job_id, {"stage": stage, "started": now, "updated": now, "done": False, "error": None, "events": []})
        job["stage"] = stage
        job["updated"] = now
        job["done"] = stage in ("done", "failed")
        job["error"] = text if stage == "failed" else job["error"]
        event = {"t": now, "stage": stage, "text": text}
        if data:
            event["data"] = data
        job["events"].append(event)


def get(job_id: str) -> "dict | None":
    """The job dict for GET /api/jobs/{id}, or None (404: unknown or expired)."""
    with _lock:
        _sweep(time.time())
        job = _jobs.get(job_id)
        return dict(job, job_id=job_id) if job else None
