"""Offline component/OCR checks: python -m pipeline.test_maturity_ocr."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from . import maturity, parse


def main():
    schema = json.loads((Path(__file__).parents[1] / "schemas/debt_maturity.json").read_text(encoding="utf8"))
    text = "Group borrowings\n2025 MSEK\nTotal 100\n2026 10\n2027 20\n2028 30\n2031 40"
    source = lambda q: {"page": 1, "quote": q}
    raw = {"scope": "group", "basis": "carrying_amount", "debt_scope": "Group borrowings", "context_source": source("Group borrowings"), "warnings": [], "fields": []}
    for sf, amounts in zip(schema["fields"], [[(100, "Total 100")], [(10, "2026 10")], [(20, "2027 20"), (30, "2028 30")], [(40, "2031 40")]]):
        raw["fields"].append(dict(key=sf["key"], unit="MSEK", period="2025", raw_label=sf["label"],
                                  components=[{"value": v, "source": source(q)} for v, q in amounts]))
    run = lambda r: maturity.validate(r, [text], [1], schema, {"fiscal_year": 2025})
    result = run(raw)
    assert result["fields"][2]["value"] == 50 and result["checks"][0]["passed"]
    assert len(result["fields"][2]["components"]) == 2
    split = deepcopy(raw)
    second = deepcopy(split["fields"][2])
    split["fields"][2]["components"] = second["components"][:1]
    second["components"] = second["components"][1:]
    split["fields"].append(second)
    assert run(split)["fields"][2]["value"] == 50  # repeated field keys must not discard earlier components
    incomplete = deepcopy(raw)
    incomplete["fields"][2]["components"].pop()
    assert all(f["value"] is None for f in run(incomplete)["fields"][1:])
    for mutation in ("duplicate", "bad_number", "bad_quote", "wrong_year", "wrong_scope", "cash_flows", "mixed_units", "empty"):
        bad = deepcopy(raw)
        f = bad["fields"][2]
        if mutation == "duplicate": f["components"].append(deepcopy(f["components"][0]))
        if mutation == "bad_number": f["components"][0]["value"] = 200
        if mutation == "bad_quote": f["components"][0]["source"]["quote"] = "2027 200"
        if mutation == "wrong_year": f["period"] = "2024"
        if mutation == "wrong_scope": bad["scope"] = "lease_only"
        if mutation == "cash_flows": bad["basis"] = "contractual_cash_flows"
        if mutation == "mixed_units": f["unit"] = "MEUR"
        if mutation == "empty": f["components"] = []
        assert run(bad)["fields"][2]["value"] is None, mutation
    assert not maturity.verified_source(source("otal 100"), [text], [1])
    page = Mock()
    page.get_images.return_value = []
    page.get_drawings.return_value = []
    page.get_links.return_value = []
    page.get_text.return_value = "Revenue 100 90"
    assert parse.page_text(page) == "Revenue 100 90"
    page.get_textpage_ocr.assert_not_called()
    with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"TESSDATA_PREFIX": root, "OCR_LANGUAGE": "eng"}):
        page.get_text.return_value = ""
        page.get_images.return_value = []
        page.get_drawings.return_value = [None] * 101  # outlined text, not an embedded image
        try:
            parse.page_text(page)
            raise AssertionError("missing OCR data must not cache empty text")
        except parse.OCRUnavailable:
            pass
        (Path(root) / "eng.traineddata").touch()
        page.get_text.side_effect = lambda kind=None, **kw: [(0, 0, 40, 10, "Revenue", 0, 0, 0), (45, 0, 60, 10, "100", 0, 0, 1)] if kind == "words" else ""
        assert parse.page_text(page) == "Revenue 100"
        assert page.get_textpage_ocr.call_args.kwargs["full"] is True
    print("maturity component and selective OCR checks passed")


if __name__ == "__main__":
    main()
