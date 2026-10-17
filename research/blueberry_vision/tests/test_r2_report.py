"""The report is derived from pixel assets and supplied predictions, not examples."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from research.blueberry_vision.evaluator import evaluate_predictions
from research.blueberry_vision.r2_common import dataset_split_hash, file_hash, seal
from research.blueberry_vision.report import ReportError, render_report


def report_inputs(
    tmp_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    (tmp_path / "images").mkdir()
    Image.new("RGB", (40, 30), (20, 30, 70)).save(tmp_path / "images/berry.png")
    record = seal(
        {
            "image_id": "image-a",
            "image_width": 40,
            "image_height": 30,
            "original_asset_ref": "images/berry.png",
            "asset_sha256": file_hash(tmp_path / "images/berry.png"),
            "SYNTHETIC": True,
            "gt_status": "complete",
            "visible_count": 1,
            "split": "test",
            "capture_session_id": "session-a",
            "sampling_unit_id": "unit-a",
            "template_group_id": "template-a",
            "near_duplicate_group_id": "group-a",
            "generation_seed": 1,
            "ignore_regions": [],
            "objects": [
                {"object_id": "berry-a", "class_label": "candidate", "bbox_xyxy": [2, 3, 12, 15]}
            ],
            "source_authority": {
                "authority_id": "synthetic-generator",
                "source_ref": "test-generated-pixels",
                "permission_status": "synthetic_only",
                "allowed_uses": ["test"],
            },
            "annotation_quality_status": "synthetic_reference",
            "annotation_version": "candidate-1",
            "label_definition_version": "candidate-1",
            "scene_metadata": {"density": "sparse", "occlusion": "none", "scene_type": "sparse"},
        },
        "record_hash",
    )
    manifest = seal(
        {"SYNTHETIC": True, "images": [record], "split_hash": dataset_split_hash([record])},
        "manifest_hash",
    )
    bundles = [
        {
            "detector_version": "pixel-baseline-1",
            "model_name": "pixel-baseline-1",
            "schema_version": "blueberry-vision-predictions/2.0.0",
            "SYNTHETIC": True,
            "config_hash": "a" * 64,
            "model_hash": "b" * 64,
            "dataset_manifest_hash": manifest["manifest_hash"],
            "split_hash": manifest["split_hash"],
            "images": [
                {
                    "image_id": "image-a",
                    "status": "ok",
                    "reason_code": None,
                    "source_asset_hash": record["asset_sha256"],
                    "predicted_visible_fruit_count": 2,
                    "detected_objects": [
                        {
                            "object_id": "a",
                            "class_label": "candidate",
                            "bbox_xyxy": [2, 3, 12, 15],
                            "score": 0.9,
                        },
                        {
                            "object_id": "b",
                            "class_label": "candidate",
                            "bbox_xyxy": [20, 2, 30, 12],
                            "score": 0.8,
                        },
                    ],
                }
            ],
        }
    ]
    bundles[0]["images"] = [seal(bundles[0]["images"][0], "prediction_hash")]
    bundles = [seal(bundles[0], "prediction_hash")]
    reports = [evaluate_predictions(manifest, bundles[0])]
    return manifest, bundles, reports


def test_report_embeds_actual_results_offline_and_exports_images(tmp_path: Path) -> None:
    manifest, bundles, evaluations = report_inputs(tmp_path)
    output = tmp_path / "report"
    result = render_report(manifest, tmp_path, bundles, evaluations, output)
    data = json.loads((output / "report.json").read_text())
    assert data["images"][0]["models"][0]["pred_count"] == 2
    assert data["models"][0]["metrics"]["precision"] == 0.5
    html = (output / "report.html").read_text()
    assert "SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY" in html
    assert "data:image/png;base64," in html
    assert "fetch(" not in html and "<script src=" not in html
    for name in ["report.md", "metrics_summary.png", "scene_collage.png"]:
        assert (output / name).is_file()
    assert len(result["overlay_paths"]) == 1
    assert len(result["error_paths"]) == 1
    assert Image.open(output / result["overlay_paths"][0]).size[0] == 40


def test_report_changes_with_actual_predictions(tmp_path: Path) -> None:
    manifest, bundles, evaluations = report_inputs(tmp_path)
    render_report(manifest, tmp_path, bundles, evaluations, tmp_path / "first")
    changed = copy.deepcopy(bundles)
    changed[0]["images"][0]["predicted_visible_fruit_count"] = 1
    changed[0]["images"][0]["detected_objects"].pop()
    changed[0]["images"][0] = seal(changed[0]["images"][0], "prediction_hash")
    changed[0] = seal(changed[0], "prediction_hash")
    with pytest.raises(ReportError, match="REPORT_PROVENANCE_BINDING_MISMATCH"):
        render_report(manifest, tmp_path, changed, evaluations, tmp_path / "stale")
    render_report(
        manifest,
        tmp_path,
        changed,
        [evaluate_predictions(manifest, changed[0])],
        tmp_path / "second",
    )
    first = json.loads((tmp_path / "first/report.json").read_text())
    second = json.loads((tmp_path / "second/report.json").read_text())
    assert first["images"][0]["models"][0]["prediction"]["predicted_visible_fruit_count"] == 2
    assert second["images"][0]["models"][0]["prediction"]["predicted_visible_fruit_count"] == 1
    assert first["report_hash"] != second["report_hash"]


def test_report_rejects_overwrite_real_assets_and_escapes_script_data(tmp_path: Path) -> None:
    manifest, bundles, evaluations = report_inputs(tmp_path)
    manifest["images"][0]["scene_metadata"]["comment"] = "</script><script>alert(1)</script>"
    manifest = seal(manifest, "manifest_hash")
    bundles[0]["dataset_manifest_hash"] = manifest["manifest_hash"]
    bundles[0] = seal(bundles[0], "prediction_hash")
    evaluations = [evaluate_predictions(manifest, bundles[0])]
    output = tmp_path / "report"
    render_report(manifest, tmp_path, bundles, evaluations, output)
    html = (output / "report.html").read_text()
    assert "</script><script>alert(1)</script>" not in html
    with pytest.raises(ReportError, match="OUTPUT_ALREADY_EXISTS"):
        render_report(manifest, tmp_path, bundles, evaluations, output)
    manifest["images"][0]["SYNTHETIC"] = False
    with pytest.raises(ReportError, match="SYNTHETIC_ONLY"):
        render_report(manifest, tmp_path, bundles, evaluations, tmp_path / "real")


def test_report_missing_gt_stays_null_and_missing_inference_is_visible(tmp_path: Path) -> None:
    manifest, bundles, evaluations = report_inputs(tmp_path)
    record = manifest["images"][0]
    record.update({"gt_status": "missing", "visible_count": None, "objects": None})
    manifest = seal(manifest, "manifest_hash")
    bundles[0]["images"] = []
    bundles[0]["dataset_manifest_hash"] = manifest["manifest_hash"]
    bundles[0] = seal(bundles[0], "prediction_hash")
    evaluations = [evaluate_predictions(manifest, bundles[0])]
    render_report(manifest, tmp_path, bundles, evaluations, tmp_path / "report")
    actual = json.loads((tmp_path / "report/report.json").read_text())
    assert actual["images"][0]["models"][0]["gt_count"] is None
    assert actual["images"][0]["models"][0]["prediction"]["status"] == "MISSING_PREDICTION"


def test_report_recomputes_metrics_and_rejects_resealed_fabrication(tmp_path: Path) -> None:
    manifest, bundles, reports = report_inputs(tmp_path)
    reports[0]["metrics"]["count_mae"] = 0
    reports[0] = seal(reports[0], "report_hash")
    with pytest.raises(ReportError, match="REPORT_METRICS_MISMATCH"):
        render_report(manifest, tmp_path, bundles, reports, tmp_path / "fabricated")
    assert not (tmp_path / "fabricated").exists()


def test_report_checks_pixels_before_creating_output(tmp_path: Path) -> None:
    from research.blueberry_vision.assets import AssetError

    manifest, bundles, reports = report_inputs(tmp_path)
    (tmp_path / "images/berry.png").write_bytes(b"corrupt")
    with pytest.raises(AssetError):
        render_report(manifest, tmp_path, bundles, reports, tmp_path / "broken")
    assert not (tmp_path / "broken").exists()


def test_markdown_is_scalar_summary_and_retains_full_original_evaluation(tmp_path: Path) -> None:
    manifest, bundles, reports = report_inputs(tmp_path)
    render_report(manifest, tmp_path, bundles, reports, tmp_path / "report")
    markdown = (tmp_path / "report/report.md").read_text()
    assert len(markdown.splitlines()) < 100
    assert "| precision | 0.5 |" in markdown
    assert (
        "Evaluated: 1; excluded: 0; missing/failed: 0; evaluated images with errors: 1." in markdown
    )
    assert "evaluation_model-0.json" in markdown and "report.json" in markdown
    assert '"curve"' not in markdown
    saved = json.loads((tmp_path / "report/evaluation_model-0.json").read_text())
    assert saved == reports[0]
    assert len(saved["failure_cases"]) == 1


def _run_template_javascript(script: str) -> Any:
    """Execute actual template helpers, without duplicating their implementation."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Optional JS helper check requires Node; browser acceptance remains separate")
    template = Path("research/blueberry_vision/review_ui.html").read_text()
    helpers = "\n".join(
        line
        for line in template.splitlines()
        if line.startswith("function validDraftBox(")
        or line.startswith("async function draftIdentity(")
    )
    result = subprocess.run(
        [node, "-e", helpers + "\n" + script], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def test_actual_ui_geometry_helper_rejects_zero_area_and_invalid_boxes() -> None:
    actual = _run_template_javascript(
        "console.log(JSON.stringify([[1,1,1,9],[1,1,9,1],[1,1,9,9],"
        "[-1,1,9,9],[1,1,11,9],[1,1,9,11],[NaN,1,9,9]].map(box=>validDraftBox(box,10,10))))"
    )
    assert actual == [False, False, True, False, False, False, False]


def test_actual_ui_identity_helper_fails_closed_without_crypto() -> None:
    actual = _run_template_javascript(
        "draftIdentity('draft',null).then(value=>console.log(JSON.stringify({value})))"
        ".catch(error=>console.log(JSON.stringify({reason:error.message})))"
    )
    assert actual == {"reason": "CRYPTO_UNAVAILABLE"}


def test_actual_ui_identity_uses_content_and_matches_sha256() -> None:
    actual = _run_template_javascript(
        "(async()=>{const c=require('node:crypto').webcrypto;"
        "console.log(JSON.stringify([await draftIdentity('first',c),"
        "await draftIdentity('second',c)]))})()"
    )
    assert actual == [
        hashlib.sha256(value.encode()).hexdigest()[:16] for value in ["first", "second"]
    ]
