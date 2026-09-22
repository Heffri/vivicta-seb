"""Self-check for path resolution (v030: dev tree vs. PyInstaller onedir). Run: python -m pipeline.test_paths"""
import os
import sys
import tempfile
from pathlib import Path


def _clear(*names):
    return {n: os.environ.pop(n, None) for n in names}


def _restore(saved):
    for n, v in saved.items():
        if v is None:
            os.environ.pop(n, None)
        else:
            os.environ[n] = v


def demo():
    from . import paths

    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    saved = _clear("ARP_DATA_DIR", "KB_DIR", "TESSDATA_PREFIX")
    try:
        # dev tree, no env overrides: matches the pre-v030 hardcoded HERE-relative paths byte for byte
        assert not getattr(sys, "frozen", False)
        assert paths.resource_dir() == backend, paths.resource_dir()
        assert paths.schemas_dir() == backend / "schemas", paths.schemas_dir()
        assert paths.fixture_path() == backend / "fixtures" / "sample_extraction.json", paths.fixture_path()
        assert paths.schemas_dir().is_dir() and paths.fixture_path().exists()  # actually bundled, not just computed
        assert paths.data_dir() == (repo / "data").resolve(), paths.data_dir()
        assert paths.tessdata_dir() == (repo / "data" / "tessdata").resolve(), paths.tessdata_dir()
        assert paths.reports_dir() == (repo / "data" / "reports").resolve(), paths.reports_dir()
        assert paths.companies_path() == (repo / "data" / "companies.json").resolve(), paths.companies_path()
        assert paths.kb_dir() == (repo / "data" / "kb").resolve(), paths.kb_dir()  # default "../data/kb" relative to backend/

        # ARP_DATA_DIR overrides data_dir() and everything derived from it, except KB_DIR-overridden kb_dir()
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARP_DATA_DIR"] = tmp
            assert paths.data_dir() == Path(tmp).resolve()
            assert paths.reports_dir() == Path(tmp).resolve() / "reports"
            assert paths.companies_path() == Path(tmp).resolve() / "companies.json"
            assert paths.kb_dir() == Path(tmp).resolve() / "kb"
            assert paths.tessdata_dir() == Path(tmp).resolve() / "tessdata"
            u = paths.uploads_dir()
            assert u == Path(tmp).resolve() / "uploads" and u.is_dir()  # auto-mkdir
            del os.environ["ARP_DATA_DIR"]

        # KB_DIR keeps its pre-existing semantics: resolved against resource_dir() (backend/), not data_dir(),
        # and wins over ARP_DATA_DIR -- unchanged behavior for the documented .env override
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARP_DATA_DIR"] = tmp
            os.environ["KB_DIR"] = "../data/kb"  # the .env.example default, spelled out
            assert paths.kb_dir() == (backend / "../data/kb").resolve() == (repo / "data" / "kb").resolve()
            os.environ["KB_DIR"] = str(Path(tmp) / "kb-abs")
            assert paths.kb_dir() == (Path(tmp) / "kb-abs").resolve()  # absolute KB_DIR short-circuits the resource_dir() join
            del os.environ["ARP_DATA_DIR"], os.environ["KB_DIR"]

        # frozen (PyInstaller onedir): resource_dir() == sys._MEIPASS, data_dir() defaults beside the onedir folder
        with tempfile.TemporaryDirectory() as tmp:
            internal = Path(tmp) / "backend" / "_internal"
            internal.mkdir(parents=True)
            bundled_tessdata = Path(tmp) / "tessdata"
            bundled_tessdata.mkdir()
            sys.frozen, sys._MEIPASS = True, str(internal)
            try:
                assert paths.resource_dir() == internal
                assert paths.schemas_dir() == internal / "schemas"
                assert paths.data_dir() == (Path(tmp) / "backend" / "data").resolve()  # beside the exe, not inside _internal
                assert paths.reports_dir() == (Path(tmp) / "backend" / "data" / "reports").resolve()
                custom = Path(tmp) / "custom"
                data_tessdata = custom / "tessdata"
                data_tessdata.mkdir(parents=True)
                for language in ("eng", "swe"):
                    (data_tessdata / f"{language}.traineddata").write_bytes(b"test")
                os.environ["ARP_DATA_DIR"] = str(custom)
                assert paths.data_dir() == custom.resolve()  # still overridable when frozen
                # w209: an empty/missing package resource must fall through to the writable data
                # copy. The desktop shell used to point TESSDATA_PREFIX at that empty package path,
                # hiding complete language files already installed under userData/data/tessdata.
                assert paths.tessdata_dir() == data_tessdata.resolve()
                for language in ("eng", "swe"):
                    (bundled_tessdata / f"{language}.traineddata").write_bytes(b"test")
                assert paths.tessdata_dir() == bundled_tessdata.resolve()
                os.environ["TESSDATA_PREFIX"] = str(Path(tmp) / "missing-explicit-tessdata")
                assert paths.tessdata_dir() == (Path(tmp) / "missing-explicit-tessdata").resolve()
                del os.environ["ARP_DATA_DIR"], os.environ["TESSDATA_PREFIX"]
            finally:
                del sys.frozen, sys._MEIPASS
    finally:
        _restore(saved)

    print("paths self-check ok")


if __name__ == "__main__":
    demo()
