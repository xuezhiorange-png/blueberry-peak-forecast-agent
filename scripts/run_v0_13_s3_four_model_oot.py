"""Explicit-input, create-only S3 operator workflow; no parameter search."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import gdd_features as g
from backend.app.area_yield import v013_feature_value_experiment as e
from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.weather_aware_backtest import (
    MODEL_A_S3,
    MODEL_B1,
    RollingTargetRow,
    _base_feature_values,
    fit_ridge_artifact,
)
from backend.app.area_yield.weather_features import build_feature_row, load_era5_daily_jsonl
from backend.app.area_yield.weather_value_conclusion import (
    S3_PRIMARY_WAPE_REFERENCE,
    complete_horizon_views,
)
from scripts.run_v0_13_s2_gdd_feature_audit import FROZEN, file_identity, frozen_business_boundary
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

GDD_HASHES = dict(
    context_identity_hash="9b84828d74579e0d23d735476dbec8f92f98245e0d7f1b21f2d70088638bbc35",
    feature_value_hash="bf777313de5a7b1f0581afc220296a29fe23f09f578b07c048eb423ddae8bedb",
    manifest_hash="0ebfd32070d6479a470d340ccf7265cd7402644da7e5b4e5b8fb3b77222df41c",
)
REGISTRY_HASH = "0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85"
IDENTITY_HASH = "850f89d0286825fc61c8165a6b0ef0e23e5fb50a323cfebcb956bc60dd0818b8"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def require(value: bool, code: str) -> None:
    if not value:
        raise e.ExperimentError(code)


def run(args: argparse.Namespace) -> dict[str, Any]:
    e.validate_contract(e.CONTRACT)
    require(not args.output.exists(), "OUTPUT_ALREADY_EXISTS")
    public_path = Path("docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json")
    require(
        g.sha256(public_path) == "cc3e81003463377dd4fe8d0adc792dc453e68c5391c8fcf98a9ceb038a4d121b",
        "FROZEN_V07_PUBLIC_AUTHORITY_CHANGED",
    )
    public = read(public_path)
    sources = dict(
        zip(
            ("2023-2024", "2024-2025", "2025-2026"),
            (args.source23, args.source24, args.source25),
            strict=True,
        )
    )
    inputs = {
        **sources,
        "weather": args.weather,
        "registry": args.registry,
        "identity": args.identity,
        "members": args.members,
        "gdd_contexts": args.gdd / "gdd-contexts.jsonl",
        "gdd_manifest": args.gdd / "gdd-manifest.json",
        "row_identities": args.gdd / "frozen-row-identities.json",
    }
    before = {key: file_identity(path) for key, path in inputs.items()}
    for season, expected in EXPECTED_SOURCE_HASHES.items():
        require(before[season]["sha256"] == expected, "FROZEN_HARVEST_SOURCE_HASH_MISMATCH")
    require(before["weather"]["sha256"] == WEATHER_DATASET_HASH, "WEATHER_SOURCE_HASH_MISMATCH")
    registry, registry_hash = load_registry(args.registry)
    require(registry_hash == REGISTRY_HASH, "REGISTRY_IDENTITY_MISMATCH")
    accepted, candidates, identity_hash, _ = load_identity_mapping(args.identity, args.members)
    require(identity_hash == IDENTITY_HASH, "IDENTITY_MAPPING_MISMATCH")
    contexts = [json.loads(line) for line in inputs["gdd_contexts"].read_text().splitlines()]
    manifest = g.build_gdd_manifest(contexts, WEATHER_DATASET_HASH)
    require(manifest == read(inputs["gdd_manifest"]), "GDD_MANIFEST_CHANGED")
    require(
        manifest["context_count"] == 14023 and all(manifest[k] == v for k, v in GDD_HASHES.items()),
        "GDD_IDENTITY_CHANGED_AFTER_S2",
    )
    context_by_key = {(r["base_id"], r["forecast_origin"]): r for r in contexts}
    identities = read(inputs["row_identities"])
    for name in ("fold_a", "fold_b"):
        frozen = FROZEN[name.upper()]
        e.verify_keys(
            identities[name]["train"], int(str(frozen["count"])), str(frozen["keys_hash"])
        )
        e.verify_keys(
            identities[name]["validation"],
            int(str(frozen["validation_count"])),
            str(frozen["validation_hash"]),
        )
        frozen_business_boundary(public["folds"][name])
    observations: dict[str, list[Any]] = defaultdict(list)
    for observation in load_era5_daily_jsonl(
        args.weather, source_dataset_hash=WEATHER_DATASET_HASH
    ):
        observations[observation.base_id].append(observation)
    bases = {r["base_id"]: r for r in registry["bases"]}
    weather_cache: dict[tuple[str, str], Any] = {}
    row_cache: dict[str, RollingTargetRow] = {}

    def rows(keys: list[str]) -> list[RollingTargetRow]:
        result = []
        for key in keys:
            if key not in row_cache:
                base, origin, target = g.parse_row_key(key)
                context = context_by_key[(base, origin)]
                g.verify_context(context)
                origin_dt = datetime.fromisoformat(origin)
                cache_key = (base, origin)
                if cache_key not in weather_cache:
                    weather_cache[cache_key] = build_feature_row(
                        observations=observations[base],
                        base_id=base,
                        forecast_origin=origin_dt,
                        target_start=origin_dt.date(),
                        target_end=origin_dt.date(),
                        source_dataset_hash=WEATHER_DATASET_HASH,
                    )
                weather = weather_cache[cache_key]
                year = target.year if target.month >= 7 else target.year - 1
                season = f"{year}-{year + 1}"
                area = Decimal(str(bases[base]["productive_area_mu"]))
                values = {
                    **_base_feature_values(
                        reference_area_mu=area,
                        target_date=target,
                        boundary=business_boundary(season),
                    ),
                    **weather.features,
                    **{k: context[k] for k in ("gdd_w7", "gdd_w14", "gdd_w30")},
                }
                row_cache[key] = RollingTargetRow(
                    key=key,
                    base_id=base,
                    base_name=str(bases[base]["canonical_base_name"]),
                    season=season,
                    forecast_origin=origin,
                    target_date=target,
                    lead_day=(target - origin_dt.date()).days,
                    reference_area_mu=area,
                    feature_values=tuple(sorted(values.items())),
                    weather_feature_hash=weather.feature_hash,
                )
            result.append(row_cache[key])
        return result

    args.output.mkdir(parents=True)
    guard = e.ExecutionGuard(args.output)
    actuals: dict[str, dict[tuple[str, Any], Any]] = {}
    events: list[str] = []

    def open_labels(season: str) -> None:
        guard.allow_label_read(season)
        parsed = load_source(sources[season], season)
        actual = _actual_rows(
            parsed=parsed,
            season=season,
            accepted=accepted,
            candidates=candidates,
            registry=registry,
        )
        actuals[season] = {(base, day.day): day for base, days in actual.items() for day in days}
        events.append(f"READ_LABELS:{season}")

    def bind(row: RollingTargetRow) -> Any:
        actual = actuals[row.season].get((row.base_id, row.target_date))
        return e.authoritative_actual(actual)

    forecasts: dict[str, list[dict[str, Any]]] = {}
    report: dict[str, Any] = {
        "schema": "V0_13_S3_CONTROLLED_OOT_V1",
        "contract": e.CONTRACT,
        "source_hashes": {k: v["sha256"] for k, v in before.items()},
        "gdd_manifest": manifest,
        "folds": {},
    }
    open_labels("2023-2024")
    for name in ("fold_a", "fold_b"):
        fold = public["folds"][name]
        if name == "fold_b":
            open_labels("2024-2025")
        training = rows(identities[name]["train"])
        labeled = []
        for row in training:
            actual = bind(row)
            require(actual is not None, "FROZEN_TRAIN_ROW_LABEL_AUTHORITY_MISMATCH")
            labeled.append((row, actual.quantity_kg))
        validation = rows(identities[name]["validation"])
        output = args.output / name
        output.mkdir()
        models = {}
        artifact_evidence = {}
        for model, model_id in e.MODELS.items():
            guard.allow_fit()
            input_hash = _training_input_hash(
                fold_id=fold["fold_id"],
                training_rows=labeled,
                feature_names=e.FEATURES[model],
                training_seasons=fold["train_seasons"],
                weather_source_hash=WEATHER_DATASET_HASH,
            )
            if model in {"M2", "M3"}:
                input_hash = digest(
                    {"ridge_input": input_hash, "gdd_manifest_hash": manifest["manifest_hash"]}
                )
            fitted = fit_ridge_artifact(
                model_id=model_id,
                fold_id=fold["fold_id"],
                rows=labeled,
                feature_names=e.FEATURES[model],
                training_input_hash=input_hash,
            )
            require(
                fitted.training_label_hash == FROZEN[name.upper()]["training_label_hash"],
                "TRAINING_LABEL_HASH_PARITY_FAILED",
            )
            payload = fitted.payload_without_hash()
            keys = payload.pop("training_row_keys")
            payload.update(
                schema="V0_13_RIDGE_ARTIFACT_V1",
                model_role="FEATURE_VALUE_EXPERIMENT_MODELS",
                standardization=e.CONTRACT["standardization"],
                zero_std_policy="SCALE_1",
                training_row_count=len(keys),
                training_row_keys_hash=digest(keys),
            )
            payload["artifact_hash"] = digest(payload)
            e.verify_artifact(payload)
            evidence = {
                k: payload[k]
                for k in (
                    "artifact_hash",
                    "training_row_count",
                    "training_row_keys_hash",
                    "training_label_hash",
                    "training_input_hash",
                )
            }
            evidence.update(
                direct_self_hash_valid=True,
                feature_count=len(e.FEATURES[model]),
                feature_schema_hash=digest(list(e.FEATURES[model])),
            )
            if model in {"M0", "M1"}:
                old = fold["model_a" if model == "M0" else "model_b"]
                compatibility = fitted.payload_without_hash()
                compatibility.update(
                    model_id=MODEL_A_S3 if model == "M0" else MODEL_B1,
                    standardization=e.CONTRACT["standardization"],
                )
                compatibility_hash = digest(compatibility)
                require(
                    compatibility_hash == old["artifact_hash"],
                    "M0_M1_V0_7_REPRODUCTION_PARITY_FAILED",
                )
                for field in (
                    "feature_means",
                    "feature_scales",
                    "coefficients",
                    "intercept",
                    "training_label_hash",
                ):
                    require(payload[field] == old[field], "M0_M1_V0_7_PARAMETER_PARITY_FAILED")
                evidence.update(
                    v07_compatibility_hash=compatibility_hash, v07_parameter_parity="PASS"
                )
            write(output / f"{model.lower()}-artifact.json", payload)
            models[model] = fitted
            artifact_evidence[model] = evidence
        prediction_rows = []
        for row in validation:
            prediction_rows.append(
                dict(
                    target_row_key=row.key,
                    season=row.season,
                    base_id=row.base_id,
                    forecast_origin=row.forecast_origin,
                    target_date=row.target_date.isoformat(),
                    lead_day=row.lead_day,
                    **{model: format(fitted.predict(row), "f") for model, fitted in models.items()},
                )
            )
        prediction_hashes = {
            model: digest(
                [
                    {"target_row_key": r["target_row_key"], "prediction": r[model]}
                    for r in prediction_rows
                ]
            )
            for model in e.MODELS
        }
        for model, old_field in (
            ("M0", "model_a_prediction_hash"),
            ("M1", "model_b_prediction_hash"),
        ):
            require(
                prediction_hashes[model] == fold["prediction_manifest"][old_field],
                "M0_M1_PREDICTION_HASH_PARITY_FAILED",
            )
        write_rows(output / "predictions-before-scoring.jsonl", prediction_rows)
        seal = dict(
            fold_id=fold["fold_id"],
            validation_season=fold["validation_season"],
            common_validation_row_count=len(validation),
            common_validation_row_keys_hash=digest([r.key for r in validation]),
            model_ids=list(e.MODELS.values()),
            artifact_hashes={m: v["artifact_hash"] for m, v in artifact_evidence.items()},
            prediction_hashes=prediction_hashes,
            weather_source_hash=WEATHER_DATASET_HASH,
            gdd_manifest_hash=manifest["manifest_hash"],
            business_boundary=frozen_business_boundary(fold),
            sealed_before_validation_label_read=True,
            file_hashes={p.name: g.sha256(p) for p in sorted(output.iterdir())},
        )
        seal["seal_hash"] = digest(seal)
        write(output / "prediction-seal.json", seal)
        guard.verify_seal(name)
        events.append(f"SEALED:{name}")
        forecasts[name] = prediction_rows
        report["folds"][name] = dict(
            models=artifact_evidence,
            prediction_hashes=prediction_hashes,
            seal_hash=seal["seal_hash"],
            training_row_count=len(training),
            training_row_keys_hash=digest([r.key for r in training]),
            validation_row_count=len(validation),
            validation_row_keys_hash=digest([r.key for r in validation]),
        )
    guard.begin_score()
    events.append("BOTH_FOLDS_VERIFIED_BEFORE_SCORE")
    scored_views = {}
    for name in ("fold_a", "fold_b"):
        fold = public["folds"][name]
        if name == "fold_b":
            open_labels("2025-2026")
        scored = []
        for prediction in forecasts[name]:
            actual = bind(row_cache[prediction["target_row_key"]])
            if actual is not None:
                scored.append(
                    {
                        **prediction,
                        "actual_daily_kg": format(actual.quantity_kg, "f"),
                        "actual_status": actual.status,
                        "actual_source_hash": actual.source_hash,
                    }
                )
        require(
            len(scored) == fold["validation_scored_row_count"],
            "VALIDATION_ACTUAL_AUTHORITY_PARITY_FAILED",
        )
        write_rows(args.output / name / "scored-rows.jsonl", scored)
        views = complete_horizon_views(
            scored, boundary=business_boundary(fold["validation_season"])
        )
        scored_views[name] = views
        report["folds"][name].update(
            scored_row_count=len(scored), unscored_row_count=len(forecasts[name]) - len(scored)
        )
        events.append(f"SCORED:{name}")
    scored_views["combined"] = {
        h: scored_views["fold_a"][h] + scored_views["fold_b"][h] for h in ("H1", "H7", "H15")
    }
    metrics: dict[str, Any] = {}
    for scope, views in scored_views.items():
        metrics[scope] = {}
        for horizon, selected in views.items():
            metrics[scope][horizon] = {
                model: {
                    **e.metric(selected, model),
                    "total_signed_bias_kg": str(
                        sum(
                            (Decimal(r[model]) - Decimal(r["actual_daily_kg"]) for r in selected),
                            Decimal(0),
                        )
                    ),
                    "cumulative": e.cumulative_metric(
                        selected, model, {"H1": 1, "H7": 7, "H15": 15}[horizon]
                    ),
                }
                for model in e.MODELS
            }
            require(
                tuple(metrics[scope][horizon][m]["pooled_wape"] for m in ("M0", "M1"))
                == S3_PRIMARY_WAPE_REFERENCE[scope][horizon],
                "M0_M1_PRIMARY_WAPE_PARITY_FAILED",
            )
    report["metrics"] = metrics
    report["comparisons"] = {}
    for label, (reference, new) in e.COMPARISONS.items():
        comparison = {
            scope: {
                h: e.compare(
                    selected,
                    reference,
                    new,
                    all_base_ids=sorted(
                        {
                            r["base_id"]
                            for f in (("fold_a", "fold_b") if scope == "combined" else (scope,))
                            for r in forecasts[f]
                        }
                    ),
                )
                for h, selected in views.items()
            }
            for scope, views in scored_views.items()
        }
        report["comparisons"][label] = {"scopes": comparison, "gate": e.predictive_gate(comparison)}
    for name in ("fold_a", "fold_b"):
        guard.verify_seal(name)
    after = {k: file_identity(p) for k, p in inputs.items()}
    require(before == after, "SOURCE_ARTIFACT_MUTATED")
    report.update(
        events=events,
        source_artifacts_unchanged=True,
        source_immutability={key: {"before": before[key], "after": after[key]} for key in before},
        predictions_unchanged_after_scoring=True,
        both_folds_sealed_before_any_metric=True,
        no_post_result_tuning=True,
        prospective_accuracy_validated=False,
        production_use_approved=False,
        peak_metrics_executed=False,
        oracle_executed=False,
        S4_authorized=False,
        S5_authorized=False,
    )
    report["score_hash"] = digest(metrics)
    report["comparison_hash"] = digest(report["comparisons"])
    report["support_gate_hash"] = digest({k: v["gate"] for k, v in report["comparisons"].items()})
    report["report_hash"] = digest(report)
    write(args.output / "sanitized-evidence.json", report)
    print(json.dumps({"status": "PASS", "report_hash": report["report_hash"]}))
    return report


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
        "gdd",
        "output",
    ):
        parser.add_argument(f"--{option}", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
