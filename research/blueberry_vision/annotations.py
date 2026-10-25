"""Controlled COCO detection conversion, without publishing labels or reading images.

COCO has no standard unavailable-GT/provenance semantics. These adapters therefore
require explicit research extensions instead of pretending a bare COCO file is an
approved R1 observation or a validated R2 dataset. Coordinates are half-open xyxy.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any, TypeGuard

from research.blueberry_vision.r2_common import JSONDict, canonical_hash, seal

ADAPTER_VERSION = "blueberry-vision-reference-adapter/2.0.0"
COCO_ADAPTER_VERSION = "blueberry-vision-coco-detection/2.0.0"


class AnnotationError(ValueError):
    """Stable conversion failures, without logging image paths or sensitive rows."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _records(value: Any, code: str) -> list[JSONDict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AnnotationError(code)
    return value


def _integer_id(value: Any) -> TypeGuard[int]:
    return type(value) is int and value > 0


def _bbox(box: Any, width: int, height: int) -> list[int | float]:
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in box
        )
    ):
        raise AnnotationError("INVALID_BBOX")
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise AnnotationError("INVALID_BBOX")
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        raise AnnotationError("BBOX_OUT_OF_BOUNDS")
    return list(box)


def _reference(record: JSONDict) -> tuple[list[JSONDict] | None, int, int]:
    if record.get("record_kind") == "model_prediction" or record.get("model_provenance"):
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    for key in ("image_id", "annotation_version", "label_definition_version", "record_hash"):
        if (
            key not in record
            or (not isinstance(record[key], str) or not record[key])
            and not (
                record[key] is None
                and record.get("gt_status") == "missing"
                and key in {"annotation_version", "label_definition_version"}
            )
        ):
            raise AnnotationError("REFERENCE_METADATA_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{64}", record["record_hash"]):
        raise AnnotationError("REFERENCE_HASH_REQUIRED")
    if not isinstance(record.get("source_authority"), dict) or not record["source_authority"]:
        raise AnnotationError("SOURCE_AUTHORITY_REQUIRED")
    authority = record["source_authority"]
    if not isinstance(authority.get("authority_id"), str) or not authority["authority_id"]:
        raise AnnotationError("SOURCE_AUTHORITY_REQUIRED")
    if not isinstance(authority.get("permission_status"), str) or authority[
        "permission_status"
    ] not in {
        "synthetic_only",
        "approved",
        "pending",
        "denied",
    }:
        raise AnnotationError("SOURCE_AUTHORITY_REQUIRED")
    if not isinstance(record.get("SYNTHETIC"), bool):
        raise AnnotationError("SOURCE_KIND_REQUIRED")
    if record["SYNTHETIC"] != (authority["permission_status"] == "synthetic_only"):
        raise AnnotationError("SOURCE_KIND_AUTHORITY_MISMATCH")
    width, height = record.get("image_width"), record.get("image_height")
    if any(
        isinstance(size, bool) or not isinstance(size, int) or size <= 0 for size in (width, height)
    ):
        raise AnnotationError("INVALID_IMAGE_DIMENSIONS")
    assert isinstance(width, int) and isinstance(height, int)
    objects, count = record.get("objects"), record.get("visible_count")
    if record.get("gt_status") == "missing":
        if objects is not None or count is not None:
            raise AnnotationError("MISSING_GT_IS_NOT_ZERO")
        return None, width, height
    if record.get("gt_status") != "complete" or not isinstance(objects, list):
        raise AnnotationError("GT_STATUS_REQUIRED")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(objects):
        raise AnnotationError("REFERENCE_COUNT_MISMATCH")
    seen: set[str] = set()
    for obj in objects:
        if not isinstance(obj, dict) or any(
            not isinstance(obj.get(key), str) or not obj[key]
            for key in ("class_label", "object_id")
        ):
            raise AnnotationError("INVALID_OBJECT")
        if obj.get("mask_polygon") is not None or obj.get("segmentation") is not None:
            raise AnnotationError("SEGMENTATION_NOT_SUPPORTED")
        if obj["object_id"] in seen:
            raise AnnotationError("DUPLICATE_OBJECT_ID")
        seen.add(obj["object_id"])
        _bbox(obj.get("bbox_xyxy"), width, height)
    return objects, width, height


def export_coco(manifest: JSONDict) -> JSONDict:
    """Export checked research geometry plus its immutable source metadata."""
    records = _records(manifest.get("images"), "IMAGES_REQUIRED")
    labels: set[str] = set()
    seen_images: set[str] = set()
    for record in records:
        objects, _, _ = _reference(record)
        if record["image_id"] in seen_images:
            raise AnnotationError("DUPLICATE_IMAGE_ID")
        seen_images.add(record["image_id"])
        labels.update(obj["class_label"] for obj in objects or [])
    category_map = {label: index + 1 for index, label in enumerate(sorted(labels))}
    images: list[JSONDict] = []
    annotations: list[JSONDict] = []
    for image_index, record in enumerate(records, start=1):
        objects, width, height = _reference(record)
        metadata = copy.deepcopy(record)
        metadata.pop("objects", None)
        images.append(
            {
                "id": image_index,
                "width": width,
                "height": height,
                "file_name": record.get("original_asset_ref"),
                "research_image_id": record["image_id"],
                "research_record": metadata,
            }
        )
        for obj in objects or []:
            x1, y1, x2, y2 = _bbox(obj["bbox_xyxy"], width, height)
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image_index,
                    "category_id": category_map[obj["class_label"]],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "area": (x2 - x1) * (y2 - y1),
                    "iscrowd": 0,
                    "research_object": copy.deepcopy(obj),
                }
            )
    provenance = {
        "schema_version": COCO_ADAPTER_VERSION,
        "original_manifest_hash": canonical_hash(manifest),
        "SYNTHETIC": manifest.get("SYNTHETIC"),
        "label_approval_status": "candidate",
        "count_unit": "visible_fruit_per_image",
        "image_files_present": manifest.get("image_files_present"),
        "asset_bytes_verified_by_converter": False,
        "asset_hash_basis": manifest.get("asset_hash_basis", "actual_asset_bytes_sha256"),
        "original_schema_version": manifest.get("schema_version"),
    }
    if "r1_adapter_provenance" in manifest:
        provenance.update(manifest["r1_adapter_provenance"])
    return seal(
        {
            "images": images,
            "annotations": annotations,
            "categories": [{"id": index, "name": label} for label, index in category_map.items()],
            "research_provenance": provenance,
        },
        "adapter_hash",
    )


def import_coco(data: JSONDict) -> JSONDict:
    """Import controlled COCO. Edits create a new draft, never approved GT.

    Plain external COCO needs source/version metadata added by its authorized
    steward first. The resulting adapter must undergo dataset validation before
    training. Unsupported crowd/masks are rejected rather than silently lost.
    """
    if not isinstance(data, dict):
        raise AnnotationError("COCO_OBJECT_REQUIRED")
    provenance = data.get("research_provenance")
    if not isinstance(provenance, dict) or provenance.get("schema_version") != COCO_ADAPTER_VERSION:
        raise AnnotationError("PROVENANCE_REQUIRED")
    if not isinstance(provenance.get("original_manifest_hash"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", provenance["original_manifest_hash"]
    ):
        raise AnnotationError("PROVENANCE_REQUIRED")
    categories: dict[int, str] = {}
    for category in _records(data.get("categories"), "INVALID_CATEGORIES"):
        category_id, label = category.get("id"), category.get("name")
        if not _integer_id(category_id) or not isinstance(label, str) or not label:
            raise AnnotationError("INVALID_CATEGORY")
        if category_id in categories or label in categories.values():
            raise AnnotationError("DUPLICATE_CATEGORY")
        categories[category_id] = label
    indexed: dict[int, JSONDict] = {}
    seen_ids: set[str] = set()
    records: list[JSONDict] = []
    for image in _records(data.get("images"), "INVALID_IMAGES"):
        image_id = image.get("id")
        if not _integer_id(image_id) or image_id in indexed:
            raise AnnotationError("DUPLICATE_IMAGE_ID")
        metadata = image.get("research_record")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("record_hash"), str):
            raise AnnotationError("REFERENCE_METADATA_REQUIRED")
        record = copy.deepcopy(metadata)
        if (
            not isinstance(record.get("image_id"), str)
            or record.get("image_id") != image.get("research_image_id")
            or record["image_id"] in seen_ids
        ):
            raise AnnotationError("DUPLICATE_IMAGE_ID")
        seen_ids.add(record["image_id"])
        if (
            type(image.get("width")) is not int
            or type(image.get("height")) is not int
            or image.get("width") != record.get("image_width")
            or image.get("height") != record.get("image_height")
        ):
            raise AnnotationError("IMAGE_DIMENSIONS_MISMATCH")
        record["objects"] = None if record.get("gt_status") == "missing" else []
        indexed[image_id] = record
        records.append(record)
    annotation_ids: set[int] = set()
    for annotation in _records(data.get("annotations"), "INVALID_ANNOTATIONS"):
        if annotation.get("segmentation") is not None or annotation.get("iscrowd", 0) != 0:
            raise AnnotationError("SEGMENTATION_NOT_SUPPORTED")
        annotation_id = annotation.get("id")
        if not _integer_id(annotation_id) or annotation_id in annotation_ids:
            raise AnnotationError("DUPLICATE_ANNOTATION_ID")
        annotation_ids.add(annotation_id)
        if not _integer_id(annotation.get("image_id")) or annotation.get("image_id") not in indexed:
            raise AnnotationError("UNKNOWN_IMAGE_ID")
        if (
            not _integer_id(annotation.get("category_id"))
            or annotation.get("category_id") not in categories
        ):
            raise AnnotationError("UNKNOWN_CATEGORY")
        record = indexed[annotation["image_id"]]
        if record["objects"] is None:
            raise AnnotationError("MISSING_GT_HAS_ANNOTATIONS")
        box = annotation.get("bbox")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(isinstance(value, bool) or not isinstance(value, int | float) for value in box)
        ):
            raise AnnotationError("INVALID_BBOX")
        x, y, width, height = box
        xyxy = _bbox([x, y, x + width, y + height], record["image_width"], record["image_height"])
        if not isinstance(annotation.get("research_object", {}), dict):
            raise AnnotationError("INVALID_OBJECT")
        obj = copy.deepcopy(annotation.get("research_object", {}))
        obj.update(
            {
                "object_id": obj.get("object_id", f"candidate-object-{annotation_id}"),
                "bbox_xyxy": xyxy,
                "class_label": categories[annotation["category_id"]],
            }
        )
        record["objects"].append(obj)
    for record in records:
        if record["gt_status"] == "complete":
            record["visible_count"] = len(record["objects"])
        original_hash = record["record_hash"]
        if seal(record, "record_hash")["record_hash"] != original_hash:
            record.update(
                {
                    "original_record_hash": original_hash,
                    "annotation_version": f"candidate-import/{record['annotation_version']}",
                    "annotation_quality_status": "draft",
                }
            )
            record["record_hash"] = seal(record, "record_hash")["record_hash"]
        _reference(record)
    return seal(
        {
            "schema_version": ADAPTER_VERSION,
            "is_validated_dataset": False,
            "SYNTHETIC": provenance.get("SYNTHETIC"),
            "images": records,
            "research_provenance": copy.deepcopy(provenance),
        },
        "adapter_hash",
    )


def export_r1_coco(manifest: JSONDict) -> JSONDict:
    """Read R1 geometry only. Descriptor hashes never become real image hashes.

    Non-detection tasks have explicit exclusion reasons. A detection record with
    only a count cannot be exported as boxes and fails GEOMETRY_UNAVAILABLE.
    """
    images: list[JSONDict] = []
    exclusions: list[JSONDict] = []
    for original in manifest.get("observations", []):
        if original.get("task_kind") != "detection":
            exclusions.append(
                {"image_id": original.get("image_id"), "reason_code": "NON_DETECTION_TASK"}
            )
            continue
        if original.get("object_count") is not None and original.get("objects") is None:
            raise AnnotationError("GEOMETRY_UNAVAILABLE")
        record = copy.deepcopy(original)
        dimensions = original["image_dimensions"]
        record.update(
            {
                "image_width": dimensions["width_px"],
                "image_height": dimensions["height_px"],
                "original_asset_ref": None,
                "gt_status": "missing" if original["object_count"] is None else "complete",
                "visible_count": original["object_count"],
                "ignore_regions": [],
            }
        )
        # Adapter records have new hashes; the untouched original R1 identity is retained.
        record["original_record_hash"] = original["record_hash"]
        record["record_hash"] = seal(record, "record_hash")["record_hash"]
        images.append(record)
    return export_coco(
        {
            "images": images,
            "SYNTHETIC": manifest["SYNTHETIC"],
            "r1_adapter_provenance": {
                "original_manifest_hash": canonical_hash(manifest),
                "image_files_present": manifest["image_files_present"],
                "asset_hash_basis": manifest["asset_hash_basis"],
                "original_schema_version": manifest["schema_version"],
                "r1_exclusions": exclusions,
            },
        }
    )
