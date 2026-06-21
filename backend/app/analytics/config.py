from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator


@dataclass(frozen=True)
class AnalyticsRules:
    version: str
    analysis_months: tuple[int, ...]
    rolling_window_days: int
    stable_peak_method: str
    mean_peak_method: str
    peak_concentration_definition: str
    spring_festival_codes: tuple[str, ...]
    unknown_farm_key: str
    unknown_subfarm_key: str
    stream_batch_size: int

    @property
    def rolling_window_radius(self) -> int:
        return self.rolling_window_days // 2


@dataclass(frozen=True)
class AnalyticsConfig:
    rules: AnalyticsRules
    config_hash: str
    snapshot: dict[str, Any]


class _AnalyticsRulesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    analysis_months: list[int]
    rolling_window_days: int
    stable_peak_method: Literal["median"]
    mean_peak_method: Literal["mean"]
    peak_concentration_definition: Literal["stable_median_3d_peak_over_total"]
    spring_festival_codes: list[str]
    unknown_farm_key: str
    unknown_subfarm_key: str
    stream_batch_size: int

    @field_validator("analysis_months")
    @classmethod
    def _validate_analysis_months(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("analysis_months must not be empty")
        normalized = sorted(set(value))
        if any(month < 1 or month > 12 for month in normalized):
            raise ValueError("analysis_months must contain values between 1 and 12")
        return normalized

    @field_validator("spring_festival_codes")
    @classmethod
    def _validate_spring_festival_codes(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("spring_festival_codes must not be empty")
        return normalized

    @field_validator("unknown_farm_key", "unknown_subfarm_key")
    @classmethod
    def _validate_unknown_keys(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("unknown key values must not be empty")
        return normalized

    @field_validator("stream_batch_size")
    @classmethod
    def _validate_stream_batch_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("stream_batch_size must be positive")
        return value

    @model_validator(mode="after")
    def _validate_window(self) -> _AnalyticsRulesFile:
        if self.rolling_window_days != 3:
            raise ValueError("rolling_window_days must be exactly 3")
        return self


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


def load_analytics_config(path: Path) -> AnalyticsConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _AnalyticsRulesFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    rules = AnalyticsRules(
        version=parsed.version,
        analysis_months=tuple(parsed.analysis_months),
        rolling_window_days=parsed.rolling_window_days,
        stable_peak_method=parsed.stable_peak_method,
        mean_peak_method=parsed.mean_peak_method,
        peak_concentration_definition=parsed.peak_concentration_definition,
        spring_festival_codes=tuple(parsed.spring_festival_codes),
        unknown_farm_key=parsed.unknown_farm_key,
        unknown_subfarm_key=parsed.unknown_subfarm_key,
        stream_batch_size=parsed.stream_batch_size,
    )
    return AnalyticsConfig(
        rules=rules,
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
