"""Server-owned frozen inputs for the V0.5 BASE-grain product.

The research artifacts are copied into small, versioned JSON snapshots.  This
loader validates those snapshots once per execution and returns the same
in-memory authority to the inference service.  No request field can select an
artifact, a registry, a history row, or a fallback policy.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest

TOTAL_MODEL_ID = "BASE_AWARE_BASELINE_R1"
TEMPORAL_MODEL_ID = "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE"
PRODUCT_MODEL_VERSION = "AREA_FORECAST_PRODUCT_V1"
REFERENCE_WORKBOOK_SHA256 = "73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7"
REFERENCE_BASE_COUNT = 39
REFERENCE_AREA_TOTAL_MU = Decimal("41335.000000")
TRAINING_DATA_MANIFEST_SHA256 = "74aed78652513cd8a0a8828a0654dddf01d2cd0926f4261ee139317e3b157c89"
IDENTITY_MAPPING_SHA256 = "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
IDENTITY_RECONSTRUCTION_MANIFEST_SHA256 = (
    "b95454505a12f22509f871f5430e35a088521f8d6a5fe85cc2ff4212f4ba895c"
)
R1_MODEL_ARTIFACT_SHA256 = "d75d691a74f393ed789da2300a2f3194170115d8b4f89cc78c8e5b1fc3a628af"
R1_ARTIFACT_MANIFEST_SHA256 = "6d7a97369b17c77454d84ed9fc02bac3a791fef283512f3266f8bc7ed352185b"
R9_CLOSEOUT_ARTIFACT_MANIFEST_SHA256 = (
    "782bb9d33eb100c9ff0c2ac79b46c1d75455cd4d73ea0c142904aedf7082eeb6"
)
R1_TEMPORAL_MODEL_CANONICAL_HASH = (
    "ee9d9d7384fac086e45539836d48dc5a7433ea441d9f4633bca702f5c55a812b"
)
HISTORY_QUANTITY_SEMANTICS = "ACCEPTED_MAPPED_FARM_SUBTOTAL_NOT_COMPLETE_FULL_SEASON_TOTAL"
HISTORY_SOURCE_FILES = {
    "2023-2024": {
        "file": "historical-primary-source-replay-r1/23~24.xls",
        "sha256": "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
    },
    "2024-2025": {
        "file": "historical-primary-source-replay-r1/24~25.xls",
        "sha256": "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
    },
}


class BaseAreaForecastError(RuntimeError):
    """Machine-readable product error without exposing private source details."""

    status_code = 400

    def __init__(self, code: str, reason: str, *, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        if status_code is not None:
            self.status_code = status_code


class BaseAreaForecastAuthorityError(BaseAreaForecastError):
    status_code = 503

    def __init__(self, reason: str) -> None:
        super().__init__("AREA_FORECAST_AUTHORITY_UNAVAILABLE", reason, status_code=503)


class BaseAreaForecastRequestError(BaseAreaForecastError):
    def __init__(self, reason: str) -> None:
        super().__init__("AREA_FORECAST_REQUEST_INVALID", reason)


class BaseAreaForecastUnsupportedError(BaseAreaForecastError):
    def __init__(self, reason: str) -> None:
        super().__init__("AREA_FORECAST_UNSUPPORTED_BASE", reason)


class BaseAreaForecastPersistenceError(BaseAreaForecastError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(code, reason)


@dataclass(frozen=True)
class BaseProductAuthority:
    """Validated registry and model snapshots held for one forecast call."""

    registry: dict[str, Any]
    model: dict[str, Any]
    registry_file_sha256: str
    model_file_sha256: str
    authority_hash: str

    @property
    def bases_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(row["base_id"]): row for row in self.registry["bases"]}

    @property
    def bases_by_name(self) -> dict[str, dict[str, Any]]:
        return {str(row["canonical_base_name"]): row for row in self.registry["bases"]}

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self.model["base_yield_history"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_registry_path() -> Path:
    return _repo_root() / "configs" / "v0_5_base_reference_registry_v1.json"


def _default_model_path() -> Path:
    return _repo_root() / "configs" / "v0_5_area_forecast_model_v1.json"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaseAreaForecastAuthorityError("ARTIFACT_FILE_UNREADABLE") from exc
    if not isinstance(payload, dict):
        raise BaseAreaForecastAuthorityError("ARTIFACT_PAYLOAD_INVALID")
    return payload, hashlib.sha256(raw).hexdigest()


def _validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("artifact_version") != "BASE_REFERENCE_AREA_REGISTRY_V1":
        raise BaseAreaForecastAuthorityError("REGISTRY_ARTIFACT_VERSION_INVALID")
    if registry.get("source_workbook_sha256") != REFERENCE_WORKBOOK_SHA256:
        raise BaseAreaForecastAuthorityError("REGISTRY_SOURCE_HASH_MISMATCH")
    if registry.get("base_count") != REFERENCE_BASE_COUNT:
        raise BaseAreaForecastAuthorityError("REGISTRY_BASE_COUNT_MISMATCH")
    try:
        total = sum(
            (Decimal(str(row["productive_area_mu"])) for row in registry["bases"]),
            Decimal(0),
        )
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_INVALID") from exc
    if total != REFERENCE_AREA_TOTAL_MU:
        raise BaseAreaForecastAuthorityError("REGISTRY_AREA_TOTAL_MISMATCH")
    if registry.get("payload_hash") != digest(
        {key: value for key, value in registry.items() if key != "payload_hash"}
    ):
        raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_HASH_MISMATCH")
    bases = registry.get("bases")
    if not isinstance(bases, list) or len(bases) != REFERENCE_BASE_COUNT:
        raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_INVALID")
    ids: set[str] = set()
    names: set[str] = set()
    for row in bases:
        if not isinstance(row, dict):
            raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_INVALID")
        base_id = row.get("base_id")
        name = row.get("canonical_base_name")
        farms = row.get("covered_farms")
        try:
            area = Decimal(str(row["productive_area_mu"]))
        except (KeyError, InvalidOperation) as exc:
            raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_INVALID") from exc
        if (
            not isinstance(base_id, str)
            or not isinstance(name, str)
            or not isinstance(farms, list)
            or not farms
            or not area.is_finite()
            or area <= 0
            or base_id in ids
            or name in names
            or any(not isinstance(farm, str) or not farm for farm in farms)
        ):
            raise BaseAreaForecastAuthorityError("REGISTRY_PAYLOAD_INVALID")
        ids.add(base_id)
        names.add(name)


def _validate_model(
    model: dict[str, Any], registry: dict[str, Any], registry_file_sha256: str
) -> None:
    if model.get("artifact_version") != "AREA_FORECAST_PRODUCT_ARTIFACT_V1":
        raise BaseAreaForecastAuthorityError("MODEL_ARTIFACT_VERSION_INVALID")
    if model.get("artifact_hash") != digest(
        {key: value for key, value in model.items() if key != "artifact_hash"}
    ):
        raise BaseAreaForecastAuthorityError("MODEL_ARTIFACT_HASH_MISMATCH")
    if model.get("total_model_id") != TOTAL_MODEL_ID:
        raise BaseAreaForecastAuthorityError("TOTAL_MODEL_AUTHORITY_MISMATCH")
    if model.get("temporal_model_id") != TEMPORAL_MODEL_ID:
        raise BaseAreaForecastAuthorityError("TEMPORAL_MODEL_AUTHORITY_MISMATCH")
    reference = model.get("reference_area_source")
    if not isinstance(reference, dict):
        raise BaseAreaForecastAuthorityError("REFERENCE_AREA_AUTHORITY_INVALID")
    if (
        reference.get("workbook_sha256") != REFERENCE_WORKBOOK_SHA256
        or reference.get("base_count") != REFERENCE_BASE_COUNT
        or reference.get("total_area_mu") != "41335.000000"
        or reference.get("registry_artifact_sha256") != registry_file_sha256
    ):
        raise BaseAreaForecastAuthorityError("REFERENCE_AREA_AUTHORITY_MISMATCH")
    if model.get("training_data_manifest_sha256") != TRAINING_DATA_MANIFEST_SHA256:
        raise BaseAreaForecastAuthorityError("TRAINING_MANIFEST_AUTHORITY_MISMATCH")
    if model.get("history_policy") != "IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK":
        raise BaseAreaForecastAuthorityError("HISTORY_POLICY_AUTHORITY_MISMATCH")
    if model.get("weather_used") is not False or model.get("future_plan_used") is not False:
        raise BaseAreaForecastAuthorityError("UNAUTHORIZED_INPUT_AUTHORITY")
    if model.get("history_quantity_semantics") != HISTORY_QUANTITY_SEMANTICS:
        raise BaseAreaForecastAuthorityError("HISTORY_SEMANTICS_AUTHORITY_MISMATCH")

    research_artifacts = model.get("research_artifacts")
    if (
        not isinstance(research_artifacts, dict)
        or research_artifacts.get("r1_model_artifact_sha256") != R1_MODEL_ARTIFACT_SHA256
        or research_artifacts.get("r1_artifact_manifest_sha256") != R1_ARTIFACT_MANIFEST_SHA256
        or research_artifacts.get("r9_closeout_manifest_sha256")
        != R9_CLOSEOUT_ARTIFACT_MANIFEST_SHA256
        or research_artifacts.get("temporal_model_artifact_sha256") != R1_MODEL_ARTIFACT_SHA256
        or research_artifacts.get("temporal_model_canonical_hash")
        != R1_TEMPORAL_MODEL_CANONICAL_HASH
    ):
        raise BaseAreaForecastAuthorityError("RESEARCH_ARTIFACT_AUTHORITY_MISMATCH")

    history_provenance = model.get("history_provenance")
    if (
        not isinstance(history_provenance, dict)
        or history_provenance.get("artifact_version") != "AREA_FORECAST_HISTORY_PROVENANCE_V1"
        or history_provenance.get("dataset") != "HISTORICAL_IDENTITY_RECONSTRUCTION_R1"
        or history_provenance.get("identity_mapping_sha256") != IDENTITY_MAPPING_SHA256
        or history_provenance.get("identity_reconstruction_manifest_sha256")
        != IDENTITY_RECONSTRUCTION_MANIFEST_SHA256
        or history_provenance.get("source_files") != HISTORY_SOURCE_FILES
        or history_provenance.get("quantity_semantics") != HISTORY_QUANTITY_SEMANTICS
        or history_provenance.get("base_count") != REFERENCE_BASE_COUNT
        or history_provenance.get("base_ids")
        != sorted(str(row["base_id"]) for row in registry["bases"])
    ):
        raise BaseAreaForecastAuthorityError("HISTORY_PROVENANCE_AUTHORITY_MISMATCH")

    temporal = model.get("temporal_model")
    if not isinstance(temporal, dict):
        raise BaseAreaForecastAuthorityError("TEMPORAL_MODEL_PAYLOAD_INVALID")
    if (
        temporal.get("model_id") != "AREA_DAILY_RIDGE_V1"
        or temporal.get("model_family") != "RIDGE_LEAST_SQUARES"
        or temporal.get("calendar") != "JULY_01_THROUGH_APRIL_15"
        or temporal.get("progress_denominator") != "TARGET_SEASON_START_TO_END_EXCLUSIVE"
    ):
        raise BaseAreaForecastAuthorityError("TEMPORAL_MODEL_PAYLOAD_INVALID")
    coefficients = temporal.get("coefficients")
    means = temporal.get("feature_mean")
    scales = temporal.get("feature_scale")
    features = temporal.get("features")
    if (
        not isinstance(coefficients, list)
        or len(coefficients) != 11
        or not isinstance(means, list)
        or len(means) != 10
        or not isinstance(scales, list)
        or len(scales) != 10
        or not isinstance(features, list)
        or features
        != [
            "reference_area_mu_div_1000",
            "season_progress",
            "sin_1",
            "cos_1",
            "sin_2",
            "cos_2",
            "area_x_sin_1",
            "area_x_cos_1",
            "area_x_sin_2",
            "area_x_cos_2",
        ]
    ):
        raise BaseAreaForecastAuthorityError("TEMPORAL_MODEL_PAYLOAD_INVALID")
    try:
        if any(not Decimal(str(value)).is_finite() for value in coefficients + means + scales):
            raise ValueError("non-finite model value")
        if any(Decimal(str(value)) <= 0 for value in scales):
            raise ValueError("non-positive model scale")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BaseAreaForecastAuthorityError("TEMPORAL_MODEL_PAYLOAD_INVALID") from exc

    bases = {str(row["base_id"]): row for row in registry["bases"]}
    history = model.get("base_yield_history")
    if not isinstance(history, list) or not history:
        raise BaseAreaForecastAuthorityError("HISTORY_AUTHORITY_MISSING")
    if history_provenance.get("history_row_count") != len(history):
        raise BaseAreaForecastAuthorityError("HISTORY_PROVENANCE_ROW_COUNT_MISMATCH")
    seen: set[tuple[str, str]] = set()
    for row in history:
        if not isinstance(row, dict):
            raise BaseAreaForecastAuthorityError("HISTORY_AUTHORITY_INVALID")
        try:
            key = (str(row["base_id"]), str(row["season"]))
            yield_value = Decimal(str(row["yield_kg_per_mu"]))
            source_area = Decimal(str(row["reference_area_mu"]))
            harvest = Decimal(str(row["harvest_total_kg"]))
        except (KeyError, InvalidOperation) as exc:
            raise BaseAreaForecastAuthorityError("HISTORY_AUTHORITY_INVALID") from exc
        base = bases.get(key[0])
        if (
            base is None
            or key in seen
            or key[1] not in {"2023-2024", "2024-2025"}
            or row.get("base_name") != base["canonical_base_name"]
            or source_area != Decimal(str(base["productive_area_mu"]))
            or not yield_value.is_finite()
            or yield_value <= 0
            or not harvest.is_finite()
            or harvest <= 0
            or row.get("identity_mapping_sha256") != IDENTITY_MAPPING_SHA256
            or row.get("identity_mapping_status") != "ACCEPTED_FROZEN_IDENTITY_MAPPING"
            or row.get("quantity_semantics") != HISTORY_QUANTITY_SEMANTICS
        ):
            raise BaseAreaForecastAuthorityError("HISTORY_AUTHORITY_INVALID")
        source = HISTORY_SOURCE_FILES.get(key[1])
        if (
            not isinstance(source, dict)
            or row.get("source_file") != source["file"]
            or row.get("source_sha256") != source["sha256"]
        ):
            raise BaseAreaForecastAuthorityError("HISTORY_SOURCE_AUTHORITY_MISMATCH")
        match_types = row.get("identity_match_types")
        source_labels = row.get("source_farm_labels")
        day_counts = row.get("source_observed_day_counts")
        if (
            not isinstance(match_types, list)
            or not match_types
            or not set(match_types) <= {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
            or not isinstance(source_labels, list)
            or not source_labels
            or any(not isinstance(label, str) or not label for label in source_labels)
            or not isinstance(day_counts, list)
            or len(day_counts) != len(source_labels)
            or any(not isinstance(count, int) or count <= 0 for count in day_counts)
        ):
            raise BaseAreaForecastAuthorityError("HISTORY_PROVENANCE_ROW_INVALID")
        expected_yield = (harvest / source_area).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        if yield_value != expected_yield:
            raise BaseAreaForecastAuthorityError("HISTORY_YIELD_PROVENANCE_MISMATCH")
        seen.add(key)
    if digest(history) != research_artifacts.get("total_model_source_canonical_hash"):
        raise BaseAreaForecastAuthorityError("TOTAL_MODEL_SOURCE_HASH_MISMATCH")


def load_base_product_authority(
    *, registry_path: Path | None = None, model_path: Path | None = None
) -> BaseProductAuthority:
    """Load and validate the two server-owned snapshots exactly once."""

    configured_registry = os.environ.get("AREA_FORECAST_REGISTRY_ARTIFACT_PATH")
    configured_model = os.environ.get("AREA_FORECAST_MODEL_ARTIFACT_PATH")
    registry_file = registry_path or (
        Path(configured_registry) if configured_registry else _default_registry_path()
    )
    model_file = model_path or (
        Path(configured_model) if configured_model else _default_model_path()
    )
    registry, registry_file_sha256 = _read_json(registry_file)
    model, model_file_sha256 = _read_json(model_file)
    _validate_registry(registry)
    _validate_model(model, registry, registry_file_sha256)
    authority_hash = digest(
        {
            "registry_file_sha256": registry_file_sha256,
            "registry_payload_hash": registry["payload_hash"],
            "model_file_sha256": model_file_sha256,
            "model_artifact_hash": model["artifact_hash"],
            "policy_version": PRODUCT_MODEL_VERSION,
        }
    )
    return BaseProductAuthority(
        registry=registry,
        model=model,
        registry_file_sha256=registry_file_sha256,
        model_file_sha256=model_file_sha256,
        authority_hash=authority_hash,
    )
