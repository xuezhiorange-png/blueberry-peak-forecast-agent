"""Bounded source-licensed PNG/JPEG imports and auxiliary image quality review."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image

from ..assets import AssetError, AssetPolicy, LoadedAsset, load_asset
from ..r2_common import JSONDict, canonical_hash, read_json, seal, verify_seal, write_json_new
from .contracts import (
    PURPOSES,
    SCHEMA_VERSION,
    DatasetError,
    validate_manifest,
    validate_source,
    validate_timestamp,
)
from .contracts import load_manifest as load_manifest

MAX_IMAGES = 100
MAX_TOTAL_BYTES = 500_000_000


def _guard_root(data_root: Path) -> None:
    """Reject symlinks in every lexical root ancestor, before R2's secure dirfd loader."""
    if ".." in data_root.parts:
        raise DatasetError("DATA_ROOT_PATH_UNSAFE")
    absolute = Path(os.path.abspath(data_root))
    for part in [*reversed(absolute.parents), absolute]:
        try:
            mode = part.lstat().st_mode
        except OSError as exc:
            raise DatasetError("DATA_ROOT_UNAVAILABLE") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise DatasetError("DATA_ROOT_PATH_UNSAFE")


def secure_load_asset(
    data_root: Path,
    asset_ref: str,
    expected_hash: str | None = None,
    expected_size: tuple[int, int] | None = None,
    policy: AssetPolicy | None = None,
) -> LoadedAsset:
    _guard_root(data_root)
    try:
        return load_asset(data_root, asset_ref, expected_hash, expected_size, policy)
    except AssetError as exc:
        raise DatasetError(exc.code) from exc


def _json(value: JSONDict | Path) -> JSONDict:
    return read_json(value) if isinstance(value, Path) else value


def _sources(registry: JSONDict) -> dict[str, JSONDict]:
    if "registry_hash" in registry and not verify_seal(registry, "registry_hash"):
        raise DatasetError("SOURCE_REGISTRY_HASH_MISMATCH")
    rows = registry.get("sources", registry.get("datasets", []))
    if not isinstance(rows, list):
        raise DatasetError("SOURCE_REGISTRY_INVALID")
    result = {}
    for source in rows:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise DatasetError("SOURCE_REGISTRY_INVALID")
        if source["source_id"] in result:
            raise DatasetError("SOURCE_ID_INVALID_OR_DUPLICATE")
        result[source["source_id"]] = source
    return result


def _folder_records(data_root: Path, source_id: object, max_images: int) -> list[JSONDict]:
    if not isinstance(source_id, str) or not source_id:
        raise DatasetError("FOLDER_SOURCE_ID_REQUIRED")
    _guard_root(data_root)
    rows = []
    for directory, subdirs, files in os.walk(data_root, followlinks=False):
        for name in subdirs:
            if (Path(directory) / name).is_symlink():
                raise DatasetError("ASSET_PATH_UNSAFE")
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink():
                raise DatasetError("ASSET_PATH_UNSAFE")
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                raise DatasetError("IMAGE_FORMAT_UNSUPPORTED")
            ref = path.relative_to(data_root).as_posix()
            rows.append(
                {
                    "image_id": "import-" + canonical_hash(ref)[:20],
                    "asset_ref": ref,
                    "source_id": source_id,
                }
            )
            if len(rows) > max_images:
                raise DatasetError("IMPORT_IMAGES_LIMIT")
    return sorted(rows, key=lambda row: row["asset_ref"])


def import_images(
    data_root: Path,
    source_index: JSONDict | Path,
    registry: JSONDict | Path,
    output_dir: Path,
    *,
    max_images: int = MAX_IMAGES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    policy: AssetPolicy | None = None,
    coco: JSONDict | Path | None = None,
) -> JSONDict:
    """Import actual pixels; reject the whole admission on any failed image or authority.

    No capture time inferred from file dates. COCO is indexed separately, with no
    target geometry in the pixel-only dataset contract. Original bytes stay put.
    """
    if (
        type(max_images) is not int
        or not 1 <= max_images <= MAX_IMAGES
        or type(max_total_bytes) is not int
        or not 1 <= max_total_bytes <= MAX_TOTAL_BYTES
    ):
        raise DatasetError("IMPORT_LIMIT_INVALID")
    active_policy = policy or AssetPolicy()
    if (
        active_policy.max_bytes > 20_000_000
        or active_policy.max_pixels > 25_000_000
        or active_policy.max_dimension > 8192
    ):
        raise DatasetError("IMPORT_ASSET_POLICY_EXCEEDS_LIMIT")
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise DatasetError("OUTPUT_PATH_UNSAFE")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DatasetError("OUTPUT_ALREADY_EXISTS")
    index, sources = _json(source_index), _sources(_json(registry))
    purpose, synthetic = index.get("purpose"), index.get("SYNTHETIC")
    if (
        purpose not in PURPOSES
        or type(synthetic) is not bool
        or synthetic != (purpose == "SYNTHETIC_ENGINEERING")
    ):
        raise DatasetError("DATASET_PURPOSE_MISMATCH")
    purpose = cast(str, purpose)
    synthetic_mode = synthetic is True
    _guard_root(data_root)
    rows = index.get("images")
    if rows is None:
        rows = _folder_records(data_root, index.get("source_id"), max_images)
    if not isinstance(rows, list) or not rows:
        raise DatasetError("DATASET_EMPTY")
    if len(rows) > max_images:
        raise DatasetError("IMPORT_IMAGES_LIMIT")
    used_sources: dict[str, JSONDict] = {}
    images: list[JSONDict] = []
    seen: set[str] = set()
    total = 0
    batch_id = "import-batch-" + canonical_hash(index)[:20]
    for row in rows:
        if not isinstance(row, dict):
            raise DatasetError("IMAGE_INDEX_INVALID")
        image_id = row.get("image_id")
        if not isinstance(image_id, str) or not image_id:
            raise DatasetError("IMAGE_ID_INVALID")
        if image_id in seen:
            raise DatasetError("IMAGE_ID_DUPLICATE")
        seen.add(image_id)
        source_id = row.get("source_id")
        if not isinstance(source_id, str):
            raise DatasetError("SOURCE_ID_UNKNOWN")
        source = sources.get(source_id)
        if source is None:
            raise DatasetError("SOURCE_ID_UNKNOWN")
        validate_source(source, purpose, synthetic_mode)
        for key in ("license_id", "license_url", "license_status"):
            if key in row and row[key] != source[key]:
                raise DatasetError("IMAGE_SOURCE_LICENSE_MISMATCH")
        if (
            row.get("SYNTHETIC", synthetic_mode) is not synthetic_mode
            or row.get("purpose", purpose) != purpose
        ):
            raise DatasetError("IMAGE_PURPOSE_MISMATCH")
        observed = row.get("observed_at")
        if observed is not None:
            validate_timestamp(observed)
        ref = row.get("asset_ref")
        if not isinstance(ref, str):
            raise DatasetError("ASSET_REF_INVALID")
        # Bound total raw bytes before decoding this entry. R2 bounds each file separately.
        if not ref.startswith("/") and ".." not in ref.split("/"):
            try:
                size = (data_root / ref).lstat().st_size
            except OSError as exc:
                raise DatasetError("ASSET_NOT_FOUND") from exc
        else:
            raise DatasetError("ASSET_REF_INVALID")
        total += size
        if total > max_total_bytes:
            raise DatasetError("IMPORT_BYTES_LIMIT")
        expected_size = None
        if "image_width" in row or "image_height" in row:
            # Missing one of the two advertised dimensions is a failed binding, not guessed.
            if type(row.get("image_width")) is not int or type(row.get("image_height")) is not int:
                raise DatasetError("IMAGE_SIZE_MISMATCH")
            expected_size = (row["image_width"], row["image_height"])
        loaded = secure_load_asset(data_root, ref, row.get("asset_sha256"), expected_size, policy)
        meta = loaded.metadata
        record: JSONDict = {
            "image_id": image_id,
            "asset_ref": ref,
            "asset_size_bytes": size,
            **{
                key: meta[key]
                for key in (
                    "asset_sha256",
                    "rgb_sha256",
                    "image_width",
                    "image_height",
                    "preprocessing_version",
                    "preprocessing_hash",
                )
            },
            "source_id": source["source_id"],
            "source_authority": {
                "source_id": source["source_id"],
                "purpose": purpose,
                "research_use": source["research_use"],
                "license_status": source["license_status"],
            },
            **{key: source[key] for key in ("license_id", "license_url", "license_status")},
            "purpose": purpose,
            "SYNTHETIC": synthetic_mode,
            "observed_at": observed,
            "capture_time_status": row.get(
                "capture_time_status",
                "UNKNOWN_NOT_PROVIDED" if observed is None else "UNKNOWN_UNVERIFIED",
            ),
            "source_provided_capture_date": row.get("source_provided_capture_date"),
            "asset_available_at": row.get("asset_available_at"),
            "base_identity": row.get(
                "base_identity", {"status": "UNRESOLVED", "base_id": None, "authority_ref": None}
            ),
            "variety": row.get("variety"),
            **{
                key: row.get(key)
                for key in (
                    "capture_session_id",
                    "sampling_unit_id",
                    "video_id",
                    "frame_index",
                    "parent_image_id",
                    "multiview_group_id",
                    "source_batch_id",
                    "annotation_version",
                    "annotation_ref",
                )
            },
            "import_batch_id": batch_id,
            "scene_metadata": row.get("scene_metadata", {}),
        }
        if not isinstance(record["base_identity"], dict):
            raise DatasetError("BASE_IDENTITY_INVALID")
        if record["base_identity"].get("status") == "UNRESOLVED":
            record["base_identity"] = {
                "status": "UNRESOLVED",
                "base_id": record["base_identity"].get("base_id"),
                "authority_ref": record["base_identity"].get("authority_ref"),
            }
        images.append(seal(record, "record_hash"))
        used_sources[source["source_id"]] = source
    annotation_index = _coco_index(_json(coco), images) if coco is not None else None
    dataset = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": index.get("dataset_id"),
            "dataset_version": index.get("dataset_version"),
            "purpose": purpose,
            "SYNTHETIC": synthetic_mode,
            "sources": [used_sources[key] for key in sorted(used_sources)],
            "images": sorted(images, key=lambda row: row["image_id"]),
            "source_index_hash": canonical_hash(index),
            "import_policy": {
                "max_images": max_images,
                "max_total_bytes": max_total_bytes,
                "max_asset_bytes": (policy or AssetPolicy()).max_bytes,
                "source_originals_modified": False,
                "capture_time_from_mtime": False,
            },
            "annotation_index": annotation_index,
        },
        "manifest_hash",
    )
    validate_manifest(dataset)
    write_json_new(output_dir / "dataset_manifest.json", dataset)
    return dataset


def _coco_index(coco: JSONDict, images: list[JSONDict]) -> JSONDict:
    """Bind standard COCO image IDs to imported files; geometry lives in annotation module."""
    if not isinstance(coco.get("images"), list) or not isinstance(coco.get("annotations"), list):
        raise DatasetError("COCO_STRUCTURE_INVALID")
    refs = {row["asset_ref"]: row for row in images}
    ids = set()
    mappings = []
    for row in coco["images"]:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in ids:
            raise DatasetError("COCO_IMAGE_ID_INVALID")
        ids.add(row["id"])
        image = refs.get(row.get("file_name"))
        if image is None:
            raise DatasetError("COCO_IMAGE_ASSET_UNMATCHED")
        if row.get("width") != image["image_width"] or row.get("height") != image["image_height"]:
            raise DatasetError("COCO_IMAGE_SIZE_MISMATCH")
        mappings.append(
            {
                "coco_image_id": row["id"],
                "image_id": image["image_id"],
                "source_asset_hash": image["asset_sha256"],
            }
        )
    if len(mappings) != len(images):
        raise DatasetError("COCO_IMAGE_COVERAGE_MISMATCH")
    if any(
        not isinstance(row, dict) or row.get("image_id") not in ids for row in coco["annotations"]
    ):
        raise DatasetError("COCO_ANNOTATION_IMAGE_UNMATCHED")
    return {
        "format": "COCO_DETECTION",
        "source_annotation_hash": canonical_hash(coco),
        "images": mappings,
        "status": "INDEXED_NOT_GT_QUALITY_APPROVED",
    }


def audit_images(dataset: JSONDict, data_root: Path) -> JSONDict:
    """Real pixel quality candidates; no quality score substitutes for human GT."""
    validate_manifest(dataset)
    rows = []
    for row in dataset["images"]:
        try:
            loaded = secure_load_asset(
                data_root,
                row["asset_ref"],
                row["asset_sha256"],
                (row["image_width"], row["image_height"]),
            )
            if (
                loaded.metadata["preprocessing_hash"] != row["preprocessing_hash"]
                or loaded.metadata["rgb_sha256"] != row["rgb_sha256"]
            ):
                raise DatasetError("PREPROCESSING_HASH_MISMATCH")
            # QA is auxiliary. Bound its float workspace separately from source decoding.
            candidate = Image.fromarray(loaded.rgb)
            candidate.thumbnail((512, 512), Image.Resampling.LANCZOS)
            rgb = np.asarray(candidate).astype(np.float64) / 255.0
            gray = rgb @ np.array([0.2126, 0.7152, 0.0722])
            value, low = rgb.max(axis=2), rgb.min(axis=2)
            saturation = np.divide(value - low, value, out=np.zeros_like(value), where=value > 0)
            laplace = (
                -4 * gray[1:-1, 1:-1]
                + gray[:-2, 1:-1]
                + gray[2:, 1:-1]
                + gray[1:-1, :-2]
                + gray[1:-1, 2:]
            )
            blur = float(laplace.var()) if laplace.size else None
            brightness, contrast = float(gray.mean()), float(gray.std())
            flags = []
            if min(row["image_width"], row["image_height"]) < 128:
                flags.append("LOW_RESOLUTION_CANDIDATE")
            if brightness < 0.08 or brightness > 0.95:
                flags.append("EXTREME_BRIGHTNESS_CANDIDATE")
            if blur is not None and blur < 0.0001:
                flags.append("LOW_DETAIL_OR_BLUR_CANDIDATE")
            rows.append(
                {
                    "image_id": row["image_id"],
                    "status": "VALID",
                    "reason_code": None,
                    "image_width": row["image_width"],
                    "image_height": row["image_height"],
                    "aspect_ratio": row["image_width"] / row["image_height"],
                    "brightness": brightness,
                    "contrast": contrast,
                    "saturation": float(saturation.mean()),
                    "laplacian_variance": blur,
                    "quality_thumbnail_dimensions": list(candidate.size),
                    "candidate_flags": flags,
                    "annotatability": "REQUIRES_HUMAN_REVIEW",
                }
            )
        except DatasetError as exc:
            rows.append(
                {
                    "image_id": row["image_id"],
                    "status": "FAILED",
                    "reason_code": exc.code,
                    "annotatability": "NOT_REVIEWABLE_DECODE_FAILED",
                }
            )
    valid = sum(row["status"] == "VALID" for row in rows)
    indexed = sum(row.get("annotation_ref") is not None for row in dataset["images"])
    return seal(
        {
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "images": rows,
            "annotation_coverage": indexed / len(rows),
            "annotation_coverage_semantics": "ASSET_REFERENCE_ONLY_NOT_QUALITY_APPROVED",
            "unannotated_count": len(rows) - indexed,
            "per_fruit_label_count": None,
            "source_distribution": {
                source["source_id"]: sum(
                    row["source_id"] == source["source_id"] for row in dataset["images"]
                )
                for source in dataset["sources"]
            },
            "summary": {
                "image_count": len(rows),
                "valid_count": valid,
                "failed_count": len(rows) - valid,
                "possible_unannotatable_candidates": sum(
                    bool(row.get("candidate_flags")) for row in rows
                ),
                "quality_metrics_are_auxiliary": True,
                "business_label_quality_inferred": False,
            },
        },
        "quality_hash",
    )
