from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

_RIDGE_FEATURES = ("total_weight_kg", "variety_hhi", "farm_hhi", "subfarm_hhi")


@dataclass(frozen=True)
class RidgeRules:
    alpha: float
    fit_intercept: bool
    features: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationRules:
    primary_scheme: str
    minimum_training_rows: int
    mape_zero_policy: str
    unit: str


@dataclass(frozen=True)
class BaselineRules:
    version: str
    target: str
    ridge: RidgeRules
    evaluation: EvaluationRules
    random_seed: int
    benchmark_mode: str = "historical_oracle"
    production_eligible: bool = False


@dataclass(frozen=True)
class BaselineConfig:
    rules: BaselineRules
    config_hash: str
    snapshot: dict[str, Any]


class _RidgeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpha: float
    fit_intercept: bool

    @field_validator("alpha")
    @classmethod
    def _validate_alpha(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ridge alpha must be positive")
        return value


class _ModelFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    target: Literal["stable_median_3d_peak_kg"]
    ridge: _RidgeFile
    features: list[str]

    @field_validator("features")
    @classmethod
    def _validate_features(cls, value: list[str]) -> list[str]:
        if tuple(value) != _RIDGE_FEATURES:
            raise ValueError(f"ridge features must be exactly {list(_RIDGE_FEATURES)}")
        return value


class _EvaluationFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_scheme: Literal["leave_one_season_out"]
    minimum_training_rows: int
    mape_zero_policy: Literal["exclude"]
    unit: Literal["kg"]

    @field_validator("minimum_training_rows")
    @classmethod
    def _validate_minimum_training_rows(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("minimum_training_rows must be positive")
        return value


class _BaselineConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: _ModelFile
    evaluation: _EvaluationFile
    random_seed: int

    @model_validator(mode="after")
    def _validate_random_seed(self) -> _BaselineConfigFile:
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        return self


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


def load_baseline_config(path: Path) -> BaselineConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _BaselineConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return BaselineConfig(
        rules=BaselineRules(
            version=parsed.model.version,
            target=parsed.model.target,
            ridge=RidgeRules(
                alpha=parsed.model.ridge.alpha,
                fit_intercept=parsed.model.ridge.fit_intercept,
                features=tuple(parsed.model.features),
            ),
            evaluation=EvaluationRules(
                primary_scheme=parsed.evaluation.primary_scheme,
                minimum_training_rows=parsed.evaluation.minimum_training_rows,
                mape_zero_policy=parsed.evaluation.mape_zero_policy,
                unit=parsed.evaluation.unit,
            ),
            random_seed=parsed.random_seed,
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
