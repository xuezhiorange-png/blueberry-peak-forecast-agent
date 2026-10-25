"""Bounded local PNG/JPEG loading for authorized synthetic research assets only.

No network, upload, production imports, or original-image mutation. Asset references
are local root-relative paths, not web URLs. Every path component is opened with
O_NOFOLLOW: symlinks are intentionally rejected, including those staying in root.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps, UnidentifiedImageError

from research.blueberry_vision.r2_common import JSONDict, canonical_hash, read_json, seal
from research.blueberry_vision.r2_contracts import (
    PREPROCESSING_VERSION,
    DatasetError,
    validate_dataset,
)

REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")


class AssetError(ValueError):
    """Stable reason only; never expose sensitive path or decoded input details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AssetPolicy:
    max_bytes: int = 20_000_000
    max_pixels: int = 25_000_000
    max_dimension: int = 8192

    def __post_init__(self) -> None:
        if any(
            type(v) is not int or v <= 0
            for v in (self.max_bytes, self.max_pixels, self.max_dimension)
        ):
            raise AssetError("ASSET_POLICY_INVALID")


@dataclass(frozen=True)
class LoadedAsset:
    rgb: npt.NDArray[np.uint8]
    metadata: JSONDict


def _read_authorized(data_root: Path, asset_ref: str, policy: AssetPolicy) -> bytes:
    if (
        not isinstance(asset_ref, str)
        or len(asset_ref) > 512
        or not REF_PATTERN.fullmatch(asset_ref)
        or any(part in {"", ".", ".."} for part in asset_ref.split("/"))
    ):
        raise AssetError("ASSET_REF_INVALID")
    if Path(asset_ref).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise AssetError("IMAGE_FORMAT_UNSUPPORTED")
    descriptors: list[int] = []
    try:
        root = data_root.resolve(strict=True)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root_fd)
        parts = asset_ref.split("/")
        for part in parts[:-1]:
            root_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            descriptors.append(root_fd)
        asset_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
        descriptors.append(asset_fd)
        info = os.fstat(asset_fd)
        if not stat.S_ISREG(info.st_mode):
            raise AssetError("ASSET_NOT_REGULAR_FILE")
        if info.st_size > policy.max_bytes:
            raise AssetError("ASSET_BYTES_LIMIT")
        pieces = []
        total = 0
        while total <= policy.max_bytes:
            block = os.read(asset_fd, min(65536, policy.max_bytes + 1 - total))
            if not block:
                break
            pieces.append(block)
            total += len(block)
        if total > policy.max_bytes:
            raise AssetError("ASSET_BYTES_LIMIT")
        return b"".join(pieces)
    except FileNotFoundError as exc:
        raise AssetError("ASSET_NOT_FOUND") from exc
    except OSError as exc:
        raise AssetError("ASSET_PATH_UNSAFE") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def load_asset(
    data_root: Path,
    asset_ref: str,
    expected_hash: str | None = None,
    expected_size: tuple[int, int] | None = None,
    policy: AssetPolicy | None = None,
) -> LoadedAsset:
    """Read bounded original bytes, verify, orient, and normalize RGB independently.

    RGB normalization: EXIF transpose first, RGBA/P transparency composited on
    opaque white, then RGB. preprocessing_hash binds original-byte hash, normalized
    RGB-byte hash, dimensions, algorithm version, and alpha background. This is
    an independent in-memory derivative; the source file is never written.
    """
    active_policy = policy or AssetPolicy()
    content = _read_authorized(data_root, asset_ref, active_policy)
    source_hash = hashlib.sha256(content).hexdigest()
    if expected_hash is not None and source_hash != expected_hash:
        raise AssetError("ASSET_HASH_MISMATCH")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise AssetError("IMAGE_FORMAT_UNSUPPORTED")
                original_width, original_height = image.size
                if original_width * original_height > active_policy.max_pixels:
                    raise AssetError("IMAGE_PIXELS_LIMIT")
                if max(original_width, original_height) > active_policy.max_dimension:
                    raise AssetError("IMAGE_DIMENSION_LIMIT")
                if getattr(image, "n_frames", 1) != 1:
                    raise AssetError("IMAGE_MULTIFRAME_UNSUPPORTED")
                image.verify()
            with Image.open(io.BytesIO(content)) as decoded:
                decoded.load()
                normalized = ImageOps.exif_transpose(decoded)
                if "A" in normalized.getbands() or "transparency" in normalized.info:
                    rgba = normalized.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    normalized = Image.alpha_composite(background, rgba).convert("RGB")
                else:
                    normalized = normalized.convert("RGB")
                width, height = normalized.size
                rgb = np.array(normalized, dtype=np.uint8, copy=True)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise AssetError("IMAGE_DECOMPRESSION_BOMB") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        if isinstance(exc, AssetError):
            raise
        raise AssetError("IMAGE_DECODE_FAILED") from exc
    if expected_size is not None and (width, height) != expected_size:
        raise AssetError("IMAGE_SIZE_MISMATCH")
    rgb_hash = hashlib.sha256(rgb.tobytes(order="C")).hexdigest()
    metadata: JSONDict = {
        "asset_sha256": source_hash,
        "image_width": width,
        "image_height": height,
        "original_width": original_width,
        "original_height": original_height,
        "rgb_sha256": rgb_hash,
        "preprocessing_version": PREPROCESSING_VERSION,
        "preprocessing_hash": canonical_hash(
            {
                "source_asset_hash": source_hash,
                "preprocessing_version": PREPROCESSING_VERSION,
                "image_width": width,
                "image_height": height,
                "rgb_sha256": rgb_hash,
                "alpha_background": [255, 255, 255],
            }
        ),
    }
    return LoadedAsset(rgb=rgb, metadata=metadata)


def load_dataset(path: Path) -> JSONDict:
    """Validate JSON plus semantic seals without rewriting or filling any field."""
    try:
        data = read_json(path)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise AssetError("DATASET_JSON_INVALID") from exc
    try:
        validate_dataset(data)
    except DatasetError as exc:
        raise AssetError(exc.code) from exc
    return data


def validate_assets(manifest_path: Path, data_root: Path) -> JSONDict:
    """Validate actual pixel bytes and preprocessing bindings; retain every failure."""
    try:
        dataset = load_dataset(manifest_path)
    except AssetError as exc:
        return seal(
            {"valid": False, "reason_code": exc.code, "images": [], "summary": {}},
            "validation_hash",
        )
    results: list[JSONDict] = []
    normalized_pixels_seen: set[tuple[int, int, str]] = set()
    for record in dataset["images"]:
        try:
            loaded = load_asset(
                data_root,
                record["original_asset_ref"],
                record["asset_sha256"],
                (record["image_width"], record["image_height"]),
            )
            normalized_identity = (
                loaded.metadata["image_width"],
                loaded.metadata["image_height"],
                loaded.metadata["rgb_sha256"],
            )
            if normalized_identity in normalized_pixels_seen:
                raise AssetError("DUPLICATE_NORMALIZED_RGB")
            normalized_pixels_seen.add(normalized_identity)
            if loaded.metadata["preprocessing_hash"] != record["preprocessing_hash"]:
                raise AssetError("PREPROCESSING_HASH_MISMATCH")
            if record["training_mask_ref"] is not None:
                mask = load_asset(
                    data_root,
                    record["training_mask_ref"],
                    record["training_mask_sha256"],
                    (record["image_width"], record["image_height"]),
                )
                if not np.all(mask.rgb == mask.rgb[:, :, :1]):
                    raise AssetError("TRAINING_MASK_NOT_GRAYSCALE")
                if not np.isin(mask.rgb[:, :, 0], (0, 128, 255)).all():
                    raise AssetError("TRAINING_MASK_VALUES_INVALID")
            results.append({"image_id": record["image_id"], "status": "VALID", "reason_code": None})
        except AssetError as exc:
            results.append(
                {"image_id": record["image_id"], "status": "FAILED", "reason_code": exc.code}
            )
    validated_count = sum(item["status"] == "VALID" for item in results)
    return seal(
        {
            "valid": validated_count == len(results),
            "dataset_manifest_hash": dataset["manifest_hash"],
            "split_hash": dataset["split_hash"],
            "images": results,
            "summary": {
                "SYNTHETIC": True,
                "validated_count": validated_count,
                "failed_count": len(results) - validated_count,
                "actual_asset_bytes_verified": validated_count == len(results),
                "normalized_rgb_exact_duplicate_analysis_performed": True,
                "authorization_authenticity_verified": False,
                "visual_near_duplicate_analysis_performed": False,
            },
        },
        "validation_hash",
    )
