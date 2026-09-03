from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from backend.app.residual_model.enums import PredictionTargetKind


@dataclass(frozen=True)
class ResidualEstimatorConfig:
    learning_rate: float
    max_iter: int
    max_leaf_nodes: int
    max_depth: int | None
    min_samples_leaf: int
    l2_regularization: float
    early_stopping: bool
    validation_fraction: float
    n_iter_no_change: int
    tol: float


@dataclass(frozen=True)
class ResidualEligibilityConfig:
    min_training_rows: int
    min_seasons: int
    min_factories: int
    max_validation_wmape: float
    require_improvement_over_structural: bool
    max_fallback_rate: float


@dataclass(frozen=True)
class ResidualModelRules:
    model_family: Literal["hist_gradient_boosting_quantile"]
    model_version: str
    feature_schema_version: str
    artifact_schema_version: str
    quantiles: tuple[float, ...]
    random_seed: int
    prediction_target_kind: PredictionTargetKind
    estimator: ResidualEstimatorConfig
    split_strategy: str
    split_version: str
    missing_values_version: str
    categorical_encoding_version: str
    categorical_unknown_policy: str
    projection_nonnegative: bool
    projection_quantile_monotonic: str
    projection_version: str
    eligibility: ResidualEligibilityConfig


@dataclass(frozen=True)
class ResidualModelConfig:
    rules: ResidualModelRules
    config_hash: str
    snapshot: dict[str, Any]


class _EstimatorFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_rate: float
    max_iter: int
    max_leaf_nodes: int
    max_depth: int | None
    min_samples_leaf: int
    l2_regularization: float
    early_stopping: bool
    validation_fraction: float
    n_iter_no_change: int
    tol: float


class _SplitFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["leave_one_season_out"]
    version: str


class _MissingFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str


class _CategoricalFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    unknown_policy: Literal["explicit_bucket", "structural_only_fallback"]


class _ProjectionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nonnegative: bool
    quantile_monotonic: Literal["cumulative_max"]
    version: str


class _EligibilityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_training_rows: int
    min_seasons: int
    min_factories: int
    max_validation_wmape: float
    require_improvement_over_structural: bool
    max_fallback_rate: float


class _ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_family: Literal["hist_gradient_boosting_quantile"]
    model_version: str
    feature_schema_version: str
    artifact_schema_version: str
    quantiles: list[float]
    random_seed: int
    prediction_target_kind: PredictionTargetKind | None = None
    estimator: _EstimatorFile
    split: _SplitFile
    missing_values: _MissingFile
    categorical_encoding: _CategoricalFile
    projection: _ProjectionFile
    eligibility: _EligibilityFile

    @field_validator("quantiles")
    @classmethod
    def _validate_quantiles(cls, value: list[float]) -> list[float]:
        if value != [0.5, 0.8, 0.9]:
            raise ValueError("quantiles must be exactly [0.5, 0.8, 0.9]")
        return value


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _config_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(snapshot).encode("utf-8")).hexdigest()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _parse_config_snapshot(snapshot: dict[str, Any]) -> ResidualModelConfig:
    try:
        parsed = _ConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    prediction_target_kind = parsed.prediction_target_kind or (
        PredictionTargetKind.LEGACY_RESIDUAL_CORRECTION
    )
    return ResidualModelConfig(
        rules=ResidualModelRules(
            model_family=parsed.model_family,
            model_version=parsed.model_version,
            feature_schema_version=parsed.feature_schema_version,
            artifact_schema_version=parsed.artifact_schema_version,
            quantiles=tuple(parsed.quantiles),
            random_seed=parsed.random_seed,
            prediction_target_kind=prediction_target_kind,
            estimator=ResidualEstimatorConfig(**parsed.estimator.model_dump()),
            split_strategy=parsed.split.strategy,
            split_version=parsed.split.version,
            missing_values_version=parsed.missing_values.version,
            categorical_encoding_version=parsed.categorical_encoding.version,
            categorical_unknown_policy=parsed.categorical_encoding.unknown_policy,
            projection_nonnegative=parsed.projection.nonnegative,
            projection_quantile_monotonic=parsed.projection.quantile_monotonic,
            projection_version=parsed.projection.version,
            eligibility=ResidualEligibilityConfig(**parsed.eligibility.model_dump()),
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )


def load_residual_model_config(path: Path) -> ResidualModelConfig:
    snapshot = _read_yaml(path)
    return _parse_config_snapshot(snapshot)


def load_residual_model_config_from_snapshot(snapshot: dict[str, Any]) -> ResidualModelConfig:
    return _parse_config_snapshot(snapshot)


FINAL_TARGET_MODEL_FAMILY = "hist_gradient_boosting_quantile"
FINAL_TARGET_MODEL_VERSION = "final-target-quantile-v1"
FINAL_TARGET_FEATURE_SCHEMA_VERSION = "final-target-features-v1"
FINAL_TARGET_ARTIFACT_SCHEMA_VERSION = "final-target-artifact-v1"
FINAL_TARGET_ACTUALS_AUTHORITY = "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION"


def build_final_target_quantile_config_snapshot(
    *,
    random_seed: int = 20260903,
    min_training_rows: int = 30,
    min_seasons: int = 2,
    min_grains: int = 2,
) -> dict[str, Any]:
    """Build an explicit final-target config snapshot without touching legacy YAML."""

    return {
        "model_family": FINAL_TARGET_MODEL_FAMILY,
        "model_version": FINAL_TARGET_MODEL_VERSION,
        "feature_schema_version": FINAL_TARGET_FEATURE_SCHEMA_VERSION,
        "artifact_schema_version": FINAL_TARGET_ARTIFACT_SCHEMA_VERSION,
        "prediction_target_kind": PredictionTargetKind.FINAL_TARGET_QUANTILE.value,
        "quantiles": [0.5, 0.8, 0.9],
        "random_seed": random_seed,
        "estimator": {
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_leaf_nodes": 31,
            "max_depth": 6,
            "min_samples_leaf": 10,
            "l2_regularization": 0.1,
            "early_stopping": False,
            "validation_fraction": 0.2,
            "n_iter_no_change": 20,
            "tol": 0.0001,
        },
        "split": {
            "strategy": "leave_one_season_out",
            "version": "final-target-split-v1",
        },
        "missing_values": {"version": "final-target-missing-v1"},
        "categorical_encoding": {
            "version": "final-target-categorical-v1",
            "unknown_policy": "explicit_bucket",
        },
        "projection": {
            "nonnegative": True,
            "quantile_monotonic": "cumulative_max",
            "version": "final-target-projection-v1",
        },
        "eligibility": {
            "min_training_rows": min_training_rows,
            "min_seasons": min_seasons,
            "min_factories": min_grains,
            "max_validation_wmape": 0.35,
            "require_improvement_over_structural": False,
            "max_fallback_rate": 0.2,
        },
    }


def load_final_target_quantile_config(
    *,
    random_seed: int = 20260903,
    min_training_rows: int = 30,
    min_seasons: int = 2,
    min_grains: int = 2,
) -> ResidualModelConfig:
    snapshot = build_final_target_quantile_config_snapshot(
        random_seed=random_seed,
        min_training_rows=min_training_rows,
        min_seasons=min_seasons,
        min_grains=min_grains,
    )
    return load_residual_model_config_from_snapshot(snapshot)


def is_final_target_quantile_config(config: ResidualModelConfig) -> bool:
    return config.rules.prediction_target_kind == PredictionTargetKind.FINAL_TARGET_QUANTILE
