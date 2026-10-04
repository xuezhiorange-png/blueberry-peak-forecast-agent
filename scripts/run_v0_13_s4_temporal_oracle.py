"""Create-only isolated S4 operator workflow; no Lane-A fit or regeneration."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield import gdd_features as g
from backend.app.area_yield import v013_feature_value_experiment as e
from backend.app.area_yield import v013_temporal_oracle as t
from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.weather_aware_backtest import (
    RollingTargetRow,
    _base_feature_values,
    fit_ridge_artifact,
)
from backend.app.area_yield.weather_features import build_feature_row, load_era5_daily_jsonl
from backend.app.area_yield.weather_value_conclusion import complete_horizon_views
from scripts.run_v0_13_s2_gdd_feature_audit import FROZEN, file_identity, frozen_business_boundary
from scripts.run_v0_13_s3_four_model_oot import (
    IDENTITY_HASH,
    REGISTRY_HASH,
    read,
    write,
    write_rows,
)
from scripts.run_v07_s1_formal_validation import (
    EXPECTED_SOURCE_HASHES,
    load_identity_mapping,
    load_registry,
    load_source,
)
from scripts.run_v07_s3_weather_aware_backtest import (
    WEATHER_DATASET_HASH,
    _actual_rows,
    _training_input_hash,
)


def run(args: argparse.Namespace) -> dict[str, Any]:
    with t.S4LabelAccessGuard(args.output, args.s3, args.source24, args.source25) as access:
        return _run(args, access)


def _run(args: argparse.Namespace, access: t.S4LabelAccessGuard) -> dict[str, Any]:
    t.validate_contract(t.CONTRACT)
    t.require(not args.output.exists(), "OUTPUT_ALREADY_EXISTS")
    public = read(Path("docs/v0-13/evidence/v0.13-s3-four-model-controlled-oot-r1.json"))[
        "control_report"
    ]
    t.verify_s3_label_free(args.s3, public)
    report = public
    old = read(Path("docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"))
    sources = dict(
        zip(
            ("2023-2024", "2024-2025", "2025-2026"),
            (args.source23, args.source24, args.source25),
            strict=True,
        )
    )
    inputs = {
        "2023-2024": args.source23,
        "weather": args.weather,
        "registry": args.registry,
        "identity": args.identity,
        "members": args.members,
        "rows": args.rows,
    }
    for fold in t.S3_SEALS:
        for filename in (
            "prediction-seal.json",
            "predictions-before-scoring.jsonl",
            *(f"{m.lower()}-artifact.json" for m in e.MODELS),
        ):
            inputs[fold + ":" + filename] = args.s3 / fold / filename
    # Label-bearing paths are excluded entirely: hashing is itself a byte read.
    before = {k: file_identity(p) for k, p in inputs.items()}
    for season, expected in EXPECTED_SOURCE_HASHES.items():
        t.require(report["source_hashes"][season] == expected, "SOURCE_HASH_MISMATCH")
    t.require(
        before["2023-2024"]["sha256"] == EXPECTED_SOURCE_HASHES["2023-2024"], "SOURCE_HASH_MISMATCH"
    )
    t.require(before["weather"]["sha256"] == WEATHER_DATASET_HASH, "WEATHER_HASH_MISMATCH")
    t.require(
        before["rows"]["sha256"] == report["source_hashes"]["row_identities"],
        "S3_ROW_AUTHORITY_CHANGED",
    )
    registry, registry_hash = load_registry(args.registry)
    t.require(registry_hash == REGISTRY_HASH, "REGISTRY_HASH_MISMATCH")
    accepted, candidates, mapping_hash, _ = load_identity_mapping(args.identity, args.members)
    t.require(mapping_hash == IDENTITY_HASH, "IDENTITY_MAPPING_MISMATCH")
    identities = read(args.rows)
    for fold in t.S3_SEALS:
        frozen = FROZEN[fold.upper()]
        e.verify_keys(
            identities[fold]["train"], int(str(frozen["count"])), str(frozen["keys_hash"])
        )
        e.verify_keys(
            identities[fold]["validation"],
            int(str(frozen["validation_count"])),
            str(frozen["validation_hash"]),
        )
        frozen_business_boundary(old["folds"][fold])
    observations: dict[str, list[Any]] = defaultdict(list)
    for observation in load_era5_daily_jsonl(
        args.weather, source_dataset_hash=WEATHER_DATASET_HASH
    ):
        observations[observation.base_id].append(observation)
    bases = {b["base_id"]: b for b in registry["bases"]}
    weather_cache: dict[tuple[str, str], Any] = {}
    row_cache: dict[str, RollingTargetRow] = {}

    def feature_rows(keys: list[str]) -> list[RollingTargetRow]:
        result = []
        for key in keys:
            if key not in row_cache:
                base, origin, target = g.parse_row_key(key)
                anchor = datetime.combine(
                    target + timedelta(days=1), time(), ZoneInfo("Asia/Shanghai")
                )
                cache = (base, target.isoformat())
                if cache not in weather_cache:
                    try:
                        weather_cache[cache] = build_feature_row(
                            observations=observations[base],
                            base_id=base,
                            forecast_origin=anchor,
                            target_start=anchor.date(),
                            target_end=anchor.date(),
                            source_dataset_hash=WEATHER_DATASET_HASH,
                        )
                    except ValueError as exc:
                        raise t.TemporalError(
                            "ORACLE_FEATURE_COVERAGE_CHANGED_FROZEN_COHORT"
                        ) from exc
                weather = weather_cache[cache]
                t.verify_oracle_window(target, anchor, weather)
                year = target.year if target.month >= 7 else target.year - 1
                season = f"{year}-{year + 1}"
                area = Decimal(str(bases[base]["productive_area_mu"]))
                values = {
                    **_base_feature_values(
                        reference_area_mu=area,
                        target_date=target,
                        boundary=business_boundary(season),
                    ),
                    **{"oracle_" + k: v for k, v in weather.features.items()},
                }
                t.require(set(values) == set(t.ORACLE_FEATURES), "ORACLE_FEATURE_SCHEMA_CHANGED")
                row_cache[key] = RollingTargetRow(
                    key=key,
                    base_id=base,
                    base_name=str(bases[base]["canonical_base_name"]),
                    season=season,
                    forecast_origin=origin,
                    target_date=target,
                    lead_day=(target - datetime.fromisoformat(origin).date()).days,
                    reference_area_mu=area,
                    feature_values=tuple(sorted(values.items())),
                    weather_feature_hash=weather.feature_hash,
                )
            result.append(row_cache[key])
        return result

    args.output.mkdir(parents=True)
    guard = access.oracle
    actuals: dict[str, dict[tuple[str, Any], Any]] = {}
    events = access.events

    def open_labels(season: str) -> None:
        guard.allow_label_read(season)
        t.require(season in ("2023-2024", "2024-2025"), "RAW_VALIDATION_READ_FORBIDDEN")
        if season == "2024-2025":
            inputs[season] = sources[season]
            before[season] = file_identity(sources[season])
            t.require(
                before[season]["sha256"] == EXPECTED_SOURCE_HASHES[season], "SOURCE_HASH_MISMATCH"
            )
        parsed = load_source(sources[season], season)
        rows = _actual_rows(
            parsed=parsed,
            season=season,
            accepted=accepted,
            candidates=candidates,
            registry=registry,
        )
        actuals[season] = {(base, day.day): day for base, days in rows.items() for day in days}
        events.append("READ_TRAIN_LABELS:" + season)

    def bind(row: RollingTargetRow) -> Any:
        return e.authoritative_actual(actuals[row.season].get((row.base_id, row.target_date)))

    forecasts = {}
    result: dict[str, Any] = dict(
        schema="V0_13_S4_TEMPORAL_ORACLE_V1",
        contract=t.CONTRACT,
        S3_authorities=t.S3_HASHES,
        S3_authority_parity="PASS",
        oracle_folds={},
    )
    open_labels("2023-2024")
    for fold in t.S3_SEALS:
        if fold == "fold_b":
            open_labels("2024-2025")
        authority = old["folds"][fold]
        training = feature_rows(identities[fold]["train"])
        labeled = []
        for row in training:
            actual = bind(row)
            t.require(actual is not None, "TRAINING_LABEL_AUTHORITY_MISMATCH")
            labeled.append((row, actual.quantity_kg))
        validation = feature_rows(identities[fold]["validation"])
        guard.allow_fit()
        input_hash = digest(
            dict(
                ridge_input=_training_input_hash(
                    fold_id=authority["fold_id"],
                    training_rows=labeled,
                    feature_names=t.ORACLE_FEATURES,
                    training_seasons=authority["train_seasons"],
                    weather_source_hash=WEATHER_DATASET_HASH,
                ),
                oracle_policy=digest(t.CONTRACT),
            )
        )
        fitted = fit_ridge_artifact(
            model_id=t.ORACLE_ID,
            fold_id=authority["fold_id"],
            rows=labeled,
            feature_names=t.ORACLE_FEATURES,
            training_input_hash=input_hash,
        )
        t.require(
            fitted.training_label_hash == FROZEN[fold.upper()]["training_label_hash"],
            "TRAINING_LABEL_HASH_MISMATCH",
        )
        payload = fitted.payload_without_hash()
        keys = payload.pop("training_row_keys")
        payload.update(
            schema="V0_13_ORACLE_RIDGE_ARTIFACT_V1",
            model_role="RESEARCH_UPPER_BOUND_ONLY",
            standardization=t.CONTRACT["standardization"],
            zero_std_policy="SCALE_1",
            deployable=False,
            future_realized_information=True,
            training_row_count=len(keys),
            training_row_keys_hash=digest(keys),
            feature_policy_hash=digest(t.CONTRACT),
        )
        payload["artifact_hash"] = digest(payload)
        t.verify_oracle_artifact(payload)
        output = args.output / fold
        output.mkdir()
        write(output / "o1-artifact.json", payload)
        predictions = [
            dict(target_row_key=row.key, O1=format(fitted.predict(row), "f")) for row in validation
        ]
        write_rows(output / "predictions-before-scoring.jsonl", predictions)
        prediction_hash = digest(
            [dict(target_row_key=r["target_row_key"], prediction=r["O1"]) for r in predictions]
        )
        seal = dict(
            fold_id=authority["fold_id"],
            validation_row_count=len(validation),
            validation_row_keys_hash=digest([r.key for r in validation]),
            artifact_hash=payload["artifact_hash"],
            prediction_hash=prediction_hash,
            feature_policy_hash=digest(t.CONTRACT),
            weather_source_hash=WEATHER_DATASET_HASH,
            oracle_lane_c=True,
            future_realized_information=True,
            business_boundary=frozen_business_boundary(authority),
            sealed_before_validation_label_read=True,
            file_hashes={p.name: g.sha256(p) for p in sorted(output.iterdir())},
        )
        seal["seal_hash"] = digest(seal)
        write(output / "prediction-seal.json", seal)
        guard.verify_seal(fold)
        events.append("ORACLE_SEALED:" + fold)
        forecasts[fold] = {r["target_row_key"]: r["O1"] for r in predictions}
        result["oracle_folds"][fold] = {
            k: payload[k]
            for k in (
                "artifact_hash",
                "training_row_count",
                "training_row_keys_hash",
                "training_label_hash",
                "training_input_hash",
            )
        }
        result["oracle_folds"][fold].update(
            prediction_hash=prediction_hash,
            seal_hash=seal["seal_hash"],
            direct_self_hash_valid=True,
            validation_row_count=len(validation),
            validation_row_keys_hash=seal["validation_row_keys_hash"],
        )
    access.open_label_gate()
    postseal_initial = {}
    reconstructed_folds = {}
    for fold in t.S3_SEALS:
        postseal_initial[fold] = access.capture_s3_identity(fold)
        prior = access.read_s3_scored_rows(fold)
        sealed = {
            r["target_row_key"]: r
            for r in (
                json.loads(line)
                for line in (args.s3 / fold / "predictions-before-scoring.jsonl")
                .read_text()
                .splitlines()
            )
        }
        seen = set()
        for row in prior:
            key = row["target_row_key"]
            t.require(key in sealed and key not in seen, "S3_ACTUAL_OR_PREDICTION_PARITY_FAILED")
            seen.add(key)
            t.require(
                all(row[k] == v for k, v in sealed[key].items()),
                "S3_ACTUAL_OR_PREDICTION_PARITY_FAILED",
            )
            quantity = Decimal(row["actual_daily_kg"])
            t.require(quantity.is_finite() and quantity >= 0, "S3_ACTUAL_AUTHORITY_INVALID")
            t.require(
                row["actual_status"] in ("KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"),
                "S3_ACTUAL_AUTHORITY_INVALID",
            )
            t.require(
                row["actual_status"] != "CONFIRMED_ZERO" or quantity == 0,
                "S3_ACTUAL_AUTHORITY_INVALID",
            )
            t.require(
                row["actual_source_hash"]
                == EXPECTED_SOURCE_HASHES[old["folds"][fold]["validation_season"]],
                "S3_ACTUAL_AUTHORITY_INVALID",
            )
        t.require(
            len(prior) == public["folds"][fold]["scored_row_count"], "S3_SCORED_ROW_COUNT_CHANGED"
        )
        reconstructed_folds[fold] = [
            {**row, "O1": forecasts[fold][row["target_row_key"]]} for row in prior
        ]
    guard.begin_score()
    events.append("S4_TEMPORAL_SCORING_STARTED")
    windows = {}
    for fold in t.S3_SEALS:
        reconstructed = reconstructed_folds[fold]
        views = complete_horizon_views(
            reconstructed, boundary=business_boundary(old["folds"][fold]["validation_season"])
        )["H15"]
        windows[fold] = t.complete_windows(views)
        t.require(
            len(windows[fold]) == (1043 if fold == "fold_a" else 2921),
            "S3_H15_AUTHORITY_PARITY_FAILED",
        )
        for model in e.MODELS:
            t.require(
                e.metric(views, model)["pooled_wape"]
                == public["metrics"][fold]["H15"][model]["pooled_wape"],
                "S3_H15_WAPE_PARITY_FAILED",
            )
        write_rows(args.output / fold / "scored-rows.jsonl", reconstructed)
        events.append("S4_SCORE_READY:" + fold)
    windows["combined"] = windows["fold_a"] + windows["fold_b"]
    combined_rows = [row for window in windows["combined"] for row in window]
    for model in e.MODELS:
        t.require(
            e.metric(combined_rows, model)["pooled_wape"]
            == public["metrics"]["combined"]["H15"][model]["pooled_wape"],
            "S3_COMBINED_H15_WAPE_PARITY_FAILED",
        )
    result["temporal_metrics"] = {
        scope: {m: t.temporal_metrics(w, m) for m in (*e.MODELS, "O1")}
        for scope, w in windows.items()
    }
    gates, timing, family = t.timing_gates(result["temporal_metrics"])
    result.update(
        timing_gates=gates,
        peak_timing_incremental_value=timing,
        peak_timing_supported_family=family,
    )
    result["oracle_comparisons"] = {}
    for model in ("M1", "M0"):
        deltas = {
            s: t.metric_delta(metrics[model], metrics["O1"])
            for s, metrics in result["temporal_metrics"].items()
        }
        result["oracle_comparisons"]["ORACLE_VS_" + model] = dict(
            deltas=deltas,
            both_dates_improve_combined=all(
                Decimal(deltas["combined"][k]) < 0 for k in ("single_date_mae", "rolling7_date_mae")
            ),
            both_dates_improve_every_fold=all(
                Decimal(deltas[s][k]) < 0
                for s in ("fold_a", "fold_b")
                for k in ("single_date_mae", "rolling7_date_mae")
            ),
            shape_not_degrade_combined=deltas["combined"]["shape_error"] is not None
            and Decimal(deltas["combined"]["shape_error"]) <= 0,
            support_classification="NOT_APPLICABLE_RESEARCH_UPPER_BOUND_ONLY",
        )
    t.verify_s3(args.s3, public)
    for fold in t.S3_SEALS:
        guard.verify_seal(fold)
    after = {k: file_identity(p) for k, p in inputs.items()}
    t.require(before == after, "SOURCE_ARTIFACT_MUTATED")
    postscore_identity = {fold: access.capture_s3_identity(fold) for fold in t.S3_SEALS}
    t.require(postseal_initial == postscore_identity, "S3_SCORED_ROWS_MUTATED")
    result.update(
        previous_result="BLOCKED",
        previous_blocker="S3_LABEL_BEARING_ARTIFACT_OPENED_BEFORE_ORACLE_SEALS",
        previous_blocker_closed=True,
        custody_correction="REMOVE_S3_SCORED_ROWS_FROM_PRESEAL_FILE_IDENTITY_INVENTORY",
        sha256_counts_as_byte_read=True,
        preseal_label_bearing_artifact_access_count=access.preseal_label_access_count,
        first_label_bearing_access_after_both_oracle_seals=True,
        prior_unaccepted_diagnostic_results_existed=True,
        R2_result_blind=False,
        prior_results_used_for_tuning=False,
        scientific_contract_changed_after_diagnostic=False,
        feature_contract_changed_after_diagnostic=False,
        metric_contract_changed_after_diagnostic=False,
        cohort_changed_after_diagnostic=False,
        S3_public_authority_parity_preseal="PASS",
        S3_label_free_prediction_authority_parity_preseal="PASS",
        S3_row_level_h15_authority_replay_postseal="PASS",
        S3_scored_rows_unchanged_during_S4=True,
        scored_rows_identity={
            fold: dict(
                post_seal_initial=postseal_initial[fold], post_score=postscore_identity[fold]
            )
            for fold in t.S3_SEALS
        },
        events=events,
        h15_counts={s: len(w) for s, w in windows.items()},
        oracle_cohort_loss=0,
        source_immutability={k: dict(before=before[k], after=after[k]) for k in before},
        sources_unchanged=True,
        S3_predictions_unchanged=True,
        lane_a_retrained=False,
        lane_a_predictions_regenerated=False,
        no_post_result_tuning=True,
        prospective_accuracy_validated=False,
        production_use_approved=False,
        oracle_deployable=False,
        oracle_prospective_equivalent=False,
        S5_authorized=False,
        version_complete=False,
        S3_h15_wape_parity="PASS",
        V0_13_S4_COMPLETE=True,
    )
    result["lane_a_temporal_hash"] = digest(
        {
            s: {m: v for m, v in metrics.items() if m != "O1"}
            for s, metrics in result["temporal_metrics"].items()
        }
    )
    result["oracle_temporal_hash"] = digest(
        {s: metrics["O1"] for s, metrics in result["temporal_metrics"].items()}
    )
    result["result_hash"] = digest(result)
    write(args.output / "sanitized-evidence.json", result)
    print(json.dumps(dict(status="PASS", result_hash=result["result_hash"], timing=timing)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "source23",
        "source24",
        "source25",
        "weather",
        "registry",
        "identity",
        "members",
        "rows",
        "s3",
        "output",
    ):
        parser.add_argument("--" + option, type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
