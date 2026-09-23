"""Run the controlled V0.8-S2 common-row comparison.

The runner verifies the S1 authority manifest before producing any output. It
seals all fold predictions using training-only inputs, writes those artifacts,
and only then re-reads the validation-season rows for scoring. Full row-level
outputs are written with private permissions to a caller-selected directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import (
    KNOWN_STATUSES,
    business_boundary,
    fit_total_model,
)
from backend.app.area_yield.v08_s2_model_comparison import (
    AREA_SEMANTICS_REFERENCE_ONLY,
    actual_total_metric,
    common_base_scope,
    daily_metrics,
    decimal_value,
    seal_daily_predictions,
    strict_historical_area_authorized,
    sum_known_mapped_subtotals,
)

BaselineBuilder = Callable[
    [Sequence[Mapping[str, Any]], Mapping[str, Mapping[str, Any]]], dict[int, float]
]
BaselinePredictor = Callable[[Mapping[int, float], str, date, Decimal], float]
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
_frozen_baseline_module = importlib.import_module(
    "scripts.run_v0_5_s3_known_support_no_weather_baseline_r1"
)
build_week_median_reference = cast(
    BaselineBuilder, _frozen_baseline_module.build_week_median_reference
)
reference_prediction = cast(BaselinePredictor, _frozen_baseline_module.reference_prediction)

TASK_ID = "V0_8_S2_CANONICAL_HISTORY_MODEL_RETRAIN_AND_OOT_COMPARISON_R1"
CONFIG_PATH = Path("configs/v0_8_s2_canonical_history_model_comparison_r1.json")
S1_EVIDENCE_PATH = Path(
    "docs/v0-8/evidence/s1-cross-season-identity-authority-application-and-canonical-dataset-rebuild-r1.json"
)
S1_CONFIG_PATH = Path("configs/v0_8_cross_season_identity_authority_r1.json")
EXPECTED_AUTHORITY_ID = "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
EXPECTED_S1_EVIDENCE_SHA256 = "fea7741e85b86d84f2d7beab9f89d458c4fe32e0cfd7fd141da2a8ca5dc70aa7"
EXPECTED_S1_CONFIG_SHA256 = "957a84ecdb6ab25da51230a14d90e8eb6bfb6eb299aeb73e312b9421d3a77824"
EXPECTED_S1_MANIFEST_SHA256 = "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"
EXPECTED_PRIVATE_FILES = {
    "canonical-base-daily-ledger-r1.csv": (
        "be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75"
    ),
    "canonical-base-season-quality-r1.csv": (
        "64a0a41afcde4ffe3c8713f62ca5cc03ee0f36599289bafd409e641df0a2f2fd"
    ),
    "cross-season-base-identity-authority-r1.csv": (
        "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b"
    ),
    "cross-season-subfarm-parent-authority-r1.csv": (
        "ca5e949301f981c92c3e9d95375e5f0bef58627854c2ff054527cc5a57308f49"
    ),
    "old-vs-new-identity-diff-r1.csv": (
        "c958d5d35146b7fc2ea16c2a34848974d62f8c38de6a44c2526c4c28d148a2f1"
    ),
    "unresolved-identity-ledger-r1.csv": (
        "d28efd9dceb0717c7303962666b3ec74fa98ed0715896df46a54ae1da9f7389d"
    ),
}
FOLDS = (
    {
        "fold_id": "FOLD_A",
        "declared_train_seasons": ("2023-2024",),
        "prior_season": "2023-2024",
        "oot_season": "2024-2025",
    },
    {
        "fold_id": "FOLD_B",
        "declared_train_seasons": ("2023-2024", "2024-2025"),
        "prior_season": "2024-2025",
        "oot_season": "2025-2026",
    },
)
PREDICTION_FIELDS = (
    "fold_id",
    "model_id",
    "base_id",
    "base_name",
    "season",
    "date",
    "predicted_quantity_kg",
    "predicted_season_total_kg",
    "prior_season",
    "prior_yield_kg_per_mu",
    "area_mu",
    "area_semantics",
    "area_type",
)
COMMON_FIELDS = (
    "fold_id",
    "base_id",
    "base_name",
    "season",
    "date",
    "forecast_model_scope",
    "reference_area_mu",
    "area_semantics",
    "actual_status",
    "actual_quantity_kg",
    "quantity_completeness_status",
    "source_sha256",
    "identity_authority_id",
    "identity_authority_sha256",
)
QUALIFICATION_FIELDS = (
    "base_id",
    "base_name",
    "season",
    "quantity_authority_status",
    "known_mapped_subtotal_kg",
    "quantity_coverage_status",
    "area_value_mu",
    "reference_area_mu",
    "area_semantics",
    "historical_actual_productive_area_mu",
    "historical_actual_productive_area_status",
    "historical_actual_area_authorized",
    "training_eligible",
    "backtest_eligible",
    "exploratory_training_eligible",
    "exclusion_reason",
)


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def verify_s1_authority(repo_root: Path, private_root: Path) -> dict[str, Any]:
    """Fail closed unless repository evidence and every S1 private file match."""

    config = _read_json(repo_root / CONFIG_PATH)
    evidence_path = repo_root / S1_EVIDENCE_PATH
    s1_config_path = repo_root / S1_CONFIG_PATH
    if file_sha256(evidence_path) != EXPECTED_S1_EVIDENCE_SHA256:
        raise ValueError("S1_EVIDENCE_HASH_MISMATCH")
    if file_sha256(s1_config_path) != EXPECTED_S1_CONFIG_SHA256:
        raise ValueError("S1_CONFIG_HASH_MISMATCH")
    evidence = _read_json(evidence_path)
    s1_config = _read_json(s1_config_path)
    if evidence.get("authority_id") != EXPECTED_AUTHORITY_ID:
        raise ValueError("S1_AUTHORITY_ID_MISMATCH")
    if (
        evidence.get("task_id")
        != "V0_8_S1_CROSS_SEASON_IDENTITY_AUTHORITY_APPLICATION_AND_CANONICAL_DATASET_REBUILD_R1"
    ):
        raise ValueError("S1_TASK_ID_MISMATCH")
    expected_totals = {
        "raw": Decimal("122983150.913"),
        "mapped": Decimal("109010615.352"),
        "unresolved": Decimal("10573929.816"),
        "excluded": Decimal("3398605.745"),
    }
    totals = evidence["all_season_totals_kg"]
    for key, expected in expected_totals.items():
        if Decimal(str(totals[key])) != expected:
            raise ValueError(f"S1_TOTAL_MISMATCH:{key}")
    if evidence["counts"]["unresolved_source_farm_labels"] != 44:
        raise ValueError("S1_UNRESOLVED_LABEL_COUNT_MISMATCH")
    if s1_config.get("authority_id") != EXPECTED_AUTHORITY_ID:
        raise ValueError("S1_CONFIG_AUTHORITY_ID_MISMATCH")
    if s1_config.get("all_season_totals_kg") != evidence.get("all_season_totals_kg"):
        raise ValueError("S1_CONFIG_EVIDENCE_TOTALS_DIVERGED")

    if private_root.stat().st_mode & 0o777 != 0o700:
        raise ValueError("PRIVATE_AUTHORITY_DIRECTORY_PERMISSION_MISMATCH")
    manifest_path = private_root / "artifact-manifest.json"
    if manifest_path.stat().st_mode & 0o777 != 0o600:
        raise ValueError("PRIVATE_AUTHORITY_MANIFEST_PERMISSION_MISMATCH")
    if file_sha256(manifest_path) != EXPECTED_S1_MANIFEST_SHA256:
        raise ValueError("S1_PRIVATE_MANIFEST_HASH_MISMATCH")
    manifest = _read_json(manifest_path)
    if manifest.get("authority_id") != EXPECTED_AUTHORITY_ID:
        raise ValueError("PRIVATE_MANIFEST_AUTHORITY_MISMATCH")
    if manifest.get("task_id") != evidence.get("task_id"):
        raise ValueError("PRIVATE_MANIFEST_TASK_MISMATCH")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict):
        raise ValueError("PRIVATE_MANIFEST_FILES_INVALID")
    verified: dict[str, str] = {}
    for filename, expected_hash in EXPECTED_PRIVATE_FILES.items():
        entry = manifest_files.get(filename)
        path = private_root / filename
        if not isinstance(entry, dict) or not path.is_file():
            raise ValueError(f"PRIVATE_AUTHORITY_FILE_MISSING:{filename}")
        if path.stat().st_mode & 0o777 != 0o600:
            raise ValueError(f"PRIVATE_AUTHORITY_FILE_PERMISSION_MISMATCH:{filename}")
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash or entry.get("sha256") != expected_hash:
            raise ValueError(f"PRIVATE_AUTHORITY_FILE_HASH_MISMATCH:{filename}")
        verified[filename] = actual_hash
    if (
        verified["cross-season-base-identity-authority-r1.csv"]
        != evidence["private_authority_sha256"]
    ):
        raise ValueError("PRIVATE_AUTHORITY_EVIDENCE_HASH_DIVERGED")
    if (
        verified["canonical-base-daily-ledger-r1.csv"]
        != evidence["private_canonical_daily_ledger_sha256"]
    ):
        raise ValueError("PRIVATE_DAILY_EVIDENCE_HASH_DIVERGED")
    if (
        verified["canonical-base-season-quality-r1.csv"]
        != evidence["private_quality_ledger_sha256"]
    ):
        raise ValueError("PRIVATE_QUALITY_EVIDENCE_HASH_DIVERGED")
    if file_sha256(manifest_path) != evidence["private_artifact_manifest_sha256"]:
        raise ValueError("PRIVATE_MANIFEST_EVIDENCE_HASH_DIVERGED")
    return {
        "config": config,
        "evidence": evidence,
        "manifest": manifest,
        "private_file_hashes": verified,
        "private_artifact_manifest_sha256": file_sha256(manifest_path),
        "s1_evidence_sha256": file_sha256(evidence_path),
        "s1_config_sha256": file_sha256(s1_config_path),
    }


def _read_season_csv(path: Path, included_seasons: set[str]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row.get("season") in included_seasons:
                selected.append(dict(row))
    return selected


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(fields), lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))
    path.chmod(0o600)


def _private_output_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    run_dir.chmod(0o700)
    return run_dir


def _registry(repo_root: Path, expected_hash: str) -> tuple[dict[str, dict[str, Any]], str]:
    path = repo_root / "configs/v0_5_base_reference_registry_v1.json"
    actual_hash = file_sha256(path)
    if actual_hash != expected_hash:
        raise ValueError("BASE_REGISTRY_HASH_MISMATCH")
    payload = _read_json(path)
    rows = payload.get("bases")
    if not isinstance(rows, list) or len(rows) != 39:
        raise ValueError("BASE_REGISTRY_COUNT_MISMATCH")
    by_id = {str(row["base_id"]): row for row in rows}
    if len(by_id) != 39:
        raise ValueError("BASE_REGISTRY_DUPLICATE_BASE_ID")
    return by_id, actual_hash


def _v07_model(
    repo_root: Path, config: Mapping[str, Any], expected_hash: str
) -> tuple[dict[str, Any], str]:
    path = repo_root / str(config["model"]["v07_model_config_path"])
    actual_hash = file_sha256(path)
    if actual_hash != expected_hash:
        raise ValueError("V07_MODEL_CONFIG_HASH_MISMATCH")
    model = _read_json(path)
    if (
        model.get("total_model_id") != "BASE_AWARE_BASELINE_R1"
        or model.get("temporal_model_id") != "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE"
        or model.get("history_policy")
        != "IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK"
        or model.get("weather_used") is not False
    ):
        raise ValueError("V07_FROZEN_MODEL_CONTRACT_MISMATCH")
    history = model.get("base_yield_history")
    if not isinstance(history, list):
        raise ValueError("V07_HISTORY_ARTIFACT_INVALID")
    return model, actual_hash


def _history_yields(model: Mapping[str, Any], season: str) -> dict[str, Decimal]:
    rows = model["base_yield_history"]
    result: dict[str, Decimal] = {}
    for row in rows:
        if row.get("season") != season:
            continue
        base_id = str(row["base_id"])
        if base_id in result:
            raise ValueError(f"V07_PRIOR_HISTORY_DUPLICATE:{season}:{base_id}")
        yield_value = decimal_value(row["yield_kg_per_mu"], field="v07_yield_kg_per_mu")
        if yield_value <= 0:
            raise ValueError("V07_NONPOSITIVE_FROZEN_YIELD")
        result[base_id] = yield_value
    return result


def _canonical_training_rows(
    daily_rows: Sequence[Mapping[str, Any]], registry_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in daily_rows:
        status = str(row["quantity_status"])
        if status not in KNOWN_STATUSES:
            continue
        base_id = str(row["base_id"])
        if base_id not in registry_by_id:
            raise ValueError("CANONICAL_TRAINING_BASE_NOT_IN_REGISTRY")
        quantity = decimal_value(row["mapped_observed_subtotal_kg"], field="training_quantity")
        if quantity < 0:
            raise ValueError("NEGATIVE_CANONICAL_TRAINING_QUANTITY")
        result.append(
            {
                "base_id": base_id,
                "season": str(row["season"]),
                "date": str(row["date"]),
                "label_known": True,
                "observed_harvest_kg": format(quantity, "f"),
            }
        )
    return result


def _candidate_model(
    *,
    prior_season: str,
    training_totals: Mapping[tuple[str, str], Decimal],
    registry_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[Any, dict[str, Decimal]]:
    samples = [
        {
            "base_id": base_id,
            "season": season,
            "quantity_kg": quantity,
            "reference_area_mu": registry_by_id[base_id]["productive_area_mu"],
            "area_status": "REFERENCE_AREA_ONLY_EXPLORATORY_NOT_HISTORICAL_ACTUAL",
            "quantity_semantics": "V08_CANONICAL_ACCEPTED_KNOWN_MAPPED_SUBTOTAL_UNKNOWN_EXCLUDED",
        }
        for (base_id, season), quantity in sorted(training_totals.items())
        if season == prior_season and quantity > 0 and base_id in registry_by_id
    ]
    model = fit_total_model(samples, prior_season=prior_season)
    return model, dict(model.base_yields_kg_per_mu)


def _baseline_rows(
    *,
    fold_id: str,
    season: str,
    prior_season: str,
    train_rows: Sequence[Mapping[str, Any]],
    base_scope: Sequence[str],
    registry_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    profile = build_week_median_reference(train_rows, registry_by_id)
    boundary = business_boundary(season)
    rows: list[dict[str, str]] = []
    totals: dict[str, Decimal] = defaultdict(Decimal)
    from backend.app.area_yield.formal_multi_season_validation import business_calendar

    for base_id in sorted(base_scope):
        base = registry_by_id[base_id]
        area = Decimal(str(base["productive_area_mu"]))
        for day in business_calendar(season, boundary):
            prediction = Decimal(str(reference_prediction(profile, season, day, area)))
            totals[base_id] += prediction
            rows.append(
                {
                    "fold_id": fold_id,
                    "model_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
                    "base_id": base_id,
                    "base_name": str(base["canonical_base_name"]),
                    "season": season,
                    "date": day.isoformat(),
                    "predicted_quantity_kg": str(prediction),
                    "predicted_season_total_kg": "",
                    "prior_season": prior_season,
                    "prior_yield_kg_per_mu": "",
                    "area_mu": format(area, "f"),
                    "area_semantics": AREA_SEMANTICS_REFERENCE_ONLY,
                    "area_type": "REFERENCE_AREA",
                }
            )
    total_text = {base_id: format(value, "f") for base_id, value in totals.items()}
    for row in rows:
        row["predicted_season_total_kg"] = total_text[row["base_id"]]
    rows.sort(key=lambda row: (row["fold_id"], row["season"], row["base_id"], row["date"]))
    return rows, {
        base_id: {"predicted_season_total_kg": value} for base_id, value in total_text.items()
    }


def _prediction_index(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str], dict[str, str]]:
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row["base_id"]), str(row["season"]), str(row["date"]))
        if key in result:
            raise ValueError("DUPLICATE_PREDICTION_ROW")
        result[key] = dict(row)
    return result


def _reveal_and_score(
    *,
    private_root: Path,
    all_predictions: Mapping[str, Sequence[Mapping[str, Any]]],
    fold_scopes: Mapping[str, Mapping[str, Any]],
    registry_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    oot_seasons = {str(fold["oot_season"]) for fold in FOLDS}
    # This is deliberately the first target-season quantity read: all prediction
    # files and their hashes have already been written and sealed by the caller.
    validation_daily = _read_season_csv(
        private_root / "canonical-base-daily-ledger-r1.csv", oot_seasons
    )
    validation_quality = _read_season_csv(
        private_root / "canonical-base-season-quality-r1.csv", oot_seasons
    )
    actual_by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in validation_daily:
        key = (str(row["base_id"]), str(row["season"]), str(row["date"]))
        if key in actual_by_key:
            raise ValueError("DUPLICATE_VALIDATION_ACTUAL_ROW")
        actual_by_key[key] = row
    quality_by_key = {(str(row["base_id"]), str(row["season"])): row for row in validation_quality}

    common_rows: list[dict[str, Any]] = []
    per_base_rows: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {"folds": {}, "combined": {}}
    metric_names = (
        "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "V0_7_PRODUCTION_MODEL",
        "V0_8_CANONICAL_HISTORY_CANDIDATE",
    )
    predictions_by_model = {
        model_id: _prediction_index(rows) for model_id, rows in all_predictions.items()
    }
    for fold in FOLDS:
        fold_id = str(fold["fold_id"])
        season = str(fold["oot_season"])
        scope = fold_scopes[fold_id]
        base_ids = list(scope["common_base_scope"])
        baseline_rows_for_fold: list[dict[str, Any]] = []
        v07_rows_for_fold: list[dict[str, Any]] = []
        v08_rows_for_fold: list[dict[str, Any]] = []
        for base_id in base_ids:
            quality = quality_by_key.get((base_id, season))
            if quality is None:
                raise ValueError("VALIDATION_QUALITY_AUTHORITY_MISSING")
            base = registry_by_id[base_id]
            target_keys = sorted(
                key for key in actual_by_key if key[0] == base_id and key[1] == season
            )
            boundary = business_boundary(season)
            expected_dates = [day.isoformat() for day in _business_days(season, boundary)]
            actual_dates = [key[2] for key in target_keys]
            if actual_dates != expected_dates:
                raise ValueError(f"VALIDATION_CALENDAR_AUTHORITY_MISMATCH:{fold_id}:{base_id}")
            for key in target_keys:
                actual = actual_by_key[key]
                joined = {
                    "fold_id": fold_id,
                    "base_id": base_id,
                    "base_name": str(base["canonical_base_name"]),
                    "season": season,
                    "date": key[2],
                    "forecast_model_scope": "COMMON_OOT_EVALUATION_SET",
                    "reference_area_mu": str(base["productive_area_mu"]),
                    "area_semantics": str(quality["area_semantics"]),
                    "actual_status": str(actual["quantity_status"]),
                    "actual_quantity_kg": str(actual["mapped_observed_subtotal_kg"] or ""),
                    "quantity_completeness_status": str(actual["quantity_completeness_status"]),
                    "source_sha256": str(actual["source_sha256"]),
                    "identity_authority_id": str(actual["identity_authority_id"]),
                    "identity_authority_sha256": str(actual["identity_authority_sha256"]),
                }
                common_rows.append(joined)
                for model_id, bucket in (
                    ("AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1", baseline_rows_for_fold),
                    ("V0_7_PRODUCTION_MODEL", v07_rows_for_fold),
                    ("V0_8_CANONICAL_HISTORY_CANDIDATE", v08_rows_for_fold),
                ):
                    prediction = predictions_by_model[model_id][key]
                    bucket.append(
                        {
                            **joined,
                            "predicted_quantity_kg": prediction["predicted_quantity_kg"],
                            "predicted_season_total_kg": prediction["predicted_season_total_kg"],
                            "model_id": model_id,
                        }
                    )
        quality_total_eligible = {
            (str(row["base_id"]), str(row["season"]))
            for row in validation_quality
            if row["season"] == season
            and row.get("business_total_coverage_status") == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
            and str(row.get("season_total_complete", "")).lower() == "true"
        }
        fold_metrics: dict[str, Any] = {"fold_id": fold_id, "oot_season": season}
        for model_id, rows in (
            ("AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1", baseline_rows_for_fold),
            ("V0_7_PRODUCTION_MODEL", v07_rows_for_fold),
            ("V0_8_CANONICAL_HISTORY_CANDIDATE", v08_rows_for_fold),
        ):
            dmetrics = daily_metrics(rows)
            eligible_total_rows = [
                (key, row)
                for key, row in quality_by_key.items()
                if key[1] == season and key in quality_total_eligible
            ]
            predicted_total_list: list[Decimal] = []
            actual_total_list: list[Decimal] = []
            pred_index = predictions_by_model[model_id]
            for (base_id, target_season), quality in eligible_total_rows:
                if base_id not in base_ids:
                    continue
                prediction_rows = [
                    pred_index[(base_id, target_season, day.isoformat())]
                    for day in _business_days(target_season, business_boundary(target_season))
                ]
                predicted_total_list.append(
                    Decimal(prediction_rows[0]["predicted_season_total_kg"])
                    if model_id != "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
                    else sum(
                        (Decimal(row["predicted_quantity_kg"]) for row in prediction_rows),
                        Decimal(0),
                    )
                )
                actual_total_list.append(
                    decimal_value(
                        quality["business_window_mapped_quantity_kg"], field="actual_total"
                    )
                )
            tmetrics = actual_total_metric(
                predicted_totals=predicted_total_list, actual_totals=actual_total_list
            )
            fold_metrics[model_id] = {
                "daily": dmetrics,
                "season_total": tmetrics,
                "season_total_noncomputable_base_count": max(
                    0, len(base_ids) - len(actual_total_list)
                ),
                "single_day_peak": {
                    "status": "NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY",
                    "eligible_base_season_count": sum(
                        1
                        for base_id in base_ids
                        if (quality := quality_by_key[(base_id, season)])
                        .get("single_day_peak_complete", "")
                        .lower()
                        == "true"
                    ),
                },
                "rolling_7day_peak": {
                    "status": "NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY",
                    "eligible_base_season_count": sum(
                        1
                        for base_id in base_ids
                        if (quality := quality_by_key[(base_id, season)])
                        .get("rolling_7day_complete", "")
                        .lower()
                        == "true"
                    ),
                },
            }
        aggregate["folds"][fold_id] = fold_metrics

        for base_id in base_ids:
            quality = quality_by_key[(base_id, season)]
            total_authorized = (
                quality.get("business_total_coverage_status") == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                and str(quality.get("season_total_complete", "")).lower() == "true"
            )
            base_metric_row: dict[str, Any] = {
                "fold_id": fold_id,
                "base_id": base_id,
                "base_name": str(registry_by_id[base_id]["canonical_base_name"]),
                "season": season,
                "actual_total_kg": str(quality["business_window_mapped_quantity_kg"]),
                "actual_total_status": str(quality["business_total_coverage_status"]),
                "actual_peak_status": str(quality["single_day_peak_coverage_status"]),
                "actual_rolling7_status": str(quality["rolling_7day_coverage_status"]),
                "known_day_count": str(quality["known_mapped_subtotal_day_count"]),
                "confirmed_zero_day_count": str(quality["confirmed_zero_day_count"]),
                "unknown_day_count": str(quality["unknown_day_count"]),
            }
            for model_id in metric_names:
                selected_rows = [
                    item
                    for item in (
                        baseline_rows_for_fold
                        if model_id == metric_names[0]
                        else v07_rows_for_fold
                        if model_id == metric_names[1]
                        else v08_rows_for_fold
                    )
                    if item["base_id"] == base_id
                ]
                base_metric_row[f"{model_id}_daily"] = daily_metrics(selected_rows)
                predictions_for_base = [
                    predictions_by_model[model_id][(base_id, season, day.isoformat())]
                    for day in _business_days(season, business_boundary(season))
                ]
                predicted_base_total = (
                    Decimal(predictions_for_base[0]["predicted_season_total_kg"])
                    if model_id != "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
                    else sum(
                        (Decimal(item["predicted_quantity_kg"]) for item in predictions_for_base),
                        Decimal(0),
                    )
                )
                base_metric_row[f"{model_id}_predicted_total_kg"] = format(
                    predicted_base_total, "f"
                )
                if total_authorized:
                    predicted_total = Decimal(base_metric_row[f"{model_id}_predicted_total_kg"])
                    actual_total = decimal_value(
                        quality["business_window_mapped_quantity_kg"],
                        field="actual_total",
                    )
                    error = predicted_total - actual_total
                    base_metric_row[f"{model_id}_season_total_absolute_error_kg"] = format(
                        abs(error), "f"
                    )
                    base_metric_row[f"{model_id}_season_total_absolute_percentage_error"] = (
                        format(abs(error) / actual_total, "f")
                        if actual_total > 0
                        else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
                    )
                else:
                    base_metric_row[f"{model_id}_season_total_absolute_error_kg"] = (
                        "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"
                    )
                    base_metric_row[f"{model_id}_season_total_absolute_percentage_error"] = (
                        "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"
                    )
            per_base_rows.append(base_metric_row)

    for model_id in metric_names:
        combined_rows = []
        for fold in FOLDS:
            fold_id = str(fold["fold_id"])
            season = str(fold["oot_season"])
            base_id_set = set(fold_scopes[fold_id]["common_base_scope"])
            model_predictions = predictions_by_model[model_id]
            for (base_id, target_season, target_date), actual in actual_by_key.items():
                if target_season != season or base_id not in base_id_set:
                    continue
                combined_rows.append(
                    {
                        "actual_status": actual["quantity_status"],
                        "actual_quantity_kg": actual["mapped_observed_subtotal_kg"],
                        "predicted_quantity_kg": model_predictions[
                            (base_id, target_season, target_date)
                        ]["predicted_quantity_kg"],
                    }
                )
        combined_predicted_totals: list[Decimal] = []
        combined_actual_totals: list[Decimal] = []
        for fold in FOLDS:
            fold_id = str(fold["fold_id"])
            season = str(fold["oot_season"])
            for base_id in fold_scopes[fold_id]["common_base_scope"]:
                quality = quality_by_key[(str(base_id), season)]
                if (
                    quality.get("business_total_coverage_status")
                    != "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                    or str(quality.get("season_total_complete", "")).lower() != "true"
                ):
                    continue
                prediction_rows = [
                    predictions_by_model[model_id][(str(base_id), season, day.isoformat())]
                    for day in _business_days(season, business_boundary(season))
                ]
                predicted_total = (
                    Decimal(prediction_rows[0]["predicted_season_total_kg"])
                    if model_id != "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
                    else sum(
                        (Decimal(row["predicted_quantity_kg"]) for row in prediction_rows),
                        Decimal(0),
                    )
                )
                combined_predicted_totals.append(predicted_total)
                combined_actual_totals.append(
                    decimal_value(
                        quality["business_window_mapped_quantity_kg"],
                        field="actual_total",
                    )
                )
        aggregate["combined"][model_id] = {
            "daily": daily_metrics(combined_rows),
            "season_total": actual_total_metric(
                predicted_totals=combined_predicted_totals,
                actual_totals=combined_actual_totals,
            ),
            "single_day_peak": {
                "status": "NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY",
                "eligible_base_season_count": 0,
            },
            "rolling_7day_peak": {
                "status": "NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY",
                "eligible_base_season_count": 0,
            },
        }
    aggregate["coverage"] = {
        "common_oot_base_season_count": sum(
            len(scope["common_base_scope"]) for scope in fold_scopes.values()
        ),
        "common_oot_daily_row_count": len(common_rows),
        "known_daily_row_count": sum(
            1 for row in common_rows if row["actual_status"] in KNOWN_STATUSES
        ),
        "unknown_daily_row_count": sum(
            1 for row in common_rows if row["actual_status"] == "UNKNOWN"
        ),
        "common_oot_dataset_sha256": digest(common_rows),
    }
    return common_rows, per_base_rows, aggregate


def _business_days(season: str, boundary: Any) -> list[date]:
    from backend.app.area_yield.formal_multi_season_validation import business_calendar

    return business_calendar(season, boundary)


def _area_qualification_rows(
    *,
    private_root: Path,
    registry_by_id: Mapping[str, Mapping[str, Any]],
    daily_totals: Mapping[tuple[str, str], Decimal],
) -> list[dict[str, str]]:
    # This is called only after sealed OOT prediction files have been written.
    all_seasons = {"2023-2024", "2024-2025", "2025-2026"}
    quality_rows = _read_season_csv(
        private_root / "canonical-base-season-quality-r1.csv", all_seasons
    )
    result: list[dict[str, str]] = []
    for row in quality_rows:
        base_id = str(row["base_id"])
        season = str(row["season"])
        registry = registry_by_id[base_id]
        area_ok = strict_historical_area_authorized(row)
        actual_area = str(row.get("historical_actual_productive_area_mu", ""))
        known_total = daily_totals.get((base_id, season), Decimal(0))
        positive_history = known_total > 0
        strict_train = area_ok and positive_history
        strict_backtest = (
            area_ok
            and row.get("business_total_coverage_status") == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
            and str(row.get("season_total_complete", "")).lower() == "true"
        )
        reasons: list[str] = []
        if not area_ok:
            reasons.append("AREA_NOT_HISTORICAL_ACTUAL_AUTHORITY")
        if not positive_history:
            reasons.append("NO_POSITIVE_CANONICAL_KNOWN_MAPPED_SUBTOTAL")
        if not strict_backtest:
            reasons.append("NO_STRICT_COMPLETE_TOTAL_BACKTEST_AUTHORITY")
        chosen_area = actual_area if area_ok else str(registry["productive_area_mu"])
        area_semantics = (
            "HISTORICAL_ACTUAL_PRODUCTIVE_AREA"
            if area_ok
            else str(row.get("area_semantics", AREA_SEMANTICS_REFERENCE_ONLY))
        )
        result.append(
            {
                "base_id": base_id,
                "base_name": str(row["canonical_base_name"]),
                "season": season,
                "quantity_authority_status": str(row["quantity_coverage_status"]),
                "known_mapped_subtotal_kg": format(known_total, "f"),
                "quantity_coverage_status": str(row["quantity_coverage_status"]),
                "area_value_mu": chosen_area,
                "reference_area_mu": str(registry["productive_area_mu"]),
                "area_semantics": area_semantics,
                "historical_actual_productive_area_mu": actual_area,
                "historical_actual_productive_area_status": str(
                    row["historical_actual_productive_area_status"]
                ),
                "historical_actual_area_authorized": str(area_ok).lower(),
                "training_eligible": str(strict_train).lower(),
                "backtest_eligible": str(strict_backtest).lower(),
                "exploratory_training_eligible": str(positive_history).lower(),
                "exclusion_reason": ";".join(reasons),
            }
        )
    result.sort(key=lambda item: (item["season"], item["base_id"]))
    return result


def _metric_rows(aggregate: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    scope_values: list[tuple[str, Mapping[str, Any]]] = []
    for fold_id, fold_payload in aggregate["folds"].items():
        scope_values.append((fold_id, fold_payload))
    scope_values.append(("COMBINED_OOT", aggregate["combined"]))
    for scope_name, payload in scope_values:
        metrics_by_model = {
            model_id: metrics
            for model_id, metrics in payload.items()
            if model_id
            in {
                "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
                "V0_7_PRODUCTION_MODEL",
                "V0_8_CANONICAL_HISTORY_CANDIDATE",
            }
        }
        for metric_name, metric_path, metric_key in (
            ("DAILY_WAPE", "daily", "daily_wape"),
            ("DAILY_MAE_KG", "daily", "daily_mae_kg"),
            ("SEASON_TOTAL_WAPE", "season_total", "season_total_wape"),
            ("SEASON_TOTAL_MAE_KG", "season_total", "season_total_mae_kg"),
        ):
            v07_value = (
                metrics_by_model["V0_7_PRODUCTION_MODEL"].get(metric_path, {}).get(metric_key)
            )
            v08_value = (
                metrics_by_model["V0_8_CANONICAL_HISTORY_CANDIDATE"]
                .get(metric_path, {})
                .get(metric_key)
            )
            baseline_value = (
                metrics_by_model["AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"]
                .get(metric_path, {})
                .get(metric_key)
            )
            change = "NOT_COMPUTABLE"
            relative = "NOT_COMPUTABLE"
            if isinstance(v07_value, str) and isinstance(v08_value, str):
                try:
                    old = Decimal(v07_value)
                    new = Decimal(v08_value)
                except Exception:  # frozen metric status strings are not numeric values
                    pass
                else:
                    change = format(new - old, "f")
                    relative = (
                        format((new - old) / old, "f") if old != 0 else "NOT_COMPUTABLE_ZERO_V07"
                    )
            rows.append(
                {
                    "scope": scope_name,
                    "metric": metric_name,
                    "baseline": str(baseline_value or "NOT_COMPUTABLE"),
                    "v0_7": str(v07_value or "NOT_COMPUTABLE"),
                    "v0_8": str(v08_value or "NOT_COMPUTABLE"),
                    "absolute_change_v08_minus_v07": change,
                    "relative_change_v08_vs_v07": relative,
                    "sample_count": str(
                        metrics_by_model["V0_8_CANONICAL_HISTORY_CANDIDATE"]
                        .get(metric_path, {})
                        .get(
                            "scored_row_count",
                            metrics_by_model["V0_8_CANONICAL_HISTORY_CANDIDATE"]
                            .get(metric_path, {})
                            .get("base_season_count", 0),
                        )
                    ),
                }
            )
    return rows


def run(*, repo_root: Path, private_root: Path, output_root: Path) -> dict[str, Any]:
    resolved_private = private_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_output == resolved_private or resolved_output.is_relative_to(resolved_private):
        raise ValueError("OUTPUT_ROOT_MUST_NOT_OVERWRITE_OR_NEST_IN_S1_AUTHORITY")
    verified = verify_s1_authority(repo_root, private_root)
    config = verified["config"]
    registry_by_id, registry_hash = _registry(
        repo_root, str(config["model"]["base_registry_sha256"])
    )
    frozen_model, v07_config_hash = _v07_model(
        repo_root, config, str(config["model"]["v07_model_config_sha256"])
    )
    if (
        frozen_model["research_artifacts"]["temporal_model_artifact_sha256"]
        != config["model"]["temporal_artifact_sha256"]
    ):
        raise ValueError("TEMPORAL_ARTIFACT_HASH_MISMATCH")
    run_dir = _private_output_dir(output_root)
    (run_dir / "model-artifact").mkdir(mode=0o700)
    (run_dir / "model-artifact").chmod(0o700)

    # Strict eligibility uses only actual-area authority. The frozen S1 quality
    # evidence states there are no such training-season rows, so only the
    # separately labelled exploratory reference-area lane can proceed.
    folds_scope: dict[str, dict[str, Any]] = {}
    all_predictions: dict[str, list[dict[str, str]]] = {
        "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1": [],
        "V0_7_PRODUCTION_MODEL": [],
        "V0_8_CANONICAL_HISTORY_CANDIDATE": [],
    }
    fit_artifacts: dict[str, dict[str, Any]] = {}

    for fold in FOLDS:
        fold_id = str(fold["fold_id"])
        train_seasons = set(fold["declared_train_seasons"])
        prior_season = str(fold["prior_season"])
        oot_season = str(fold["oot_season"])
        # Only past-season ledger rows are materialized for training and fitting.
        train_daily = _read_season_csv(
            private_root / "canonical-base-daily-ledger-r1.csv", train_seasons
        )
        prior_aggregate = sum_known_mapped_subtotals(train_daily, included_seasons={prior_season})
        prior_v08_totals = {
            base_id: quantity
            for (base_id, season), quantity in prior_aggregate.items()
            if season == prior_season and quantity > 0
        }
        candidate_model, candidate_yields = _candidate_model(
            prior_season=prior_season,
            training_totals={
                (base_id, prior_season): total for base_id, total in prior_v08_totals.items()
            },
            registry_by_id=registry_by_id,
        )
        v07_yields = _history_yields(frozen_model, prior_season)
        common_bases = common_base_scope(
            v07_yield_by_base=v07_yields,
            canonical_history_by_base=candidate_yields,
            registry_base_ids=set(registry_by_id),
        )
        if not common_bases:
            raise ValueError(f"EMPTY_COMMON_OOT_SCOPE:{fold_id}")
        train_rows = _canonical_training_rows(train_daily, registry_by_id)
        boundary = business_boundary(oot_season)
        v07_rows, _, v07_prediction_hash = seal_daily_predictions(
            fold_id=fold_id,
            model_id="V0_7_PRODUCTION_MODEL",
            season=oot_season,
            prior_season=prior_season,
            base_scope=common_bases,
            yield_by_base=v07_yields,
            registry_by_id=registry_by_id,
            temporal_model=frozen_model["temporal_model"],
            boundary=boundary,
        )
        v08_rows, _, v08_prediction_hash = seal_daily_predictions(
            fold_id=fold_id,
            model_id="V0_8_CANONICAL_HISTORY_CANDIDATE",
            season=oot_season,
            prior_season=prior_season,
            base_scope=common_bases,
            yield_by_base=candidate_yields,
            registry_by_id=registry_by_id,
            temporal_model=frozen_model["temporal_model"],
            boundary=boundary,
        )
        baseline_rows, baseline_totals = _baseline_rows(
            fold_id=fold_id,
            season=oot_season,
            prior_season=prior_season,
            train_rows=train_rows,
            base_scope=common_bases,
            registry_by_id=registry_by_id,
        )
        all_predictions["V0_7_PRODUCTION_MODEL"].extend(v07_rows)
        all_predictions["V0_8_CANONICAL_HISTORY_CANDIDATE"].extend(v08_rows)
        all_predictions["AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"].extend(baseline_rows)
        model_artifact = {
            "model_id": "V0_8_CANONICAL_HISTORY_CANDIDATE",
            "total_model_id": "BASE_AWARE_BASELINE_R1",
            "temporal_model_id": "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "fold_id": fold_id,
            "declared_train_seasons": list(fold["declared_train_seasons"]),
            "immediate_prior_season": prior_season,
            "training_total_model_artifact": candidate_model.payload(),
            "training_total_model_hash": candidate_model.artifact_hash,
            "temporal_artifact_sha256": config["model"]["temporal_artifact_sha256"],
            "area_semantics": "REFERENCE_AREA_ONLY_EXPLORATORY_NOT_PRODUCTION_ELIGIBLE",
            "authority_id": EXPECTED_AUTHORITY_ID,
            "private_authority_sha256": verified["private_file_hashes"][
                "cross-season-base-identity-authority-r1.csv"
            ],
            "private_daily_ledger_sha256": verified["private_file_hashes"][
                "canonical-base-daily-ledger-r1.csv"
            ],
            "strict_area_model_training_feasible": False,
            "production_eligible": False,
        }
        model_artifact["artifact_hash"] = digest(model_artifact)
        fit_artifacts[fold_id] = {
            "candidate_model": candidate_model,
            "candidate_yields": candidate_yields,
            "v07_yields": v07_yields,
            "common_base_scope": common_bases,
            "train_seasons": list(fold["declared_train_seasons"]),
            "prior_season": prior_season,
            "oot_season": oot_season,
            "prediction_hashes": {
                "v07": v07_prediction_hash,
                "v08": v08_prediction_hash,
                "baseline": digest(baseline_rows),
            },
            "candidate_artifact_hash": model_artifact["artifact_hash"],
            "baseline_profile": {
                "baseline_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
                "bin_width_days": 7,
                "aggregation": "PER_BASE_MEAN_KG_PER_MU_THEN_BASE_EQUAL_MEDIAN",
                "tie_break": "NEAREST_BIN_THEN_EARLIER_BIN",
                "profile": {
                    str(key): format(Decimal(str(value)), "f")
                    for key, value in sorted(
                        build_week_median_reference(train_rows, registry_by_id).items()
                    )
                },
                "predicted_totals": baseline_totals,
            },
            "training_row_hash": digest(train_rows),
            "candidate_training_hash": candidate_model.training_sample_hash,
            "target_boundary": boundary.payload(),
        }
        folds_scope[fold_id] = {
            "common_base_scope": common_bases,
            "v07_prior_base_count": len(v07_yields),
            "v08_canonical_prior_base_count": len(candidate_yields),
            "common_base_count": len(common_bases),
            "train_row_count": len(train_rows),
            "train_seasons": list(fold["declared_train_seasons"]),
            "prior_season": prior_season,
            "oot_season": oot_season,
            "prediction_hashes": fit_artifacts[fold_id]["prediction_hashes"],
            "candidate_training_hash": candidate_model.training_sample_hash,
            "candidate_artifact_hash": model_artifact["artifact_hash"],
        }
        _write_json(
            run_dir / "model-artifact" / f"{fold_id.lower()}-v0-8-candidate.json", model_artifact
        )

    # Seal artifacts before any validation quantity is loaded.
    pred_files = {
        "baseline-predictions.csv": all_predictions["AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"],
        "v0-7-replay-predictions.csv": all_predictions["V0_7_PRODUCTION_MODEL"],
        "v0-8-candidate-predictions.csv": all_predictions["V0_8_CANONICAL_HISTORY_CANDIDATE"],
    }
    for filename, rows in pred_files.items():
        _write_csv(run_dir / filename, rows, PREDICTION_FIELDS)
    sealed_prediction_hashes = {
        model_id: digest(rows) for model_id, rows in all_predictions.items()
    }
    sealed_prediction_file_hashes = {
        filename: file_sha256(run_dir / filename) for filename in pred_files
    }
    if any(not digest_value for digest_value in sealed_prediction_hashes.values()):
        raise ValueError("PREDICTION_SEAL_HASH_MISSING")

    common_rows, per_base_rows, aggregate = _reveal_and_score(
        private_root=private_root,
        all_predictions=all_predictions,
        fold_scopes=folds_scope,
        registry_by_id=registry_by_id,
    )
    daily_totals = sum_known_mapped_subtotals(
        _read_season_csv(
            private_root / "canonical-base-daily-ledger-r1.csv",
            {"2023-2024", "2024-2025", "2025-2026"},
        ),
        included_seasons={"2023-2024", "2024-2025", "2025-2026"},
    )
    qualification_rows = _area_qualification_rows(
        private_root=private_root,
        registry_by_id=registry_by_id,
        daily_totals=daily_totals,
    )
    _write_csv(
        run_dir / "training-sample-qualification.csv", qualification_rows, QUALIFICATION_FIELDS
    )
    _write_csv(run_dir / "common-oot-evaluation-set.csv", common_rows, COMMON_FIELDS)
    _write_csv(
        run_dir / "base-season-metric-comparison.csv",
        per_base_rows,
        tuple(sorted({key for row in per_base_rows for key in row})),
    )
    metric_rows = _metric_rows(aggregate)
    _write_csv(
        run_dir / "metric-comparison.csv",
        metric_rows,
        (
            "scope",
            "metric",
            "baseline",
            "v0_7",
            "v0_8",
            "absolute_change_v08_minus_v07",
            "relative_change_v08_vs_v07",
            "sample_count",
        ),
    )

    training_seasons = {str(season) for fold in FOLDS for season in fold["declared_train_seasons"]}
    oot_seasons = {str(fold["oot_season"]) for fold in FOLDS}
    strict_train_rows = [
        row
        for row in qualification_rows
        if row["training_eligible"] == "true" and row["season"] in training_seasons
    ]
    strict_oot_rows = [
        row
        for row in qualification_rows
        if row["backtest_eligible"] == "true" and row["season"] in oot_seasons
    ]
    # Validation actuals have now been revealed, but they have not influenced
    # any model, common prediction scope, or sealed prediction byte.
    comparison_payload: dict[str, Any] = {
        "task_id": TASK_ID,
        "authority_id": EXPECTED_AUTHORITY_ID,
        "authority_hashes": {
            "s1_evidence_sha256": verified["s1_evidence_sha256"],
            "s1_config_sha256": verified["s1_config_sha256"],
            "private_artifact_manifest_sha256": verified["private_artifact_manifest_sha256"],
            "private_file_sha256": verified["private_file_hashes"],
            "base_registry_sha256": registry_hash,
            "v07_model_config_sha256": v07_config_hash,
        },
        "strict_area_lane": {
            "required_status": "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND",
            "training_feasible": False,
            "strict_training_base_season_count": len(strict_train_rows),
            "strict_oot_base_season_count": len(strict_oot_rows),
            "reason": "NO_HISTORICAL_ACTUAL_PRODUCTIVE_AREA_AUTHORITY_IN_TRAINING_SEASONS",
        },
        "exploratory_lane": {
            "executed": True,
            "lane": "EXPLORATORY_REFERENCE_AREA",
            "production_eligible": False,
            "training_data_authority_changed": True,
            "model_architecture_changed": False,
            "weather_used": False,
        },
        "models": {
            "baseline": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
            "v07": "BASE_AWARE_BASELINE_R1+AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "v08": (
                "BASE_AWARE_BASELINE_R1+AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE;CANONICAL_S1_HISTORY"
            ),
            "v07_model_artifact_sha256": v07_config_hash,
            "v08_fold_artifact_sha256": {
                fold_id: values["candidate_artifact_hash"]
                for fold_id, values in folds_scope.items()
            },
        },
        "folds": folds_scope,
        "predictions": {
            "sealed_before_validation_actual_load": True,
            "validation_label_leakage": False,
            "prediction_hashes": sealed_prediction_hashes,
            "prediction_file_sha256": sealed_prediction_file_hashes,
            "common_oot_base_season_count": aggregate["coverage"]["common_oot_base_season_count"],
            "common_oot_daily_row_count": aggregate["coverage"]["common_oot_daily_row_count"],
            "common_oot_known_daily_row_count": aggregate["coverage"]["known_daily_row_count"],
            "common_oot_unknown_daily_row_count": aggregate["coverage"]["unknown_daily_row_count"],
            "common_oot_dataset_sha256": aggregate["coverage"]["common_oot_dataset_sha256"],
        },
        "metrics": aggregate,
        "metric_comparison": metric_rows,
        "peak_metric_policy": {
            "single_day_peak": "NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY",
            "rolling_7day_peak": "NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY",
            "unknown_actual_is_zero": False,
        },
        "result": "INSUFFICIENT_STRICT_AUTHORITY_FOR_COMPARISON",
        "production_promotion_authorized": False,
        "v07_artifacts_modified": False,
    }
    output_files = {
        path.relative_to(run_dir).as_posix(): file_sha256(path)
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }
    row_counts = {
        "training-sample-qualification.csv": len(qualification_rows),
        "common-oot-evaluation-set.csv": len(common_rows),
        "baseline-predictions.csv": len(pred_files["baseline-predictions.csv"]),
        "v0-7-replay-predictions.csv": len(pred_files["v0-7-replay-predictions.csv"]),
        "v0-8-candidate-predictions.csv": len(pred_files["v0-8-candidate-predictions.csv"]),
        "metric-comparison.csv": len(metric_rows),
        "base-season-metric-comparison.csv": len(per_base_rows),
    }
    private_manifest = {
        "task_id": TASK_ID,
        "artifact_version": "V0_8_S2_MODEL_COMPARISON_PRIVATE_ARTIFACTS_V1",
        "policy": "PRIVATE_ROW_LEVEL_MODEL_PREDICTIONS_AND_OOT_LABELS",
        "input_authority_hashes": comparison_payload["authority_hashes"],
        "output_files_sha256": output_files,
        "row_counts": row_counts,
        "prediction_hashes": sealed_prediction_hashes,
        "common_oot_dataset_sha256": comparison_payload["predictions"]["common_oot_dataset_sha256"],
        "candidate_model_artifact_hashes": comparison_payload["models"]["v08_fold_artifact_sha256"],
        "result": comparison_payload["result"],
    }
    manifest_bytes = _json_bytes(private_manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    (run_dir / "artifact-manifest.json").write_bytes(manifest_bytes)
    (run_dir / "artifact-manifest.json").chmod(0o600)
    summary = {
        **comparison_payload,
        "private_artifact_manifest_sha256": manifest_sha,
        "private_artifact_run_id": run_dir.name,
        "strict_area_training_eligible_count": len(strict_train_rows),
        "strict_oot_eligible_count": len(strict_oot_rows),
        "qualification_status_counts": dict(
            Counter(row["historical_actual_productive_area_status"] for row in qualification_rows)
        ),
        "private_artifact_row_counts": row_counts,
        "strict_area_model_training_feasible": False,
        "business_answers_strict_lane": {
            "season_total_improved": "INSUFFICIENT_EVIDENCE",
            "daily_curve_improved": "INSUFFICIENT_EVIDENCE",
            "single_day_peak_improved": "INSUFFICIENT_EVIDENCE",
            "rolling_7day_peak_improved": "INSUFFICIENT_EVIDENCE",
        },
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-artifact-dir",
        type=Path,
        required=True,
        help="Existing V0.8-S1 private artifact directory; read-only input.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Private output root; a new unique run directory is created.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(
        repo_root=args.repo_root.resolve(),
        private_root=args.private_artifact_dir.resolve(),
        output_root=args.output_root.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
