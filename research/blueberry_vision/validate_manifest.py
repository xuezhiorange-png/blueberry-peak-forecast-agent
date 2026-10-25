"""Metadata-only validator. Reads one JSON file; never opens images or contacts services."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import ValidationError

from research.blueberry_vision.contracts import (
    VisionManifest,
    VisionObservation,
    canonical_record_hash,
    parse_timestamp,
)

ValidationMode = Literal["contract", "experiment"]
EVALUATION_SPLITS = {"train", "validation", "test", "out_of_domain"}


class Issue(TypedDict):
    code: str
    path: str


class ValidationReport(TypedDict):
    valid: bool
    mode: str
    errors: list[Issue]
    summary: dict[str, Any]


def _path(parts: tuple[str | int, ...]) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _schema_error_code(error_type: str) -> str:
    if error_type == "missing":
        return "SCHEMA_REQUIRED"
    if error_type == "extra_forbidden":
        return "SCHEMA_EXTRA"
    return "SCHEMA_VALIDATION"


def validate_data(data: object, *, mode: str = "contract") -> ValidationReport:
    """Validate metadata and declared suitability, without mutating or trusting source claims."""
    errors: list[Issue] = []

    def add(code: str, path: str) -> None:
        errors.append({"code": code, "path": path})

    report: ValidationReport = {"valid": False, "mode": mode, "errors": errors, "summary": {}}
    if mode not in {"contract", "experiment"}:
        add("INVALID_MODE", "/mode")
        return report
    if not isinstance(data, dict):
        add("MANIFEST_OBJECT_REQUIRED", "/")
        return report
    try:
        manifest = VisionManifest.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors(include_url=False, include_context=False, include_input=False):
            add(_schema_error_code(err["type"]), _path(err["loc"]))
        return report
    cutoff = parse_timestamp(manifest.as_of_cutoff)
    report["summary"] = {
        "record_count": len(manifest.observations),
        "synthetic_records": sum(r.SYNTHETIC for r in manifest.observations),
        "real_observation_records": sum(
            r.record_kind == "real_observation" for r in manifest.observations
        ),
        "prediction_records": sum(
            r.record_kind == "model_prediction" for r in manifest.observations
        ),
        "missing_count_records": sum(r.object_count is None for r in manifest.observations),
        "splits": dict(sorted(Counter(r.split for r in manifest.observations).items())),
        "image_files_present": manifest.image_files_present,
        "image_assets_verified": False,
        "authorization_authenticity_verified": False,
        "near_duplicate_image_analysis_performed": False,
        "algorithm_metrics_computed": False,
    }

    # Manifest-level provenance never upgrades fabricated metadata to real training evidence.
    kinds = {r.record_kind for r in manifest.observations}
    if len(kinds) > 1:
        add("MIXED_RECORD_KINDS", "/observations")
    if manifest.SYNTHETIC:
        if kinds != {"synthetic_observation"} or any(
            not r.SYNTHETIC for r in manifest.observations
        ):
            add("SYNTHETIC_MANIFEST_KIND_MISMATCH", "/SYNTHETIC")
        if manifest.image_files_present or manifest.purpose != "offline_synthetic_validation":
            add("SYNTHETIC_ASSET_DECLARATION_INVALID", "/image_files_present")
        if manifest.asset_hash_basis != "synthetic_descriptor_sha256":
            add("SYNTHETIC_HASH_BASIS_INVALID", "/asset_hash_basis")
    else:
        if any(
            r.SYNTHETIC or r.record_kind == "synthetic_observation" for r in manifest.observations
        ):
            add("REAL_MANIFEST_SYNTHETIC_RECORD", "/SYNTHETIC")
        if manifest.asset_hash_basis != "actual_asset_bytes_sha256":
            add("REAL_HASH_BASIS_INVALID", "/asset_hash_basis")
        if manifest.purpose != "metadata_contract":
            add("REAL_MANIFEST_PURPOSE_INVALID", "/purpose")

    review = manifest.near_duplicate_review
    if review.status != "completed" or review.completed_at is None:
        add("NEAR_DUPLICATE_REVIEW_REQUIRED", "/near_duplicate_review")
    elif parse_timestamp(review.completed_at) > cutoff:
        add("NEAR_DUPLICATE_REVIEW_AFTER_AS_OF", "/near_duplicate_review/completed_at")
    elif parse_timestamp(review.completed_at) < max(
        parse_timestamp(r.asset_available_at) for r in manifest.observations
    ):
        add("NEAR_DUPLICATE_REVIEW_BEFORE_ASSETS", "/near_duplicate_review/completed_at")
    expected_basis = "synthetic_declared" if manifest.SYNTHETIC else "authorized_asset_review"
    if review.basis != expected_basis:
        add("NEAR_DUPLICATE_REVIEW_BASIS_MISMATCH", "/near_duplicate_review/basis")

    label_defs = {entry.version: entry for entry in manifest.label_definitions}
    annotation_defs = {entry.version: entry for entry in manifest.annotation_versions}
    if len(label_defs) != len(manifest.label_definitions):
        add("DUPLICATE_LABEL_VERSION", "/label_definitions")
    if len(annotation_defs) != len(manifest.annotation_versions):
        add("DUPLICATE_ANNOTATION_VERSION", "/annotation_versions")
    for index, definition in enumerate(manifest.label_definitions):
        if len(set(definition.class_names)) != len(definition.class_names):
            add("DUPLICATE_CLASS_DEFINITION", f"/label_definitions/{index}/class_names")
    for index, annotation_definition in enumerate(manifest.annotation_versions):
        if annotation_definition.label_definition_version not in label_defs:
            add("ANNOTATION_LABEL_VERSION_MISMATCH", f"/annotation_versions/{index}")
    for split, split_cutoff in (manifest.split_cutoffs or {}).items():
        if parse_timestamp(split_cutoff) > cutoff:
            add("SPLIT_CUTOFF_AFTER_AS_OF", f"/split_cutoffs/{split}")

    # Exact assets may not appear twice, including two records in the same split.
    unique_fields = {
        "observation_id": "DUPLICATE_OBSERVATION_ID",
        "image_id": "DUPLICATE_IMAGE_ID",
        "asset_hash": "DUPLICATE_ASSET_HASH",
    }
    for field, code in unique_fields.items():
        seen: set[str] = set()
        for index, record in enumerate(manifest.observations):
            value = getattr(record, field)
            if value in seen:
                add(code, f"/observations/{index}/{field}")
            seen.add(value)
    groups = {
        "near_duplicate_group_id": "NEAR_DUPLICATE_SPLIT_LEAKAGE",
        "capture_session_id": "CAPTURE_SESSION_SPLIT_LEAKAGE",
        "sampling_unit_id": "SAMPLING_UNIT_SPLIT_LEAKAGE",
    }
    parents = list(range(len(manifest.observations)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        parents[find(left)] = find(right)

    for field, code in groups.items():
        assigned: dict[str, str] = {}
        all_records: dict[str, int] = {}
        for index, record in enumerate(manifest.observations):
            value = getattr(record, field)
            if value in all_records:
                union(all_records[value], index)
            all_records[value] = index
            if record.split == "unassigned":
                continue
            if value in assigned and assigned[value] != record.split:
                add(code, f"/observations/{index}/{field}")
            assigned[value] = record.split
    # Unassigned records can bridge groups and reveal leakage between assigned splits.
    component_splits: dict[int, str] = {}
    for index, record in enumerate(manifest.observations):
        if record.split == "unassigned":
            continue
        root = find(index)
        if root in component_splits and component_splits[root] != record.split:
            add("CONNECTED_GROUP_SPLIT_LEAKAGE", f"/observations/{index}/split")
        component_splits[root] = record.split

    for index, record in enumerate(manifest.observations):
        prefix = f"/observations/{index}"
        raw_record = data["observations"][index]
        if canonical_record_hash(raw_record) != record.record_hash:
            add("RECORD_HASH_MISMATCH", f"{prefix}/record_hash")
        observed = parse_timestamp(record.observed_at)
        asset_available = parse_timestamp(record.asset_available_at)
        available = parse_timestamp(record.available_at)
        if observed > asset_available:
            add("ASSET_BEFORE_CAPTURE", f"{prefix}/asset_available_at")
        if asset_available > available:
            add("RECORD_BEFORE_ASSET", f"{prefix}/available_at")
        if available > cutoff:
            add("AS_OF_LEAKAGE", f"{prefix}/available_at")
        record_split_cutoff = (manifest.split_cutoffs or {}).get(record.split)
        if record_split_cutoff is not None and available > parse_timestamp(record_split_cutoff):
            add("SPLIT_CUTOFF_LEAKAGE", f"{prefix}/available_at")
        if record.annotation_available_at is not None:
            annotation_available = parse_timestamp(record.annotation_available_at)
            if annotation_available > available:
                add("ANNOTATION_AFTER_RECORD", f"{prefix}/annotation_available_at")
            if annotation_available < asset_available:
                add("ANNOTATION_BEFORE_ASSET", f"{prefix}/annotation_available_at")

        identity = record.base_identity
        if identity.status == "resolved":
            if identity.base_id is None or identity.authority_ref is None:
                add("IDENTITY_AUTHORITY_REQUIRED", f"{prefix}/base_identity")
            if identity.unresolved_reason is not None:
                add("IDENTITY_RESOLVED_HAS_UNRESOLVED_REASON", f"{prefix}/base_identity")
        else:
            if identity.base_id is not None:
                add("IDENTITY_UNRESOLVED_HAS_BASE", f"{prefix}/base_identity/base_id")
            if identity.authority_ref is not None or identity.unresolved_reason is None:
                add("IDENTITY_UNRESOLVED_REASON_REQUIRED", f"{prefix}/base_identity")

        source = record.source_authority
        if source.permission_status in {"pending", "denied"}:
            add("SOURCE_PERMISSION_REJECTED", f"{prefix}/source_authority/permission_status")
        elif record.SYNTHETIC:
            if source.permission_status != "synthetic_only":
                add("SYNTHETIC_SOURCE_PERMISSION_REQUIRED", f"{prefix}/source_authority")
        elif source.permission_status != "approved":
            add("REAL_SOURCE_PERMISSION_REQUIRED", f"{prefix}/source_authority")
        if "metadata_validation" not in source.allowed_uses:
            add("SOURCE_USE_NOT_ALLOWED", f"{prefix}/source_authority/allowed_uses")
        if record.split in EVALUATION_SPLITS and record.split not in source.allowed_uses:
            add("SOURCE_USE_NOT_ALLOWED", f"{prefix}/source_authority/allowed_uses")
        if not record.SYNTHETIC:
            if source.evidence_ref is None:
                add("SOURCE_EVIDENCE_REQUIRED", f"{prefix}/source_authority/evidence_ref")
            if source.granted_at is None or source.expires_at is None:
                add("SOURCE_VALIDITY_REQUIRED", f"{prefix}/source_authority")
            else:
                granted = parse_timestamp(source.granted_at)
                expires = parse_timestamp(source.expires_at)
                if granted > available or granted > cutoff:
                    add("SOURCE_PERMISSION_NOT_YET_VALID", f"{prefix}/source_authority/granted_at")
                if expires <= available or expires <= cutoff:
                    add("SOURCE_PERMISSION_EXPIRED", f"{prefix}/source_authority/expires_at")
                if granted >= expires:
                    add("SOURCE_VALIDITY_ORDER_INVALID", f"{prefix}/source_authority")

        if record.record_kind == "synthetic_observation" and not record.SYNTHETIC:
            add("SYNTHETIC_RECORD_FLAG_REQUIRED", f"{prefix}/SYNTHETIC")
        if record.record_kind in {"real_observation", "model_prediction"} and record.SYNTHETIC:
            add("REAL_RECORD_FLAG_INVALID", f"{prefix}/SYNTHETIC")
        if record.record_kind == "model_prediction":
            if record.split in EVALUATION_SPLITS:
                add("PREDICTION_NOT_GROUND_TRUTH", f"{prefix}/split")
            if record.model_provenance is None:
                add("MODEL_PROVENANCE_REQUIRED", f"{prefix}/model_provenance")
            elif parse_timestamp(record.model_provenance.generated_at) > available:
                add("PREDICTION_AFTER_RECORD", f"{prefix}/model_provenance/generated_at")
            elif parse_timestamp(record.model_provenance.generated_at) < asset_available:
                add("PREDICTION_BEFORE_ASSET", f"{prefix}/model_provenance/generated_at")
        elif record.model_provenance is not None:
            add("OBSERVATION_HAS_MODEL_PROVENANCE", f"{prefix}/model_provenance")

        labels = label_defs.get(record.label_definition_version or "")
        annotation = annotation_defs.get(record.annotation_version or "")
        if record.label_definition_version is not None and labels is None:
            add("UNKNOWN_LABEL_VERSION", f"{prefix}/label_definition_version")
        if record.annotation_version is not None and annotation is None:
            add("UNKNOWN_ANNOTATION_VERSION", f"{prefix}/annotation_version")
        if (
            annotation is not None
            and annotation.label_definition_version != record.label_definition_version
        ):
            add("ANNOTATION_LABEL_VERSION_MISMATCH", f"{prefix}/annotation_version")
        if labels is not None:
            if record.task_kind not in labels.task_kinds:
                add("LABEL_TASK_MISMATCH", f"{prefix}/task_kind")
            if record.class_labels is not None and any(
                name not in labels.class_names for name in record.class_labels
            ):
                add("UNKNOWN_CLASS_LABEL", f"{prefix}/class_labels")
        elif record.class_labels is not None or record.objects is not None:
            add("LABEL_VERSION_REQUIRED", f"{prefix}/label_definition_version")

        completed = (
            record.annotation_quality_status == "reviewed"
            and annotation is not None
            and labels is not None
            and record.annotation_available_at is not None
        )
        if record.object_count is None:
            if record.missing_count_reason is None:
                add("MISSING_COUNT_REASON_REQUIRED", f"{prefix}/missing_count_reason")
            if record.class_labels is not None or record.objects is not None:
                add("MISSING_COUNT_HAS_OBJECT_LABELS", f"{prefix}/object_count")
        else:
            if record.missing_count_reason is not None:
                add("PRESENT_COUNT_HAS_MISSING_REASON", f"{prefix}/missing_count_reason")
            if record.class_labels is None or len(record.class_labels) != record.object_count:
                add("COUNT_LABELS_MISMATCH", f"{prefix}/class_labels")
            if record.objects is not None and len(record.objects) != record.object_count:
                add("COUNT_OBJECTS_MISMATCH", f"{prefix}/objects")
            if (
                record.object_count == 0
                and record.record_kind != "model_prediction"
                and not completed
            ):
                add("ZERO_WITHOUT_COMPLETED_ANNOTATION", f"{prefix}/object_count")
        if record.annotation_quality_status == "reviewed" and not completed:
            add("REVIEWED_ANNOTATION_INCOMPLETE", f"{prefix}/annotation_quality_status")
        if record.split in EVALUATION_SPLITS and record.record_kind != "model_prediction":
            if not completed:
                add("ANNOTATION_NOT_REVIEWED", f"{prefix}/annotation_quality_status")
            if record.object_count is None or record.class_labels is None:
                add("EVALUATION_LABELS_MISSING", f"{prefix}/object_count")

        _validate_objects(record, prefix, labels.class_names if labels else [], add)

        if mode == "experiment" and record.split in EVALUATION_SPLITS:
            if labels is not None and labels.approval_status != "approved":
                add("EXPERIMENT_LABEL_APPROVAL_REQUIRED", f"{prefix}/label_definition_version")
            if identity.status != "resolved":
                add("EXPERIMENT_IDENTITY_REQUIRED", f"{prefix}/base_identity")
            if record.task_kind == "detection" and record.objects is None:
                add("EXPERIMENT_DETECTION_BOXES_REQUIRED", f"{prefix}/objects")
            if record.task_kind == "instance_segmentation":
                add("EXPERIMENT_SEGMENTATION_ADAPTER_NOT_IMPLEMENTED", f"{prefix}/task_kind")
            if record.task_kind == "yield_proxy":
                add("EXPERIMENT_WEIGHT_CALIBRATION_NOT_IMPLEMENTED", f"{prefix}/task_kind")

    if mode == "experiment":
        assigned_records = [r for r in manifest.observations if r.split in EVALUATION_SPLITS]
        if len({r.task_kind for r in assigned_records}) > 1:
            add("EXPERIMENT_MULTIPLE_TASKS", "/observations")
        if len({r.label_definition_version for r in assigned_records}) > 1:
            add("EXPERIMENT_MULTIPLE_LABEL_DEFINITIONS", "/observations")
        if manifest.SYNTHETIC:
            add("SYNTHETIC_NOT_EXPERIMENT_DATA", "/SYNTHETIC")
        if kinds != {"real_observation"}:
            add("EXPERIMENT_REAL_OBSERVATIONS_REQUIRED", "/observations")
        if not manifest.image_files_present:
            add("EXPERIMENT_IMAGE_ASSETS_REQUIRED", "/image_files_present")
        if not {"train", "validation", "test"} <= {r.split for r in manifest.observations}:
            add("EXPERIMENT_SPLITS_REQUIRED", "/observations")
    report["valid"] = not errors
    return report


def _validate_objects(
    record: VisionObservation,
    prefix: str,
    class_names: list[str],
    add: Callable[[str, str], None],
) -> None:
    if record.objects is None:
        return
    seen: set[str] = set()
    labels: list[str] = []
    for index, obj in enumerate(record.objects):
        path = f"{prefix}/objects/{index}"
        labels.append(obj.class_label)
        if obj.object_id in seen:
            add("DUPLICATE_OBJECT_ID", f"{path}/object_id")
        seen.add(obj.object_id)
        if obj.class_label not in class_names:
            add("UNKNOWN_OBJECT_CLASS", f"{path}/class_label")
        if obj.bbox_xyxy is not None:
            x1, y1, x2, y2 = obj.bbox_xyxy
            if x1 >= x2 or y1 >= y2:
                add("BBOX_INVALID_ORDER", f"{path}/bbox_xyxy")
            if (
                min(x1, x2) < 0
                or min(y1, y2) < 0
                or max(x1, x2) > record.image_dimensions.width_px
                or max(y1, y2) > record.image_dimensions.height_px
            ):
                add("BBOX_OUT_OF_BOUNDS", f"{path}/bbox_xyxy")
        elif record.task_kind == "detection":
            add("DETECTION_BBOX_REQUIRED", f"{path}/bbox_xyxy")
        if obj.mask_polygon is not None:
            polygon = obj.mask_polygon
            if len(polygon) < 3 or len({tuple(p) for p in polygon}) < 3:
                add("MASK_POLYGON_INVALID", f"{path}/mask_polygon")
            elif any(
                not (0 <= x <= record.image_dimensions.width_px)
                or not (0 <= y <= record.image_dimensions.height_px)
                for x, y in polygon
            ):
                add("MASK_OUT_OF_BOUNDS", f"{path}/mask_polygon")
        elif record.task_kind == "instance_segmentation":
            add("SEGMENTATION_MASK_REQUIRED", f"{path}/mask_polygon")
    if record.class_labels is not None and labels != record.class_labels:
        add("OBJECT_CLASS_LABELS_MISMATCH", f"{prefix}/objects")


class InvalidJSON(ValueError):
    pass


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidJSON("Duplicate JSON member")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise InvalidJSON("Non-finite JSON number")


def validate_file(path: Path, *, mode: str = "contract") -> ValidationReport:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {
            "valid": False,
            "mode": mode,
            "errors": [{"code": "FILE_READ_ERROR", "path": "/"}],
            "summary": {},
        }
    try:
        data = json.loads(content, object_pairs_hook=_unique_keys, parse_constant=_reject_nonfinite)
    except (ValueError, RecursionError):
        return {
            "valid": False,
            "mode": mode,
            "errors": [{"code": "INVALID_JSON", "path": "/"}],
            "summary": {},
        }
    return validate_data(data, mode=mode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--mode", choices=("contract", "experiment"), default="contract")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    report = validate_file(args.manifest, mode=args.mode)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    else:
        print(f"valid={str(report['valid']).lower()} mode={report['mode']}")
        for error in report["errors"]:
            print(f"{error['code']} {error['path']}")
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
