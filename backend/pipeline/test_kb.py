"""Self-check for KB save idempotency (v024). Run: python -m pipeline.test_kb"""
import json
import os
import tempfile
import time
from pathlib import Path


def demo():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KB_DIR"] = tmp
        from . import kb, parse
        assert kb.kb_dir() == Path(tmp).resolve(), kb.kb_dir()  # env var actually redirects kb_dir()

        stem = "acme_2025"
        meta = {"company": "Acme", "fiscal_year": 2025, "language": "en", "source_url": None,
                "pages": 2, "sha256": "deadbeef", "filename": "acme.pdf"}
        texts = ["page one text", "page two text"]
        d = kb.kb_dir() / stem

        kb.save_report(stem, meta, texts)
        meta_1, pages_1 = (d / "meta.json").read_bytes(), (d / "pages.jsonl").read_bytes()
        meta_mtime_1, pages_mtime_1 = (d / "meta.json").stat().st_mtime_ns, (d / "pages.jsonl").stat().st_mtime_ns
        assert json.loads(meta_1)["parser"] == parse.PARSER_VERSION

        time.sleep(0.01)  # mtime-resolution guard: a same-tick rewrite could pass by accident
        kb.save_report(stem, meta, texts)  # same sha256, same parser -> must be a no-op
        assert (d / "meta.json").read_bytes() == meta_1, "meta.json rewritten on a same-sha256/same-parser save"
        assert (d / "pages.jsonl").read_bytes() == pages_1, "pages.jsonl rewritten on a same-sha256/same-parser save"
        assert (d / "meta.json").stat().st_mtime_ns == meta_mtime_1, "meta.json mtime changed on a no-op save"
        assert (d / "pages.jsonl").stat().st_mtime_ns == pages_mtime_1, "pages.jsonl mtime changed on a no-op save"

        # sha256 change -> the upgrade/re-parse path stays: rewrite, even at the same parser version
        time.sleep(0.01)
        meta_new_sha = {**meta, "sha256": "beefdead"}
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
        meta_2 = (d / "meta.json").read_bytes()
        assert meta_2 != meta_1, "sha256 change did not rewrite meta.json"
        assert json.loads(meta_2)["sha256"] == "beefdead"
        assert (d / "pages.jsonl").read_bytes() != pages_1, "sha256 change did not rewrite pages.jsonl"

        # PARSER_VERSION bump -> rewrite, even at the same sha256 (the v2->v3 upgrade path)
        old_version = parse.PARSER_VERSION
        parse.PARSER_VERSION = old_version + 1
        try:
            time.sleep(0.01)
            kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
            meta_3 = (d / "meta.json").read_bytes()
            assert meta_3 != meta_2, "parser version bump did not rewrite meta.json"
            assert json.loads(meta_3)["parser"] == old_version + 1

            time.sleep(0.01)  # same (sha256, parser) again post-bump -> back to a no-op
            kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
            assert (d / "meta.json").read_bytes() == meta_3, "meta.json rewritten on a no-op save after the version bump"
        finally:
            parse.PARSER_VERSION = old_version

        # legacy meta with no "parser" key at all (pre-existing data/kb entries) -> writes once, then idempotent
        (d / "meta.json").write_text(json.dumps({"sha256": meta_new_sha["sha256"], "pages": 2}), encoding="utf-8")
        pre = (d / "meta.json").read_bytes()
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])  # upgrade write: legit, allowed once
        post_1 = (d / "meta.json").read_bytes()
        assert post_1 != pre and json.loads(post_1)["parser"] == old_version
        time.sleep(0.01)
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])  # now idempotent
        assert (d / "meta.json").read_bytes() == post_1, "second save after the legacy upgrade still rewrote meta.json"

    print("kb self-check ok")


if __name__ == "__main__":
    demo()
