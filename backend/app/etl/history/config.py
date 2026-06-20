from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from backend.app.etl.history.schemas import (
    AliasConfig,
    FatalQualityThresholds,
    ImportConfig,
    ImportRules,
    SourceSpec,
)


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


def load_import_config(
    manifest_path: Path,
    rules_path: Path,
    factory_aliases_path: Path,
    variety_aliases_path: Path,
) -> ImportConfig:
    manifest = _read_yaml(manifest_path)
    rules_data = _read_yaml(rules_path)
    factory_data = _read_yaml(factory_aliases_path)
    variety_data = _read_yaml(variety_aliases_path)
    snapshot = {
        "manifest": manifest,
        "rules": rules_data,
        "factory_aliases": factory_data,
        "variety_aliases": variety_data,
    }
    sources = [
        SourceSpec(
            path=Path(item["path"]),
            source_name=str(item["source_name"]),
            season_code=str(item["season_code"]),
            enabled=bool(item.get("enabled", True)),
            expected_sheets=[str(sheet) for sheet in item.get("expected_sheets", [])],
            expected_sheets_behavior=str(item.get("expected_sheets_behavior", "warning")),
            header_aliases={
                str(key): str(value) for key, value in item.get("header_aliases", {}).items()
            },
            header_row=item.get("header_row"),
            description=str(item.get("description", "")),
        )
        for item in manifest.get("sources", [])
    ]
    threshold_data = rules_data.get("fatal_quality_thresholds", {})
    rules = ImportRules(
        version=str(rules_data["version"]),
        valid_months={int(month) for month in rules_data["valid_months"]},
        excluded_grades={str(value) for value in rules_data["excluded_grades"]},
        excluded_factories={str(value) for value in rules_data["excluded_factories"]},
        deduplicate_suspected_business_rows_in_curated=bool(
            rules_data.get("deduplicate_suspected_business_rows_in_curated", True)
        ),
        date_formats=[str(value) for value in rules_data["date_formats"]],
        variety_prefixes_to_remove=[
            str(value) for value in rules_data.get("variety_prefixes_to_remove", [])
        ],
        empty_strings={
            str(value) for value in rules_data.get("empty_values", {}).get("strings", [])
        },
        max_issue_examples=int(rules_data.get("report", {}).get("max_issue_examples", 50)),
        allow_unknown_factory_in_analysis=bool(
            rules_data.get("allow_unknown_factory_in_analysis", False)
        ),
        allow_unknown_variety_in_analysis=bool(
            rules_data.get("allow_unknown_variety_in_analysis", False)
        ),
        allow_empty_factory_in_analysis=bool(
            rules_data.get("allow_empty_factory_in_analysis", False)
        ),
        allow_empty_variety_in_analysis=bool(
            rules_data.get("allow_empty_variety_in_analysis", False)
        ),
        fatal_quality_thresholds=FatalQualityThresholds(
            max_invalid_date_count=_optional_int(threshold_data.get("max_invalid_date_count")),
            max_invalid_date_ratio=_optional_decimal(threshold_data.get("max_invalid_date_ratio")),
            max_invalid_weight_count=_optional_int(threshold_data.get("max_invalid_weight_count")),
            max_invalid_weight_ratio=_optional_decimal(
                threshold_data.get("max_invalid_weight_ratio")
            ),
        ),
    )
    factory_aliases = AliasConfig(
        version=str(factory_data["version"]),
        aliases={str(key): str(value) for key, value in factory_data.get("aliases", {}).items()},
    )
    variety_aliases = AliasConfig(
        version=str(variety_data["version"]),
        aliases={str(key): str(value) for key, value in variety_data.get("aliases", {}).items()},
        remove_prefixes=[str(value) for value in variety_data.get("remove_prefixes", [])],
    )
    return ImportConfig(
        sources=sources,
        rules=rules,
        factory_aliases=factory_aliases,
        variety_aliases=variety_aliases,
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
