from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


@dataclass(frozen=True)
class ProductionPlanRules:
    version: str
    interval_semantics: Literal["half_open"]
    explicit_total_tolerance_kg: Decimal
    explicit_total_mismatch_behavior: Literal["warn", "reject"]


@dataclass(frozen=True)
class ProductionPlanConfig:
    rules: ProductionPlanRules
    config_hash: str
    snapshot: dict[str, Any]


class _ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    interval_semantics: Literal["half_open"]
    explicit_total_tolerance_kg: Decimal
    explicit_total_mismatch_behavior: Literal["warn", "reject"]

    @field_validator("explicit_total_tolerance_kg")
    @classmethod
    def _validate_tolerance(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("explicit_total_tolerance_kg must be non-negative")
        return value


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _config_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(snapshot).encode("utf-8")).hexdigest()


def load_production_plan_config(path: Path) -> ProductionPlanConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _ConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return ProductionPlanConfig(
        rules=ProductionPlanRules(
            version=parsed.version,
            interval_semantics=parsed.interval_semantics,
            explicit_total_tolerance_kg=parsed.explicit_total_tolerance_kg,
            explicit_total_mismatch_behavior=parsed.explicit_total_mismatch_behavior,
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
