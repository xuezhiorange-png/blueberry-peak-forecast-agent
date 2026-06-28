from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


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
    return ResidualModelConfig(
        rules=ResidualModelRules(
            model_family=parsed.model_family,
            model_version=parsed.model_version,
            feature_schema_version=parsed.feature_schema_version,
            artifact_schema_version=parsed.artifact_schema_version,
            quantiles=tuple(parsed.quantiles),
            random_seed=parsed.random_seed,
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
