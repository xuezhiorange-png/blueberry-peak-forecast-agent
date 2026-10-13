"""Versioned, strict metadata contracts for future authorized vision experiments."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

OBSERVATION_SCHEMA_VERSION = "blueberry-vision-observation/1.0.0"
MANIFEST_SCHEMA_VERSION = "blueberry-vision-manifest/1.0.0"
TIME_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


def parse_timestamp(value: str) -> datetime:
    """Compare instants in UTC without changing their original serialized strings."""
    if not re.fullmatch(TIME_PATTERN, value):
        raise ValueError("RFC3339 timestamp with timezone required")
    if value.endswith("-00:00"):
        raise ValueError("Unknown local offset is not allowed for point-in-time metadata")
    timestamp = datetime.fromisoformat(value.replace("t", "T").replace("z", "Z"))
    if timestamp.tzinfo is None:
        raise ValueError("Timezone required")
    try:
        return timestamp.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("Timestamp must fit the UTC datetime range") from exc


def _validate_time(value: str) -> str:
    parse_timestamp(value)
    return value


Timestamp = Annotated[
    str,
    Field(pattern=TIME_PATTERN, json_schema_extra={"format": "date-time"}),
    AfterValidator(_validate_time),
]
Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S(?:.*\S)?$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Split = Literal["train", "validation", "test", "out_of_domain", "unassigned"]
TaskKind = Literal["detection", "instance_segmentation", "maturity_classification", "yield_proxy"]
AllowedUse = Literal["metadata_validation", "train", "validation", "test", "out_of_domain"]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class BaseIdentity(StrictContract):
    status: Literal["resolved", "unresolved"]
    base_id: Identifier | None
    authority_ref: Identifier | None
    unresolved_reason: Identifier | None


class DeviceMetadata(StrictContract):
    device_id: Identifier
    camera_model: Identifier
    view_angle_degrees: Annotated[float, Field(ge=-180, le=180)] | None
    capture_distance_m: Annotated[float, Field(gt=0)] | None
    lighting: Literal["diffuse", "direct_sun", "shade", "artificial", "mixed", "unknown"]
    metadata_ref: Identifier


class ImageDimensions(StrictContract):
    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]


class SourceAuthority(StrictContract):
    authority_id: Identifier
    source_ref: Identifier
    permission_status: Literal["synthetic_only", "approved", "pending", "denied"]
    evidence_ref: Identifier | None
    allowed_uses: Annotated[list[AllowedUse], Field(min_length=1)]
    granted_at: Timestamp | None
    expires_at: Timestamp | None


class ModelProvenance(StrictContract):
    model_version: Identifier
    model_hash: Sha256
    generated_at: Timestamp
    provenance_ref: Identifier


class VisionObject(StrictContract):
    object_id: Identifier
    class_label: Identifier
    bbox_xyxy: Annotated[list[float], Field(min_length=4, max_length=4)] | None
    mask_polygon: list[Annotated[list[float], Field(min_length=2, max_length=2)]] | None


class VisionObservation(StrictContract):
    """Nullable entries are required; unavailable data cannot silently become zero."""

    schema_version: Literal["blueberry-vision-observation/1.0.0"]
    observation_id: Identifier
    image_id: Identifier
    asset_hash: Sha256
    capture_session_id: Identifier
    near_duplicate_group_id: Identifier
    observed_at: Timestamp
    asset_available_at: Timestamp
    available_at: Timestamp
    base_identity: BaseIdentity
    season_id: Identifier
    sampling_unit_id: Identifier
    variety_id: Identifier | None
    occlusion: Literal["none", "partial", "heavy", "unknown"]
    device: DeviceMetadata
    image_dimensions: ImageDimensions
    record_kind: Literal["real_observation", "synthetic_observation", "model_prediction"]
    SYNTHETIC: bool
    split: Split
    task_kind: TaskKind
    annotation_version: Identifier | None
    label_definition_version: Identifier | None
    annotation_quality_status: Literal["not_annotated", "in_progress", "reviewed", "rejected"]
    annotation_available_at: Timestamp | None
    object_count: Annotated[int, Field(ge=0)] | None
    count_unit: Literal["fruit_count"]
    missing_count_reason: Identifier | None
    class_labels: list[Identifier] | None
    objects: list[VisionObject] | None
    source_authority: SourceAuthority
    model_provenance: ModelProvenance | None
    record_hash: Sha256


class LabelDefinition(StrictContract):
    version: Identifier
    task_kinds: Annotated[list[TaskKind], Field(min_length=1)]
    class_names: Annotated[list[Identifier], Field(min_length=1)]
    approval_status: Literal["candidate", "approved"]
    source_ref: Identifier


class AnnotationVersion(StrictContract):
    version: Identifier
    label_definition_version: Identifier
    guideline_ref: Identifier


class NearDuplicateReview(StrictContract):
    status: Literal["completed", "pending"]
    method: Identifier
    evidence_ref: Identifier
    completed_at: Timestamp | None
    scope: Literal["entire_manifest"]
    basis: Literal["synthetic_declared", "authorized_asset_review"]


class VisionManifest(StrictContract):
    schema_version: Literal["blueberry-vision-manifest/1.0.0"]
    manifest_id: Identifier
    SYNTHETIC: bool
    purpose: Literal["offline_synthetic_validation", "metadata_contract"]
    image_files_present: bool
    asset_hash_basis: Literal["synthetic_descriptor_sha256", "actual_asset_bytes_sha256"]
    as_of_cutoff: Timestamp
    split_cutoffs: dict[Split, Timestamp] | None
    label_definitions: list[LabelDefinition]
    annotation_versions: list[AnnotationVersion]
    near_duplicate_review: NearDuplicateReview
    observations: Annotated[list[VisionObservation], Field(min_length=1)]


def canonical_record_hash(record: dict[str, Any]) -> str:
    """Hash original JSON values, excluding only the record_hash field itself."""
    payload = {key: value for key, value in record.items() if key != "record_hash"}
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
