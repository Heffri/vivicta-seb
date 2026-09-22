"""Self-check for pipeline/jobs.py's in-memory progress table. No network, no filesystem.
Run: python -m pipeline.test_jobs"""
from . import jobs


def demo():
    # no job_id: step() is a no-op, nothing to get() back -- every fetch.py/llm.py call site can pass
    # an optional job_id straight through with no None-check
    before = len(jobs._jobs)
    jobs.step(None, "directory", "checking saved reports")
    jobs.step("", "directory", "checking saved reports")
    assert len(jobs._jobs) == before, "step() with a falsy job_id must not create an entry"
    assert jobs.get("") is None and jobs.get("does-not-exist") is None

    # first step() creates the job; stage/updated track the latest event, events accumulate in order
    jid = "job-1"
    jobs.step(jid, "directory", "checking saved reports")
    job = jobs.get(jid)
    assert job["job_id"] == jid
    assert job["stage"] == "directory" and job["done"] is False and job["error"] is None
    assert [e["stage"] for e in job["events"]] == ["directory"]
    assert job["events"][0]["text"] == "checking saved reports"
    assert "data" not in job["events"][0], "no kwargs -> no data key on the event"

    jobs.step(jid, "mfn", "searching MFN feeds")
    jobs.step(jid, "model_search", "asking the connected model to search the web")
    job = jobs.get(jid)
    assert [e["stage"] for e in job["events"]] == ["directory", "mfn", "model_search"], "events append, in order"
    assert job["stage"] == "model_search" and job["started"] <= job["updated"]

    # data kwargs (download's bytes/total) ride on the event only, never flattened onto the job dict
    jobs.step(jid, "download", "downloading report.pdf", bytes=1024, total=4096)
    job = jobs.get(jid)
    assert job["events"][-1]["data"] == {"bytes": 1024, "total": 4096}, job["events"][-1]
    assert "bytes" not in job and "data" not in job

    # done: a terminal, successful stage
    jid_done = "job-done"
    jobs.step(jid_done, "directory", "checking saved reports")
    jobs.step(jid_done, "done", "3 candidate(s)")
    job = jobs.get(jid_done)
    assert job["done"] is True and job["error"] is None and job["stage"] == "done"

    # failed: also terminal, and its text becomes the job's error; a later non-failed step (a fresh
    # job_id per retry is the frontend's own contract, but the table itself does not forbid re-use)
    # clears it again, since only "failed" itself sets the field
    jid_failed = "job-failed"
    jobs.step(jid_failed, "ddg", "crawling + DuckDuckGo search")
    jobs.step(jid_failed, "failed", "no annual report found for Acme 2025")
    job = jobs.get(jid_failed)
    assert job["done"] is True and job["error"] == "no annual report found for Acme 2025" and job["stage"] == "failed"

    # unknown/expired job_id: get() returns None (the route's 404)
    assert jobs.get("never-stepped") is None

    # expiry: a job whose last event is older than the TTL is swept lazily, on the next step()/get()
    # from *any* job_id -- no background thread, matches the "no persistence, single process" design
    jid_stale = "job-stale"
    jobs.step(jid_stale, "directory", "checking saved reports")
    jobs._jobs[jid_stale]["updated"] -= jobs.JOB_TTL_SECONDS + 1
    assert jobs.get(jid_stale) is None, "past the TTL, get() must not return the stale entry"
    assert jid_stale not in jobs._jobs, "the sweep must actually delete it, not just hide it from get()"

    jid_stale2 = "job-stale-2"
    jobs.step(jid_stale2, "directory", "checking saved reports")
    jobs._jobs[jid_stale2]["updated"] -= jobs.JOB_TTL_SECONDS + 1
    jobs.step("job-fresh", "directory", "checking saved reports")  # a step() on an unrelated job also sweeps
    assert jid_stale2 not in jobs._jobs

    print("jobs self-check ok")


if __name__ == "__main__":
    demo()
