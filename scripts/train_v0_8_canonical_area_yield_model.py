"""Materialize, fit, seal, and score the V0.8-S8 frozen OOT experiment."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.area_yield.formal_multi_season_validation import (
    business_boundary,
    predict_daily_curve,
)
from backend.app.area_yield.v08_s8_training_backtest import (
    OOT_SEASON,
    TARGET_END,
    TARGET_START,
    TRAINING_SEASONS,
    S8BacktestError,
    _is_true,
    _key,
    canonical_json_bytes,
    compose_daily_curve,
    csv_bytes,
    decimal_text,
    decimal_value,
    derive_peaks,
    fit_two_stage_model,
    numeric_distribution,
    predict_season_total,
    read_csv,
    score_model_daily,
    score_season_totals,
    season_calendar,
    sha256_bytes,
    sha256_file,
    signed_metric_delta,
    validate_curve,
    verify_model_artifact,
    write_private_bytes,
    write_private_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = Path.home() / "Documents/blueberry-area-yield-artifacts"
CONFIG_PATH = REPO_ROOT / "configs/v0_8_s8_training_backtest_r1.json"
TRAIN_FIELDS = [
    "base_id",
    "canonical_base_name",
    "season",
    "area_mu",
    "season_total_quantity_kg",
    "strict_training_eligible",
    "yield_kg_per_mu",
    "daily_curve_available",
    "daily_curve_source_signature",
    "area_authority_id",
    "area_authority_sha256",
    "quantity_authority_id",
    "quantity_authority_sha256",
    "identity_authority_id",
    "identity_authority_sha256",
    "source_signature",
    "eligibility_signature",
]
TRAIN_DAILY_FIELDS = [
    "base_id",
    "season",
    "date",
    "new_quantity_kg",
    "new_quantity_status",
    "new_completeness_status",
    "source_row_count",
    "source_signature",
]
AREA_FIELDS = [
    "base_id",
    "canonical_base_name",
    "season",
    "area_mu",
    "area_authority_id",
    "area_authority_sha256",
    "identity_authority_id",
    "identity_authority_sha256",
    "quantity_authority_sha256",
]
SEASON_PRED_FIELDS = [
    "model_id",
    "base_id",
    "canonical_base_name",
    "season",
    "target_area_mu",
    "predicted_season_total_kg",
    "estimated_yield_kg_per_mu",
    "prediction_basis",
    "model_artifact_sha256",
]
DAILY_PRED_FIELDS = [
    "model_id",
    "base_id",
    "canonical_base_name",
    "season",
    "date",
    "target_area_mu",
    "predicted_season_total_kg",
    "predicted_daily_quantity_kg",
    "predicted_share",
    "model_artifact_sha256",
]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S8BacktestError(f"EXPECTED_JSON_OBJECT:{path.name}")
    return value


def _write_json(path: Path, value: Any) -> None:
    write_private_json(path, value)


def _training_code_hash() -> str:
    code_paths = {
        "model": REPO_ROOT / "backend/app/area_yield/v08_s8_training_backtest.py",
        "runner": Path(__file__).resolve(),
    }
    return sha256_bytes(
        canonical_json_bytes({name: sha256_file(path) for name, path in sorted(code_paths.items())})
    )


def _secure_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    payload = csv_bytes(fields, rows)
    write_private_bytes(path, payload)
    return sha256_bytes(payload)


def _read_season_partition(
    path: Path, *, seasons: set[str], fields: Sequence[str]
) -> list[dict[str, str]]:
    """Select requested seasons before extracting any other cell values."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise S8BacktestError(f"EMPTY_CSV:{path.name}") from exc
        positions = {name: index for index, name in enumerate(header)}
        if "season" not in positions or any(name not in positions for name in fields):
            raise S8BacktestError(f"CSV_SCHEMA_MISMATCH:{path.name}")
        season_index = positions["season"]
        result: list[dict[str, str]] = []
        for row in reader:
            if len(row) != len(header):
                raise S8BacktestError(f"CSV_ROW_WIDTH_INVALID:{path.name}")
            season = row[season_index]
            if season not in seasons:
                continue
            result.append({field: row[positions[field]] for field in fields})
    return result


def _repo_pins(config: Mapping[str, Any]) -> None:
    expected = config["pinned_repository_evidence"]
    paths = {
        "s4_evidence": (
            "docs/v0-8/evidence/s4-user-confirmed-three-season-area-authority-application-r1.json"
        ),
        "s6_evidence": (
            "docs/v0-8/evidence/s6-no-record-zero-semantics-and-season-total-rebuild-r1.json"
        ),
        "s7_evidence": "docs/v0-8/evidence/s7-training-season-source-identity-closure-r1.json",
        "s4_config": "configs/v0_8_s4_three_season_area_authority_r1.json",
        "s6_config": "configs/v0_8_s6_no_record_zero_semantics_r1.json",
        "s7_config": "configs/v0_8_s7_training_source_identity_closure_r1.json",
    }
    for name, relative in paths.items():
        actual = sha256_file(REPO_ROOT / relative)
        if actual != expected[name]:
            raise S8BacktestError(f"REPOSITORY_EVIDENCE_HASH_MISMATCH:{name}")


PRIVATE_PIN_FILES = {
    "s4_artifact_manifest": ("s4", "artifact-manifest.json"),
    "s4_area_authority": ("s4", "three-season-historical-area-authority-r1.csv"),
    "s4_business_confirmation": ("s4", "three-season-area-business-confirmation-r1.json"),
    "s4_area_overlay": ("s4", "v0-8-three-season-area-authority-overlay-r1.csv"),
    "s6_artifact_manifest": ("s6", "artifact-manifest.json"),
    "s6_zero_confirmation": ("s6", "no-record-zero-business-confirmation-r1.json"),
    "s6_daily_zero_overlay": ("s6", "canonical-daily-harvest-zero-semantics-overlay-r1.csv"),
    "s6_season_total_authority": ("s6", "season-total-authority-overlay-r1.csv"),
    "s6_season_completeness": ("s6", "base-season-quantity-completeness-r2.csv"),
    "s6_strict_eligibility": ("s6", "strict-training-eligibility-r2.csv"),
    "s6_quantity_conservation": ("s6", "quantity-conservation-r2.csv"),
    "s7_artifact_manifest": ("s7", "artifact-manifest.json"),
    "s7_training_eligibility": ("s7", "strict-training-eligibility-s7-r1.csv"),
    "s7_identity_overlay": ("s7", "training-season-source-identity-overlay-r1.csv"),
    "s7_quantity_conservation": ("s7", "quantity-conservation-s7-r1.csv"),
}


def verify_private_pins(artifact_root: Path, config: Mapping[str, Any]) -> dict[str, str]:
    expected = config["pinned_private_inputs"]
    roots = config["private_input_roots"]
    verified: dict[str, str] = {}
    for key, (root_key, filename) in PRIVATE_PIN_FILES.items():
        path = artifact_root / roots[root_key] / filename
        if not path.is_file():
            raise S8BacktestError(f"PINNED_PRIVATE_INPUT_MISSING:{key}")
        actual = sha256_file(path)
        if actual != expected[key]:
            raise S8BacktestError(f"PRIVATE_AUTHORITY_HASH_MISMATCH:{key}")
        verified[key] = actual

    for root_key, manifest_key in (
        ("s4", "s4_artifact_manifest"),
        ("s6", "s6_artifact_manifest"),
        ("s7", "s7_artifact_manifest"),
    ):
        manifest = _read_json(artifact_root / roots[root_key] / "artifact-manifest.json")
        if not isinstance(manifest.get("artifacts"), dict):
            raise S8BacktestError(f"PRIVATE_MANIFEST_SCHEMA_INVALID:{root_key}")
        for key, (file_root, filename) in PRIVATE_PIN_FILES.items():
            if file_root != root_key or key == manifest_key:
                continue
            if manifest["artifacts"].get(filename) != expected[key]:
                raise S8BacktestError(f"PRIVATE_MANIFEST_CONTENT_HASH_MISMATCH:{key}")

    s6_summary = _read_json(artifact_root / roots["s6"] / "closure-summary-r1.json")
    s6_pins = s6_summary.get("business_rule", {}).get("authority_inputs", {})
    expected_s1 = {
        "s1_private_manifest": ("acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"),
        "s1_private:canonical-base-daily-ledger-r1.csv": (
            "be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75"
        ),
        "s1_private:canonical-base-season-quality-r1.csv": (
            "64a0a41afcde4ffe3c8713f62ca5cc03ee0f36599289bafd409e641df0a2f2fd"
        ),
        "s1_private:cross-season-base-identity-authority-r1.csv": (
            "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b"
        ),
    }
    if any(s6_pins.get(name) != value for name, value in expected_s1.items()):
        raise S8BacktestError("S6_S1_AUTHORITY_PINS_MISMATCH")

    s7_evidence = _read_json(
        REPO_ROOT / "docs/v0-8/evidence/s7-training-season-source-identity-closure-r1.json"
    )
    s7_input_pins = s7_evidence.get("s6_inputs", {})
    expected_s7_s6 = {
        "zero_business_confirmation_sha256": expected["s6_zero_confirmation"],
        "daily_zero_overlay_sha256": expected["s6_daily_zero_overlay"],
        "season_total_authority_sha256": expected["s6_season_total_authority"],
        "training_eligibility_sha256": expected["s6_strict_eligibility"],
        "conservation_sha256": expected["s6_quantity_conservation"],
    }
    if any(s7_input_pins.get(name) != value for name, value in expected_s7_s6.items()):
        raise S8BacktestError("S7_S6_INPUT_PINS_MISMATCH")
    return verified


def _load_model_and_registry(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str, str]:
    model_cfg = config["v07_frozen_comparator"]
    config_path = REPO_ROOT / model_cfg["config_path"]
    registry_path = REPO_ROOT / model_cfg["registry_path"]
    config_hash = sha256_file(config_path)
    registry_hash = sha256_file(registry_path)
    if config_hash != model_cfg["config_sha256"] or registry_hash != model_cfg["registry_sha256"]:
        raise S8BacktestError("V07_FROZEN_INPUT_HASH_MISMATCH")
    model = _read_json(config_path)
    registry_data = _read_json(registry_path)
    if model.get("artifact_hash") != model_cfg["artifact_sha256"]:
        raise S8BacktestError("V07_FROZEN_MODEL_ARTIFACT_HASH_MISMATCH")
    if model.get("history_policy") != "IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK":
        raise S8BacktestError("V07_FROZEN_HISTORY_POLICY_MISMATCH")
    if (
        model.get("research_artifacts", {}).get("temporal_model_artifact_sha256")
        != model_cfg["temporal_artifact_sha256"]
    ):
        raise S8BacktestError("V07_TEMPORAL_ARTIFACT_HASH_MISMATCH")
    if (
        model.get("research_artifacts", {}).get("temporal_model_canonical_hash")
        != model_cfg["temporal_artifact_canonical_hash"]
    ):
        raise S8BacktestError("V07_TEMPORAL_CANONICAL_HASH_MISMATCH")
    history = [
        row
        for row in model.get("base_yield_history", [])
        if row.get("season") == model_cfg["prior_season"]
    ]
    history_ids = [str(row["base_id"]) for row in history]
    if len(history) != model_cfg["expected_prior_yield_base_count"] or len(set(history_ids)) != len(
        history
    ):
        raise S8BacktestError("V07_PRIOR_YIELD_COHORT_MISMATCH")
    if not isinstance(registry_data.get("bases"), list) or len(registry_data["bases"]) != 39:
        raise S8BacktestError("V07_REGISTRY_MUST_HAVE_39_BASES")
    registry_by_id = {str(row["base_id"]): row for row in registry_data["bases"]}
    if len(registry_by_id) != 39:
        raise S8BacktestError("V07_REGISTRY_DUPLICATE_BASE_ID")
    return model, registry_by_id, config_hash, registry_hash


def _input_paths(artifact_root: Path, config: Mapping[str, Any]) -> dict[str, Path]:
    roots = config["private_input_roots"]
    return {
        "area": artifact_root / roots["s4"] / "three-season-historical-area-authority-r1.csv",
        "s4_eligibility": artifact_root
        / roots["s4"]
        / "three-season-area-quantity-training-eligibility-r1.csv",
        "daily": artifact_root
        / roots["s6"]
        / "canonical-daily-harvest-zero-semantics-overlay-r1.csv",
        "season_total": artifact_root / roots["s6"] / "season-total-authority-overlay-r1.csv",
        "completeness": artifact_root / roots["s6"] / "base-season-quantity-completeness-r2.csv",
        "s6_eligibility": artifact_root / roots["s6"] / "strict-training-eligibility-r2.csv",
        "s7_eligibility": artifact_root / roots["s7"] / "strict-training-eligibility-s7-r1.csv",
    }


def _preflight_cohort(
    paths: Mapping[str, Path], config: Mapping[str, Any], area_rows: Sequence[Mapping[str, str]]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    expected_area = config["cohort"]["canonical_base_count"]
    area_oot = [row for row in area_rows if row["season"] == OOT_SEASON]
    area_ids = {row["base_id"] for row in area_oot}
    if len(area_oot) != expected_area or len(area_ids) != expected_area:
        raise S8BacktestError("BLOCKED_OOT_COHORT_NOT_39_COMPLETE:AREA_SCOPE")

    oot_eligibility = _read_season_partition(
        paths["s6_eligibility"],
        seasons={OOT_SEASON},
        fields=["base_id", "season", "area_eligible", "strict_oot_eligible"],
    )
    oot_completeness = _read_season_partition(
        paths["completeness"],
        seasons={OOT_SEASON},
        fields=[
            "base_id",
            "season",
            "season_start_date",
            "season_end_date",
            "expected_calendar_day_count",
            "daily_curve_evaluation_eligible",
            "season_total_training_eligible",
        ],
    )
    oot_total_status = _read_season_partition(
        paths["season_total"],
        seasons={OOT_SEASON},
        fields=["base_id", "season", "quantity_authority_status"],
    )
    eligibility_by_id = {row["base_id"]: row for row in oot_eligibility}
    completeness_by_id = {row["base_id"]: row for row in oot_completeness}
    total_by_id = {row["base_id"]: row for row in oot_total_status}
    expected_calendar = season_calendar(OOT_SEASON)
    if any(
        len(mapping) != expected_area
        for mapping in (eligibility_by_id, completeness_by_id, total_by_id)
    ):
        raise S8BacktestError("BLOCKED_OOT_COHORT_NOT_39_COMPLETE:AUTHORITY_ROWS")
    valid_total_statuses = {
        "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY",
        "BUSINESS_TOTAL_RECONCILED_WITH_DAILY_SUM",
    }
    for base_id in sorted(area_ids):
        eligibility = eligibility_by_id.get(base_id)
        completeness = completeness_by_id.get(base_id)
        total = total_by_id.get(base_id)
        if (
            eligibility is None
            or not _is_true(eligibility["area_eligible"])
            or not _is_true(eligibility["strict_oot_eligible"])
            or completeness is None
            or not _is_true(completeness["daily_curve_evaluation_eligible"])
            or int(completeness["expected_calendar_day_count"]) != len(expected_calendar)
            or completeness["season_start_date"] != TARGET_START.isoformat()
            or completeness["season_end_date"] != TARGET_END.isoformat()
            or total is None
            or total["quantity_authority_status"] not in valid_total_statuses
        ):
            raise S8BacktestError(f"BLOCKED_OOT_COHORT_NOT_39_COMPLETE:{base_id}")
    area_inputs = [
        {
            "base_id": row["base_id"],
            "canonical_base_name": row["canonical_base_name"],
            "season": row["season"],
            "area_mu": row["historical_actual_area_mu"],
            "area_authority_id": row["area_authority_id"],
            "area_authority_sha256": config["pinned_private_inputs"]["s4_area_authority"],
            "identity_authority_id": row["identity_authority_id"],
            "identity_authority_sha256": row["identity_authority_sha256"],
            "quantity_authority_sha256": config["pinned_private_inputs"][
                "s6_season_total_authority"
            ],
        }
        for row in sorted(area_oot, key=lambda item: item["base_id"])
    ]
    return area_inputs, {
        "oot_area_base_count": len(area_inputs),
        "oot_authority_eligible_count": len(eligibility_by_id),
        "oot_daily_curve_eligible_count": len(completeness_by_id),
        "oot_expected_days_per_base": len(expected_calendar),
        "oot_season_total_authority_count": len(total_by_id),
    }


def _materialize_training(
    *,
    paths: Mapping[str, Path],
    config: Mapping[str, Any],
    output_root: Path,
    area_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    pinned = config["pinned_private_inputs"]
    area_by_key = {(row["base_id"], row["season"]): row for row in area_rows}
    quantity_rows = _read_season_partition(
        paths["season_total"],
        seasons=set(TRAINING_SEASONS),
        fields=[
            "base_id",
            "base_name",
            "season",
            "season_total_quantity_kg",
            "quantity_authority_status",
            "quantity_authority_basis",
            "daily_curve_evaluation_eligible",
            "blocker_codes",
            "quantity_authority_id",
        ],
    )
    quantity_by_key = {_key(row): row for row in quantity_rows}
    completeness_rows = _read_season_partition(
        paths["completeness"],
        seasons=set(TRAINING_SEASONS),
        fields=[
            "base_id",
            "season",
            "expected_calendar_day_count",
            "season_total_training_eligible",
            "daily_curve_evaluation_eligible",
            "season_start_date",
            "season_end_date",
        ],
    )
    completeness_by_key = {_key(row): row for row in completeness_rows}
    s6_eligibility = _read_season_partition(
        paths["s6_eligibility"],
        seasons=set(TRAINING_SEASONS),
        fields=[
            "base_id",
            "season",
            "area_eligible",
            "strict_training_eligible",
            "exclusion_reason",
        ],
    )
    s6_eligible_keys = {
        _key(row) for row in s6_eligibility if _is_true(row["strict_training_eligible"])
    }
    s7_rows = read_csv(paths["s7_eligibility"])
    s7_eligible_keys = {_key(row) for row in s7_rows if _is_true(row["strict_training_eligible"])}
    if s6_eligible_keys != s7_eligible_keys or len(s6_eligible_keys) != 37:
        raise S8BacktestError("S7_S6_STRICT_TRAINING_COHORT_MISMATCH")

    eligible_daily = _read_season_partition(
        paths["daily"],
        seasons=set(TRAINING_SEASONS),
        fields=[
            "base_id",
            "base_name",
            "season",
            "date",
            "new_quantity_status",
            "new_completeness_status",
            "new_quantity_kg",
            "source_row_count",
            "authority_eligible_daily",
        ],
    )
    daily_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in eligible_daily:
        key = _key(row)
        if key in s6_eligible_keys:
            daily_by_key[key].append(row)

    training_rows: list[dict[str, Any]] = []
    training_curve_rows: list[dict[str, Any]] = []
    for base_id, season in sorted(s6_eligible_keys, key=lambda key: (key[1], key[0])):
        key = (base_id, season)
        area = area_by_key.get(key)
        quantity = quantity_by_key.get(key)
        coverage = completeness_by_key.get(key)
        if area is None or quantity is None or coverage is None:
            raise S8BacktestError("STRICT_TRAINING_AUTHORITY_ROW_MISSING")
        if not _is_true(area["authority_eligible"]) or not _is_true(
            coverage["season_total_training_eligible"]
        ):
            raise S8BacktestError("STRICT_TRAINING_ELIGIBILITY_REVOKED")
        if quantity["quantity_authority_status"] not in {
            "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY",
            "BUSINESS_TOTAL_RECONCILED_WITH_DAILY_SUM",
        }:
            raise S8BacktestError("STRICT_TRAINING_QUANTITY_AUTHORITY_INVALID")
        curve = sorted(daily_by_key.get(key, []), key=lambda row: row["date"])
        total = decimal_value(quantity["season_total_quantity_kg"], "training_total")
        validate_curve(curve, season=season, expected_total=total)
        curve_digest_rows = [
            {
                "date": row["date"],
                "quantity_kg": row["new_quantity_kg"],
                "status": row["new_completeness_status"],
            }
            for row in curve
        ]
        curve_signature = sha256_bytes(canonical_json_bytes(curve_digest_rows))
        area_mu = decimal_value(area["historical_actual_area_mu"], "training_area")
        identity_hash = str(area["identity_authority_sha256"])
        identity_id = str(area["identity_authority_id"])
        source_signature = sha256_bytes(
            canonical_json_bytes(
                {
                    "base_id": base_id,
                    "season": season,
                    "area_authority_sha256": pinned["s4_area_authority"],
                    "quantity_authority_sha256": pinned["s6_season_total_authority"],
                    "identity_authority_sha256": identity_hash,
                    "daily_curve_source_signature": curve_signature,
                }
            )
        )
        eligibility_signature = sha256_bytes(
            canonical_json_bytes(
                {
                    "area_eligible": True,
                    "quantity_authority_status": quantity["quantity_authority_status"],
                    "season_total_training_eligible": True,
                    "daily_curve_evaluation_eligible": _is_true(
                        coverage["daily_curve_evaluation_eligible"]
                    ),
                    "blocker_codes": quantity["blocker_codes"],
                }
            )
        )
        training_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": area["canonical_base_name"],
                "season": season,
                "area_mu": decimal_text(area_mu),
                "season_total_quantity_kg": decimal_text(total),
                "strict_training_eligible": True,
                "yield_kg_per_mu": decimal_text(total / area_mu),
                "daily_curve_available": True,
                "daily_curve_source_signature": curve_signature,
                "area_authority_id": area["area_authority_id"],
                "area_authority_sha256": pinned["s4_area_authority"],
                "quantity_authority_id": quantity["quantity_authority_id"],
                "quantity_authority_sha256": pinned["s6_season_total_authority"],
                "identity_authority_id": identity_id,
                "identity_authority_sha256": identity_hash,
                "source_signature": source_signature,
                "eligibility_signature": eligibility_signature,
            }
        )
        for row in curve:
            training_curve_rows.append(
                {
                    "base_id": base_id,
                    "season": season,
                    "date": row["date"],
                    "new_quantity_kg": row["new_quantity_kg"],
                    "new_quantity_status": row["new_quantity_status"],
                    "new_completeness_status": row["new_completeness_status"],
                    "source_row_count": row["source_row_count"],
                    "source_signature": curve_signature,
                }
            )

    if len(training_rows) != 37:
        raise S8BacktestError("TRAINING_DATASET_ROW_COUNT_NOT_37")
    counts = {
        season: sum(row["season"] == season for row in training_rows) for season in TRAINING_SEASONS
    }
    if counts != {"2023-2024": 15, "2024-2025": 22}:
        raise S8BacktestError("TRAINING_SEASON_COUNTS_NOT_15_AND_22")
    if len({row["base_id"] for row in training_rows}) != 26:
        raise S8BacktestError("TRAINING_UNIQUE_BASE_COUNT_DRIFT")

    training_sha = _secure_csv(
        output_root / "v0-8-canonical-training-dataset-r1.csv", TRAIN_FIELDS, training_rows
    )
    daily_sha = _secure_csv(
        output_root / "training-daily-curves-r1.csv",
        TRAIN_DAILY_FIELDS,
        sorted(training_curve_rows, key=lambda row: (row["season"], row["base_id"], row["date"])),
    )
    training_manifest = {
        "row_count": len(training_rows),
        "unique_base_season_count": len(s6_eligible_keys),
        "unique_base_count": 26,
        "season_counts": counts,
        "training_dataset_sha256": training_sha,
        "training_daily_curve_row_count": len(training_curve_rows),
        "training_daily_curve_sha256": daily_sha,
        "blocked_training_rows_included": 0,
        "seasons": list(TRAINING_SEASONS),
        "oot_labels_read": False,
        "authority_pins": dict(config["pinned_private_inputs"]),
    }
    _write_json(output_root / "training-dataset-manifest-r1.json", training_manifest)
    return {
        "training_rows": training_rows,
        "training_daily_rows": training_curve_rows,
        "training_dataset_sha256": training_sha,
        "training_daily_sha256": daily_sha,
        "training_manifest": training_manifest,
    }


def _fit_child(args: argparse.Namespace) -> None:
    config = _read_json(args.config)
    training_rows = read_csv(args.training_dataset)
    daily_rows = read_csv(args.training_daily)
    model = fit_two_stage_model(
        training_rows,
        daily_rows,
        config_sha256=sha256_file(args.config),
        training_code_sha256=_training_code_hash(),
        training_dataset_sha256=sha256_file(args.training_dataset),
        training_daily_sha256=sha256_file(args.training_daily),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    _write_json(output, model)
    if model["training_row_count"] != config["cohort"]["training_base_season_count"]:
        raise S8BacktestError("FIT_CHILD_TRAINING_COUNT_MISMATCH")


def _prediction_child(args: argparse.Namespace) -> None:
    config = _read_json(args.config)
    model = _read_json(args.model)
    verify_model_artifact(model)
    area_rows = read_csv(args.oot_area)
    v07_model, registry_by_id, _, _ = _load_model_and_registry(config)
    v07_history = {
        str(row["base_id"]): decimal_value(row["yield_kg_per_mu"], "v07_yield")
        for row in v07_model["base_yield_history"]
        if row.get("season") == config["v07_frozen_comparator"]["prior_season"]
    }
    season_predictions: list[dict[str, Any]] = []
    daily_predictions: list[dict[str, Any]] = []
    boundary = business_boundary(OOT_SEASON)
    if boundary.start != TARGET_START or boundary.end != TARGET_END:
        raise S8BacktestError("FROZEN_OOT_BOUNDARY_MISMATCH")
    for area_row in sorted(area_rows, key=lambda row: row["base_id"]):
        base_id = str(area_row["base_id"])
        area = decimal_value(area_row["area_mu"], "oot_area")
        registry_area = decimal_value(
            registry_by_id[base_id]["productive_area_mu"], "v07_reference_area"
        )
        if area != registry_area:
            raise S8BacktestError("V07_AND_S8_OOT_AREA_INPUTS_DIFFER")
        for model_id, use_base_yield in (
            ("AREA_PROPORTIONAL_POOLED_TRAINING_YIELD_R1", False),
            ("V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1", True),
        ):
            total_prediction = predict_season_total(
                model, base_id=base_id, area_mu=area, use_base_yield=use_base_yield
            )
            predicted_total = decimal_value(
                total_prediction["predicted_season_total_kg"], "predicted_total"
            )
            daily = compose_daily_curve(model=model, predicted_total_kg=predicted_total)
            season_predictions.append(
                {
                    "model_id": model_id,
                    "base_id": base_id,
                    "canonical_base_name": area_row["canonical_base_name"],
                    "season": OOT_SEASON,
                    "target_area_mu": decimal_text(area),
                    "predicted_season_total_kg": decimal_text(predicted_total),
                    "estimated_yield_kg_per_mu": total_prediction["predicted_yield_kg_per_mu"],
                    "prediction_basis": total_prediction["prediction_basis"],
                    "model_artifact_sha256": model["artifact_hash"],
                }
            )
            for daily_row in daily:
                daily_predictions.append(
                    {
                        "model_id": model_id,
                        "base_id": base_id,
                        "canonical_base_name": area_row["canonical_base_name"],
                        "season": OOT_SEASON,
                        "date": daily_row["date"],
                        "target_area_mu": decimal_text(area),
                        "predicted_season_total_kg": decimal_text(predicted_total),
                        "predicted_daily_quantity_kg": daily_row["predicted_daily_quantity_kg"],
                        "predicted_share": daily_row["predicted_share"],
                        "model_artifact_sha256": model["artifact_hash"],
                    }
                )
        if base_id in v07_history:
            v07_total = (area * v07_history[base_id]).quantize(Decimal("0.000001"))
            v07_curve = predict_daily_curve(
                season=OOT_SEASON,
                reference_area_mu=registry_area,
                predicted_total_kg=v07_total,
                temporal_model=v07_model["temporal_model"],
                boundary=boundary,
            )
            season_predictions.append(
                {
                    "model_id": "V0_7_PRODUCTION_MODEL",
                    "base_id": base_id,
                    "canonical_base_name": area_row["canonical_base_name"],
                    "season": OOT_SEASON,
                    "target_area_mu": decimal_text(area),
                    "predicted_season_total_kg": decimal_text(v07_total),
                    "estimated_yield_kg_per_mu": decimal_text(v07_history[base_id]),
                    "prediction_basis": "FROZEN_V07_IMMEDIATE_PRIOR_BASE_HISTORY",
                    "model_artifact_sha256": config["v07_frozen_comparator"]["artifact_sha256"],
                }
            )
            for daily_row in v07_curve:
                daily_predictions.append(
                    {
                        "model_id": "V0_7_PRODUCTION_MODEL",
                        "base_id": base_id,
                        "canonical_base_name": area_row["canonical_base_name"],
                        "season": OOT_SEASON,
                        "date": daily_row["date"],
                        "target_area_mu": decimal_text(area),
                        "predicted_season_total_kg": decimal_text(v07_total),
                        "predicted_daily_quantity_kg": daily_row["predicted_quantity_kg"],
                        "predicted_share": daily_row["normalized_share"],
                        "model_artifact_sha256": config["v07_frozen_comparator"]["artifact_sha256"],
                    }
                )
    season_predictions.sort(key=lambda row: (row["model_id"], row["base_id"]))
    daily_predictions.sort(key=lambda row: (row["model_id"], row["base_id"], row["date"]))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    _secure_csv(output_dir / "season-predictions.csv", SEASON_PRED_FIELDS, season_predictions)
    _secure_csv(output_dir / "daily-predictions.csv", DAILY_PRED_FIELDS, daily_predictions)
    _write_json(
        output_dir / "prediction-manifest.json",
        {
            "oot_season": OOT_SEASON,
            "season_prediction_row_count": len(season_predictions),
            "daily_prediction_row_count": len(daily_predictions),
            "season_prediction_sha256": sha256_file(output_dir / "season-predictions.csv"),
            "daily_prediction_sha256": sha256_file(output_dir / "daily-predictions.csv"),
            "oot_actual_labels_read": False,
            "model_artifact_sha256": model["artifact_hash"],
        },
    )


def _load_oot_truth(
    paths: Mapping[str, Path],
) -> tuple[dict[str, Decimal], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    # This function is invoked only after the prediction seal exists and matches.
    total_rows = _read_season_partition(
        paths["season_total"],
        seasons={OOT_SEASON},
        fields=[
            "base_id",
            "base_name",
            "season_total_quantity_kg",
            "quantity_authority_status",
            "quantity_authority_basis",
        ],
    )
    completeness_rows = _read_season_partition(
        paths["completeness"],
        seasons={OOT_SEASON},
        fields=[
            "base_id",
            "expected_calendar_day_count",
            "daily_curve_evaluation_eligible",
            "season_total_training_eligible",
        ],
    )
    daily_rows = _read_season_partition(
        paths["daily"],
        seasons={OOT_SEASON},
        fields=[
            "base_id",
            "base_name",
            "date",
            "new_quantity_kg",
            "new_quantity_status",
            "new_completeness_status",
            "authority_eligible_daily",
        ],
    )
    totals = {
        row["base_id"]: decimal_value(row["season_total_quantity_kg"], "oot_actual_total")
        for row in total_rows
    }
    if len(totals) != 39:
        raise S8BacktestError("BLOCKED_OOT_COHORT_NOT_39_COMPLETE:TOTAL_LABELS")
    completeness_by_id = {row["base_id"]: row for row in completeness_rows}
    daily_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        daily_by_base[row["base_id"]].append(
            {
                "date": row["date"],
                "actual_quantity_kg": row["new_quantity_kg"],
                "actual_completeness_status": row["new_completeness_status"],
                "authority_eligible_daily": row["authority_eligible_daily"],
            }
        )
    if set(daily_by_base) != set(totals) or set(completeness_by_id) != set(totals):
        raise S8BacktestError("BLOCKED_OOT_COHORT_NOT_39_COMPLETE:DAILY_LABELS")
    meta_by_id: dict[str, dict[str, Any]] = {}
    total_rows_by_id = {row["base_id"]: row for row in total_rows}
    for base_id in sorted(totals):
        if total_rows_by_id[base_id]["quantity_authority_status"] not in {
            "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY",
            "BUSINESS_TOTAL_RECONCILED_WITH_DAILY_SUM",
        }:
            raise S8BacktestError(f"BLOCKED_OOT_COHORT_NOT_39_COMPLETE:TOTAL_AUTHORITY:{base_id}")
        if not _is_true(completeness_by_id[base_id]["daily_curve_evaluation_eligible"]) or int(
            completeness_by_id[base_id]["expected_calendar_day_count"]
        ) != len(season_calendar(OOT_SEASON)):
            raise S8BacktestError(f"BLOCKED_OOT_COHORT_NOT_39_COMPLETE:DAILY_COVERAGE:{base_id}")
        rows = sorted(daily_by_base[base_id], key=lambda row: row["date"])
        validate_curve(rows, season=OOT_SEASON, expected_total=totals[base_id])
        peaks = derive_peaks(rows)
        meta_by_id[base_id] = {
            "base_name": total_rows_by_id[base_id]["base_name"],
            "quantity_authority_status": total_rows_by_id[base_id]["quantity_authority_status"],
            "quantity_authority_basis": total_rows_by_id[base_id]["quantity_authority_basis"],
            "daily_curve_sha256": sha256_bytes(
                canonical_json_bytes(
                    [
                        {"date": row["date"], "actual_quantity_kg": row["actual_quantity_kg"]}
                        for row in rows
                    ]
                )
            ),
            "daily_row_count": len(rows),
            "expected_day_count": int(completeness_by_id[base_id]["expected_calendar_day_count"]),
            **peaks,
        }
    return totals, daily_by_base, meta_by_id


def _read_predictions(directory: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return read_csv(directory / "season-predictions.csv"), read_csv(
        directory / "daily-predictions.csv"
    )


def _as_decimal_index(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, Decimal]]:
    result: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in rows:
        result[row["model_id"]][row["base_id"]] = decimal_value(
            row["predicted_season_total_kg"], "predicted_total"
        )
    return result


def _daily_groups(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        result[row["model_id"]][row["base_id"]].append(dict(row))
    return result


def _metric_comparisons(metrics: Mapping[str, Any], v08: str, comparator: str) -> dict[str, str]:
    mappings = (
        ("season_total_wape", "season_total", "wape"),
        ("season_total_mae", "season_total", "mae"),
        ("daily_wape", "daily", "daily_wape"),
        ("daily_mae", "daily", "daily_mae"),
        ("single_day_peak_quantity_wape", "daily", "single_day_peak_wape"),
        ("single_day_peak_date_mae_days", "daily", "single_day_peak_date_mae_days"),
        ("rolling7_peak_quantity_wape", "daily", "rolling7_peak_wape"),
        ("rolling7_peak_start_date_mae_days", "daily", "rolling7_start_date_mae_days"),
    )
    result: dict[str, str] = {}
    for output_key, group, metric in mappings:
        if group == "season_total":
            candidate = metrics["season_total"][v08][metric]
            other = metrics["season_total"][comparator][metric]
        else:
            daily_path = {
                "daily_wape": ("daily", "wape"),
                "daily_mae": ("daily", "mae"),
                "single_day_peak_wape": ("single_day_peak", "wape"),
                "single_day_peak_date_mae_days": ("single_day_peak", "date_mae_days"),
                "rolling7_peak_wape": ("rolling7_peak", "wape"),
                "rolling7_start_date_mae_days": ("rolling7_peak", "start_date_mae_days"),
            }[metric]
            group_key, metric_key = daily_path
            candidate = metrics["daily"][v08][group_key][metric_key]
            other = metrics["daily"][comparator][group_key][metric_key]
        result[output_key] = signed_metric_delta(candidate, other)
    return result


def _score_once(
    *,
    prediction_dir: Path,
    paths: Mapping[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    totals_actual, daily_actual, oot_meta = _load_oot_truth(paths)
    season_predictions, daily_predictions = _read_predictions(prediction_dir)
    season_index = _as_decimal_index(season_predictions)
    daily_index = _daily_groups(daily_predictions)
    v07_id = "V0_7_PRODUCTION_MODEL"
    baseline_id = "AREA_PROPORTIONAL_POOLED_TRAINING_YIELD_R1"
    v08_id = "V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1"
    expected_ids = set(totals_actual)
    if set(season_index[baseline_id]) != expected_ids or set(season_index[v08_id]) != expected_ids:
        raise S8BacktestError("BASELINE_OR_V08_NOT_FULL_39_OOT")
    common_ids = set(season_index[v07_id])
    if len(common_ids) != 30 or not common_ids <= expected_ids:
        raise S8BacktestError("V07_COMMON_COMPARATOR_COHORT_NOT_EXPECTED_30")
    if any(
        set(daily_index[model]) != expected
        for model, expected in (
            (baseline_id, expected_ids),
            (v08_id, expected_ids),
            (v07_id, common_ids),
        )
    ):
        raise S8BacktestError("DAILY_PREDICTION_COHORT_MISMATCH")

    actual_rows_by_base = daily_actual
    full_actual = totals_actual
    full_preds = {model: season_index[model] for model in (baseline_id, v08_id)}
    common_actual = {base_id: totals_actual[base_id] for base_id in common_ids}
    common_preds = {
        model: {base_id: season_index[model][base_id] for base_id in common_ids}
        for model in (baseline_id, v07_id, v08_id)
    }
    season_metrics = {
        "FULL_39_OOT": score_season_totals(full_actual, full_preds),
        "COMMON_COMPARATOR_COHORT": score_season_totals(common_actual, common_preds),
    }
    daily_metrics: dict[str, Any] = {"FULL_39_OOT": {}, "COMMON_COMPARATOR_COHORT": {}}
    for model_id in (baseline_id, v08_id):
        selected_actual = {base_id: actual_rows_by_base[base_id] for base_id in expected_ids}
        daily_metrics["FULL_39_OOT"][model_id] = score_model_daily(
            [row for base_id in sorted(expected_ids) for row in daily_index[model_id][base_id]],
            selected_actual,
        )
    for model_id in (baseline_id, v07_id, v08_id):
        daily_metrics["COMMON_COMPARATOR_COHORT"][model_id] = score_model_daily(
            [row for base_id in sorted(common_ids) for row in daily_index[model_id][base_id]],
            {base_id: actual_rows_by_base[base_id] for base_id in common_ids},
        )

    comparison = {
        "V0_8_VS_V0_7_COMMON_COHORT": _metric_comparisons(
            {
                "season_total": season_metrics["COMMON_COMPARATOR_COHORT"],
                "daily": daily_metrics["COMMON_COMPARATOR_COHORT"],
            },
            v08_id,
            v07_id,
        ),
        "V0_8_VS_BASELINE_COMMON_COHORT": _metric_comparisons(
            {
                "season_total": season_metrics["COMMON_COMPARATOR_COHORT"],
                "daily": daily_metrics["COMMON_COMPARATOR_COHORT"],
            },
            v08_id,
            baseline_id,
        ),
        "V0_8_VS_BASELINE_FULL_39": _metric_comparisons(
            {"season_total": season_metrics["FULL_39_OOT"], "daily": daily_metrics["FULL_39_OOT"]},
            v08_id,
            baseline_id,
        ),
    }
    scores = {
        "season_total": season_metrics,
        "daily": daily_metrics,
        "comparisons": comparison,
        "common_comparator_oot_count": len(common_ids),
        "full_v08_oot_count": len(expected_ids),
        "full_oot_actual_base_season_count": len(totals_actual),
        "oot_truth_signatures": {
            base_id: oot_meta[base_id]["daily_curve_sha256"] for base_id in sorted(oot_meta)
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for filename, key in (
        ("season-total-metrics-r1.json", "season_total"),
        ("daily-curve-metrics-r1.json", "daily"),
    ):
        _write_json(output_dir / filename, scores[key])
    _write_json(
        output_dir / "rolling7-peak-metrics-r1.json",
        {
            scope: {
                model_id: metrics["rolling7_peak"] for model_id, metrics in scope_metrics.items()
            }
            for scope, scope_metrics in daily_metrics.items()
        },
    )
    _write_json(
        output_dir / "single-day-peak-metrics-r1.json",
        {
            scope: {
                model_id: metrics["single_day_peak"] for model_id, metrics in scope_metrics.items()
            }
            for scope, scope_metrics in daily_metrics.items()
        },
    )
    _write_json(output_dir / "metric-comparison-r1.json", comparison)
    _write_json(output_dir / "score-summary-r1.json", scores)
    _materialize_scored_artifacts(
        output_dir=output_dir,
        season_predictions=season_predictions,
        daily_predictions=daily_predictions,
        actual_totals=totals_actual,
        actual_daily=daily_actual,
        oot_meta=oot_meta,
        season_metrics=season_metrics,
        daily_metrics=daily_metrics,
    )
    return scores


def _materialize_scored_artifacts(
    *,
    output_dir: Path,
    season_predictions: Sequence[Mapping[str, str]],
    daily_predictions: Sequence[Mapping[str, str]],
    actual_totals: Mapping[str, Decimal],
    actual_daily: Mapping[str, Sequence[Mapping[str, Any]]],
    oot_meta: Mapping[str, Mapping[str, Any]],
    season_metrics: Mapping[str, Any],
    daily_metrics: Mapping[str, Any],
) -> None:
    area_by_base = {row["base_id"]: row["target_area_mu"] for row in season_predictions}
    name_by_base = {row["base_id"]: row["canonical_base_name"] for row in season_predictions}
    model_total: dict[str, dict[str, Decimal]] = defaultdict(dict)
    model_yield: dict[str, dict[str, str]] = defaultdict(dict)
    model_hash: dict[str, dict[str, str]] = defaultdict(dict)
    for season_prediction in season_predictions:
        model_id = season_prediction["model_id"]
        model_total[model_id][season_prediction["base_id"]] = decimal_value(
            season_prediction["predicted_season_total_kg"], "pred_total"
        )
        model_yield[model_id][season_prediction["base_id"]] = season_prediction[
            "estimated_yield_kg_per_mu"
        ]
        model_hash[model_id][season_prediction["base_id"]] = season_prediction[
            "model_artifact_sha256"
        ]
    daily_by_model_base = _daily_groups(daily_predictions)
    v08_id = "V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1"
    baseline_id = "AREA_PROPORTIONAL_POOLED_TRAINING_YIELD_R1"
    v07_id = "V0_7_PRODUCTION_MODEL"

    total_fields = [
        "base_id",
        "canonical_base_name",
        "season",
        "actual_area_mu",
        "actual_season_total_kg",
        "predicted_season_total_kg",
        "predicted_yield_kg_per_mu",
        "prediction_basis",
        "actual_peak_date",
        "actual_peak_quantity_kg",
        "predicted_peak_date",
        "predicted_peak_quantity_kg",
        "actual_rolling7_start_date",
        "actual_rolling7_end_date",
        "actual_rolling7_peak_quantity_kg",
        "predicted_rolling7_start_date",
        "predicted_rolling7_end_date",
        "predicted_rolling7_peak_quantity_kg",
        "model_artifact_sha256",
    ]
    model_name_map = {
        v08_id: "v0-8-oot-season-total-predictions-r1.csv",
        baseline_id: "baseline-oot-predictions-r1.csv",
        v07_id: "v0-7-oot-predictions-r1.csv",
    }
    for model_id, filename in model_name_map.items():
        rows: list[dict[str, Any]] = []
        for base_id in sorted(model_total[model_id]):
            daily_rows = sorted(daily_by_model_base[model_id][base_id], key=lambda row: row["date"])
            actual_peak = derive_peaks(actual_daily[base_id])
            predicted_peak = derive_peaks(daily_rows)
            pred = next(
                row
                for row in season_predictions
                if row["model_id"] == model_id and row["base_id"] == base_id
            )
            rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": pred["canonical_base_name"],
                    "season": OOT_SEASON,
                    "actual_area_mu": area_by_base[base_id],
                    "actual_season_total_kg": decimal_text(actual_totals[base_id]),
                    "predicted_season_total_kg": decimal_text(model_total[model_id][base_id]),
                    "predicted_yield_kg_per_mu": model_yield[model_id][base_id],
                    "prediction_basis": pred["prediction_basis"],
                    "actual_peak_date": actual_peak["single_day_peak_date"],
                    "actual_peak_quantity_kg": actual_peak["single_day_peak_quantity_kg"],
                    "predicted_peak_date": predicted_peak["single_day_peak_date"],
                    "predicted_peak_quantity_kg": predicted_peak["single_day_peak_quantity_kg"],
                    "actual_rolling7_start_date": actual_peak["rolling7_start_date"],
                    "actual_rolling7_end_date": actual_peak["rolling7_end_date"],
                    "actual_rolling7_peak_quantity_kg": actual_peak["rolling7_peak_quantity_kg"],
                    "predicted_rolling7_start_date": predicted_peak["rolling7_start_date"],
                    "predicted_rolling7_end_date": predicted_peak["rolling7_end_date"],
                    "predicted_rolling7_peak_quantity_kg": predicted_peak[
                        "rolling7_peak_quantity_kg"
                    ],
                    "model_artifact_sha256": model_hash[model_id][base_id],
                }
            )
        _secure_csv(output_dir / filename, total_fields, rows)

    daily_fields = [
        "model_id",
        "base_id",
        "canonical_base_name",
        "season",
        "date",
        "actual_quantity_kg",
        "actual_completeness_status",
        "predicted_daily_quantity_kg",
        "predicted_share",
        "model_artifact_sha256",
    ]
    all_daily_scored: list[dict[str, Any]] = []
    for model_id in (baseline_id, v07_id, v08_id):
        for base_id in sorted(daily_by_model_base[model_id]):
            actuals = {row["date"]: row for row in actual_daily[base_id]}
            for row in sorted(
                daily_by_model_base[model_id][base_id], key=lambda item: item["date"]
            ):
                actual_row = actuals[row["date"]]
                all_daily_scored.append(
                    {
                        "model_id": model_id,
                        "base_id": base_id,
                        "canonical_base_name": name_by_base[base_id],
                        "season": OOT_SEASON,
                        "date": row["date"],
                        "actual_quantity_kg": actual_row["actual_quantity_kg"],
                        "actual_completeness_status": actual_row.get(
                            "actual_completeness_status", ""
                        ),
                        "predicted_daily_quantity_kg": row["predicted_daily_quantity_kg"],
                        "predicted_share": row["predicted_share"],
                        "model_artifact_sha256": row["model_artifact_sha256"],
                    }
                )
    daily_filenames = {
        baseline_id: "baseline-oot-daily-predictions-r1.csv",
        v07_id: "v0-7-oot-daily-predictions-r1.csv",
        v08_id: "v0-8-oot-daily-predictions-r1.csv",
    }
    for model_id, filename in daily_filenames.items():
        _secure_csv(
            output_dir / filename,
            daily_fields,
            [row for row in all_daily_scored if row["model_id"] == model_id],
        )

    comparison_rows: list[dict[str, Any]] = []
    full_daily_by_model = daily_metrics["FULL_39_OOT"]
    common_daily_by_model = daily_metrics["COMMON_COMPARATOR_COHORT"]
    common_ids = set(model_total[v07_id])
    for base_id in sorted(actual_totals):
        comparison_row: dict[str, Any] = {
            "base_id": base_id,
            "canonical_base_name": name_by_base[base_id],
            "actual_total": decimal_text(actual_totals[base_id]),
        }
        for model_id, short in ((baseline_id, "baseline"), (v07_id, "v07"), (v08_id, "v08")):
            prediction = model_total[model_id].get(base_id)
            comparison_row[f"{short}_total"] = (
                decimal_text(prediction) if prediction is not None else "NOT_AVAILABLE"
            )
            comparison_row[f"{short}_abs_error"] = (
                decimal_text(abs(prediction - actual_totals[base_id]))
                if prediction is not None
                else "NOT_AVAILABLE"
            )
            daily_metric = (
                common_daily_by_model[model_id]["per_base_daily"].get(base_id)
                if model_id == v07_id or base_id in common_ids
                else full_daily_by_model[model_id]["per_base_daily"].get(base_id)
            )
            comparison_row[f"{short}_daily_wape"] = (
                daily_metric.get("wape", "NOT_AVAILABLE") if daily_metric else "NOT_AVAILABLE"
            )
            peak_detail = (
                common_daily_by_model[model_id]["per_base_peak_truth_and_predictions"].get(base_id)
                if model_id == v07_id or base_id in common_ids
                else full_daily_by_model[model_id]["per_base_peak_truth_and_predictions"].get(
                    base_id
                )
            )
            comparison_row[f"{short}_peak_date_error_days"] = (
                abs(
                    (
                        date.fromisoformat(peak_detail["predicted_peak_date"])
                        - date.fromisoformat(peak_detail["actual_peak_date"])
                    ).days
                )
                if peak_detail
                else "NOT_AVAILABLE"
            )
            comparison_row[f"{short}_peak_quantity_abs_error_kg"] = (
                decimal_text(
                    abs(
                        decimal_value(peak_detail["predicted_peak_quantity_kg"], "pred_peak")
                        - decimal_value(peak_detail["actual_peak_quantity_kg"], "actual_peak")
                    )
                )
                if peak_detail
                else "NOT_AVAILABLE"
            )
            comparison_row[f"{short}_rolling7_start_error_days"] = (
                abs(
                    (
                        date.fromisoformat(peak_detail["predicted_rolling7_start_date"])
                        - date.fromisoformat(peak_detail["actual_rolling7_start_date"])
                    ).days
                )
                if peak_detail
                else "NOT_AVAILABLE"
            )
            comparison_row[f"{short}_rolling7_quantity_abs_error_kg"] = (
                decimal_text(
                    abs(
                        decimal_value(peak_detail["predicted_rolling7_peak_quantity_kg"], "pred_r7")
                        - decimal_value(
                            peak_detail["actual_rolling7_peak_quantity_kg"], "actual_r7"
                        )
                    )
                )
                if peak_detail
                else "NOT_AVAILABLE"
            )
        comparison_row["common_comparator_member"] = base_id in common_ids
        comparison_rows.append(comparison_row)
    _secure_csv(
        output_dir / "model-comparison-by-base-r1.csv",
        [
            "base_id",
            "canonical_base_name",
            "actual_total",
            "baseline_total",
            "v07_total",
            "v08_total",
            "baseline_abs_error",
            "v07_abs_error",
            "v08_abs_error",
            "baseline_daily_wape",
            "v07_daily_wape",
            "v08_daily_wape",
            "baseline_peak_date_error_days",
            "v07_peak_date_error_days",
            "v08_peak_date_error_days",
            "baseline_peak_quantity_abs_error_kg",
            "v07_peak_quantity_abs_error_kg",
            "v08_peak_quantity_abs_error_kg",
            "baseline_rolling7_start_error_days",
            "v07_rolling7_start_error_days",
            "v08_rolling7_start_error_days",
            "baseline_rolling7_quantity_abs_error_kg",
            "v07_rolling7_quantity_abs_error_kg",
            "v08_rolling7_quantity_abs_error_kg",
            "common_comparator_member",
        ],
        comparison_rows,
    )

    oot_dataset_rows: list[dict[str, Any]] = []
    for base_id in sorted(actual_totals):
        oot_dataset_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": name_by_base[base_id],
                "season": OOT_SEASON,
                "area_mu": area_by_base[base_id],
                "actual_season_total_quantity_kg": decimal_text(actual_totals[base_id]),
                "actual_yield_kg_per_mu": decimal_text(
                    actual_totals[base_id] / decimal_value(area_by_base[base_id], "oot_area")
                ),
                "daily_curve_available": True,
                "actual_daily_curve_sha256": oot_meta[base_id]["daily_curve_sha256"],
                "actual_daily_row_count": oot_meta[base_id]["daily_row_count"],
                "actual_single_day_peak_date": oot_meta[base_id]["single_day_peak_date"],
                "actual_single_day_peak_quantity_kg": oot_meta[base_id][
                    "single_day_peak_quantity_kg"
                ],
                "actual_rolling7_start_date": oot_meta[base_id]["rolling7_start_date"],
                "actual_rolling7_end_date": oot_meta[base_id]["rolling7_end_date"],
                "actual_rolling7_peak_quantity_kg": oot_meta[base_id]["rolling7_peak_quantity_kg"],
                "quantity_authority_status": oot_meta[base_id]["quantity_authority_status"],
            }
        )
    _secure_csv(
        output_dir / "v0-8-canonical-oot-dataset-r1.csv",
        list(oot_dataset_rows[0].keys()),
        oot_dataset_rows,
    )


def _distribution_audit(
    training_rows: Sequence[Mapping[str, str]],
    oot_rows: Sequence[Mapping[str, Any]],
    model: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    train_areas = [decimal_value(row["area_mu"], "train_area") for row in training_rows]
    train_totals = [
        decimal_value(row["season_total_quantity_kg"], "train_total") for row in training_rows
    ]
    train_yields = [decimal_value(row["yield_kg_per_mu"], "train_yield") for row in training_rows]
    oot_areas = [decimal_value(row["area_mu"], "oot_area") for row in oot_rows]
    oot_totals = [
        decimal_value(row["actual_season_total_quantity_kg"], "oot_total") for row in oot_rows
    ]
    oot_yields = [decimal_value(row["actual_yield_kg_per_mu"], "oot_yield") for row in oot_rows]
    low, high = min(train_areas), max(train_areas)
    extrapolation: list[dict[str, Any]] = []
    for row in sorted(oot_rows, key=lambda item: str(item["base_id"])):
        area = decimal_value(row["area_mu"], "oot_area")
        category = (
            "LOW_EXTRAPOLATION"
            if area < low
            else "HIGH_EXTRAPOLATION"
            if area > high
            else "IN_RANGE"
        )
        extrapolation.append(
            {
                "base_id": row["base_id"],
                "canonical_base_name": row["canonical_base_name"],
                "target_area_mu": decimal_text(area),
                "training_area_min_mu": decimal_text(low),
                "training_area_max_mu": decimal_text(high),
                "area_extrapolation_status": category,
            }
        )
    audit = {
        "training": {
            "row_count": len(training_rows),
            "unique_base_count": len({row["base_id"] for row in training_rows}),
            "season_counts": {
                season: sum(row["season"] == season for row in training_rows)
                for season in TRAINING_SEASONS
            },
            "area_mu": numeric_distribution(train_areas),
            "season_total_kg": numeric_distribution(train_totals),
            "yield_kg_per_mu": numeric_distribution(train_yields),
        },
        "oot": {
            "base_season_count": len(oot_rows),
            "area_mu": numeric_distribution(oot_areas),
            "actual_season_total_kg": numeric_distribution(oot_totals),
            "actual_yield_kg_per_mu": numeric_distribution(oot_yields),
            "actual_labels_used_for_training_or_tuning": False,
        },
        "area_extrapolation": {
            "training_area_range_mu": [decimal_text(low), decimal_text(high)],
            "oot_outside_training_range_count": sum(
                row["area_extrapolation_status"] != "IN_RANGE" for row in extrapolation
            ),
            "oot_in_range_count": sum(
                row["area_extrapolation_status"] == "IN_RANGE" for row in extrapolation
            ),
            "oot_low_extrapolation_count": sum(
                row["area_extrapolation_status"] == "LOW_EXTRAPOLATION" for row in extrapolation
            ),
            "oot_high_extrapolation_count": sum(
                row["area_extrapolation_status"] == "HIGH_EXTRAPOLATION" for row in extrapolation
            ),
        },
        "yield_extrapolation": {
            "training_yield_range_kg_per_mu": [
                decimal_text(min(train_yields)),
                decimal_text(max(train_yields)),
            ],
            "oot_outside_training_yield_range_count": sum(
                value < min(train_yields) or value > max(train_yields) for value in oot_yields
            ),
            "diagnostic_only_no_oot_row_excluded": True,
        },
        "unseen_base_fallback_count": 39 - int(model["training_unique_base_count"]),
    }
    return audit, extrapolation


def run_full(*, artifact_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise S8BacktestError("PRIVATE_OUTPUT_DIRECTORY_ALREADY_EXISTS_NO_OVERWRITE")
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    config = _read_json(CONFIG_PATH)
    if config["baseline_main_sha"] != "5c66d8d8565eb87e1434e61de2939dcce4d7df75":
        raise S8BacktestError("BASELINE_MAIN_SHA_CONFIG_MISMATCH")
    _repo_pins(config)
    private_pins = verify_private_pins(artifact_root, config)
    v07_model, v07_registry, v07_config_hash, registry_hash = _load_model_and_registry(config)
    paths = _input_paths(artifact_root, config)
    area_rows = read_csv(paths["area"])
    if len(area_rows) != 117 or len({(row["base_id"], row["season"]) for row in area_rows}) != 117:
        raise S8BacktestError("S4_AREA_AUTHORITY_NOT_117_UNIQUE_ROWS")
    for season in ("2023-2024", "2024-2025", OOT_SEASON):
        seasonal = [row for row in area_rows if row["season"] == season]
        total_area = sum(
            (decimal_value(row["historical_actual_area_mu"], "area") for row in seasonal),
            Decimal(0),
        )
        if len(seasonal) != 39 or total_area != Decimal(41335):
            raise S8BacktestError(f"S4_AREA_AUTHORITY_SEASON_INTEGRITY_FAILURE:{season}")
    for area_row in area_rows:
        if (
            area_row["identity_authority_sha256"]
            != config["identity_authority"]["identity_authority_sha256"]
        ):
            raise S8BacktestError("S4_IDENTITY_AUTHORITY_HASH_MISMATCH")
    oot_area_rows, oot_preflight = _preflight_cohort(paths, config, area_rows)
    for row in oot_area_rows:
        base_id = row["base_id"]
        if base_id not in v07_registry or decimal_value(
            row["area_mu"], "oot_area"
        ) != decimal_value(v07_registry[base_id]["productive_area_mu"], "v07_area"):
            raise S8BacktestError("V07_REGISTRY_AND_S4_OOT_AREA_DIFF")
    _secure_csv(output_root / "oot-area-input-r1.csv", AREA_FIELDS, oot_area_rows)
    output_root.joinpath("model-artifact").mkdir(mode=0o700)
    output_root.joinpath("model-artifact").chmod(0o700)

    training = _materialize_training(
        paths=paths, config=config, output_root=output_root, area_rows=area_rows
    )
    write_private_bytes(output_root / "v0-8-model-config-r1.json", CONFIG_PATH.read_bytes())
    config_hash = sha256_file(CONFIG_PATH)
    replay_paths: list[Path] = []
    for index in (1, 2):
        replay_dir = output_root / "model-artifact" / f"training-replay-{index}"
        replay_dir.mkdir(mode=0o700)
        replay_dir.chmod(0o700)
        model_path = replay_dir / "v0-8-model-artifact-r1.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--phase",
            "fit",
            "--config",
            str(CONFIG_PATH),
            "--training-dataset",
            str(output_root / "v0-8-canonical-training-dataset-r1.csv"),
            "--training-daily",
            str(output_root / "training-daily-curves-r1.csv"),
            "--output",
            str(model_path),
        ]
        subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        replay_paths.append(model_path)
    model_hashes = [sha256_file(path) for path in replay_paths]
    models = [_read_json(path) for path in replay_paths]
    if model_hashes[0] != model_hashes[1] or models[0] != models[1]:
        raise S8BacktestError("BLOCKED_NON_DETERMINISTIC_MODEL_TRAINING")
    model = models[0]
    verify_model_artifact(model)

    prediction_dirs: list[Path] = []
    for index, model_path in enumerate(replay_paths, start=1):
        prediction_dir = output_root / f"prediction-replay-{index}"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--phase",
            "predict",
            "--config",
            str(CONFIG_PATH),
            "--model",
            str(model_path),
            "--oot-area",
            str(output_root / "oot-area-input-r1.csv"),
            "--output-dir",
            str(prediction_dir),
        ]
        subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        prediction_dirs.append(prediction_dir)
    pred_hashes = [
        (
            sha256_file(path / "season-predictions.csv"),
            sha256_file(path / "daily-predictions.csv"),
        )
        for path in prediction_dirs
    ]
    if pred_hashes[0] != pred_hashes[1]:
        raise S8BacktestError("BLOCKED_NON_DETERMINISTIC_PREDICTIONS")
    prediction_seal = {
        "oot_labels_read_before_seal": False,
        "training_model_artifact_sha256": model_hashes[0],
        "training_replay_model_artifact_sha256": model_hashes[1],
        "prediction_replay_hashes": [
            {
                "season_predictions_sha256": item[0],
                "daily_predictions_sha256": item[1],
            }
            for item in pred_hashes
        ],
        "season_prediction_rows": 108,
        "daily_prediction_rows": 28944,
        "oot_area_feature_rows": 39,
        "v07_prior_support_count": 30,
        "v08_and_baseline_support_count": 39,
        "seal_hash": "",
    }
    prediction_seal.pop("seal_hash")
    prediction_seal["seal_hash"] = sha256_bytes(canonical_json_bytes(prediction_seal))
    _write_json(output_root / "sealed-predictions-r1.json", prediction_seal)

    sealed_payload = dict(prediction_seal)
    sealed_hash = str(sealed_payload.pop("seal_hash"))
    if sha256_bytes(canonical_json_bytes(sealed_payload)) != sealed_hash:
        raise S8BacktestError("PREDICTION_SEAL_HASH_INVALID")
    daily_rows_per_replay = [
        len(read_csv(path / "daily-predictions.csv")) for path in prediction_dirs
    ]
    if any(count != prediction_seal["daily_prediction_rows"] for count in daily_rows_per_replay):
        raise S8BacktestError("PREDICTION_SEAL_DAILY_ROW_COUNT_MISMATCH")
    for prediction_dir, expected_hashes in zip(prediction_dirs, pred_hashes, strict=True):
        if (
            sha256_file(prediction_dir / "season-predictions.csv") != expected_hashes[0]
            or sha256_file(prediction_dir / "daily-predictions.csv") != expected_hashes[1]
        ):
            raise S8BacktestError("SEALED_PREDICTION_ARTIFACT_CHANGED")

    # No OOT quantity is parsed above this line. Scoring truth is now released.
    score_directories: list[Path] = []
    score_values: list[dict[str, Any]] = []
    for index, prediction_dir in enumerate(prediction_dirs, start=1):
        score_dir = output_root / f"scoring-replay-{index}"
        score_value = _score_once(prediction_dir=prediction_dir, paths=paths, output_dir=score_dir)
        score_directories.append(score_dir)
        score_values.append(score_value)
    score_hashes = [sha256_file(path / "score-summary-r1.json") for path in score_directories]
    if score_hashes[0] != score_hashes[1] or score_values[0] != score_values[1]:
        raise S8BacktestError("BLOCKED_NON_DETERMINISTIC_METRICS")

    final_score_dir = score_directories[0]
    final_names = [
        "v0-8-canonical-oot-dataset-r1.csv",
        "v0-8-oot-season-total-predictions-r1.csv",
        "v0-8-oot-daily-predictions-r1.csv",
        "baseline-oot-daily-predictions-r1.csv",
        "v0-7-oot-daily-predictions-r1.csv",
        "baseline-oot-predictions-r1.csv",
        "v0-7-oot-predictions-r1.csv",
        "model-comparison-by-base-r1.csv",
        "season-total-metrics-r1.json",
        "daily-curve-metrics-r1.json",
        "single-day-peak-metrics-r1.json",
        "rolling7-peak-metrics-r1.json",
        "metric-comparison-r1.json",
    ]
    for filename in final_names:
        source = final_score_dir / filename
        (output_root / filename).write_bytes(source.read_bytes())
        (output_root / filename).chmod(0o600)

    training_rows = read_csv(output_root / "v0-8-canonical-training-dataset-r1.csv")
    oot_rows = read_csv(output_root / "v0-8-canonical-oot-dataset-r1.csv")
    dist, extrapolation_rows = _distribution_audit(training_rows, oot_rows, model)
    _secure_csv(
        output_root / "area-extrapolation-audit-r1.csv",
        list(extrapolation_rows[0].keys()),
        extrapolation_rows,
    )
    _write_json(output_root / "train-oot-distribution-audit-r1.json", dist)
    _write_json(
        output_root / "oot-dataset-manifest-r1.json",
        {
            "row_count": len(oot_rows),
            "unique_base_season_count": len(oot_rows),
            "season": OOT_SEASON,
            "daily_curve_complete_base_count": len(oot_rows),
            "oot_dataset_sha256": sha256_file(output_root / "v0-8-canonical-oot-dataset-r1.csv"),
            "oot_labels_used_for_training_or_tuning": False,
            "prediction_seal_sha256": sha256_file(output_root / "sealed-predictions-r1.json"),
        },
    )

    score_summary = score_values[0]
    common_total = score_summary["season_total"]["COMMON_COMPARATOR_COHORT"]
    full_total = score_summary["season_total"]["FULL_39_OOT"]
    common_daily = score_summary["daily"]["COMMON_COMPARATOR_COHORT"]
    full_daily = score_summary["daily"]["FULL_39_OOT"]
    final_summary = {
        "task_id": config["task_id"],
        "result": "PASS_V0_8_TRAINING_AND_OOT_BACKTEST_COMPLETED",
        "base_main_sha": config["baseline_main_sha"],
        "head_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "branch": subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "pr_number": "NONE",
        "pr_state": "LOCAL_ONLY",
        "cohort": {
            "training_rows": 37,
            "training_unique_bases": 26,
            "training_season_counts": {"2023-2024": 15, "2024-2025": 22},
            "blocked_training_rows_included": 0,
            "oot_rows": 39,
            "oot_days_per_base": 268,
            "train_oot_overlap_count": 0,
            "oot_leakage_gate": "PASS",
            "common_comparator_count": 30,
        },
        "authority_hashes": {
            "s4_area_authority": private_pins["s4_area_authority"],
            "s4_business_confirmation": private_pins["s4_business_confirmation"],
            "s6_zero_confirmation": private_pins["s6_zero_confirmation"],
            "s6_daily_zero_overlay": private_pins["s6_daily_zero_overlay"],
            "s6_season_total_authority": private_pins["s6_season_total_authority"],
            "s6_strict_eligibility": private_pins["s6_strict_eligibility"],
            "s7_artifact_manifest": private_pins["s7_artifact_manifest"],
            "s7_training_eligibility": private_pins["s7_training_eligibility"],
            "s7_identity_overlay": private_pins["s7_identity_overlay"],
            "v07_model_config": v07_config_hash,
            "v07_model_artifact": config["v07_frozen_comparator"]["artifact_sha256"],
            "v07_registry": registry_hash,
        },
        "model": {
            "model_id": model["model_id"],
            "model_family": model["model_family"],
            "architecture": model["architecture"],
            "model_architecture_changed_vs_v07": True,
            "weather_used": False,
            "training_dataset_sha256": training["training_dataset_sha256"],
            "oot_dataset_sha256": sha256_file(output_root / "v0-8-canonical-oot-dataset-r1.csv"),
            "model_config_sha256": config_hash,
            "training_code_sha256": _training_code_hash(),
            "model_artifact_sha256": model_hashes[0],
            "model_replay_hash_match": model_hashes[0] == model_hashes[1],
            "prediction_replay_hash_match": pred_hashes[0] == pred_hashes[1],
            "metric_replay_hash_match": score_hashes[0] == score_hashes[1],
            "deterministic_training": True,
            "model_training_executed": True,
            "model_refit_executed": True,
            "independent_oot_backtest_executed": True,
        },
        "metrics": {
            "full_39_oot": {
                "season_total": {
                    model_id: {
                        key: metrics[key]
                        for key in (
                            "n",
                            "wape",
                            "mae",
                            "median_ape",
                            "bias_mean_predicted_minus_actual",
                        )
                    }
                    for model_id, metrics in full_total.items()
                },
                "daily": {
                    model_id: {
                        "wape": metrics["daily"]["wape"],
                        "mae": metrics["daily"]["mae"],
                        "n": metrics["daily"]["n"],
                    }
                    for model_id, metrics in full_daily.items()
                },
            },
            "common_comparator_30": {
                "season_total": {
                    model_id: {
                        key: metrics[key]
                        for key in (
                            "n",
                            "wape",
                            "mae",
                            "median_ape",
                            "bias_mean_predicted_minus_actual",
                        )
                    }
                    for model_id, metrics in common_total.items()
                },
                "daily": {
                    model_id: {
                        "wape": metrics["daily"]["wape"],
                        "mae": metrics["daily"]["mae"],
                        "n": metrics["daily"]["n"],
                    }
                    for model_id, metrics in common_daily.items()
                },
                "single_day_peak": {
                    model_id: {
                        "quantity_wape": metrics["single_day_peak"]["wape"],
                        "date_mae_days": metrics["single_day_peak"]["date_mae_days"],
                    }
                    for model_id, metrics in common_daily.items()
                },
                "rolling7_peak": {
                    model_id: {
                        "quantity_wape": metrics["rolling7_peak"]["wape"],
                        "start_date_mae_days": metrics["rolling7_peak"]["start_date_mae_days"],
                    }
                    for model_id, metrics in common_daily.items()
                },
            },
            "deltas_v08_minus_comparator": score_summary["comparisons"],
        },
        "distribution_audit": dist,
        "prediction_seal_sha256": sha256_file(output_root / "sealed-predictions-r1.json"),
        "score_summary_sha256": score_hashes[0],
        "oot_preflight": oot_preflight,
        "model_readiness_status": "BACKTEST_COMPLETED_NOT_PRODUCTION_READY",
        "model_production_ready": False,
        "business_acceptance_threshold": "NOT_DEFINED",
        "production_promotion_authorized": False,
        "weather_used": False,
        "future_production_plan_used": False,
        "v07_comparison_executed": True,
        "baseline_comparison_executed": True,
        "private_row_level_data_committed": False,
        "ready_action_taken": False,
        "merge_action_taken": False,
        "deployment_performed": False,
    }
    _write_json(output_root / "backtest-summary-r1.json", final_summary)

    all_files = sorted(
        path
        for path in output_root.rglob("*")
        if path.is_file() and path.name != "artifact-manifest.json"
    )
    manifest = {
        "task_id": config["task_id"],
        "artifact_policy": "PRIVATE_CONTROLLED_ROW_LEVEL_DATA;NO_PRIVATE_LABELS_IN_GIT",
        "file_mode": "0600",
        "directory_mode": "0700",
        "artifacts": {str(path.relative_to(output_root)): sha256_file(path) for path in all_files},
        "source_pins": private_pins,
        "model_config_sha256": config_hash,
        "training_code_sha256": _training_code_hash(),
        "training_dataset_sha256": training["training_dataset_sha256"],
        "oot_dataset_sha256": sha256_file(output_root / "v0-8-canonical-oot-dataset-r1.csv"),
        "model_artifact_sha256": model_hashes[0],
        "prediction_hashes": {
            "season": pred_hashes[0][0],
            "daily": pred_hashes[0][1],
        },
        "score_summary_sha256": score_hashes[0],
    }
    _write_json(output_root / "artifact-manifest.json", manifest)
    return {
        **final_summary,
        "private_artifact_manifest_sha256": sha256_file(output_root / "artifact-manifest.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("full", "fit", "predict"), default="full")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / "v0-8-s8-canonical-training-oot-backtest-r1",
    )
    parser.add_argument("--training-dataset", type=Path)
    parser.add_argument("--training-daily", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--oot-area", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if args.phase == "fit":
        if not all((args.training_dataset, args.training_daily, args.output)):
            parser.error("fit requires --training-dataset --training-daily --output")
        _fit_child(args)
        return
    if args.phase == "predict":
        if not all((args.model, args.oot_area, args.output_dir)):
            parser.error("predict requires --model --oot-area --output-dir")
        _prediction_child(args)
        return
    summary = run_full(artifact_root=args.artifact_root, output_root=args.output_root)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
