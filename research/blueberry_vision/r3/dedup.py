"""Pixel equality and reviewable perceptual candidate graph, not identity inference."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

from ..r2_common import JSONDict, canonical_hash, seal, verify_seal
from .contracts import DatasetError, validate_manifest, validate_timestamp
from .ingestion import secure_load_asset

DEDUP_VERSION = "r3-dhash-candidate-graph/3.0.0"


def dhash_rgb(rgb: npt.NDArray[np.uint8]) -> str:
    """64-bit horizontal dHash, Pillow grayscale LANCZOS; bits true for left > right."""
    small = np.asarray(Image.fromarray(rgb).convert("L").resize((9, 8), Image.Resampling.LANCZOS))
    value = 0
    for bit in (small[:, :-1] > small[:, 1:]).ravel():
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def _crop_dhash(rgb: npt.NDArray[np.uint8]) -> str:
    height, width = rgb.shape[:2]
    margin_x, margin_y = width // 8, height // 8
    return dhash_rgb(rgb[margin_y : height - margin_y, margin_x : width - margin_x])


def _distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def find_near_duplicates(dataset: JSONDict, data_root: Path, threshold: int = 6) -> JSONDict:
    """Compare every bounded pilot pair, preserving failures and pending crop/resize links.

    Exact bytes/RGB are mechanically confirmed equal; perceptual closeness is
    PENDING, and must block cross-split isolation until reviewed. Flat scenes can
    have the same dHash despite depicting unrelated objects: no identity claim.
    """
    validate_manifest(dataset)
    if type(threshold) is not int or not 0 <= threshold <= 64:
        raise DatasetError("DEDUP_THRESHOLD_INVALID")
    if len(dataset["images"]) > 100:
        raise DatasetError("DEDUP_PILOT_IMAGES_LIMIT")
    rows: list[JSONDict] = []
    for image in dataset["images"]:
        try:
            loaded = secure_load_asset(
                data_root,
                image["asset_ref"],
                image["asset_sha256"],
                (image["image_width"], image["image_height"]),
            )
            if (
                loaded.metadata["rgb_sha256"] != image["rgb_sha256"]
                or loaded.metadata["preprocessing_hash"] != image["preprocessing_hash"]
            ):
                raise DatasetError("PREPROCESSING_HASH_MISMATCH")
            rows.append(
                {
                    "image_id": image["image_id"],
                    "status": "VALID",
                    "reason_code": None,
                    "asset_sha256": image["asset_sha256"],
                    "rgb_sha256": image["rgb_sha256"],
                    "image_width": image["image_width"],
                    "image_height": image["image_height"],
                    "dhash": dhash_rgb(loaded.rgb),
                    "center_crop_dhash": _crop_dhash(loaded.rgb),
                }
            )
        except DatasetError as exc:
            rows.append(
                {"image_id": image["image_id"], "status": "FAILED", "reason_code": exc.code}
            )
    valid = [row for row in rows if row["status"] == "VALID"]
    edges = []
    for index, left in enumerate(valid):
        for right in valid[index + 1 :]:
            relation = None
            distance: int | None = None
            comparison = "RAW_ASSET_SHA256"
            if left["asset_sha256"] == right["asset_sha256"]:
                relation = "ASSET_SHA256_EXACT"
            elif left["rgb_sha256"] == right["rgb_sha256"] and (
                left["image_width"],
                left["image_height"],
            ) == (right["image_width"], right["image_height"]):
                relation, comparison = "NORMALIZED_RGB_EXACT", "NORMALIZED_RGB_SHA256"
            else:
                alternatives = [
                    (_distance(left["dhash"], right["dhash"]), "FULL_DHASH"),
                    (_distance(left["center_crop_dhash"], right["dhash"]), "CENTER_CROP_DHASH"),
                    (_distance(left["dhash"], right["center_crop_dhash"]), "CENTER_CROP_DHASH"),
                ]
                # Crop relation wins ties to expose that this is a coarse crop candidate.
                distance, comparison = min(alternatives, key=lambda item: (item[0], item[1]))
                if distance <= threshold:
                    relation = "PERCEPTUAL_SIMILARITY"
            if relation is not None:
                identity = {
                    "image_id_a": left["image_id"],
                    "image_id_b": right["image_id"],
                    "relation": relation,
                    "comparison": comparison,
                }
                edges.append(
                    {
                        **identity,
                        "edge_id": canonical_hash(identity)[:24],
                        "distance": distance,
                        "status": "PENDING" if relation == "PERCEPTUAL_SIMILARITY" else "CONFIRMED",
                        "review": None,
                        "confirmation_basis": "PIXEL_OR_FILE_EQUALITY_ONLY"
                        if relation != "PERCEPTUAL_SIMILARITY"
                        else None,
                        "same_business_fruit_identity_proven": False,
                    }
                )
    # Video/parent/multiview linkage is explicit metadata, separate from hash similarity.
    metadata_edges = []
    records = dataset["images"]
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            links = []
            for key in (
                "capture_session_id",
                "sampling_unit_id",
                "video_id",
                "multiview_group_id",
                "source_batch_id",
            ):
                if left.get(key) is not None and left.get(key) == right.get(key):
                    links.append(key)
            if (
                left.get("parent_image_id") == right["image_id"]
                or right.get("parent_image_id") == left["image_id"]
                or (
                    left.get("parent_image_id") is not None
                    and left.get("parent_image_id") == right.get("parent_image_id")
                )
            ):
                links.append("parent_image_id")
            if links:
                identity = {
                    "image_id_a": left["image_id"],
                    "image_id_b": right["image_id"],
                    "relation": "DECLARED_GROUP_ASSOCIATION",
                    "association_fields": links,
                }
                metadata_edges.append(
                    {
                        **identity,
                        "edge_id": canonical_hash(identity)[:24],
                        "status": "CONFIRMED",
                        "confirmation_basis": "DECLARED_METADATA_NOT_PHYSICAL_IDENTITY",
                        "review": None,
                        "same_business_fruit_identity_proven": False,
                    }
                )
    all_edges = edges + metadata_edges
    return seal(
        {
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "dedup_version": DEDUP_VERSION,
            "threshold": threshold,
            "hash_algorithm": "64bit_horizontal_dhash_Pillow_L_LANCZOS_9x8",
            "crop_policy": "center_75_percent_each_dimension",
            "images": rows,
            "edges": all_edges,
            "candidate_edges": [edge for edge in edges if edge["status"] == "PENDING"],
            "summary": {
                "image_count": len(rows),
                "failed_count": len(rows) - len(valid),
                "candidate_pair_count": sum(edge["status"] == "PENDING" for edge in edges),
                "exact_pair_count": sum(edge["status"] == "CONFIRMED" for edge in edges),
                "metadata_link_count": len(metadata_edges),
            },
            "limitations": [
                "Perceptual similarity is candidate evidence with false positives and negatives.",
                "Center crop is a hint; arbitrary crop, rotation and tracking are not solved.",
                "PENDING links cannot cross independent splits; reviewer IDs are assertions.",
                "Exact pixels do not prove the same business fruit or canonical identity.",
            ],
        },
        "duplicate_hash",
    )


def review_duplicate(
    report: JSONDict, edge_id: str, status: str, reviewer_id: str, reviewed_at: str, reason: str
) -> JSONDict:
    """Create a new immutable review snapshot; preserve parent and unauthenticated assertion."""
    if not verify_seal(report, "duplicate_hash"):
        raise DatasetError("DUPLICATE_REPORT_HASH_MISMATCH")
    if status not in {"CONFIRMED", "REJECTED"} or not reviewer_id or not reason:
        raise DatasetError("DUPLICATE_REVIEW_INVALID")
    validate_timestamp(reviewed_at, "DUPLICATE_REVIEW_TIME_INVALID")
    changed = copy.deepcopy(report)
    found = False
    for edge in changed["edges"]:
        if edge["edge_id"] == edge_id:
            if edge["relation"] != "PERCEPTUAL_SIMILARITY":
                raise DatasetError("EXACT_EQUALITY_REJECTION_FORBIDDEN")
            found = True
            edge["status"] = status
            edge["review"] = {
                "reviewer_id": reviewer_id,
                "identity_authenticated": False,
                "reviewed_at": reviewed_at,
                "reason": reason,
            }
    if not found:
        raise DatasetError("DUPLICATE_EDGE_UNKNOWN")
    changed["candidate_edges"] = [
        edge
        for edge in changed["edges"]
        if edge["relation"] == "PERCEPTUAL_SIMILARITY" and edge["status"] == "PENDING"
    ]
    changed["summary"]["candidate_pair_count"] = len(changed["candidate_edges"])
    changed["parent_duplicate_hash"] = report["duplicate_hash"]
    return seal(changed, "duplicate_hash")
