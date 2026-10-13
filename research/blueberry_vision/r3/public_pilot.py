"""Assemble bounded licensed pilot pixels without copying labels into inference inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import cast

from ..assets import AssetError, AssetPolicy, _read_authorized
from ..r2_common import (
    JSONDict,
    _finite_float,
    _reject_constant,
    _unique_keys,
    seal,
    verify_seal,
)
from .contracts import DatasetError, validate_source, validate_timestamp
from .ingestion import _guard_root, secure_load_asset

PURPOSE = "PUBLIC_EXTERNAL_BENCHMARK"
MAX_IMAGES = 100
MAX_TOTAL_BYTES = 500_000_000
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
AUTHORITY_KEYS = (
    "source_id",
    "name",
    "official_url",
    "publisher",
    "creator",
    "purpose",
    "SYNTHETIC",
    "license_id",
    "license_name",
    "license_url",
    "license_status",
    "research_use",
    "commercial_use",
    "model_training",
    "redistribution",
    "attribution_required",
    "share_alike_derivatives",
    "license_conditions",
    "license_evidence",
)
PROVENANCE_KEYS = (
    "original_asset_ref",
    "original_asset_sha256",
    "source_member",
    "source_url",
    "publisher_image_id",
    "preprocessing",
)


def _json_input(value: JSONDict | Path) -> JSONDict:
    if isinstance(value, dict):
        return value
    _guard_root(value.parent)
    descriptor: int | None = None
    try:
        descriptor = os.open(value, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8_000_000:
            raise DatasetError("PILOT_JSON_SIZE_OR_TYPE_INVALID")
        chunks, total = [], 0
        while total <= 8_000_000:
            block = os.read(descriptor, min(65536, 8_000_001 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
        if total > 8_000_000:
            raise DatasetError("PILOT_JSON_SIZE_OR_TYPE_INVALID")
        result = json.loads(
            b"".join(chunks),
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        if not isinstance(result, dict):
            raise DatasetError("PILOT_JSON_OBJECT_REQUIRED")
        return cast(JSONDict, result)
    except (OSError, ValueError, UnicodeError) as exc:
        if isinstance(exc, DatasetError):
            raise
        raise DatasetError("PILOT_JSON_UNSAFE_OR_INVALID") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _portable(value: object) -> object:
    """Keep published provenance, excluding local runtime paths and fetch timestamps."""
    if isinstance(value, dict):
        volatile = {
            "retrieved_at",
            "checked_at",
            "downloaded_at",
            "local_path",
            "workspace_path",
            "output_dir",
            "hostname",
        }
        return {key: _portable(item) for key, item in value.items() if key not in volatile}
    if isinstance(value, list):
        return [_portable(item) for item in value]
    if isinstance(value, str) and (value.startswith("/") or value.startswith("file://")):
        raise DatasetError("PROVENANCE_LOCAL_PATH_FORBIDDEN")
    return value


def _merge_sources(registry: JSONDict, supplement: JSONDict) -> dict[str, JSONDict]:
    result: dict[str, JSONDict] = {}
    for catalog in (registry, supplement):
        if "registry_hash" in catalog and not verify_seal(catalog, "registry_hash"):
            raise DatasetError("SOURCE_REGISTRY_HASH_MISMATCH")
        rows = catalog.get("sources")
        if not isinstance(rows, list):
            raise DatasetError("SOURCE_REGISTRY_INVALID")
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("source_id"), str):
                raise DatasetError("SOURCE_REGISTRY_INVALID")
            identifier = row["source_id"]
            if not identifier or identifier in seen:
                raise DatasetError("SOURCE_ID_INVALID_OR_DUPLICATE")
            seen.add(identifier)
            authority = cast(
                JSONDict, _portable({key: row[key] for key in AUTHORITY_KEYS if key in row})
            )
            if identifier in result and result[identifier] != authority:
                raise DatasetError("SOURCE_AUTHORITY_CONFLICT")
            result[identifier] = authority
    return result


def _prepare_row(row: JSONDict, bucket: str, sources: dict[str, JSONDict]) -> JSONDict:
    if row.get("SYNTHETIC", False) is not False or row.get("purpose", PURPOSE) != PURPOSE:
        raise DatasetError("IMAGE_PURPOSE_MISMATCH")
    identifier, source_id = row.get("image_id"), row.get("source_id")
    if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
        raise DatasetError("IMAGE_ID_INVALID")
    if not isinstance(source_id, str) or source_id not in sources:
        raise DatasetError("SOURCE_ID_UNKNOWN")
    source = sources[source_id]
    validate_source(source, PURPOSE, False)
    for key in ("license_id", "license_url", "license_status"):
        if key in row and row[key] != source[key]:
            raise DatasetError("IMAGE_SOURCE_LICENSE_MISMATCH")
    digest = row.get("asset_sha256")
    if not isinstance(digest, str) or not HASH_PATTERN.fullmatch(digest):
        raise DatasetError("IMAGE_HASH_REQUIRED")
    ref = row.get("asset_ref")
    if not isinstance(ref, str):
        raise DatasetError("ASSET_REF_INVALID")
    if (
        ref.startswith("/")
        or any(part in {"", ".", ".."} for part in ref.split("/"))
        or Path(ref).suffix.lower() not in {".png", ".jpg", ".jpeg"}
    ):
        raise DatasetError("ASSET_REF_INVALID")
    if type(row.get("image_width")) is not int or type(row.get("image_height")) is not int:
        raise DatasetError("IMAGE_SIZE_MISMATCH")
    observed = row.get("observed_at")
    if observed is not None:
        validate_timestamp(observed)
        if row.get("capture_time_status") != "SOURCE_VERIFIED":
            raise DatasetError("CAPTURE_TIME_STATUS_MISMATCH")
    elif not str(row.get("capture_time_status", "UNKNOWN_NOT_PROVIDED")).startswith("UNKNOWN"):
        raise DatasetError("CAPTURE_TIME_STATUS_MISMATCH")
    identity = row.get("base_identity", {"status": "UNRESOLVED"})
    if (
        not isinstance(identity, dict)
        or identity.get("status") != "UNRESOLVED"
        or identity.get("base_id") is not None
        or identity.get("authority_ref") is not None
    ):
        raise DatasetError("PUBLIC_BENCHMARK_COMPANY_IDENTITY_FORBIDDEN")
    raw_hash = row.get("original_asset_sha256", digest)
    if not isinstance(raw_hash, str) or not HASH_PATTERN.fullmatch(raw_hash):
        raise DatasetError("PARENT_ASSET_HASH_INVALID")
    provenance = {key: _portable(row[key]) for key in PROVENANCE_KEYS if key in row}
    provenance.update(
        {
            "parent_asset_sha256": raw_hash,
            "imported_asset_sha256": digest,
            "source_asset_ref": ref,
            "original_bytes_copied": raw_hash == digest,
            "reference_annotations_copied": False,
        }
    )
    pre = row.get("preprocessing")
    if pre is not None and (
        not isinstance(pre, dict)
        or pre.get("original_asset_sha256") != raw_hash
        or pre.get("derived_asset_sha256") != digest
    ):
        raise DatasetError("DERIVATIVE_PROVENANCE_HASH_MISMATCH")
    output: JSONDict = {
        "image_id": identifier,
        "source_id": source_id,
        "asset_ref": f"{bucket}/{digest}{Path(ref).suffix.lower()}",
        "asset_sha256": digest,
        "image_width": row["image_width"],
        "image_height": row["image_height"],
        "purpose": PURPOSE,
        "SYNTHETIC": False,
        **{key: source[key] for key in ("license_id", "license_url", "license_status")},
        "observed_at": observed,
        "capture_time_status": row.get("capture_time_status", "UNKNOWN_NOT_PROVIDED"),
        "source_provided_capture_date": row.get("source_provided_capture_date"),
        "base_identity": {"status": "UNRESOLVED", "base_id": None, "authority_ref": None},
        "variety": row.get("variety"),
        "source_batch_id": row.get("source_batch_id") or f"public-source-batch-{source_id}",
        "multiview_group_id": row.get("multiview_group_id"),
        "scene_metadata": provenance,
    }
    for key in (
        "asset_available_at",
        "original_asset_ref",
        "original_asset_sha256",
        "capture_session_id",
        "sampling_unit_id",
        "video_id",
        "frame_index",
        "parent_image_id",
    ):
        if key in row:
            output[key] = row[key]
    return output


def _create_output_root(output_dir: Path) -> int:
    if ".." in output_dir.parts:
        raise DatasetError("OUTPUT_PATH_UNSAFE")
    absolute = Path(os.path.abspath(output_dir))
    parts = absolute.parts[1:]
    if not parts:
        raise DatasetError("OUTPUT_ALREADY_EXISTS")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        try:
            os.mkdir(parts[-1], dir_fd=descriptor)
        except FileExistsError as exc:
            raise DatasetError("OUTPUT_ALREADY_EXISTS") from exc
        child = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        os.close(descriptor)
        return child
    except OSError as exc:
        os.close(descriptor)
        raise DatasetError("OUTPUT_PATH_UNSAFE") from exc
    except DatasetError:
        os.close(descriptor)
        raise


def _write_new(directory_fd: int, name: str, content: bytes) -> None:
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
    finally:
        os.close(descriptor)


def prepare_public_pilot(
    commons_root: Path,
    quality_root: Path,
    registry: JSONDict | Path,
    supplement: JSONDict | Path,
    output_dir: Path,
    *,
    max_images: int = MAX_IMAGES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> JSONDict:
    """Copy only authorized PNG/JPEG bytes into a new immutable inference data root.

    Source indexes are asset-only adapters. Publisher boxes/counts and local paths
    are deliberately excluded; source time and company identity are never guessed.
    Each actual file must bind its mandatory original-byte SHA256 and dimensions.
    """
    if (
        type(max_images) is not int
        or not 1 <= max_images <= MAX_IMAGES
        or type(max_total_bytes) is not int
        or not 1 <= max_total_bytes <= MAX_TOTAL_BYTES
    ):
        raise DatasetError("PREPARE_LIMIT_INVALID")
    sources = _merge_sources(_json_input(registry), _json_input(supplement))
    policy = AssetPolicy()
    records: list[JSONDict] = []
    copies: list[tuple[Path, str, JSONDict]] = []
    ids: set[str] = set()
    used_sources: set[str] = set()
    total = 0
    for bucket, root in (("commons", commons_root), ("quality", quality_root)):
        _guard_root(root)
        source_index = _json_input(root / "source_index.json")
        if source_index.get("purpose") != PURPOSE or source_index.get("SYNTHETIC") is not False:
            raise DatasetError("DATASET_PURPOSE_MISMATCH")
        if "index_hash" in source_index and not verify_seal(source_index, "index_hash"):
            raise DatasetError("SOURCE_INDEX_HASH_MISMATCH")
        rows = source_index.get("images")
        if not isinstance(rows, list) or not rows:
            raise DatasetError("DATASET_EMPTY")
        for row in rows:
            if not isinstance(row, dict):
                raise DatasetError("IMAGE_INDEX_INVALID")
            prepared = _prepare_row(row, bucket, sources)
            if prepared["image_id"] in ids:
                raise DatasetError("IMAGE_ID_DUPLICATE")
            ids.add(prepared["image_id"])
            if len(ids) > max_images:
                raise DatasetError("PREPARE_IMAGES_LIMIT")
            try:
                content = _read_authorized(root, row["asset_ref"], policy)
            except AssetError as exc:
                raise DatasetError(exc.code) from exc
            if hashlib.sha256(content).hexdigest() != prepared["asset_sha256"]:
                raise DatasetError("ASSET_HASH_MISMATCH")
            total += len(content)
            if total > max_total_bytes:
                raise DatasetError("PREPARE_BYTES_LIMIT")
            secure_load_asset(
                root,
                row["asset_ref"],
                prepared["asset_sha256"],
                (prepared["image_width"], prepared["image_height"]),
                policy,
            )
            prepared["bytes"] = len(content)
            records.append(prepared)
            copies.append((root, row["asset_ref"], prepared))
            used_sources.add(prepared["source_id"])
    combined_registry = seal(
        {
            "registry_version": "blueberry-vision-public-pilot-authorities/3.0.0",
            "purpose": PURPOSE,
            "SYNTHETIC": False,
            "sources": [sources[key] for key in sorted(used_sources)],
            "catalog_scope": "SELECTED_IMAGE_SOURCE_AUTHORITIES_ONLY",
        },
        "registry_hash",
    )
    combined_index = seal(
        {
            "dataset_id": "blueberry-r3-combined-public-pilot",
            "dataset_version": "3.0.0",
            "purpose": PURPOSE,
            "SYNTHETIC": False,
            "image_count": len(records),
            "total_bytes": total,
            "images": sorted(records, key=lambda row: row["image_id"]),
            "source_registry_hash": combined_registry["registry_hash"],
            "reference_status": "ANNOTATIONS_EXCLUDED_FROM_ASSET_INDEX",
        },
        "index_hash",
    )
    output_fd = _create_output_root(output_dir)
    bucket_fds: dict[str, int] = {}
    written: set[str] = set()
    try:
        for bucket in ("commons", "quality"):
            os.mkdir(bucket, dir_fd=output_fd)
            bucket_fds[bucket] = os.open(
                bucket, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=output_fd
            )
        for root, ref, prepared in copies:
            destination = prepared["asset_ref"]
            if destination in written:
                continue
            _guard_root(root)
            try:
                content = _read_authorized(root, ref, policy)
            except AssetError as exc:
                raise DatasetError(exc.code) from exc
            if hashlib.sha256(content).hexdigest() != prepared["asset_sha256"]:
                raise DatasetError("ASSET_CHANGED_DURING_PREPARATION")
            bucket, name = destination.split("/", 1)
            _write_new(bucket_fds[bucket], name, content)
            written.add(destination)
        for name, document in (
            ("source_index.json", combined_index),
            ("source_registry.json", combined_registry),
        ):
            data = json.dumps(
                document, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False
            )
            _write_new(output_fd, name, (data + "\n").encode("utf-8"))
    finally:
        for descriptor in bucket_fds.values():
            os.close(descriptor)
        os.close(output_fd)
    return seal(
        {
            "source_index": combined_index,
            "source_registry": combined_registry,
            "image_count": len(records),
            "total_asset_bytes": total,
            "copy_policy": {
                "max_images": max_images,
                "max_total_bytes": max_total_bytes,
                "source_originals_modified": False,
                "reference_annotations_copied": False,
                "network_access": False,
            },
        },
        "prepare_hash",
    )
