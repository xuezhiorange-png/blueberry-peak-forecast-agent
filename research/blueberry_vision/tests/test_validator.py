"""Preparation guards: these tests read fabricated metadata, never image assets."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.contracts import (
    VisionManifest,
    VisionObservation,
    canonical_record_hash,
)
from research.blueberry_vision.validate_manifest import validate_data

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (ROOT / "fixtures/synthetic_manifest.json").read_text(encoding="utf-8")
    )
    return loaded


def seal(data: dict[str, Any]) -> dict[str, Any]:
    for record in data["observations"]:
        record["record_hash"] = canonical_record_hash(record)
    return data


def codes(data: dict[str, Any], *, mode: str = "contract") -> set[str]:
    return {item["code"] for item in validate_data(data, mode=mode)["errors"]}


def make_real(data: dict[str, Any]) -> dict[str, Any]:
    data["SYNTHETIC"] = False
    data["image_files_present"] = True
    data["asset_hash_basis"] = "actual_asset_bytes_sha256"
    data["near_duplicate_review"]["basis"] = "authorized_asset_review"
    data["purpose"] = "metadata_contract"
    for definition in data["label_definitions"]:
        definition["approval_status"] = "approved"
    for record in data["observations"]:
        record["SYNTHETIC"] = False
        record["record_kind"] = "real_observation"
        record["source_authority"].update(
            permission_status="approved",
            evidence_ref="opaque-approved-authorization-ref",
            granted_at="2020-01-01T00:00:00Z",
            expires_at="2022-01-01T00:00:00Z",
        )
    data["observations"] = [r for r in data["observations"] if r["split"] != "unassigned"]
    return seal(data)


def test_committed_schemas_match_models() -> None:
    for model, name in (
        (VisionObservation, "vision_observation.schema.json"),
        (VisionManifest, "vision_manifest.schema.json"),
    ):
        assert json.loads((ROOT / "schemas" / name).read_text()) == model.model_json_schema()


def test_synthetic_fixture_contract_only(manifest: dict[str, Any]) -> None:
    report = validate_data(manifest)
    assert report["valid"] is True
    assert report["summary"]["image_files_present"] is False
    assert report["summary"]["synthetic_records"] == 5
    assert report["summary"]["missing_count_records"] == 1
    assert "SYNTHETIC_NOT_EXPERIMENT_DATA" in codes(manifest, mode="experiment")


def test_metadata_validation_does_not_modify_input(manifest: dict[str, Any]) -> None:
    before = copy.deepcopy(manifest)
    validate_data(manifest)
    assert manifest == before
    assert manifest["observations"][-1]["object_count"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("object_count", True),
        ("object_count", "2"),
        ("object_count", -1),
        ("count_unit", "kg"),
        ("SYNTHETIC", "true"),
        ("asset_hash", "not-a-sha256"),
        ("annotation_quality_status", "approved-by-name"),
        ("observed_at", "2021-01-01T12:00:00"),
        ("observed_at", "2021-02-30T12:00:00Z"),
        ("observed_at", "2021-01-01T12:00:00+00:99"),
        ("observed_at", "2021-01-01T12:00:00+01:60"),
        ("observed_at", "2021-01-01T12:00:00-00:00"),
        ("observed_at", "0001-01-01T00:00:00+01:00"),
        ("observed_at", "9999-12-31T23:59:59-01:00"),
        ("available_at", 1609459200),
    ],
)
def test_invalid_schema_values_rejected(
    manifest: dict[str, Any], field: str, value: object
) -> None:
    manifest["observations"][0][field] = value
    assert validate_data(seal(manifest))["valid"] is False


@pytest.mark.parametrize(
    "field", ["object_count", "annotation_version", "record_hash", "base_identity"]
)
def test_nullable_does_not_mean_optional(manifest: dict[str, Any], field: str) -> None:
    del manifest["observations"][0][field]
    assert "SCHEMA_REQUIRED" in codes(manifest)


def test_unknown_field_rejected_without_leaking_values(manifest: dict[str, Any]) -> None:
    secret = "sensitive-business-value-do-not-print"
    manifest["observations"][0]["unexpected"] = secret
    report = validate_data(seal(manifest))
    assert "SCHEMA_EXTRA" in {e["code"] for e in report["errors"]}
    assert secret not in json.dumps(report)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("asset_available_at", "2020-12-31T23:59:59Z", "ASSET_BEFORE_CAPTURE"),
        ("available_at", "2021-01-01T12:00:01Z", "RECORD_BEFORE_ASSET"),
        ("annotation_available_at", "2021-01-03T00:00:00Z", "ANNOTATION_AFTER_RECORD"),
        ("available_at", "2021-03-01T00:00:00Z", "AS_OF_LEAKAGE"),
    ],
)
def test_point_in_time_guards(manifest: dict[str, Any], field: str, value: str, code: str) -> None:
    manifest["observations"][0][field] = value
    assert code in codes(seal(manifest))


def test_timezone_comparisons_use_utc(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["observed_at"] = "2021-01-01T20:00:00+08:00"
    record["asset_available_at"] = "2021-01-01T12:01:00Z"
    assert validate_data(seal(manifest))["valid"] is True
    record["observed_at"] = "2021-01-01T07:00:00-06:00"
    assert "ASSET_BEFORE_CAPTURE" in codes(seal(manifest))


def test_split_cutoff_and_manifest_cutoff(manifest: dict[str, Any]) -> None:
    manifest["split_cutoffs"] = {"train": "2021-01-01T12:01:00Z"}
    assert "SPLIT_CUTOFF_LEAKAGE" in codes(manifest)
    manifest["split_cutoffs"] = {"train": "2022-01-01T00:00:00Z"}
    assert "SPLIT_CUTOFF_AFTER_AS_OF" in codes(manifest)


@pytest.mark.parametrize("field", ["observation_id", "image_id", "asset_hash"])
def test_duplicate_ids_and_exact_assets(manifest: dict[str, Any], field: str) -> None:
    manifest["observations"][1][field] = manifest["observations"][0][field]
    expected = {
        "observation_id": "DUPLICATE_OBSERVATION_ID",
        "image_id": "DUPLICATE_IMAGE_ID",
        "asset_hash": "DUPLICATE_ASSET_HASH",
    }
    assert expected[field] in codes(seal(manifest))


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("near_duplicate_group_id", "NEAR_DUPLICATE_SPLIT_LEAKAGE"),
        ("capture_session_id", "CAPTURE_SESSION_SPLIT_LEAKAGE"),
        ("sampling_unit_id", "SAMPLING_UNIT_SPLIT_LEAKAGE"),
    ],
)
def test_cross_split_group_leakage(manifest: dict[str, Any], field: str, code: str) -> None:
    manifest["observations"][1][field] = manifest["observations"][0][field]
    assert code in codes(seal(manifest))


def test_same_group_within_split_allowed(manifest: dict[str, Any]) -> None:
    manifest["observations"][1]["split"] = "train"
    for field in ("near_duplicate_group_id", "capture_session_id", "sampling_unit_id"):
        manifest["observations"][1][field] = manifest["observations"][0][field]
    assert validate_data(seal(manifest))["valid"] is True


def test_unassigned_record_cannot_bridge_independent_splits(manifest: dict[str, Any]) -> None:
    train, validation, bridge = (
        manifest["observations"][0],
        manifest["observations"][1],
        manifest["observations"][-1],
    )
    bridge["near_duplicate_group_id"] = train["near_duplicate_group_id"]
    bridge["capture_session_id"] = validation["capture_session_id"]
    assert "CONNECTED_GROUP_SPLIT_LEAKAGE" in codes(seal(manifest))


def test_same_base_different_units_allowed(manifest: dict[str, Any]) -> None:
    assert (
        manifest["observations"][0]["base_identity"] == manifest["observations"][1]["base_identity"]
    )
    assert validate_data(manifest)["valid"] is True


def test_unresolved_identity_is_explicit(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][-1]
    assert record["base_identity"]["status"] == "unresolved"
    record["base_identity"]["base_id"] = "guessed-from-farm-name"
    assert "IDENTITY_UNRESOLVED_HAS_BASE" in codes(seal(manifest))


def test_resolved_identity_requires_authority(manifest: dict[str, Any]) -> None:
    manifest["observations"][0]["base_identity"]["authority_ref"] = None
    assert "IDENTITY_AUTHORITY_REQUIRED" in codes(seal(manifest))


@pytest.mark.parametrize("field", ["annotation_version", "label_definition_version"])
def test_unknown_label_or_annotation_version(manifest: dict[str, Any], field: str) -> None:
    manifest["observations"][0][field] = "unregistered-version"
    expected = (
        "UNKNOWN_ANNOTATION_VERSION" if field == "annotation_version" else "UNKNOWN_LABEL_VERSION"
    )
    assert expected in codes(seal(manifest))


def test_label_not_in_versioned_definition(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["class_labels"][0] = "invented-business-standard"
    assert "UNKNOWN_CLASS_LABEL" in codes(seal(manifest))


def test_annotation_binding_and_review_status(manifest: dict[str, Any]) -> None:
    manifest["annotation_versions"][0]["label_definition_version"] = "missing-definition"
    assert "ANNOTATION_LABEL_VERSION_MISMATCH" in codes(manifest)
    manifest["observations"][0]["annotation_quality_status"] = "in_progress"
    assert "ANNOTATION_NOT_REVIEWED" in codes(seal(manifest))


@pytest.mark.parametrize("status", ["pending", "denied"])
def test_unapproved_sources_rejected(manifest: dict[str, Any], status: str) -> None:
    manifest["observations"][0]["source_authority"]["permission_status"] = status
    assert "SOURCE_PERMISSION_REJECTED" in codes(seal(manifest))


def test_authorization_expiry_scope_and_evidence(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    assert validate_data(data, mode="experiment")["valid"] is True
    source = data["observations"][0]["source_authority"]
    source["expires_at"] = "2021-01-01T00:00:00Z"
    source["allowed_uses"] = ["metadata_validation"]
    source["evidence_ref"] = None
    found = codes(seal(data))
    assert {
        "SOURCE_PERMISSION_EXPIRED",
        "SOURCE_USE_NOT_ALLOWED",
        "SOURCE_EVIDENCE_REQUIRED",
    } <= found


def test_authorization_exclusive_expiry(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    data["observations"][0]["source_authority"]["expires_at"] = data["as_of_cutoff"]
    assert "SOURCE_PERMISSION_EXPIRED" in codes(seal(data))


def test_mixed_real_and_synthetic_rejected(manifest: dict[str, Any]) -> None:
    manifest["observations"][0]["record_kind"] = "real_observation"
    manifest["observations"][0]["SYNTHETIC"] = False
    assert "MIXED_RECORD_KINDS" in codes(seal(manifest))


def test_prediction_never_becomes_ground_truth(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["record_kind"] = "model_prediction"
    record["SYNTHETIC"] = False
    record["model_provenance"] = {
        "model_version": "test-model-v1",
        "model_hash": "a" * 64,
        "generated_at": "2021-01-01T12:03:00Z",
        "provenance_ref": "opaque-model-provenance-ref",
    }
    found = codes(seal(manifest))
    assert {"PREDICTION_NOT_GROUND_TRUTH", "PREDICTION_AFTER_RECORD"} <= found


def test_zero_prediction_is_output_not_ground_truth(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    for record in data["observations"]:
        record.update(
            record_kind="model_prediction",
            split="unassigned",
            object_count=0,
            class_labels=[],
            objects=[],
            annotation_version=None,
            annotation_quality_status="not_annotated",
            annotation_available_at=None,
            model_provenance={
                "model_version": "test-model-v1",
                "model_hash": "a" * 64,
                "generated_at": record["available_at"],
                "provenance_ref": "fabricated-provenance-no-model-training",
            },
        )
    seal(data)
    assert validate_data(data)["valid"] is True
    assert "EXPERIMENT_REAL_OBSERVATIONS_REQUIRED" in codes(data, mode="experiment")


def test_missing_not_zero_and_zero_requires_completed_annotation(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][-1]
    assert record["object_count"] is None
    record["missing_count_reason"] = None
    assert "MISSING_COUNT_REASON_REQUIRED" in codes(seal(manifest))
    record["object_count"] = 0
    record["class_labels"] = []
    record["objects"] = []
    assert "ZERO_WITHOUT_COMPLETED_ANNOTATION" in codes(seal(manifest))


def test_missing_annotations_for_evaluation_rejected(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][-1]
    record["split"] = "test"
    assert "EVALUATION_LABELS_MISSING" in codes(seal(manifest))


def test_count_and_bbox_geometry(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["object_count"] = 999
    record["objects"][0]["bbox_xyxy"] = [0, 0, 99999, 12]
    found = codes(seal(manifest))
    assert {"COUNT_LABELS_MISMATCH", "COUNT_OBJECTS_MISMATCH", "BBOX_OUT_OF_BOUNDS"} <= found
    record["objects"][0]["bbox_xyxy"] = [10, 10, 5, 5]
    assert "BBOX_INVALID_ORDER" in codes(seal(manifest))


def test_invalid_polygon_guard(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["task_kind"] = "instance_segmentation"
    record["objects"][0]["mask_polygon"] = [[0, 0], [1, 1]]
    assert "MASK_POLYGON_INVALID" in codes(seal(manifest))


def test_hash_tampering_and_canonical_unicode(manifest: dict[str, Any]) -> None:
    record = manifest["observations"][0]
    record["device"]["device_id"] = "模拟设备"
    assert "RECORD_HASH_MISMATCH" in codes(manifest)
    assert validate_data(seal(manifest))["valid"] is True


def test_near_duplicate_evidence_is_declared_not_computed(manifest: dict[str, Any]) -> None:
    manifest["near_duplicate_review"]["status"] = "pending"
    assert "NEAR_DUPLICATE_REVIEW_REQUIRED" in codes(manifest)
    manifest["near_duplicate_review"]["status"] = "completed"
    manifest["near_duplicate_review"]["completed_at"] = "2020-01-01T00:00:00Z"
    assert "NEAR_DUPLICATE_REVIEW_BEFORE_ASSETS" in codes(manifest)


def test_experiment_requires_all_main_splits(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    data["observations"] = [r for r in data["observations"] if r["split"] != "validation"]
    assert "EXPERIMENT_SPLITS_REQUIRED" in codes(data, mode="experiment")


def test_experiment_candidate_labels_not_business_approved(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    data["label_definitions"][0]["approval_status"] = "candidate"
    assert "EXPERIMENT_LABEL_APPROVAL_REQUIRED" in codes(data, mode="experiment")


def test_experiment_cannot_mix_tasks_to_satisfy_three_splits(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    data["observations"][2]["task_kind"] = "maturity_classification"
    seal(data)
    assert validate_data(data)["valid"] is True
    assert "EXPERIMENT_MULTIPLE_TASKS" in codes(data, mode="experiment")


def test_experiment_requires_same_label_definition_across_splits(manifest: dict[str, Any]) -> None:
    data = make_real(manifest)
    label = copy.deepcopy(data["label_definitions"][0])
    label["version"] = "fabricated-label-definition-v2"
    annotation = copy.deepcopy(data["annotation_versions"][0])
    annotation.update(version="fabricated-annotation-v2", label_definition_version=label["version"])
    data["label_definitions"].append(label)
    data["annotation_versions"].append(annotation)
    data["observations"][1].update(
        label_definition_version=label["version"], annotation_version=annotation["version"]
    )
    seal(data)
    assert validate_data(data)["valid"] is True
    assert "EXPERIMENT_MULTIPLE_LABEL_DEFINITIONS" in codes(data, mode="experiment")


@pytest.mark.parametrize("contents", ["{bad-json", "[]", '{"observations": null}'])
def test_cli_bad_inputs_exit_two(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(contents)
    result = subprocess.run(
        [sys.executable, "-m", "research.blueberry_vision.validate_manifest", str(path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["valid"] is False
    assert result.stderr == ""


@pytest.mark.parametrize(
    "contents",
    ['{"SYNTHETIC": true, "SYNTHETIC": false}', '{"x": NaN}', '{"x": Infinity}'],
)
def test_cli_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(contents)
    result = subprocess.run(
        [sys.executable, "-m", "research.blueberry_vision.validate_manifest", str(path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["errors"][0]["code"] == "INVALID_JSON"


def test_cli_success_and_missing_file(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "research.blueberry_vision.validate_manifest"]
    result = subprocess.run(
        [*command, str(ROOT / "fixtures/synthetic_manifest.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["valid"] is True
    failed = subprocess.run(
        [*command, str(tmp_path / "missing.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["errors"][0]["code"] == "FILE_READ_ERROR"


def test_cli_no_silent_zero_in_valid_output(tmp_path: Path, manifest: dict[str, Any]) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(manifest))
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "research.blueberry_vision.validate_manifest", str(path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert path.read_bytes() == before
