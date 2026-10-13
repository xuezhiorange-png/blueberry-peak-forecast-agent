"""Version 2 synthetic pixel-assets adapter; R1 metadata semantics remain unchanged.

Boxes use normalized-image pixel coordinates and half-open [x1,y1,x2,y2].
Synthetic references are renderer references, never business-approved observations.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, field_validator

from research.blueberry_vision.contracts import (
    BaseIdentity,
    Identifier,
    Sha256,
    SourceAuthority,
    StrictContract,
    Timestamp,
    canonical_record_hash,
    parse_timestamp,
)
from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    JSONDict,
    dataset_split_hash,
    verify_seal,
)

DATASET_SCHEMA_VERSION = "blueberry-vision-dataset/2.0.0"
PREPROCESSING_VERSION = "rgb-exif-transpose/1.0.0"
LABEL_DEFINITION_VERSION = "synthetic-visible-fruit/2.0.0"
ANNOTATION_VERSION = "synthetic-render-reference/2.0.0"
R2Split = Literal["train", "validation", "test", "out_of_domain"]
NonnegativeInt = Annotated[int, Field(ge=0)]
BBox = Annotated[list[float], Field(min_length=4, max_length=4)]
AssetRef = Annotated[
    str, Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
]


class DatasetError(ValueError):
    """A stable reason code without input values, identities, or exception details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class R2Object(StrictContract):
    object_id: Identifier
    class_label: Literal["SYNTHETIC_BLUEBERRY_VISIBLE"]
    bbox_xyxy: BBox


class R2ImageRecord(StrictContract):
    image_id: Identifier
    original_asset_ref: AssetRef
    asset_sha256: Sha256
    image_width: Annotated[int, Field(gt=0, le=8192)]
    image_height: Annotated[int, Field(gt=0, le=8192)]
    observed_at: Timestamp
    asset_available_at: Timestamp
    available_at: Timestamp
    capture_session_id: Identifier
    sampling_unit_id: Identifier
    base_identity: BaseIdentity
    source_authority: SourceAuthority
    SYNTHETIC: Literal[True]
    split: R2Split
    generation_seed: NonnegativeInt
    template_group_id: Identifier
    near_duplicate_group_id: Identifier
    preprocessing_version: Literal["rgb-exif-transpose/1.0.0"]
    preprocessing_hash: Sha256
    label_definition_version: Identifier
    annotation_version: Identifier
    annotation_quality_status: Literal["synthetic_reference"]
    gt_status: Literal["complete", "missing"]
    visible_count: NonnegativeInt | None
    objects: Annotated[list[R2Object], Field(max_length=100_000)] | None
    ignore_regions: Annotated[list[BBox], Field(max_length=100_000)]
    drawn_object_count: NonnegativeInt
    hidden_object_count: NonnegativeInt
    ignored_object_count: NonnegativeInt
    scene_metadata: dict[str, Any]
    training_mask_ref: AssetRef | None
    training_mask_sha256: Sha256 | None
    record_hash: Sha256

    @field_validator("SYNTHETIC", mode="before")
    @classmethod
    def actual_boolean(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("SYNTHETIC requires a JSON boolean")
        return value


class R2Dataset(StrictContract):
    schema_version: Literal["blueberry-vision-dataset/2.0.0"]
    SYNTHETIC: Literal[True]
    image_files_present: Literal[True]
    generator_version: Identifier
    generation_config: dict[str, Any]
    label_definition_version: Identifier
    annotation_version: Identifier
    images: Annotated[list[R2ImageRecord], Field(min_length=1, max_length=10_000)]
    manifest_hash: Sha256
    split_hash: Sha256

    @field_validator("SYNTHETIC", "image_files_present", mode="before")
    @classmethod
    def actual_boolean(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Flags require JSON booleans")
        return value


# One hash foundation is shared by generation, validation, and experiment evidence.
compute_split_hash = dataset_split_hash


def _bbox_guard(box: list[float], width: int, height: int) -> None:
    x1, y1, x2, y2 = box
    if x1 >= x2 or y1 >= y2:
        raise DatasetError("BBOX_INVALID_ORDER")
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise DatasetError("BBOX_OUT_OF_BOUNDS")


def validate_dataset(data: JSONDict) -> R2Dataset:
    """Check immutable synthetic provenance, geometry, time and split declarations.

    This does not authenticate external authority or detect visual similarity. All
    declared seed/template/session/unit/near-duplicate groups are split-atomic.
    """
    try:
        dataset = R2Dataset.model_validate(data)
    except ValidationError as exc:
        raise DatasetError("DATASET_SCHEMA_INVALID") from exc
    if not verify_seal(data, "manifest_hash"):
        raise DatasetError("MANIFEST_HASH_MISMATCH")
    if dataset.split_hash != dataset_split_hash(data["images"]):
        raise DatasetError("SPLIT_HASH_MISMATCH")
    if dataset.label_definition_version != LABEL_DEFINITION_VERSION:
        raise DatasetError("UNKNOWN_LABEL_DEFINITION_VERSION")
    if dataset.annotation_version != ANNOTATION_VERSION:
        raise DatasetError("UNKNOWN_ANNOTATION_VERSION")

    unique_fields = ("image_id", "asset_sha256", "original_asset_ref")
    group_fields = (
        "generation_seed",
        "template_group_id",
        "near_duplicate_group_id",
        "capture_session_id",
        "sampling_unit_id",
    )
    uniques: dict[str, set[object]] = {field: set() for field in unique_fields}
    groups: dict[str, dict[object, str]] = {field: {} for field in group_fields}
    for index, record in enumerate(dataset.images):
        raw = data["images"][index]
        if canonical_record_hash(raw) != record.record_hash:
            raise DatasetError("RECORD_HASH_MISMATCH")
        for field, seen in uniques.items():
            value = getattr(record, field)
            if value in seen:
                raise DatasetError(f"DUPLICATE_{field.upper()}")
            seen.add(value)
        for field, assigned in groups.items():
            value = getattr(record, field)
            if value in assigned and assigned[value] != record.split:
                raise DatasetError(f"{field.upper()}_SPLIT_LEAKAGE")
            assigned[value] = record.split

        observed = parse_timestamp(record.observed_at)
        asset_available = parse_timestamp(record.asset_available_at)
        available = parse_timestamp(record.available_at)
        if observed > asset_available:
            raise DatasetError("ASSET_BEFORE_CAPTURE")
        if asset_available > available:
            raise DatasetError("RECORD_BEFORE_ASSET")
        identity = record.base_identity
        if identity.status == "resolved":
            if identity.base_id is None or identity.authority_ref is None:
                raise DatasetError("IDENTITY_AUTHORITY_REQUIRED")
            if identity.unresolved_reason is not None:
                raise DatasetError("IDENTITY_RESOLVED_HAS_UNRESOLVED_REASON")
        else:
            if identity.base_id is not None:
                raise DatasetError("IDENTITY_UNRESOLVED_HAS_BASE")
            if identity.authority_ref is not None or identity.unresolved_reason is None:
                raise DatasetError("IDENTITY_UNRESOLVED_REASON_REQUIRED")
        source = record.source_authority
        if source.permission_status != "synthetic_only":
            raise DatasetError("SYNTHETIC_SOURCE_PERMISSION_REQUIRED")
        if not {"metadata_validation", record.split} <= set(source.allowed_uses):
            raise DatasetError("SOURCE_USE_NOT_ALLOWED")
        if (source.granted_at is None) != (source.expires_at is None):
            raise DatasetError("SOURCE_VALIDITY_REQUIRED")
        if source.granted_at is not None and source.expires_at is not None:
            granted = parse_timestamp(source.granted_at)
            expires = parse_timestamp(source.expires_at)
            if granted >= expires:
                raise DatasetError("SOURCE_VALIDITY_ORDER_INVALID")
            if granted > available:
                raise DatasetError("SOURCE_PERMISSION_NOT_YET_VALID")
            if expires <= available:
                raise DatasetError("SOURCE_PERMISSION_EXPIRED")
        if record.label_definition_version != dataset.label_definition_version:
            raise DatasetError("LABEL_DEFINITION_VERSION_MISMATCH")
        if record.annotation_version != dataset.annotation_version:
            raise DatasetError("ANNOTATION_VERSION_MISMATCH")
        if record.gt_status == "missing":
            if record.visible_count is not None or record.objects is not None:
                raise DatasetError("MISSING_GT_HAS_LABELS")
        else:
            if record.visible_count is None or record.objects is None:
                raise DatasetError("COMPLETE_GT_REQUIRES_LABELS")
            if record.visible_count != len(record.objects):
                raise DatasetError("COUNT_OBJECTS_MISMATCH")
            if record.drawn_object_count != (
                record.visible_count + record.hidden_object_count + record.ignored_object_count
            ):
                raise DatasetError("DRAWN_VISIBLE_COUNT_MISMATCH")
            object_ids = [obj.object_id for obj in record.objects]
            if len(set(object_ids)) != len(object_ids):
                raise DatasetError("DUPLICATE_OBJECT_ID")
            for obj in record.objects:
                if obj.class_label != CLASS_LABEL:
                    raise DatasetError("UNKNOWN_CLASS_LABEL")
                _bbox_guard(obj.bbox_xyxy, record.image_width, record.image_height)
        for box in record.ignore_regions:
            _bbox_guard(box, record.image_width, record.image_height)
        if (record.training_mask_ref is None) != (record.training_mask_sha256 is None):
            raise DatasetError("TRAINING_MASK_BINDING_REQUIRED")
    return dataset
