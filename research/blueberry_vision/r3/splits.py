"""Versioned graph isolation and research-integrity test seals.

These offline controls bind artifacts and order scoring operations. They do not
provide authenticated reviewers, access control, or an unseen public benchmark.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ..r2_common import (
    JSONDict,
    canonical_hash,
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)

SPLITS = frozenset({"TRAIN", "VALIDATION", "TEST", "OUT_OF_DOMAIN", "UNASSIGNED"})
EVALUATION_SPLITS = frozenset({"TEST", "OUT_OF_DOMAIN"})
KNOWN_GROUP_FIELDS = (
    "capture_session_id",
    "sampling_unit_id",
    "video_id",
    "source_batch_id",
    "multiview_group_id",
)
UNKNOWN_VALUES = frozenset({"", "UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE"})
HASH_FIELDS = (
    "config_hash",
    "model_hash",
    "training_data_hash",
    "evaluation_protocol_hash",
)


class SplitError(ValueError):
    """Stable admission or isolation failure, never a fabricated PASS."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _known(value: object) -> bool:
    return isinstance(value, str) and value not in UNKNOWN_VALUES


def _images(dataset: JSONDict) -> dict[str, JSONDict]:
    if not verify_seal(dataset, "manifest_hash"):
        raise SplitError("DATASET_HASH_INVALID")
    rows = dataset.get("images")
    if not isinstance(rows, list) or not rows:
        raise SplitError("DATASET_IMAGES_REQUIRED")
    result: dict[str, JSONDict] = {}
    for row in rows:
        if not isinstance(row, dict) or not _known(row.get("image_id")):
            raise SplitError("IMAGE_ID_INVALID")
        image_id = row["image_id"]
        if image_id in result:
            raise SplitError("IMAGE_ID_DUPLICATE")
        if not _is_hash(row.get("asset_sha256")):
            raise SplitError("ASSET_HASH_INVALID")
        result[image_id] = row
    return result


def _edge(a: str, b: str, relation: str, **extra: Any) -> JSONDict:
    first, second = sorted((a, b))
    return {"image_id_a": first, "image_id_b": second, "relation": relation, **extra}


def _graph_edges(images: dict[str, JSONDict], duplicate_report: JSONDict | None) -> list[JSONDict]:
    edges: list[JSONDict] = []
    # Group by an explicit namespace. Equal unknown values never become a group.
    for field in (*KNOWN_GROUP_FIELDS, "asset_sha256", "rgb_sha256"):
        groups: dict[str, list[str]] = {}
        for image_id, row in sorted(images.items()):
            value = row.get(field)
            if _known(value):
                groups.setdefault(cast(str, value), []).append(image_id)
        for members in groups.values():
            for member in members[1:]:
                edges.append(_edge(members[0], member, field))
    for image_id, row in sorted(images.items()):
        parent = row.get("parent_image_id")
        if _known(parent):
            if parent not in images:
                raise SplitError("PARENT_IMAGE_UNKNOWN")
            if parent == image_id:
                raise SplitError("PARENT_IMAGE_SELF")
            edges.append(_edge(image_id, parent, "parent_image_id"))
    if duplicate_report is not None:
        # The pending-only view intentionally drops confirmed perceptual links.
        # Every non-rejected edge still constrains the connected split group.
        candidates = duplicate_report.get("edges", duplicate_report.get("candidate_edges", []))
        if not isinstance(candidates, list):
            raise SplitError("DUPLICATE_REPORT_INVALID")
        for item in candidates:
            if not isinstance(item, dict):
                raise SplitError("DUPLICATE_REPORT_INVALID")
            a, b = item.get("image_id_a"), item.get("image_id_b")
            if (
                not isinstance(a, str)
                or not isinstance(b, str)
                or a not in images
                or b not in images
                or a == b
            ):
                raise SplitError("DUPLICATE_IMAGE_UNKNOWN")
            status = item.get("status", "PENDING")
            if not isinstance(status, str) or status not in {"PENDING", "CONFIRMED", "REJECTED"}:
                raise SplitError("DUPLICATE_REVIEW_STATUS_INVALID")
            if status == "REJECTED":
                review = item.get("review", item)
                if not isinstance(review, dict) or not all(
                    _known(review.get(key))
                    for key in ("reviewer_id", "reviewed_at", "review_reason")
                ):
                    raise SplitError("DUPLICATE_REJECTION_REVIEW_REQUIRED")
                # Exact asset/RGB equality independently forms an unbreakable edge.
                continue
            edges.append(
                _edge(
                    a,
                    b,
                    str(item.get("relation", "near_duplicate_candidate")),
                    review_status=status,
                )
            )
    return sorted(edges, key=lambda row: (row["image_id_a"], row["image_id_b"], row["relation"]))


def _holdouts(images: dict[str, JSONDict], records: list[JSONDict]) -> JSONDict:
    scope = {row["image_id"]: row["split"] for row in records}
    results: JSONDict = {}
    for dimension in ("cross_base", "cross_date"):
        train_values: set[str] = set()
        test_values: set[str] = set()
        unknown = 0
        for image_id, row in images.items():
            split = scope[image_id]
            if split == "UNASSIGNED":
                continue
            if dimension == "cross_base":
                identity = row.get("base_identity", {})
                value = (
                    identity.get("base_id")
                    if isinstance(identity, dict) and identity.get("status") == "CANONICAL"
                    else None
                )
            else:
                timestamp = row.get("observed_at")
                try:
                    observed = (
                        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        if isinstance(timestamp, str)
                        else None
                    )
                    value = (
                        observed.date().isoformat()
                        if observed is not None and observed.utcoffset() is not None
                        else None
                    )
                except ValueError:
                    value = None
            if not _known(value):
                unknown += 1
            elif split in {"TRAIN", "VALIDATION"}:
                train_values.add(cast(str, value))
            elif split in EVALUATION_SPLITS:
                test_values.add(cast(str, value))
        overlap = sorted(train_values & test_values)
        verified = not unknown and bool(train_values) and bool(test_values) and not overlap
        results[dimension] = {
            "status": "VERIFIED_DECLARED_METADATA" if verified else "UNVERIFIED",
            "reason_code": (
                None
                if verified
                else "UNKNOWN_HOLDOUT_METADATA"
                if unknown
                else "HOLDOUT_SCOPE_INSUFFICIENT"
                if not train_values or not test_values
                else "HOLDOUT_VALUE_OVERLAP"
            ),
            "unknown_count": unknown,
            "overlap": overlap,
        }
    return results


def build_split(
    dataset: JSONDict,
    assignments: JSONDict,
    duplicate_report: JSONDict | None = None,
    *,
    split_version: str = "1",
    output_path: Path | None = None,
) -> JSONDict:
    """Bind explicit assignments and connected associations; do not randomize images."""
    images = _images(dataset)
    if duplicate_report is not None and "duplicate_hash" in duplicate_report:
        if not verify_seal(duplicate_report, "duplicate_hash"):
            raise SplitError("DUPLICATE_REPORT_HASH_INVALID")
        if duplicate_report.get("dataset_manifest_hash") != dataset["manifest_hash"]:
            raise SplitError("DUPLICATE_DATASET_MISMATCH")
    if not isinstance(assignments, dict) or any(key not in images for key in assignments):
        raise SplitError("SPLIT_IMAGE_UNKNOWN")
    if any(not isinstance(value, str) or value not in SPLITS for value in assignments.values()):
        raise SplitError("SPLIT_VALUE_INVALID")
    if not _known(split_version):
        raise SplitError("SPLIT_VERSION_INVALID")
    edges = _graph_edges(images, duplicate_report)
    parent = {image_id: image_id for image_id in images}

    def find(image_id: str) -> str:
        while parent[image_id] != image_id:
            parent[image_id] = parent[parent[image_id]]
            image_id = parent[image_id]
        return image_id

    for edge in edges:
        a, b = find(edge["image_id_a"]), find(edge["image_id_b"])
        if a != b:
            first, second = sorted((a, b))
            parent[second] = first
    members: dict[str, list[str]] = {}
    for image_id in sorted(images):
        members.setdefault(find(image_id), []).append(image_id)
    groups = []
    group_index: dict[str, str] = {}
    for image_ids in sorted(members.values()):
        assigned = {assignments.get(image_id, "UNASSIGNED") for image_id in image_ids}
        assigned.discard("UNASSIGNED")
        if len(assigned) > 1:
            raise SplitError("GROUP_CROSS_SPLIT")
        group_id = canonical_hash(image_ids)
        for image_id in image_ids:
            group_index[image_id] = group_id
        groups.append(
            {"group_id": group_id, "image_ids": image_ids, "assigned_splits": sorted(assigned)}
        )
    records = [
        {
            "image_id": image_id,
            "asset_sha256": row["asset_sha256"],
            "split": assignments.get(image_id, "UNASSIGNED"),
            "group_id": group_index[image_id],
        }
        for image_id, row in sorted(images.items())
    ]
    result = seal(
        {
            "schema_version": "blueberry-vision-split/3.0.0",
            "split_version": split_version,
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": dataset.get("purpose"),
            "SYNTHETIC": dataset.get("SYNTHETIC"),
            "records": records,
            "groups": groups,
            "association_edges": edges,
            "duplicate_report_hash": canonical_hash(duplicate_report)
            if duplicate_report is not None
            else None,
            "holdout_verification": _holdouts(images, records),
            "limitations": [
                "Declared associations and pending perceptual candidates are "
                "conservatively connected.",
                "Undetected near duplicates and unknown metadata remain unverified.",
                "Metadata integrity does not authenticate source identity "
                "or grant business authority.",
            ],
        },
        "split_hash",
    )
    if output_path is not None:
        write_json_new(output_path, result)
    return result


def _annotation_rows(annotations: JSONDict | list[JSONDict] | None) -> list[JSONDict]:
    if annotations is None:
        return []
    if isinstance(annotations, list):
        return annotations
    if "annotations_hash" in annotations and not verify_seal(annotations, "annotations_hash"):
        raise SplitError("ANNOTATION_BUNDLE_HASH_INVALID")
    rows = annotations.get("snapshots", annotations.get("images", []))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SplitError("ANNOTATION_BUNDLE_INVALID")
    return cast(list[JSONDict], rows)


def _reference_reasons(snapshot: JSONDict, synthetic: bool, image: JSONDict) -> list[str]:
    """Reuse annotation qualification; never upgrade legacy metadata into real GT."""
    from .annotations import AnnotationError, reference_eligibility, validate_snapshot

    reasons = []
    if (
        snapshot.get("reference_kind") == "MODEL_PREDICTION"
        or snapshot.get("annotation_origin") == "MODEL"
    ):
        reasons.append("PREDICTION_CANNOT_BE_GT")
    if not _known(snapshot.get("annotation_version")):
        reasons.append("ANNOTATION_VERSION_MISSING")
    if not _known(snapshot.get("label_definition_version")):
        reasons.append("LABEL_DEFINITION_VERSION_MISSING")
    if snapshot.get("simulated") or snapshot.get("workflow_mode") == "SIMULATED_ENGINEERING":
        if not synthetic:
            reasons.append("SIMULATED_REFERENCE_NOT_REAL_GT")
    try:
        validate_snapshot(snapshot, image)
        if not synthetic:
            eligibility = reference_eligibility(snapshot)
            if not eligibility.get("eligible"):
                reasons.extend(eligibility.get("reason_codes", ["GT_QUALITY_INSUFFICIENT"]))
                reasons.append("GT_QUALITY_INSUFFICIENT")
        elif snapshot.get("review_status") != "SEALED":
            reasons.append("GT_QUALITY_INSUFFICIENT")
    except AnnotationError as exc:
        reasons.extend([exc.code, "GT_QUALITY_INSUFFICIENT"])
    return reasons


def _split_reasons(dataset: JSONDict, split: JSONDict) -> list[str]:
    if not verify_seal(split, "split_hash"):
        return ["SPLIT_HASH_INVALID"]
    if split.get("dataset_manifest_hash") != dataset.get("manifest_hash"):
        return ["SPLIT_DATASET_MISMATCH"]
    images = _images(dataset)
    records = split.get("records", [])
    if not isinstance(records, list):
        return ["SPLIT_RECORDS_INVALID"]
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("image_id"), str)
        or not isinstance(row.get("split"), str)
        or not isinstance(row.get("group_id"), str)
        for row in records
    ):
        return ["SPLIT_RECORDS_INVALID"]
    image_ids = [row.get("image_id") for row in records]
    if (
        len(records) != len(images)
        or set(image_ids) != set(images)
        or len(set(image_ids)) != len(image_ids)
    ):
        return ["SPLIT_IMAGE_IDENTITY_MISMATCH"]
    groups: dict[str, set[str]] = {}
    for row in records:
        if (
            row.get("split") not in SPLITS
            or row.get("asset_sha256") != images[row["image_id"]]["asset_sha256"]
        ):
            return ["SPLIT_IMAGE_IDENTITY_MISMATCH"]
        groups.setdefault(row.get("group_id", ""), set()).add(row["split"])
    if any(len(values - {"UNASSIGNED"}) > 1 for values in groups.values()):
        return ["GROUP_CROSS_SPLIT"]
    # Recompute declared edges rather than trusting a resealed group_id edited by hand.
    scope = {row["image_id"]: row["split"] for row in records}
    for edge in _graph_edges(images, {"candidate_edges": split.get("association_edges", [])}):
        values = {scope[edge["image_id_a"]], scope[edge["image_id_b"]]} - {"UNASSIGNED"}
        if len(values) > 1:
            return ["GROUP_CROSS_SPLIT"]
    return []


def _source_reasons(dataset: JSONDict, scope: set[str]) -> list[str]:
    sources_value = dataset.get("sources", [])
    if isinstance(sources_value, dict):
        sources = sources_value
    elif isinstance(sources_value, list):
        sources = {row.get("source_id"): row for row in sources_value if isinstance(row, dict)}
    else:
        sources = {}
    reasons = []
    purpose = dataset.get("purpose")
    expected_license = {
        "PUBLIC_EXTERNAL_BENCHMARK": "LICENSE_VERIFIED",
        "AUTHORIZED_ORCHARD_PILOT": "AUTHORITY_VERIFIED",
        "SYNTHETIC_ENGINEERING": "SYNTHETIC_AUTHORITY",
    }.get(cast(str, purpose))
    if expected_license is None:
        reasons.append("DATA_PURPOSE_INVALID")
    for image_id, row in _images(dataset).items():
        if image_id not in scope:
            continue
        source = sources.get(row.get("source_id"))
        if not isinstance(source, dict):
            reasons.append("SOURCE_AUTHORITY_MISSING")
        elif source.get("license_status") != expected_license:
            reasons.append("LICENSE_UNVERIFIED")
        elif source.get("research_use") is not True:
            reasons.append("RESEARCH_USE_NOT_AUTHORIZED")
        elif source.get("purpose") != purpose or source.get("SYNTHETIC") is not dataset.get(
            "SYNTHETIC"
        ):
            reasons.append("SOURCE_PURPOSE_MISMATCH")
        elif not _known(source.get("license_id")) or not _known(source.get("license_url")):
            reasons.append("LICENSE_REFERENCE_MISSING")
        elif purpose == "AUTHORIZED_ORCHARD_PILOT" and not _known(
            source.get("authorization_evidence_ref")
        ):
            reasons.append("ORCHARD_AUTHORIZATION_EVIDENCE_MISSING")
    if type(dataset.get("SYNTHETIC")) is not bool or (
        purpose == "SYNTHETIC_ENGINEERING"
    ) != dataset.get("SYNTHETIC"):
        reasons.append("DATA_PURPOSE_SYNTHETIC_MISMATCH")
    return reasons


def _training_scope_reasons(dataset: JSONDict, split: JSONDict, freeze: JSONDict) -> list[str]:
    """Validate declared fitting scope; keep external/synthetic training provenance separate."""
    reasons: list[str] = []
    assigned = {row["image_id"]: row["split"] for row in split.get("records", [])}
    scope = {image_id for image_id, value in assigned.items() if value in EVALUATION_SPLITS}
    images = _images(dataset)
    training_ids = freeze.get("training_image_ids")
    training_assets = freeze.get("training_asset_hashes")
    for declared in (training_ids, training_assets):
        if declared is not None and (
            not isinstance(declared, list)
            or any(not isinstance(value, str) for value in declared)
            or len(set(declared)) != len(declared)
        ):
            reasons.append("TRAINING_SCOPE_INVALID")
    if (
        isinstance(training_ids, list)
        and all(isinstance(value, str) for value in training_ids)
        and set(training_ids) & scope
    ):
        reasons.append("TRAINING_TEST_LEAKAGE")
    test_assets = {images[image_id]["asset_sha256"] for image_id in scope}
    if (
        isinstance(training_assets, list)
        and all(isinstance(value, str) for value in training_assets)
        and set(training_assets) & test_assets
    ):
        reasons.append("TRAINING_TEST_LEAKAGE")
    if freeze.get("training_dataset_manifest_hash") == dataset["manifest_hash"]:
        if not isinstance(training_ids, list) or not training_ids:
            reasons.append("TRAINING_SCOPE_NOT_DECLARED")
        elif any(assigned.get(image_id) != "TRAIN" for image_id in training_ids):
            reasons.append("TRAINING_SCOPE_INVALID")
    return reasons


def check_admission(
    dataset: JSONDict,
    split: JSONDict,
    annotations: JSONDict | list[JSONDict] | None,
    *,
    freeze: JSONDict | None = None,
    test_seal: JSONDict | None = None,
    predictions: JSONDict | None = None,
    ledger: JSONDict | Path | None = None,
) -> JSONDict:
    """Return explicit NOT_EVALUABLE coverage and reasons for every failed gate."""
    reasons = _split_reasons(dataset, split)
    records = split.get("records", [])
    scope = {
        row["image_id"]
        for row in records
        if isinstance(row, dict)
        and isinstance(row.get("image_id"), str)
        and isinstance(row.get("split"), str)
        and row.get("split") in EVALUATION_SPLITS
        and row["image_id"] in _images(dataset)
    }
    if not scope:
        reasons.append("TEST_SCOPE_EMPTY")
    reasons.extend(_source_reasons(dataset, scope))
    if (
        freeze is None
        or not verify_seal(freeze, "freeze_hash")
        or any(not _is_hash(freeze.get(key)) for key in HASH_FIELDS)
    ):
        reasons.append("CONFIG_NOT_FROZEN")
    elif freeze.get("configuration_frozen") is False:
        reasons.append("CONFIG_NOT_FROZEN")
    elif freeze.get("dataset_manifest_hash") not in (None, dataset.get("manifest_hash")):
        reasons.append("FREEZE_DATASET_MISMATCH")
    if freeze is not None:
        reasons.extend(_training_scope_reasons(dataset, split, freeze))
    refs: dict[str, JSONDict] = {}
    try:
        rows = _annotation_rows(annotations)
    except SplitError as exc:
        reasons.append(exc.code)
        rows = []
    for annotation_row in rows:
        image_id = annotation_row.get("image_id")
        if not isinstance(image_id, str) or image_id not in _images(dataset):
            reasons.append("ANNOTATION_IMAGE_IDENTITY_MISMATCH")
            continue
        if image_id in refs:
            reasons.append("ANNOTATION_VERSION_CONFLICT")
        refs[image_id] = annotation_row
    if isinstance(annotations, dict):
        if annotations.get("dataset_manifest_hash") != dataset.get("manifest_hash"):
            reasons.append("ANNOTATION_DATASET_MISMATCH")
        if annotations.get("purpose") != dataset.get("purpose") or annotations.get(
            "SYNTHETIC"
        ) != dataset.get("SYNTHETIC"):
            reasons.append("GT_PURPOSE_MISMATCH")
    images = _images(dataset)
    label_versions = {
        refs[image_id].get("label_definition_version")
        for image_id in scope
        if image_id in refs and isinstance(refs[image_id].get("label_definition_version"), str)
    }
    if len(label_versions) > 1:
        reasons.append("LABEL_DEFINITION_VERSION_CONFLICT")
    qualified = 0
    per_image = []
    for image_id in sorted(scope):
        row = refs.get(image_id)
        local: list[str] = []
        if (
            row is None
            or row.get("gt_status") == "UNANNOTATED"
            or row.get("objects") is None
            or row.get("visible_count") is None
        ):
            local.append("GT_MISSING")
        else:
            hash_key = "snapshot_hash" if "snapshot_hash" in row else "annotation_hash"
            if not verify_seal(row, hash_key):
                local.append("ANNOTATION_HASH_INVALID")
            if row.get("source_asset_hash") != images[image_id]["asset_sha256"]:
                local.append("GT_ASSET_IDENTITY_MISMATCH")
            local.extend(
                _reference_reasons(
                    row,
                    dataset.get("SYNTHETIC") is True,
                    {
                        **images[image_id],
                        "purpose": dataset.get("purpose"),
                        "SYNTHETIC": dataset.get("SYNTHETIC"),
                    },
                )
            )
            if row.get("purpose") not in (None, dataset.get("purpose")):
                local.append("GT_PURPOSE_MISMATCH")
            if row.get("SYNTHETIC") not in (None, dataset.get("SYNTHETIC")):
                local.append("GT_PURPOSE_MISMATCH")
            objects = row["objects"]
            if not isinstance(objects, list) or any(not isinstance(obj, dict) for obj in objects):
                local.append("GT_OBJECTS_INVALID")
                objects = []
            targets = [obj for obj in objects if obj.get("disposition", "TARGET") == "TARGET"]
            if (
                type(row.get("visible_count")) is not int
                or row["visible_count"] < 0
                or row["visible_count"] != len(targets)
            ):
                local.append("GT_COUNT_INVALID")
            for obj in objects:
                box = obj.get("bbox_xyxy")
                if (
                    not isinstance(box, list)
                    or len(box) != 4
                    or any(type(number) not in (int, float) for number in box)
                    or not 0 <= box[0] < box[2] <= images[image_id]["image_width"]
                    or not 0 <= box[1] < box[3] <= images[image_id]["image_height"]
                ):
                    local.append("GT_GEOMETRY_INVALID")
        reasons.extend(local)
        qualified += not local
        per_image.append(
            {"image_id": image_id, "qualified": not local, "reason_codes": sorted(set(local))}
        )
    if test_seal is not None:
        if (
            not verify_seal(test_seal, "test_seal_hash")
            or test_seal.get("status") != "SEALED_RESEARCH_INTEGRITY"
        ):
            reasons.append("TEST_SEAL_INVALID")
        else:
            current = _seal_payload(dataset, split, refs, freeze)
            for key in (
                "dataset_manifest_hash",
                "split_hash",
                "sealed_images",
                "freeze_hash",
                "train_validation_scope_hash",
            ):
                if test_seal.get(key) != current.get(key):
                    reasons.append("SEALED_TEST_CHANGED")
                    break
    if predictions is not None:
        if not verify_seal(predictions, "prediction_hash"):
            reasons.append("PREDICTION_HASH_INVALID")
        if predictions.get("dataset_manifest_hash") != dataset["manifest_hash"]:
            reasons.append("PREDICTION_DATASET_MISMATCH")
        if (
            freeze is None
            or predictions.get("freeze_hash") != freeze.get("freeze_hash")
            or any(
                predictions.get(key) != freeze.get(key)
                for key in ("model_hash", "config_hash", "training_data_hash")
            )
        ):
            reasons.append("PREDICTION_FREEZE_MISMATCH")
        if test_seal is None:
            reasons.append("TEST_SEAL_REQUIRED")
        if ledger is None:
            reasons.append("EXPOSURE_LEDGER_REQUIRED")
        else:
            try:
                resolved = load_exposure_ledger(ledger) if isinstance(ledger, Path) else ledger
                _validate_ledger(resolved)
                events = resolved["events"]
                reference_hash = (
                    annotations.get("annotations_hash")
                    if isinstance(annotations, dict)
                    else canonical_hash(annotations)
                )
                if not any(
                    event["event"] == "GT_SCORE_READ"
                    and event["details"].get("prediction_hash")
                    == predictions.get("prediction_hash")
                    and event["details"].get("freeze_hash") == predictions.get("freeze_hash")
                    and event["details"].get("annotations_hash") == reference_hash
                    for event in events
                ):
                    reasons.append("GT_SCORE_READ_NOT_RECORDED")
            except (SplitError, KeyError, TypeError):
                reasons.append("EXPOSURE_LEDGER_INVALID")
    reasons = sorted(set(reasons))
    return seal(
        {
            "schema_version": "blueberry-vision-admission/3.0.0",
            "status": "NOT_EVALUABLE"
            if reasons
            else "ADMITTED_SYNTHETIC_ENGINEERING"
            if dataset.get("SYNTHETIC")
            else "ADMITTED_EXTERNAL_BENCHMARK",
            "reason_codes": reasons,
            "purpose": dataset.get("purpose"),
            "SYNTHETIC": dataset.get("SYNTHETIC"),
            "dataset_manifest_hash": dataset["manifest_hash"],
            "split_hash": split.get("split_hash"),
            "evaluated_scope_count": len(scope),
            "qualified_reference_count": qualified,
            "missing_or_unqualified_count": len(scope) - qualified,
            "images": per_image,
            "independent_access_control": False,
        },
        "admission_hash",
    )


def _seal_payload(
    dataset: JSONDict,
    split: JSONDict,
    refs: dict[str, JSONDict],
    freeze: JSONDict | None,
) -> JSONDict:
    records = split.get("records", [])
    sealed_images = [
        {
            "image_id": row["image_id"],
            "asset_sha256": row["asset_sha256"],
            "annotation_version": refs.get(row["image_id"], {}).get("annotation_version"),
            "label_definition_version": refs.get(row["image_id"], {}).get(
                "label_definition_version"
            ),
            "annotation_hash": refs.get(row["image_id"], {}).get(
                "snapshot_hash", refs.get(row["image_id"], {}).get("annotation_hash")
            ),
        }
        for row in records
        if row["split"] in EVALUATION_SPLITS
    ]
    return {
        "dataset_manifest_hash": dataset["manifest_hash"],
        "split_hash": split["split_hash"],
        "sealed_images": sealed_images,
        "train_validation_scope_hash": canonical_hash(
            [row for row in records if row["split"] in {"TRAIN", "VALIDATION"}]
        ),
        "freeze_hash": (freeze or {}).get("freeze_hash"),
        **{key: (freeze or {}).get(key) for key in HASH_FIELDS},
    }


def seal_test(
    dataset: JSONDict,
    split: JSONDict,
    annotations: JSONDict | list[JSONDict] | None,
    freeze: JSONDict | None,
    *,
    exposure_history: list[JSONDict] | None = None,
    ledger: JSONDict | Path | None = None,
    output_path: Path | None = None,
) -> JSONDict:
    """Seal qualified references or preserve an explicit unscorable admission report."""
    admission = check_admission(dataset, split, annotations, freeze=freeze)
    refs = {row["image_id"]: row for row in _annotation_rows(annotations)}
    payload = _seal_payload(dataset, split, refs, freeze)
    synthetic = dataset.get("SYNTHETIC") is True
    exposure = (
        "SIMULATED_ENGINEERING"
        if synthetic
        else "EXPOSED_PUBLIC_BENCHMARK"
        if dataset.get("purpose") == "PUBLIC_EXTERNAL_BENCHMARK"
        else "OFFLINE_RESEARCH_SEAL_NO_INDEPENDENT_ACCESS_CONTROL"
    )
    ledger_value = load_exposure_ledger(ledger) if isinstance(ledger, Path) else ledger
    result = seal(
        {
            "schema_version": "blueberry-vision-test-seal/3.0.0",
            "status": "NOT_EVALUABLE" if admission["reason_codes"] else "SEALED_RESEARCH_INTEGRITY",
            "reason_codes": admission["reason_codes"],
            **payload,
            "purpose": dataset.get("purpose"),
            "SYNTHETIC": synthetic,
            "test_exposure": exposure,
            "exposure_history": exposure_history or [],
            "exposure_ledger_hash": (ledger_value or {}).get("ledger_hash"),
            "independent_access_control": False,
            "reviewer_identity_authenticated": False,
            "real_orchard_accuracy_approved": False,
            "limitations": [
                "Research artifact integrity and an append-only ledger "
                "are not a production custody system.",
                "Public reference exposure prevents any previously-unseen blind-test claim.",
            ],
        },
        "test_seal_hash",
    )
    if output_path is not None:
        write_json_new(output_path, result)
    return result


def _validate_ledger(ledger: JSONDict) -> None:
    if not verify_seal(ledger, "ledger_hash") or not isinstance(ledger.get("events"), list):
        raise SplitError("EXPOSURE_LEDGER_INVALID")
    prior_hash = None
    previous: list[JSONDict] = []
    for sequence, event in enumerate(ledger["events"], 1):
        if (
            not isinstance(event, dict)
            or not verify_seal(event, "event_hash")
            or event.get("sequence") != sequence
            or event.get("previous_event_hash") != prior_hash
        ):
            raise SplitError("EXPOSURE_LEDGER_INVALID")
        _event_order(previous, event["event"], event["details"])
        previous.append(event)
        prior_hash = event["event_hash"]


def _event_order(events: list[JSONDict], event: str, details: JSONDict) -> None:
    if event not in {"CONFIG_FROZEN", "PREDICTIONS_FIXED", "GT_SCORE_READ", "PUBLIC_GT_EXPOSED"}:
        raise SplitError("EXPOSURE_EVENT_INVALID")
    if event == "PUBLIC_GT_EXPOSED":
        return
    if not _is_hash(details.get("freeze_hash")):
        raise SplitError("EXPOSURE_ORDER_INVALID")
    if event == "CONFIG_FROZEN":
        return
    frozen = any(
        item["event"] == "CONFIG_FROZEN"
        and item["details"].get("freeze_hash") == details.get("freeze_hash")
        for item in events
    )
    if not frozen or not _is_hash(details.get("prediction_hash")):
        raise SplitError("EXPOSURE_ORDER_INVALID")
    if event == "GT_SCORE_READ":
        if not _is_hash(details.get("annotations_hash")) or not any(
            item["event"] == "PREDICTIONS_FIXED"
            and item["details"].get("freeze_hash") == details.get("freeze_hash")
            and item["details"].get("prediction_hash") == details.get("prediction_hash")
            for item in events
        ):
            raise SplitError("EXPOSURE_ORDER_INVALID")


def load_exposure_ledger(directory: Path) -> JSONDict:
    """Read bounded immutable event files and verify both numbering and hash chain."""
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise SplitError("EXPOSURE_LEDGER_PATH_INVALID")
    events: list[JSONDict] = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            if path.is_symlink():
                raise SplitError("EXPOSURE_LEDGER_PATH_INVALID")
            try:
                event = read_json(path, max_bytes=1_000_000)
                if path.name != f"{len(events) + 1:06d}_{event['event']}.json":
                    raise SplitError("EXPOSURE_LEDGER_INVALID")
                events.append(event)
            except (ValueError, OSError, KeyError) as exc:
                raise SplitError("EXPOSURE_LEDGER_INVALID") from exc
    result = seal(
        {
            "schema_version": "blueberry-vision-exposure-ledger/3.0.0",
            "events": events,
            "independent_access_control": False,
        },
        "ledger_hash",
    )
    _validate_ledger(result)
    return result


def append_exposure_event(
    directory: Path,
    event: str,
    details: JSONDict,
    *,
    actor_id: str = "offline-self-asserted-operator",
    artifact_path: Path | None = None,
) -> JSONDict:
    """Create a new numbered file exclusively; never rewrite a previous event."""
    ledger = load_exposure_ledger(directory)
    _event_order(ledger["events"], event, details)
    if not _known(actor_id):
        raise SplitError("EXPOSURE_ACTOR_INVALID")
    artifact: JSONDict | None = None
    if artifact_path is not None:
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise SplitError("EXPOSURE_ARTIFACT_INVALID")
        artifact = {"filename": artifact_path.name, "file_sha256": file_hash(artifact_path)}
    events = ledger["events"]
    result = seal(
        {
            "schema_version": "blueberry-vision-exposure-event/3.0.0",
            "sequence": len(events) + 1,
            "previous_event_hash": events[-1]["event_hash"] if events else None,
            "event": event,
            "details": details,
            "artifact": artifact,
            "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "actor_id": actor_id,
            "actor_identity_authenticated": False,
            "independent_access_control": False,
        },
        "event_hash",
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{len(events) + 1:06d}_{event}.json"
    try:
        write_json_new(path, result)
    except FileExistsError as exc:
        raise SplitError("EXPOSURE_LEDGER_CONCURRENT_WRITE") from exc
    return result
