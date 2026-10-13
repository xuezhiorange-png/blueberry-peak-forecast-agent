"""Independent R3 asset-only external benchmark contract, never a relaxed R1 gate."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..r2_common import JSONDict, read_json, verify_seal

SCHEMA_VERSION = "blueberry-vision-external-dataset/3.0.0"
PURPOSES = ("PUBLIC_EXTERNAL_BENCHMARK", "AUTHORIZED_ORCHARD_PILOT", "SYNTHETIC_ENGINEERING")
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class DatasetError(ValueError):
    """Stable data admission reason, without printing image bytes or sensitive paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BaseIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["UNRESOLVED", "CANONICAL"]
    base_id: Identifier | None = None
    authority_ref: Identifier | None = None


class R3Image(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    image_id: Identifier
    asset_ref: Annotated[str, Field(min_length=1, max_length=512)]
    asset_sha256: Hash
    rgb_sha256: Hash
    image_width: Annotated[int, Field(gt=0, le=8192)]
    image_height: Annotated[int, Field(gt=0, le=8192)]
    asset_size_bytes: Annotated[int, Field(gt=0, le=20_000_000)]
    preprocessing_version: Identifier
    preprocessing_hash: Hash
    source_id: Identifier
    source_authority: dict[str, object]
    license_id: Identifier
    license_url: Identifier
    license_status: Identifier
    purpose: Literal[
        "PUBLIC_EXTERNAL_BENCHMARK", "AUTHORIZED_ORCHARD_PILOT", "SYNTHETIC_ENGINEERING"
    ]
    SYNTHETIC: bool
    observed_at: str | None
    capture_time_status: Identifier
    source_provided_capture_date: str | None = None
    asset_available_at: str | None = None
    base_identity: BaseIdentity
    variety: str | None = None
    capture_session_id: Identifier | None = None
    sampling_unit_id: Identifier | None = None
    video_id: Identifier | None = None
    frame_index: Annotated[int, Field(ge=0)] | None = None
    parent_image_id: Identifier | None = None
    multiview_group_id: Identifier | None = None
    source_batch_id: Identifier | None = None
    import_batch_id: Identifier
    annotation_version: str | None = None
    annotation_ref: str | None = None
    scene_metadata: dict[str, object] = Field(default_factory=dict)
    record_hash: Hash


class R3Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["blueberry-vision-external-dataset/3.0.0"]
    dataset_id: Identifier
    dataset_version: Identifier
    purpose: Literal[
        "PUBLIC_EXTERNAL_BENCHMARK", "AUTHORIZED_ORCHARD_PILOT", "SYNTHETIC_ENGINEERING"
    ]
    SYNTHETIC: bool
    sources: list[dict[str, object]]
    images: list[R3Image]
    source_index_hash: Hash
    import_policy: dict[str, object]
    annotation_index: dict[str, object] | None = None
    manifest_hash: Hash


def validate_timestamp(value: object, code: str = "CAPTURE_TIME_INVALID") -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        raise DatasetError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetError(code) from exc
    if parsed.utcoffset() is None:
        raise DatasetError(code)


def validate_source(source: JSONDict, purpose: str, synthetic: bool) -> None:
    if purpose not in PURPOSES:
        raise DatasetError("DATASET_PURPOSE_MISMATCH")
    if source.get("purpose") != purpose or source.get("SYNTHETIC") is not synthetic:
        raise DatasetError("SOURCE_PURPOSE_MISMATCH")
    expected = {
        "PUBLIC_EXTERNAL_BENCHMARK": "LICENSE_VERIFIED",
        "AUTHORIZED_ORCHARD_PILOT": "AUTHORITY_VERIFIED",
        "SYNTHETIC_ENGINEERING": "SYNTHETIC_AUTHORITY",
    }[purpose]
    if source.get("license_status") != expected:
        raise DatasetError("SOURCE_LICENSE_NOT_VERIFIED")
    if source.get("research_use") is not True:
        raise DatasetError("SOURCE_RESEARCH_USE_NOT_ALLOWED")
    if not source.get("license_id") or not source.get("license_url"):
        raise DatasetError("SOURCE_LICENSE_REFERENCE_MISSING")
    if purpose == "AUTHORIZED_ORCHARD_PILOT" and not source.get("authorization_evidence_ref"):
        raise DatasetError("ORCHARD_AUTHORIZATION_EVIDENCE_MISSING")


def validate_manifest(dataset: JSONDict) -> JSONDict:
    """Validate strict geometry-free records, source permissions and canonical bindings."""
    try:
        parsed = R3Dataset.model_validate(dataset)
    except ValidationError as exc:
        raise DatasetError("DATASET_SCHEMA_INVALID") from exc
    if not verify_seal(dataset, "manifest_hash"):
        raise DatasetError("DATASET_MANIFEST_HASH_MISMATCH")
    if parsed.SYNTHETIC != (parsed.purpose == "SYNTHETIC_ENGINEERING"):
        raise DatasetError("DATASET_PURPOSE_MISMATCH")
    if not parsed.sources or not parsed.images:
        raise DatasetError("DATASET_EMPTY")
    sources: dict[str, JSONDict] = {}
    for source in dataset["sources"]:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in sources:
            raise DatasetError("SOURCE_ID_INVALID_OR_DUPLICATE")
        validate_source(source, parsed.purpose, parsed.SYNTHETIC)
        sources[source_id] = source
    ids: set[str] = set()
    for row in dataset["images"]:
        if row["image_id"] in ids:
            raise DatasetError("IMAGE_ID_DUPLICATE")
        ids.add(row["image_id"])
        if not verify_seal(row, "record_hash"):
            raise DatasetError("IMAGE_RECORD_HASH_MISMATCH")
        source = sources.get(row["source_id"])
        if source is None:
            raise DatasetError("SOURCE_ID_UNKNOWN")
        if row["purpose"] != parsed.purpose or row["SYNTHETIC"] is not parsed.SYNTHETIC:
            raise DatasetError("IMAGE_PURPOSE_MISMATCH")
        if any(row[key] != source[key] for key in ("license_id", "license_url", "license_status")):
            raise DatasetError("IMAGE_SOURCE_LICENSE_MISMATCH")
        if row["source_authority"] != {
            "source_id": source["source_id"],
            "purpose": source["purpose"],
            "research_use": source["research_use"],
            "license_status": source["license_status"],
        }:
            raise DatasetError("IMAGE_SOURCE_AUTHORITY_MISMATCH")
        if row["observed_at"] is None:
            if not row["capture_time_status"].startswith("UNKNOWN"):
                raise DatasetError("CAPTURE_TIME_STATUS_MISMATCH")
        else:
            validate_timestamp(row["observed_at"])
            if row["capture_time_status"] not in {
                "SOURCE_VERIFIED",
                "AUTHORIZED_CAPTURE_RECORD",
                "SIMULATED",
            }:
                raise DatasetError("CAPTURE_TIME_STATUS_MISMATCH")
            if row["capture_time_status"] == "SIMULATED" and not parsed.SYNTHETIC:
                raise DatasetError("CAPTURE_TIME_STATUS_MISMATCH")
        if row["asset_available_at"] is not None:
            validate_timestamp(row["asset_available_at"], "ASSET_AVAILABLE_TIME_INVALID")
            if row["observed_at"] is not None and datetime.fromisoformat(
                row["asset_available_at"].replace("Z", "+00:00")
            ) < datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")):
                raise DatasetError("ASSET_AVAILABLE_BEFORE_CAPTURE")
        identity = row["base_identity"]
        if identity["status"] == "CANONICAL":
            if not identity.get("base_id") or not identity.get("authority_ref"):
                raise DatasetError("CANONICAL_IDENTITY_AUTHORITY_MISSING")
            if parsed.purpose == "PUBLIC_EXTERNAL_BENCHMARK":
                raise DatasetError("PUBLIC_BENCHMARK_COMPANY_IDENTITY_FORBIDDEN")
        elif identity.get("base_id") is not None or identity.get("authority_ref") is not None:
            raise DatasetError("UNRESOLVED_IDENTITY_HAS_CANONICAL_ID")
    return dataset


def load_manifest(path: Path) -> JSONDict:
    try:
        return validate_manifest(read_json(path))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, DatasetError):
            raise
        raise DatasetError("DATASET_JSON_INVALID") from exc
