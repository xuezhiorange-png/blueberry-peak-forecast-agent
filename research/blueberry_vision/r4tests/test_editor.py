import json
import re

import pytest

from research.blueberry_vision.r4.package import build_package, clean_editor


@pytest.mark.parametrize("slot", ["A", "B"])
@pytest.mark.parametrize("preview_only", [True, False])
def test_editor_never_supplies_model_answers(public_preview, tmp_path, slot, preview_only):
    dataset, root = public_preview
    package = build_package(dataset)
    output = tmp_path / "editor.html"
    proof = clean_editor(package, dataset, root, output, slot=slot, preview_only=preview_only)
    assert proof["full_resolution"] is not preview_only
    html = output.read_text()
    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    assert match
    payload = json.loads(match.group(1))
    assert payload["task_id"] == package["tasks"][slot]["task_id"]
    assert "work_package_binding={package_hash:report.package_hash" in html
    for row in payload["images"]:
        assert row["models"][0]["detected_objects"] == []
        assert row["models"][0]["predicted_count"] is None
        assert row["annotation_objects"] == []
        assert row["pending_candidate_objects"] == []
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        clean_editor(package, dataset, root, output, slot=slot)
