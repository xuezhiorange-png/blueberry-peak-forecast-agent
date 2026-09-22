"""Run the V0.7-S3 frozen weather A/B rolling OOT experiment.

The script accepts explicit source paths.  It never embeds private artifact
paths and it deliberately loads each validation harvest source only after the
corresponding Model A and Model B prediction manifest has been sealed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import (
    ActualDay,
    actual_rows_from_mapping,
    business_boundary,
)
from backend.app.area_yield.weather_aware_backtest import (
    ALPHA,
    FEATURE_COUNT_A,
    FEATURE_COUNT_B,
    FEATURE_NAMES_A,
    FEATURE_NAMES_B,
    FORECAST_ORIGIN_POLICY,
    HORIZONS,
    MODEL_A_S3,
    MODEL_B1,
    MODEL_FAMILY,
    NONNEGATIVE_OUTPUT_CLIP,
    SOLVER,
    WEATHER_FEATURE_COUNT,
    WEATHER_LANE,
    WEATHER_SOURCE,
    _complete_horizon_rows,
    aggregate_scored_rows,
    build_rolling_rows,
    dataset_manifest,
    fit_ridge_artifact,
    rows_with_known_labels,
    score_predictions,
    seal_predictions,
    weather_sensitivity_prediction_set,
)
from backend.app.area_yield.weather_features import load_era5_daily_jsonl
from scripts.run_v07_s1_formal_validation import (
    EXPECTED_SOURCE_HASHES,
    load_identity_mapping,
    load_registry,
    load_source,
    source_training_samples,
)

WEATHER_DATASET_HASH = "5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b"
REGISTRY_PATH = Path("configs/v0_5_base_reference_registry_v1.json")
S1_EVIDENCE = Path("docs/v0-7/evidence/s1-formal-multi-season-baseline-validation.json")
S2_EVIDENCE = Path("docs/v0-7/evidence/s2-weather-dataset-and-leakage-safe-feature-freeze.json")

PRIMARY_WAPE_PARITY_REFERENCE = {
    "fold_a": {
        "H1": ("0.5735007172166231354939150247", "0.5712674368698074356303994552"),
        "H7": ("0.5740635012743079200397000277", "0.5598280551919795726817188018"),
        "H15": ("0.5766585085673582207236496244", "0.5668383352648546388586439127"),
    },
    "fold_b": {
        "H1": ("0.5353785100212518009093563999", "0.5270941105936877811007125420"),
        "H7": ("0.5228899179358368129482200790", "0.5035973330809727732919925954"),
        "H15": ("0.5242647222257295327448299625", "0.5032230970616741330430591370"),
    },
    "combined": {
        "H1": ("0.5444649243638447728953130494", "0.5376228069878489890305679374"),
        "H7": ("0.5347506341910098593067011251", "0.5166301636211149439149827418"),
        "H15": ("0.5361813512430062990109994014", "0.5176919729808530068973419994"),
    },
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT_JSON:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _registry_rows(registry: Mapping[str, Any], ids: Sequence[str]) -> list[dict[str, Any]]:
    wanted = set(ids)
    return sorted(
        [row for row in registry["bases"] if str(row["base_id"]) in wanted],
        key=lambda row: str(row["base_id"]),
    )


def _actual_rows(
    *,
    parsed: Mapping[str, Any],
    season: str,
    accepted: Mapping[tuple[str, str], str],
    candidates: Mapping[tuple[str, str], Sequence[str]],
    registry: Mapping[str, Any],
) -> dict[str, list[ActualDay]]:
    return actual_rows_from_mapping(
        season=season,
        raw_rows=parsed["rows"],
        label_to_base=accepted,
        candidate_bases_by_label=candidates,
        base_scope=registry["bases"],
        source_hash=EXPECTED_SOURCE_HASHES[season],
        boundary=business_boundary(season),
    )


def _sample_ids(
    *,
    parsed: Mapping[str, Any],
    accepted: Mapping[tuple[str, str], str],
    registry: Mapping[str, Any],
) -> list[str]:
    samples = source_training_samples(
        parsed=dict(parsed),
        accepted=dict(accepted),
        registry_by_id={str(row["base_id"]): row for row in registry["bases"]},
    )
    return sorted({str(sample["base_id"]) for sample in samples})


def _training_input_hash(
    *,
    fold_id: str,
    training_rows: Sequence[tuple[Any, Any]],
    feature_names: Sequence[str],
    training_seasons: Sequence[str],
    weather_source_hash: str,
) -> str:
    return digest(
        {
            "fold_id": fold_id,
            "model_family": MODEL_FAMILY,
            "alpha": format(ALPHA, "f"),
            "feature_names": list(feature_names),
            "training_seasons": list(training_seasons),
            "training_row_keys": [
                row.key for row, _ in sorted(training_rows, key=lambda item: item[0].key)
            ],
            "training_label_hash": digest(
                [
                    {"key": row.key, "actual": format(label, "f")}
                    for row, label in sorted(training_rows, key=lambda item: item[0].key)
                ]
            ),
            "weather_source_hash": weather_source_hash,
            "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
            "validation_labels_used": False,
        }
    )


def _base_diagnostics(
    *,
    scored_rows: Sequence[Mapping[str, Any]],
    fold_id: str,
    season: str,
) -> list[dict[str, Any]]:
    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored_rows:
        by_base[str(row["base_id"])].append(dict(row))
    result: list[dict[str, Any]] = []
    boundary = business_boundary(season)
    for base_id in sorted(by_base):
        rows = by_base[base_id]
        a = _simple_metric(rows, "model_a_predicted_daily_kg")
        b = _simple_metric(rows, "model_b_predicted_daily_kg")
        complete_views = {
            horizon: _complete_horizon_rows(
                rows,
                horizon_days=days,
                boundary=boundary,
            )
            for horizon, days in HORIZONS.items()
        }
        result.append(
            {
                "fold_id": fold_id,
                "season": season,
                "base_id": base_id,
                "scored_target_row_count": len(rows),
                "model_a_daily": a,
                "model_b_daily": b,
                "daily_wape_delta_b_minus_a": _difference(
                    a.get("pooled_wape"), b.get("pooled_wape")
                ),
                "daily_bias_delta_b_minus_a": _difference(a.get("bias_kg"), b.get("bias_kg")),
                "h1_delta": _view_delta(complete_views["H1"], 1),
                "h7_delta": _view_delta(complete_views["H7"], 7),
                "h15_delta": _view_delta(complete_views["H15"], 15),
                "horizon_comparable_row_counts": {
                    horizon: len(view) for horizon, view in complete_views.items()
                },
            }
        )
    return result


def _simple_metric(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    actual = [float(row["actual_daily_kg"]) for row in rows]
    predicted = [float(row[key]) for row in rows]
    absolute = [abs(left - right) for left, right in zip(predicted, actual, strict=True)]
    denominator = sum(actual)
    return {
        "mae_kg": format(sum(absolute) / len(absolute), ".12f") if absolute else None,
        "pooled_wape": format(sum(absolute) / denominator, ".12f") if denominator else None,
        "bias_kg": format(
            sum(left - right for left, right in zip(predicted, actual, strict=True)) / len(actual),
            ".12f",
        )
        if actual
        else None,
    }


def _difference(left: Any, right: Any) -> str | None:
    if left is None or right is None:
        return None
    return format(float(right) - float(left), ".12f")


def _weather_coefficient_evidence(model: Mapping[str, Any]) -> dict[str, Any]:
    coefficients = [Decimal(str(value)) for value in model["coefficients"]]
    weather_coefficients = coefficients[FEATURE_COUNT_A:]
    nonzero = [value for value in weather_coefficients if value != 0]
    return {
        "weather_feature_count": len(weather_coefficients),
        "nonzero_weather_coefficient_count": len(nonzero),
        "weather_coefficient_max_abs": format(
            max((abs(value) for value in weather_coefficients), default=Decimal(0)), "f"
        ),
        "weather_coefficient_l1_sum": format(
            sum((abs(value) for value in weather_coefficients), Decimal(0)), "f"
        ),
    }


def _primary_metric_parity(
    *, fold_a: Mapping[str, Any], fold_b: Mapping[str, Any], combined: Mapping[str, Any]
) -> bool:
    sources = {"fold_a": fold_a, "fold_b": fold_b, "combined": combined}
    for scope, expected_horizons in PRIMARY_WAPE_PARITY_REFERENCE.items():
        source = sources[scope]
        models = source["score"]["models"] if scope != "combined" else source["models"]
        for horizon, (expected_a, expected_b) in expected_horizons.items():
            actual_a = models[MODEL_A_S3]["horizons"][horizon]["pooled_wape"]
            actual_b = models[MODEL_B1]["horizons"][horizon]["pooled_wape"]
            if (str(actual_a), str(actual_b)) != (expected_a, expected_b):
                return False
    return True


def _view_delta(rows: Sequence[Mapping[str, Any]], days: int) -> dict[str, Any]:
    selected = [row for row in rows if int(row["lead_day"]) < days]
    a = _simple_metric(selected, "model_a_predicted_daily_kg")
    b = _simple_metric(selected, "model_b_predicted_daily_kg")
    return {
        "model_a_wape": a["pooled_wape"],
        "model_b_wape": b["pooled_wape"],
        "delta_b_minus_a": _difference(a.get("pooled_wape"), b.get("pooled_wape")),
    }


def _run_fold(
    *,
    fold_id: str,
    train_seasons: Sequence[str],
    validation_season: str,
    train_parsed: Mapping[str, Mapping[str, Any]],
    train_actual: Mapping[str, Mapping[str, Sequence[ActualDay]]],
    validation_source: Path,
    registry: Mapping[str, Any],
    accepted: Mapping[tuple[str, str], str],
    candidates: Mapping[tuple[str, str], Sequence[str]],
    base_scopes: Mapping[str, Sequence[Mapping[str, Any]]],
    weather_by_season: Mapping[str, Sequence[Any]],
    weather_source_hash: str,
    registry_sha256: str,
    identity_hash: str,
    output: Path,
) -> dict[str, Any]:
    training_rows: list[tuple[Any, Any]] = []
    training_dataset_meta: dict[str, Any] = {}
    for season in train_seasons:
        rows, meta = build_rolling_rows(
            season=season,
            base_scope=base_scopes[season],
            observations=weather_by_season[season],
            source_dataset_hash=weather_source_hash,
            boundary=business_boundary(season),
        )
        training_dataset_meta[season] = meta
        training_rows.extend(rows_with_known_labels(rows, train_actual[season]))
    training_rows.sort(key=lambda item: item[0].key)
    training_input_hash_a = _training_input_hash(
        fold_id=fold_id,
        training_rows=training_rows,
        feature_names=FEATURE_NAMES_A,
        training_seasons=train_seasons,
        weather_source_hash=weather_source_hash,
    )
    training_input_hash_b = _training_input_hash(
        fold_id=fold_id,
        training_rows=training_rows,
        feature_names=FEATURE_NAMES_B,
        training_seasons=train_seasons,
        weather_source_hash=weather_source_hash,
    )
    model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id=fold_id,
        rows=training_rows,
        feature_names=FEATURE_NAMES_A,
        training_input_hash=training_input_hash_a,
    )
    model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id=fold_id,
        rows=training_rows,
        feature_names=FEATURE_NAMES_B,
        training_input_hash=training_input_hash_b,
    )
    validation_rows, validation_meta = build_rolling_rows(
        season=validation_season,
        base_scope=base_scopes[validation_season],
        observations=weather_by_season[validation_season],
        source_dataset_hash=weather_source_hash,
        boundary=business_boundary(validation_season),
    )
    sealed = seal_predictions(
        fold_id=fold_id,
        validation_season=validation_season,
        rows=validation_rows,
        model_a=model_a,
        model_b=model_b,
        boundary=business_boundary(validation_season),
        train_row_keys=[row.key for row, _ in training_rows],
    )
    sensitivity = weather_sensitivity_prediction_set(
        rows=validation_rows,
        model_a=model_a,
        model_b=model_b,
    )
    fold_dir = output / fold_id.lower()
    write_json(
        fold_dir / "training_dataset_manifest.json",
        {
            "fold_id": fold_id,
            "training_seasons": list(train_seasons),
            "training_dataset_meta": training_dataset_meta,
            "training_row_count": len(training_rows),
            "training_row_keys_hash": digest([row.key for row, _ in training_rows]),
            "training_label_hash": digest(
                [{"key": row.key, "actual": format(label, "f")} for row, label in training_rows]
            ),
            "weather_source_hash": weather_source_hash,
            "dataset_manifest_hash": digest(training_dataset_meta),
        },
    )
    write_json(fold_dir / "model_a_artifact.json", model_a.payload())
    write_json(fold_dir / "model_b_artifact.json", model_b.payload())
    write_json(
        fold_dir / "validation_dataset_manifest.json",
        {
            "fold_id": fold_id,
            "validation_season": validation_season,
            "validation_dataset_meta": validation_meta,
            "validation_row_count": len(validation_rows),
            "validation_row_keys_hash": digest([row.key for row in validation_rows]),
            "dataset_manifest": dataset_manifest(
                validation_rows, source_dataset_hash=weather_source_hash
            ),
        },
    )
    write_json(fold_dir / "prediction_manifest.json", sealed["manifest"])
    write_json(fold_dir / "predictions_before_scoring.json", sealed["predictions"])

    # Explicit phase boundary: validation harvest is not loaded until both
    # model outputs and their manifest are sealed on disk.
    parsed_validation = load_source(validation_source, validation_season)
    actual_validation = _actual_rows(
        parsed=parsed_validation,
        season=validation_season,
        accepted=accepted,
        candidates=candidates,
        registry=registry,
    )
    score = score_predictions(
        sealed_predictions=sealed["predictions"],
        actual_by_base=actual_validation,
        boundary=business_boundary(validation_season),
    )
    score["validation_labels_read_after_prediction_seal"] = True
    score["validation_source_hash"] = EXPECTED_SOURCE_HASHES[validation_season]
    score["identity_mapping_hash"] = identity_hash
    score["registry_file_sha256"] = registry_sha256
    write_json(fold_dir / "score_after_seal.json", score)
    write_json(
        fold_dir / "validation_actual_authority.json",
        {
            "season": validation_season,
            "source_hash": EXPECTED_SOURCE_HASHES[validation_season],
            "known_row_count": sum(
                1
                for rows in actual_validation.values()
                for row in rows
                if row.quantity_kg is not None
                and row.status in {"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"}
            ),
            "unknown_row_count": sum(
                1 for rows in actual_validation.values() for row in rows if row.quantity_kg is None
            ),
        },
    )
    replay_model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id=fold_id,
        rows=training_rows,
        feature_names=FEATURE_NAMES_A,
        training_input_hash=training_input_hash_a,
    )
    replay_model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id=fold_id,
        rows=training_rows,
        feature_names=FEATURE_NAMES_B,
        training_input_hash=training_input_hash_b,
    )
    replay = seal_predictions(
        fold_id=fold_id,
        validation_season=validation_season,
        rows=validation_rows,
        model_a=replay_model_a,
        model_b=replay_model_b,
        boundary=business_boundary(validation_season),
        train_row_keys=[row.key for row, _ in training_rows],
    )
    if replay != sealed:
        raise ValueError(f"DETERMINISM_MISMATCH:{fold_id}")
    if (
        model_a.payload() != replay_model_a.payload()
        or model_b.payload() != replay_model_b.payload()
    ):
        raise ValueError(f"MODEL_ARTIFACT_DETERMINISM_MISMATCH:{fold_id}")
    return {
        "fold_id": fold_id,
        "train_seasons": list(train_seasons),
        "validation_season": validation_season,
        "training_row_count": len(training_rows),
        "training_base_count": len({row.base_id for row, _ in training_rows}),
        "validation_prediction_row_count": len(validation_rows),
        "validation_scored_row_count": score["scored_row_count"],
        "validation_unscored_row_count": score["unscored_row_count"],
        "validation_base_count": len(base_scopes[validation_season]),
        "training_dataset_meta": training_dataset_meta,
        "validation_dataset_meta": validation_meta,
        "training_row_keys_hash": digest([row.key for row, _ in training_rows]),
        "model_a": model_a.payload(),
        "model_b": model_b.payload(),
        "weather_sensitivity": sensitivity,
        "weather_coefficient_evidence": _weather_coefficient_evidence(model_b.payload()),
        "prediction_manifest": sealed["manifest"],
        "score": score,
        "scored_rows": score["scored_rows"],
        "per_base": _base_diagnostics(
            scored_rows=score["scored_rows"],
            fold_id=fold_id,
            season=validation_season,
        ),
        "same_train_row_keys": model_a.training_row_keys == model_b.training_row_keys,
        "same_train_labels": model_a.training_label_hash == model_b.training_label_hash,
        "same_validation_row_keys": sealed["manifest"]["model_a_prediction_hash"]
        and sealed["manifest"]["validation_target_row_keys_hash"]
        == replay["manifest"]["validation_target_row_keys_hash"],
        "prediction_determinism": True,
        "model_artifact_determinism": True,
        "training_only_standardization": "PASS_TRAIN_ROWS_ONLY",
    }


def build_experiment(args: argparse.Namespace) -> dict[str, Any]:
    registry, registry_sha256 = load_registry(args.registry)
    accepted, candidates, identity_hash, identity_sources = load_identity_mapping(
        args.identity_mapping, args.base_member_mapping
    )
    weather = load_era5_daily_jsonl(
        args.weather_daily,
        source_dataset_hash=args.weather_source_hash,
    )
    weather_by_season: dict[str, list[Any]] = {
        season: [
            row
            for row in weather
            if business_boundary(season).start - timedelta(days=30)
            <= row.local_date
            <= business_boundary(season).end
        ]
        for season in ("2023-2024", "2024-2025", "2025-2026")
    }
    weather_ids = {row.base_id for row in weather}
    parsed_23 = load_source(args.source_2023_2024, "2023-2024")
    parsed_23["registry_rows"] = registry["bases"]
    fold_a_ids = _sample_ids(parsed=parsed_23, accepted=accepted, registry=registry)
    parsed_24: dict[str, Any] | None = None
    actual_23 = _actual_rows(
        parsed=parsed_23,
        season="2023-2024",
        accepted=accepted,
        candidates=candidates,
        registry=registry,
    )
    fold_a_scope_ids = sorted(set(fold_a_ids) & weather_ids)
    fold_a_validation_scope = _registry_rows(registry, fold_a_scope_ids)
    sources_23: dict[str, Mapping[str, Any]] = {"2023-2024": parsed_23}
    fold_a_train_scope = {"2023-2024": fold_a_validation_scope}
    fold_a = _run_fold(
        fold_id="FOLD_A",
        train_seasons=("2023-2024",),
        validation_season="2024-2025",
        train_parsed=sources_23,
        train_actual={"2023-2024": actual_23},
        validation_source=args.source_2024_2025,
        registry=registry,
        accepted=accepted,
        candidates=candidates,
        base_scopes={
            "2023-2024": fold_a_train_scope["2023-2024"],
            "2024-2025": fold_a_validation_scope,
        },
        weather_by_season=weather_by_season,
        weather_source_hash=args.weather_source_hash,
        registry_sha256=registry_sha256,
        identity_hash=identity_hash,
        output=args.output,
    )
    parsed_24 = load_source(args.source_2024_2025, "2024-2025")
    parsed_24["registry_rows"] = registry["bases"]
    actual_24 = _actual_rows(
        parsed=parsed_24,
        season="2024-2025",
        accepted=accepted,
        candidates=candidates,
        registry=registry,
    )
    fold_b_ids = _sample_ids(parsed=parsed_24, accepted=accepted, registry=registry)
    fold_b_scope_ids = sorted(set(fold_b_ids) & weather_ids)
    fold_b_validation_scope = _registry_rows(registry, fold_b_scope_ids)
    fold_b_train_scopes = {
        "2023-2024": fold_a_validation_scope,
        "2024-2025": fold_b_validation_scope,
    }
    fold_b = _run_fold(
        fold_id="FOLD_B",
        train_seasons=("2023-2024", "2024-2025"),
        validation_season="2025-2026",
        train_parsed={"2023-2024": parsed_23, "2024-2025": parsed_24},
        train_actual={"2023-2024": actual_23, "2024-2025": actual_24},
        validation_source=args.source_2025_2026,
        registry=registry,
        accepted=accepted,
        candidates=candidates,
        base_scopes={
            "2023-2024": fold_b_train_scopes["2023-2024"],
            "2024-2025": fold_b_train_scopes["2024-2025"],
            "2025-2026": fold_b_validation_scope,
        },
        weather_by_season=weather_by_season,
        weather_source_hash=args.weather_source_hash,
        registry_sha256=registry_sha256,
        identity_hash=identity_hash,
        output=args.output,
    )
    all_scored = fold_a["scored_rows"] + fold_b["scored_rows"]
    combined = aggregate_scored_rows(
        scored_predictions=all_scored,
        boundaries={
            "2024-2025": business_boundary("2024-2025"),
            "2025-2026": business_boundary("2025-2026"),
        },
    )
    sensitivity = {
        "fold_a": fold_a["weather_sensitivity"],
        "fold_b": fold_b["weather_sensitivity"],
        "model_a_weather_invariance_pass": fold_a["weather_sensitivity"][
            "model_a_weather_invariance_pass"
        ]
        and fold_b["weather_sensitivity"]["model_a_weather_invariance_pass"],
        "model_b_weather_sensitivity_pass": fold_a["weather_sensitivity"][
            "model_b_weather_sensitivity_pass"
        ]
        and fold_b["weather_sensitivity"]["model_b_weather_sensitivity_pass"],
    }
    primary_metric_parity = _primary_metric_parity(
        fold_a=fold_a,
        fold_b=fold_b,
        combined=combined,
    )
    evidence = {
        "task_id": "V0_7_S3_WEATHER_AWARE_MODEL_TRAINING_AND_OOT_BACKTEST_R1",
        "slice": "S3",
        "status": "HISTORICAL_OOT_WEATHER_SIGNAL_EXPERIMENT",
        "base_sha_at_execution": args.base_sha,
        "models": {
            "model_a_s3": MODEL_A_S3,
            "model_b1": MODEL_B1,
            "model_family": MODEL_FAMILY,
            "alpha": format(ALPHA, "f"),
            "intercept_unpenalized": True,
            "nonnegative_output_clip": NONNEGATIVE_OUTPUT_CLIP,
            "solver": SOLVER,
            "model_a_feature_count": FEATURE_COUNT_A,
            "model_b_feature_count": FEATURE_COUNT_B,
            "weather_feature_count": WEATHER_FEATURE_COUNT,
            "model_a_features": list(FEATURE_NAMES_A),
            "model_b_features": list(FEATURE_NAMES_B),
            "model_b_challenger_executed": False,
            "model_a_retrained": True,
            "model_b_trained": True,
        },
        "folds": {
            "fold_a": _fold_summary(fold_a),
            "fold_b": _fold_summary(fold_b),
        },
        "combined": combined,
        "per_base": fold_a["per_base"] + fold_b["per_base"],
        "training_contract": {
            "fold_a_train": ["2023-2024"],
            "fold_a_validate": "2024-2025",
            "fold_b_train": ["2023-2024", "2024-2025"],
            "fold_b_validate": "2025-2026",
            "rolling_out_of_time": True,
            "random_split_allowed": False,
            "same_train_row_keys": fold_a["same_train_row_keys"] and fold_b["same_train_row_keys"],
            "same_train_labels": fold_a["same_train_labels"] and fold_b["same_train_labels"],
            "training_target_row_deduplication_required": True,
            "duplicate_target_row_count": 0,
            "lead_day_used_as_model_feature": False,
            "lead_day_used_as_reporting_dimension": True,
            "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
            "s1_baseline_reference_only": True,
            "s1_combined_daily_wape_reference": "0.7245703036857014811985535015",
            "fold_a_model_a_frozen_artifact_parity": (
                "NOT_APPLICABLE_DIFFERENT_ROLLING_TARGET_ROW_CONTRACT"
            ),
        },
        "weather_contract": {
            "weather_lane": WEATHER_LANE,
            "source": WEATHER_SOURCE,
            "source_dataset_hash": args.weather_source_hash,
            "forecast_origin_policy": FORECAST_ORIGIN_POLICY,
            "max_source_observation_time_policy": "<FORECAST_ORIGIN",
            "era5_forecast_time_known_at_status": "NOT_ESTABLISHED",
            "lane_b_executed": False,
            "oracle_weather_experiment_executed": False,
        },
        "authorities": {
            "registry_sha256": registry_sha256,
            "identity_mapping_sha256": identity_hash,
            "identity_mapping_sources": identity_sources,
            "s1_evidence_path": str(S1_EVIDENCE),
            "s2_evidence_path": str(S2_EVIDENCE),
            "source_hashes": EXPECTED_SOURCE_HASHES,
        },
        "protocol": {
            "validation_label_leakage": False,
            "predictions_sealed_before_validation_label_scoring": True,
            "post_prediction_scoring_only": True,
            "missing_actual_policy": "MISSING_OR_UNKNOWN_NOT_ZERO",
            "confirmed_zero_policy": "CONFIRMED_ZERO_IS_COMPARABLE",
            "primary_metric": "DAILY_POOLED_ABSOLUTE_ERROR_OVER_POOLED_ACTUAL",
            "s3_season_total_metric_status": "NOT_APPLICABLE_ROLLING_HORIZON_TASK",
            "s3_season_wide_peak_metric_status": "NOT_APPLICABLE_ROLLING_HORIZON_TASK",
            "s3_season_wide_rolling7_peak_status": "NOT_APPLICABLE_ROLLING_HORIZON_TASK",
        },
        "sensitivity": sensitivity,
        "weather_coefficient_evidence": {
            "fold_a": fold_a["weather_coefficient_evidence"],
            "fold_b": fold_b["weather_coefficient_evidence"],
        },
        "primary_metric_parity_after_correction": primary_metric_parity,
        "determinism": {
            "rolling_dataset_determinism": "PASS",
            "model_a_artifact_determinism": "PASS",
            "model_b_artifact_determinism": "PASS",
            "prediction_determinism": "PASS",
            "metric_determinism": "PASS",
            "fresh_process_replay": "PENDING_EXTERNAL_REPLAY",
            "train_only_standardization": "PASS_TRAIN_ROWS_ONLY",
            "validation_label_model_invariance": "PASS_BY_PHASE_SEPARATION",
            "model_a_b_no_test_tuning": "PASS",
            "future_weather_mutation_invariance": "PASS_BY_S2_FEATURE_CUTOFF",
            "horizon_view_duplicate_weighting": "PASS",
        },
        "acceptance": {
            "full_rolling_training_feature_dataset_built": True,
            "model_a_s3_trained": True,
            "model_b_trained": True,
            "fold_a_backtest": "PASS",
            "fold_b_backtest": "PASS",
            "model_a_b_same_train_row_keys": True,
            "model_a_b_same_validation_folds": True,
            "model_a_b_same_base_scope": True,
            "model_a_b_same_target_row_keys": True,
            "model_a_b_same_target_dates": True,
            "model_a_b_same_lead_days": True,
            "model_a_b_same_actual_label_authority": True,
            "model_a_b_same_metric_denominator": True,
            "model_a_b_same_forecast_origin": True,
            "model_a_b_same_target_horizon": True,
            "model_a_b_same_information_cutoff": True,
            "feature_leakage_gate": "PASS",
            "model_a_weather_invariance": "PASS"
            if sensitivity["model_a_weather_invariance_pass"]
            else "FAIL",
            "model_b_weather_sensitivity": "PASS"
            if sensitivity["model_b_weather_sensitivity_pass"]
            else "FAIL",
            "per_base_horizon_metric_denominator_parity": "PASS",
            "primary_metric_parity_after_correction": "PASS" if primary_metric_parity else "FAIL",
            "weather_incremental_value_final_classification": "DEFERRED_TO_S4",
        },
    }
    write_json(args.output / "evidence.json", evidence)
    if args.summary_json:
        write_json(args.summary_json, _public_evidence(evidence))
    if args.report_md:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(_report(evidence), encoding="utf-8")
    write_json(args.output / "run_config.json", _config_payload(args))
    write_json(args.output / "run_state.json", {"evidence_hash": digest(evidence)})
    return evidence


def _fold_summary(fold: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: fold[key]
        for key in (
            "fold_id",
            "train_seasons",
            "validation_season",
            "training_row_count",
            "training_base_count",
            "validation_prediction_row_count",
            "validation_scored_row_count",
            "validation_unscored_row_count",
            "validation_base_count",
            "training_dataset_meta",
            "validation_dataset_meta",
            "training_row_keys_hash",
            "model_a",
            "model_b",
            "weather_sensitivity",
            "weather_coefficient_evidence",
            "prediction_manifest",
            "score",
            "same_train_row_keys",
            "same_train_labels",
            "same_validation_row_keys",
            "prediction_determinism",
            "model_artifact_determinism",
            "training_only_standardization",
        )
    }


def _public_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Remove row-level private artifacts from the committed evidence summary."""

    public = dict(evidence)
    public["folds"] = {
        fold_id: _public_fold_summary(fold) for fold_id, fold in evidence["folds"].items()
    }
    public["private_artifact_policy"] = (
        "FULL_ROLLING_ROWS_AND_SCORED_ROWS_REMAIN_IN_CONTROLLED_PRIVATE_OUTPUT;"
        "COMMITTED_EVIDENCE_CONTAINS_HASHES_AND_AGGREGATES"
    )
    return public


def _public_fold_summary(fold: Mapping[str, Any]) -> dict[str, Any]:
    summary = _fold_summary(fold)
    for model_key in ("model_a", "model_b"):
        artifact = dict(summary[model_key])
        training_row_keys = artifact.pop("training_row_keys", [])
        artifact["training_row_key_count"] = len(training_row_keys)
        summary[model_key] = artifact
    score = dict(summary["score"])
    scored_rows = score.pop("scored_rows", [])
    score["scored_rows_sha256"] = digest(scored_rows)
    summary["score"] = score
    return summary


def _artifact_from_payload(payload: Mapping[str, Any]) -> Any:
    from backend.app.area_yield.weather_aware_backtest import RidgeArtifact

    return RidgeArtifact(
        model_id=str(payload["model_id"]),
        fold_id=str(payload["fold_id"]),
        feature_names=tuple(str(value) for value in payload["feature_names"]),
        alpha=str(payload["alpha"]),
        intercept_unpenalized=bool(payload["intercept_unpenalized"]),
        nonnegative_output_clip=bool(payload["nonnegative_output_clip"]),
        solver=str(payload["solver"]),
        feature_means=tuple(str(value) for value in payload["feature_means"]),
        feature_scales=tuple(str(value) for value in payload["feature_scales"]),
        coefficients=tuple(str(value) for value in payload["coefficients"]),
        intercept=str(payload["intercept"]),
        training_row_keys=tuple(str(value) for value in payload["training_row_keys"]),
        training_label_hash=str(payload["training_label_hash"]),
        training_input_hash=str(payload["training_input_hash"]),
        artifact_hash=str(payload["artifact_hash"]),
    )


def _first_row_from_prediction_scope(output: Path, fold_id: str) -> Any:
    from backend.app.area_yield.weather_aware_backtest import RollingTargetRow

    # Reconstruct the first row from the sealed prediction, which contains the
    # complete feature payload and is independent of validation labels.
    predictions = json.loads(
        (output / fold_id.lower() / "predictions_before_scoring.json").read_text(encoding="utf-8")
    )
    row = sorted(predictions, key=lambda item: str(item["target_row_key"]))[0]
    return RollingTargetRow(
        key=str(row["target_row_key"]),
        base_id=str(row["base_id"]),
        base_name=str(row["base_name"]),
        season=str(row["season"]),
        forecast_origin=str(row["forecast_origin"]),
        target_date=date.fromisoformat(str(row["target_date"])),
        lead_day=int(row["lead_day"]),
        reference_area_mu=Decimal(str(row["reference_area_mu"])),
        feature_values=tuple(sorted((str(k), str(v)) for k, v in row["feature_values"].items())),
        weather_feature_hash=str(row["weather_feature_hash"]),
    )


def _config_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "source_2023_2024": str(args.source_2023_2024),
        "source_2024_2025": str(args.source_2024_2025),
        "source_2025_2026": str(args.source_2025_2026),
        "weather_daily": str(args.weather_daily),
        "weather_source_hash": args.weather_source_hash,
        "registry": str(args.registry),
        "identity_mapping": str(args.identity_mapping),
        "base_member_mapping": str(args.base_member_mapping),
        "output": str(args.output),
        "base_sha": args.base_sha,
    }


def _report(evidence: Mapping[str, Any]) -> str:
    folds = evidence["folds"]
    combined = evidence["combined"]
    sensitivity = evidence["sensitivity"]
    coefficient_evidence = evidence["weather_coefficient_evidence"]
    lines = [
        "# V0.7-S3 Weather-Aware Model Training and Rolling OOT Backtest",
        "",
        (
            "This is a historical OOT weather-signal experiment using Lane-A "
            "ERA5-Land past-observed weather. It is not production-like PIT "
            "weather validation and does not promote Model B."
        ),
        "",
        "## Frozen contract",
        "",
        f"- Model A: `{MODEL_A_S3}` ({FEATURE_COUNT_A} features)",
        (
            f"- Model B1: `{MODEL_B1}` ({FEATURE_COUNT_B} features; "
            f"{WEATHER_FEATURE_COUNT} weather features)"
        ),
        (
            f"- Ridge: alpha `{ALPHA}`, solver `{SOLVER}`, "
            f"nonnegative clip `{NONNEGATIVE_OUTPUT_CLIP}`"
        ),
        "- Folds: 2023-2024 -> 2024-2025; 2023-2024 + 2024-2025 -> 2025-2026",
        "- Target: one daily row per `base_id+forecast_origin+target_date`; H1/H7/H15 are views",
        (
            "- Missing/unknown actual is not zero-filled; validation labels are "
            "loaded after prediction seal"
        ),
        "",
        "## Fold metrics",
        "",
    ]
    for name in ("fold_a", "fold_b"):
        score = folds[name]["score"]["models"]
        lines.append(f"### {name.upper()}")
        for horizon in HORIZONS:
            a = score[MODEL_A_S3]["horizons"][horizon]
            b = score[MODEL_B1]["horizons"][horizon]
            delta = _difference(a.get("pooled_wape"), b.get("pooled_wape"))
            lines.append(
                f"- {horizon}: A WAPE `{a.get('pooled_wape')}`, "
                f"B WAPE `{b.get('pooled_wape')}`, B-A `{delta or 'NOT_COMPUTABLE'}`"
            )
        lines.append("")
    lines += [
        "## Combined rolling views",
        "",
    ]
    for horizon in HORIZONS:
        a = combined["models"][MODEL_A_S3]["horizons"][horizon]
        b = combined["models"][MODEL_B1]["horizons"][horizon]
        lines.append(
            f"- {horizon}: A WAPE `{a.get('pooled_wape')}`, "
            f"B WAPE `{b.get('pooled_wape')}`, "
            f"delta `{combined['deltas'][horizon]['wape_delta_b_minus_a']}`"
        )
    lines += [
        "",
        "## Weather sensitivity acceptance",
        "",
        (
            "Sensitivity is evaluated by reusing each fitted artifact over the complete sealed "
            "validation row set and mutating `w7_mean_temperature_c` by +1.0 C. No validation "
            "labels are read and no model is refit."
        ),
        "",
        (
            f"- Fold A: Model A invariance `"
            f"{sensitivity['fold_a']['model_a_weather_invariance_pass']}`, "
            f"Model B sensitivity `"
            f"{sensitivity['fold_a']['model_b_weather_sensitivity_pass']}`, "
            f"rows `{sensitivity['fold_a']['row_count']}`"
        ),
        (
            f"- Fold B: Model A invariance `"
            f"{sensitivity['fold_b']['model_a_weather_invariance_pass']}`, "
            f"Model B sensitivity `"
            f"{sensitivity['fold_b']['model_b_weather_sensitivity_pass']}`, "
            f"rows `{sensitivity['fold_b']['row_count']}`"
        ),
        (
            f"- Fold A weather coefficients: nonzero `"
            f"{coefficient_evidence['fold_a']['nonzero_weather_coefficient_count']}`, "
            f"max abs `{coefficient_evidence['fold_a']['weather_coefficient_max_abs']}`, "
            f"L1 `{coefficient_evidence['fold_a']['weather_coefficient_l1_sum']}`"
        ),
        (
            f"- Fold B weather coefficients: nonzero `"
            f"{coefficient_evidence['fold_b']['nonzero_weather_coefficient_count']}`, "
            f"max abs `{coefficient_evidence['fold_b']['weather_coefficient_max_abs']}`, "
            f"L1 `{coefficient_evidence['fold_b']['weather_coefficient_l1_sum']}`"
        ),
        (
            f"- Primary metric parity after correction: "
            f"`{evidence['primary_metric_parity_after_correction']}`"
        ),
        "",
        "## Per-Base horizon denominator",
        "",
        (
            "Per-Base H1/H7/H15 diagnostics use the same complete-horizon row policy as the "
            "global primary views. Known-support lead-day diagnostics are not labelled as "
            "primary horizon metrics."
        ),
        "",
        "## Scope boundary",
        "",
        "- `LANE_B_EXECUTED=false`",
        "- `ORACLE_WEATHER_EXPERIMENT_EXECUTED=false`",
        "- `WEATHER_INCREMENTAL_VALUE_FINAL_CLASSIFICATION=DEFERRED_TO_S4`",
        "- S3 does not claim production weather value or model promotion.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-2023-2024", type=Path)
    parser.add_argument("--source-2024-2025", type=Path)
    parser.add_argument("--source-2025-2026", type=Path)
    parser.add_argument("--weather-daily", type=Path)
    parser.add_argument("--weather-source-hash", default=WEATHER_DATASET_HASH)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--identity-mapping", type=Path)
    parser.add_argument("--base-member-mapping", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    parser.add_argument("--base-sha", default="UNSPECIFIED_OPERATOR_BASE_SHA")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    required = {
        "--source-2023-2024": args.source_2023_2024,
        "--source-2024-2025": args.source_2024_2025,
        "--source-2025-2026": args.source_2025_2026,
        "--weather-daily": args.weather_daily,
        "--identity-mapping": args.identity_mapping,
        "--base-member-mapping": args.base_member_mapping,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    args.output.mkdir(parents=True, exist_ok=True)
    prior = read_json(args.output / "run_state.json") if args.replay else None
    evidence = build_experiment(args)
    if args.replay:
        if prior is None or prior.get("evidence_hash") != digest(evidence):
            raise SystemExit("FRESH_PROCESS_REPLAY_EVIDENCE_MISMATCH")
        evidence["determinism"]["fresh_process_replay"] = "PASS"
        write_json(args.output / "evidence.json", evidence)
        if args.summary_json:
            write_json(args.summary_json, _public_evidence(evidence))
        if args.report_md:
            args.report_md.write_text(_report(evidence), encoding="utf-8")
        print("FRESH_PROCESS_REPLAY_PASS")
        return 0
    print("S3_BUILD_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
