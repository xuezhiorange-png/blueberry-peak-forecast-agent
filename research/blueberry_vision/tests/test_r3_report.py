"""R3 public report security, unknown GT semantics, and actual annotation helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from research.blueberry_vision.r2_common import canonical_hash, file_hash, seal
from research.blueberry_vision.r3.annotations import create_draft
from research.blueberry_vision.r3.evaluation import (
    compact_metrics,
    evaluation_protocol,
    match_reference,
)
from research.blueberry_vision.r3.ingestion import import_images
from research.blueberry_vision.r3.report import ReportError, render_report


def inputs(
    tmp_path: Path, *, redistribution: bool = True, synthetic: bool = False, gt: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    Image.new("RGB", (64, 48), (28, 40, 85)).save(tmp_path / "berry.png")
    purpose = "SYNTHETIC_ENGINEERING" if synthetic else "PUBLIC_EXTERNAL_BENCHMARK"
    source = {
        "source_id": "source-a",
        "purpose": purpose,
        "SYNTHETIC": synthetic,
        "name": "Synthetic fixture" if synthetic else "Licensed public fixture",
        "license_status": "SYNTHETIC_AUTHORITY" if synthetic else "LICENSE_VERIFIED",
        "research_use": True,
        "redistribution": redistribution,
        "license_id": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "official_url": "https://example.org/source",
        "creator": "Fixture Author",
        "attribution_required": True,
        "share_alike_derivatives": True,
    }
    record = {
        "image_id": "image-a",
        "asset_ref": "berry.png",
        "asset_sha256": file_hash(tmp_path / "berry.png"),
        "image_width": 64,
        "image_height": 48,
        "source_id": "source-a",
        "scene_metadata": {"density": "sparse", "occlusion": "none", "lighting": "UNKNOWN"},
        "observed_at": None,
        "base_identity": {"status": "UNRESOLVED"},
    }
    dataset = import_images(
        tmp_path,
        {
            "dataset_id": "fixture",
            "dataset_version": "3.0.0",
            "purpose": purpose,
            "SYNTHETIC": synthetic,
            "images": [record],
        },
        {"sources": [source]},
        tmp_path / "import",
    )
    record = dataset["images"][0]
    bundle = seal(
        {
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": purpose,
            "SYNTHETIC": synthetic,
            "model_name": "R2 Baseline A",
            "model_key": "A",
            "model_hash": "m" * 64,
            "config_hash": "c" * 64,
            "images": [
                {
                    "image_id": "image-a",
                    "source_asset_hash": record["asset_sha256"],
                    "status": "ok",
                    "detected_objects": [
                        {
                            "object_id": "p1",
                            "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
                            "bbox_xyxy": [2, 3, 15, 18],
                            "score": 0.9,
                        }
                    ],
                    "predicted_visible_fruit_count": 1,
                }
            ],
        },
        "prediction_hash",
    )
    annotation = create_draft(
        record,
        annotation_version="fixture-v1",
        annotator_id="test-operator",
        purpose=purpose,
        synthetic=synthetic,
        workflow_mode="SIMULATED_ENGINEERING" if synthetic else "OFFLINE_SELF_ASSERTED",
        provenance={
            "kind": "DOCUMENTED_PUBLISHER_ANNOTATION",
            "annotation_origin": "HUMAN",
            "evidence_status": "VERIFIED",
            "evidence_refs": ["TEST_ONLY_FAKE_METADATA_NEVER_REAL_IMAGE_EVIDENCE"],
            "source_annotation_version": "fixture-v1",
            "source_annotation_hash": "a" * 64,
        }
        if gt
        else None,
        objects=[
            {
                "object_id": "g1",
                "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
                "bbox_xyxy": [2, 3, 15, 18],
                "disposition": "TARGET",
            }
        ]
        if gt
        else None,
    )
    row = {
        "image_id": "image-a",
        "status": "EVALUATED" if gt else "NOT_EVALUABLE",
        "reference_count": 1 if gt else None,
        "predicted_count": 1,
        "signed_count_error": 0 if gt else None,
        "absolute_count_error": 0 if gt else None,
        "tp": 1 if gt else None,
        "fp": 0 if gt else None,
        "fn": 0 if gt else None,
        "false_positive_indices": [],
        "false_negative_indices": [],
        "reason_codes": [] if gt else ["GT_MISSING"],
    }
    row["reference_hash"] = annotation["snapshot_hash"]
    if gt:
        row.update(match_reference(annotation["objects"], bundle["images"][0]["detected_objects"]))
    metrics = compact_metrics([row])
    metrics["RESEARCH_AP50"] = 1.0 if gt else None
    evaluation = seal(
        {
            "dataset_manifest_hash": dataset["manifest_hash"],
            "prediction_hash": bundle["prediction_hash"],
            "purpose": purpose,
            "SYNTHETIC": synthetic,
            "status": "EVALUATED" if gt else "NOT_EVALUABLE",
            "evaluation_protocol": evaluation_protocol(),
            "evaluation_protocol_hash": canonical_hash(evaluation_protocol()),
            "metrics": metrics,
            "per_image_results": [row],
            "subgroup_metrics": {},
            "reason_codes": row["reason_codes"],
        },
        "report_hash",
    )
    return dataset, [bundle], [evaluation], [annotation]


def test_missing_gt_is_unknown_and_never_zero(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    result = render_report(
        dataset,
        tmp_path,
        predictions,
        evaluations,
        annotations,
        tmp_path / "report",
        public_export=True,
    )
    payload = json.loads((tmp_path / "report/report.json").read_text())
    assert payload["images"][0]["models"][0]["reference_count"] is None
    assert payload["images"][0]["models"][0]["predicted_count"] == 1
    assert payload["models"][0]["metrics"]["precision"] is None
    assert result["embedded_count"] == 1
    html = (tmp_path / "report/report.html").read_text()
    assert "PUBLIC EXTERNAL BENCHMARK" in html
    assert "NOT_EVALUABLE" in html
    assert "Fixture Author" in html and "CC-BY-SA-4.0" in html
    assert "data:image/jpeg;base64," in html
    assert "https://example.org/source" in html
    assert "fetch(" not in html and "<script src=" not in html
    assert str(tmp_path) not in html


def test_redistribution_denied_public_export_has_no_image_bytes(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, redistribution=False)
    result = render_report(
        dataset,
        tmp_path,
        predictions,
        evaluations,
        annotations,
        tmp_path / "report",
        public_export=True,
    )
    assert result["embedded_count"] == 0
    html = (tmp_path / "report/report.html").read_text()
    assert "data:image/" not in html
    assert "REDISTRIBUTION_NOT_AUTHORIZED" in html
    assert not list((tmp_path / "report").glob("*.png"))


def test_controlled_local_export_embeds_licensed_research_image(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, redistribution=False)
    result = render_report(
        dataset,
        tmp_path,
        predictions,
        evaluations,
        annotations,
        tmp_path / "report",
        public_export=False,
    )
    assert result["embedded_count"] == 1
    assert result["distribution_mode"] == "LOCAL_CONTROLLED_ONLY"
    assert "LOCAL CONTROLLED" in (tmp_path / "report/report.html").read_text()


@pytest.mark.parametrize("changed", ["dataset", "prediction", "evaluation", "annotation"])
def test_stale_or_tampered_artifacts_rejected(tmp_path: Path, changed: str) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    obj = {
        "dataset": dataset,
        "prediction": predictions[0],
        "evaluation": evaluations[0],
        "annotation": annotations[0],
    }[changed]
    obj["tamper"] = True
    with pytest.raises(ReportError):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_resealed_mismatched_prediction_rejected(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    predictions[0]["images"][0]["source_asset_hash"] = "f" * 64
    predictions[0] = seal(predictions[0], "prediction_hash")
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="PREDICTION_IMAGE_BINDING_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_source_domain_mixing_rejected(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    predictions[0]["purpose"] = "SYNTHETIC_ENGINEERING"
    predictions[0] = seal(predictions[0], "prediction_hash")
    with pytest.raises(ReportError, match="DOMAIN_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_no_metrics_claim_without_qualified_gt(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    evaluations[0]["metrics"]["precision"] = 1.0
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="METRICS_WITHOUT_REFERENCE"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_sealed_outputs_not_overwritten(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    out = tmp_path / "report"
    render_report(dataset, tmp_path, predictions, evaluations, annotations, out)
    with pytest.raises(ReportError, match="OUTPUT_ALREADY_EXISTS"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, out)


def test_report_is_compact_and_contains_actual_metric_charts(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, gt=True)
    evaluations[0]["metrics"]["precision_curve"] = [0.5] * 50000
    evaluations[0] = seal(evaluations[0], "report_hash")
    render_report(
        dataset,
        tmp_path,
        predictions,
        evaluations,
        annotations,
        tmp_path / "report",
        public_export=True,
    )
    payload = json.loads((tmp_path / "report/report.json").read_text())
    assert "precision_curve" not in payload["models"][0]["metrics"]
    assert payload["charts"]["count_error_histogram"][0]["bins"] == [{"error": 0, "count": 1}]
    assert len((tmp_path / "report/report.json").read_bytes()) < 20000


def test_embedding_budget_blocks_resource_growth(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    with pytest.raises(ReportError, match="EMBEDDED_BYTE_LIMIT"):
        render_report(
            dataset,
            tmp_path,
            predictions,
            evaluations,
            annotations,
            tmp_path / "report",
            max_embedded_bytes=1,
        )


def test_template_scripts_are_real_geometry_and_draft_helpers(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional; browser acceptance separately recorded")
    template = Path("research/blueberry_vision/r3/review_ui.html").read_text()
    script = template.split("/* GEOMETRY_HELPERS_START */", 1)[1].split(
        "/* GEOMETRY_HELPERS_END */", 1
    )[0]
    runner = tmp_path / "helper.cjs"
    runner.write_text(
        script
        + """
const assert = require('node:assert/strict');
assert.equal(validBox([1,2,5,6],10,10),true);
assert.equal(validBox([1,2,1,6],10,10),false);
assert.equal(validBox([1,2,15,6],10,10),false);
assert.equal(validBox([1,2,NaN,6],10,10),false);
assert.deepEqual(moveBox([1,2,5,6],20,-20,10,10),[6,0,10,4]);
assert.deepEqual(resizeBox([1,2,5,6],-4,13,10,10),[0,2,5,10]);
assert.equal(targetCount([{disposition:'TARGET'},{disposition:'IGNORE'},{disposition:'UNCERTAIN'}],'COMPLETE'),1);
assert.equal(targetCount([],'UNANNOTATED'),null);
assert.equal(targetCount([],'EMPTY_VERIFIED'),0);
"""
    )
    subprocess.run([node, str(runner)], check=True, capture_output=True, text=True)


def test_source_license_unverified_cannot_be_embedded(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    dataset["sources"][0]["license_status"] = "LICENSE_UNVERIFIED"
    dataset = seal(dataset, "manifest_hash")
    predictions[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    predictions[0] = seal(predictions[0], "prediction_hash")
    evaluations[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="SOURCE_RESEARCH_PERMISSION_REQUIRED"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_annotation_asset_binding_is_checked(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    annotations[0]["source_asset_hash"] = "f" * 64
    annotations[0] = seal(annotations[0], "snapshot_hash")
    with pytest.raises(ReportError, match="ANNOTATION_IMAGE_BINDING_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_synthetic_banner_is_distinct_from_external(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, synthetic=True)
    render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")
    html = (tmp_path / "report/report.html").read_text()
    assert "SYNTHETIC ENGINEERING" in html
    assert "NOT REAL BLUEBERRY ACCURACY" in html


def test_annotation_bundle_roundtrip_input(tmp_path: Path) -> None:
    from research.blueberry_vision.r3.annotations import annotation_bundle

    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    bundle = annotation_bundle(dataset, annotations)
    result = render_report(dataset, tmp_path, predictions, evaluations, bundle, tmp_path / "report")
    assert result["embedded_count"] == 1
    payload = json.loads((tmp_path / "report/report.json").read_text())
    assert payload["images"][0]["annotation"]["snapshot_hash"] == annotations[0]["snapshot_hash"]


def test_changed_frozen_protocol_rejected(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    evaluations[0]["evaluation_protocol"]["iou_threshold"] = 0.1
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="EVALUATION_PROTOCOL_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_resealed_metric_claim_recomputed(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, gt=True)
    evaluations[0]["metrics"]["count_mae"] = 88
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="METRICS_RECOMPUTATION_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_prediction_reference_matching_recomputed(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, gt=True)
    evaluations[0]["per_image_results"][0]["tp"] = 0
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="MATCHING_EVIDENCE_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_candidate_draft_never_qualifies_for_real_score(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path, gt=True)
    annotations[0]["provenance"] = {"kind": "SELF_ASSERTED_LOCAL_DRAFT"}
    annotations[0] = seal(annotations[0], "snapshot_hash")
    evaluations[0]["per_image_results"][0]["reference_hash"] = annotations[0]["snapshot_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="REFERENCE_QUALITY_NOT_ELIGIBLE"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_prediction_failure_count_remains_null(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    prediction = predictions[0]["images"][0]
    prediction.update(status="failed", detected_objects=None, predicted_visible_fruit_count=None)
    predictions[0] = seal(predictions[0], "prediction_hash")
    row = evaluations[0]["per_image_results"][0]
    row["predicted_count"] = None
    row["reason_codes"].append("PREDICTION_FAILED")
    evaluations[0]["metrics"] = compact_metrics([row])
    evaluations[0]["metrics"]["RESEARCH_AP50"] = None
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")
    payload = json.loads((tmp_path / "report/report.json").read_text())
    assert payload["images"][0]["models"][0]["predicted_count"] is None
    assert payload["models"][0]["metrics"]["failed_count"] == 1


def test_public_json_contains_no_images_or_asset_local_paths(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    render_report(
        dataset,
        tmp_path,
        predictions,
        evaluations,
        annotations,
        tmp_path / "report",
        public_export=True,
    )
    compact = (tmp_path / "report/report.json").read_text()
    assert "data:image" not in compact
    assert "berry.png" not in compact
    assert str(tmp_path) not in compact


def test_untrusted_metadata_cannot_close_json_script(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    dataset["sources"][0]["name"] = "</script><script>window.pwned=true</script>"
    dataset = seal(dataset, "manifest_hash")
    predictions[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    predictions[0] = seal(predictions[0], "prediction_hash")
    evaluations[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")
    html = (tmp_path / "report/report.html").read_text()
    assert "<script>window.pwned" not in html
    assert r"\u003c/script>" in html


def test_crypto_and_canonical_helper_against_independent_python_hash(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional; browser acceptance separately recorded")
    template = Path("research/blueberry_vision/r3/review_ui.html").read_text()
    script = template.split("/* GEOMETRY_HELPERS_START */", 1)[1].split(
        "/* GEOMETRY_HELPERS_END */", 1
    )[0]
    payload = {"z": [1, 1.125, None], "a": "候选"}
    runner = tmp_path / "crypto.cjs"
    runner.write_text(
        script
        + "\nconst assert = require('node:assert/strict');\n"
        + "const crypto = require('node:crypto').webcrypto;\n"
        + f"const payload={json.dumps(payload, ensure_ascii=False)};\n"
        + f"const expected={json.dumps(canonical_hash(payload))};\n"
        + "(async()=>{assert.equal(await draftDigest(payload,crypto),expected);"
        + "await assert.rejects(draftDigest(payload,null),/CRYPTO_UNAVAILABLE/);})();"
    )
    subprocess.run([node, str(runner)], check=True, capture_output=True, text=True)


def test_report_rejects_symlinked_data_root(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    link = tmp_path / "root-link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ReportError, match="ASSET_LOAD_FAILED"):
        render_report(dataset, link, predictions, evaluations, annotations, tmp_path / "report")


def test_report_rejects_symlinked_root_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "actual"
    root.mkdir()
    dataset, predictions, evaluations, annotations = inputs(root)
    (tmp_path / "ancestor-link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ReportError, match="ASSET_LOAD_FAILED"):
        render_report(
            dataset,
            tmp_path / "ancestor-link/actual",
            predictions,
            evaluations,
            annotations,
            tmp_path / "report",
        )


def test_missing_sealed_prediction_renders_excluded_scope_not_zero(tmp_path: Path) -> None:
    from research.blueberry_vision.r3.annotations import annotation_bundle
    from research.blueberry_vision.r3.evaluation import (
        evaluate_real,
        freeze_r2_baselines,
        run_real_inference,
    )
    from research.blueberry_vision.r3.splits import (
        append_exposure_event,
        build_split,
        seal_test,
    )
    from research.blueberry_vision.tests.test_r3_evaluation import simulated_reference

    original, _, _, _ = inputs(tmp_path, synthetic=True)
    source = original["sources"][0]
    Image.new("RGB", (64, 48), (80, 110, 40)).save(tmp_path / "other.png")
    dataset = import_images(
        tmp_path,
        {
            "dataset_id": "omitted-prediction-report-fixture",
            "dataset_version": "3.0.0",
            "purpose": "SYNTHETIC_ENGINEERING",
            "SYNTHETIC": True,
            "images": [
                {"image_id": "image-a", "source_id": source["source_id"], "asset_ref": "berry.png"},
                {"image_id": "image-b", "source_id": source["source_id"], "asset_ref": "other.png"},
            ],
        },
        {"sources": [source]},
        tmp_path / "omitted-import",
    )
    freeze = freeze_r2_baselines()
    ledger = tmp_path / "omitted-ledger"
    append_exposure_event(ledger, "CONFIG_FROZEN", {"freeze_hash": freeze["freeze_hash"]})
    prediction = run_real_inference(
        dataset,
        tmp_path,
        freeze,
        image_ids=["image-a"],
        output_path=tmp_path / "partial-prediction.json",
        ledger_dir=ledger,
    )
    annotation = annotation_bundle(
        dataset,
        [simulated_reference(dataset, name)["snapshots"][0] for name in ("image-a", "image-b")],
    )
    split = build_split(dataset, {"image-a": "TEST", "image-b": "OUT_OF_DOMAIN"})
    test_seal = seal_test(dataset, split, annotation, freeze, ledger=ledger)
    evaluation = evaluate_real(
        dataset, prediction, annotation, split, test_seal, freeze=freeze, ledger=ledger
    )
    render_report(dataset, tmp_path, prediction, evaluation, annotation, tmp_path / "report")
    payload = json.loads((tmp_path / "report/report.json").read_text())
    missing = next(row for row in payload["images"] if row["image_id"] == "image-b")["models"][0]
    assert missing["predicted_count"] is None
    assert missing["reference_count"] is None
    assert missing["signed_count_error"] is None
    assert "PREDICTION_MISSING" in missing["reason_codes"]
    assert payload["models"][0]["metrics"]["missing_prediction_count"] == 1
    assert payload["models"][0]["metrics"]["excluded_count"] == 2
    assert payload["charts"]["coverage"][0]["missing_prediction_count"] == 1
    html = (tmp_path / "report/report.html").read_text()
    assert "Missing prediction" in html


@pytest.mark.parametrize(
    "reason,predicted_count", [("GT_MISSING", None), ("PREDICTION_MISSING", 0)]
)
def test_missing_prediction_requires_explicit_reason_and_null_count(
    tmp_path: Path, reason: str, predicted_count: int | None
) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    predictions[0]["images"] = []
    predictions[0] = seal(predictions[0], "prediction_hash")
    row = evaluations[0]["per_image_results"][0]
    row["reason_codes"] = [reason]
    row["predicted_count"] = predicted_count
    evaluations[0]["metrics"] = compact_metrics([row])
    evaluations[0]["metrics"]["RESEARCH_AP50"] = None
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="EVALUATION_PREDICTION_COUNT_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_report_verifies_resealed_exif_against_actual_bytes(tmp_path: Path) -> None:
    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    dataset["images"][0]["exif_orientation"] = 2
    dataset["images"][0] = seal(dataset["images"][0], "record_hash")
    dataset = seal(dataset, "manifest_hash")
    predictions[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    predictions[0] = seal(predictions[0], "prediction_hash")
    evaluations[0]["dataset_manifest_hash"] = dataset["manifest_hash"]
    evaluations[0]["prediction_hash"] = predictions[0]["prediction_hash"]
    evaluations[0] = seal(evaluations[0], "report_hash")
    with pytest.raises(ReportError, match="IMAGE_COORDINATE_METADATA_MISMATCH"):
        render_report(dataset, tmp_path, predictions, evaluations, annotations, tmp_path / "report")


def test_unreviewed_geometry_is_editor_only_not_gt_or_accuracy(tmp_path: Path) -> None:
    from research.blueberry_vision.r3.annotations import annotation_bundle

    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    bundle = annotation_bundle(dataset, annotations)
    candidate = {
        "object_id": "external-unreviewed-1",
        "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
        "bbox_xyxy": [3, 4, 16, 18],
        "disposition": "TARGET",
    }
    bundle["draft_geometry"] = {"image-a": [candidate]}
    bundle = seal(bundle, "annotations_hash")
    render_report(dataset, tmp_path, predictions, evaluations, bundle, tmp_path / "report")
    payload = json.loads((tmp_path / "report/report.json").read_text())
    row = payload["images"][0]
    assert row["pending_candidate_objects"] == [candidate]
    assert row["pending_candidate_status"] == "UNREVIEWED_NOT_GT"
    assert row["annotation_objects"] == []
    assert row["annotation"]["gt_status"] == "UNANNOTATED"
    assert row["models"][0]["reference_count"] is None
    assert payload["models"][0]["metrics"]["precision"] is None
    html = (tmp_path / "report/report.html").read_text()
    assert "Unreviewed candidates" in html
    assert "row.pending_candidate_objects?.length?row.pending_candidate_objects" in html


@pytest.mark.parametrize(
    "image_id,bbox", [("different-image", [3, 4, 16, 18]), ("image-a", [3, 4, 160, 18])]
)
def test_pending_geometry_cannot_bypass_image_or_bounds_binding(
    tmp_path: Path, image_id: str, bbox: list[int]
) -> None:
    from research.blueberry_vision.r3.annotations import annotation_bundle

    dataset, predictions, evaluations, annotations = inputs(tmp_path)
    bundle = annotation_bundle(dataset, annotations)
    bundle["draft_geometry"] = {
        image_id: [
            {
                "object_id": "candidate",
                "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
                "bbox_xyxy": bbox,
                "disposition": "TARGET",
            }
        ]
    }
    bundle = seal(bundle, "annotations_hash")
    with pytest.raises(ReportError):
        render_report(dataset, tmp_path, predictions, evaluations, bundle, tmp_path / "report")
