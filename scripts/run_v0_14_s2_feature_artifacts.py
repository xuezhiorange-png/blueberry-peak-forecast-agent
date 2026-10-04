"""Explicit operator-only S2 workflow: qualification, single pair fit, no scores."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from backend.app.area_yield import v014_future_weather_features as f
from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.gdd_features import parse_row_key
from backend.app.area_yield.weather_aware_backtest import (
    BASE_FEATURES,
    RollingTargetRow,
    _base_feature_values,
    _label_hash,
    fit_ridge_artifact,
)
from backend.app.pit.shadow_forecast import WeatherForecastProviderError
from scripts.run_v07_s1_formal_validation import (
    EXPECTED_SOURCE_HASHES,
    load_identity_mapping,
    load_registry,
    load_source,
)
from scripts.run_v07_s3_weather_aware_backtest import _actual_rows

PARENT_COUNT = 59471
PARENT_HASH = "5ee82a037b7c8a0d1cc396ad69ffb92421e44b40d57d8a89c87567b8027a97d4"
PARENT_LABEL_HASH = "97169c277b1ae737ab6b01a202defedf36c0f87dc69e2535b33afab146699eac"
MODELS = {
    "c0": "V0_14_C0_BASE_ONLY_PROSPECTIVE_COMPARATOR",
    "w1": "V0_14_W1_AS_ISSUED_WEATHER_PROSPECTIVE_CANDIDATE",
}


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"sha256": sha(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def verify_bundle(root: Path) -> dict[str, Any]:
    manifest = read(root / "bundle-manifest.json")
    f.require(digest(manifest["files"]) == manifest["bundle_hash"], "BUNDLE_HASH_MISMATCH")
    for entry in manifest["files"]:
        name = Path(entry["name"])
        f.require(not name.is_absolute() and len(name.parts) == 1, "UNSAFE_BUNDLE_PATH")
        path = root / name
        f.require(
            sha(path) == entry["sha256"] and path.stat().st_size == entry["size"],
            "BUNDLE_FILE_MISMATCH",
        )
    for model_name in ("c0", "w1"):
        f.verify_artifact(read(root / f"{model_name}-artifact.json"))
    f.validate_policy(read(root / "feature-policy.json"))
    f.verify_pair(read(root / "c0-artifact.json"), read(root / "w1-artifact.json"))
    cohort = read(root / "training-cohort-manifest.json")
    f.require(
        cohort["train_seasons"] == f.POLICY["train_seasons"]
        and cohort["parent_row_count"] == PARENT_COUNT
        and cohort["parent_row_key_hash"] == PARENT_HASH
        and len(cohort["training_row_keys"]) == cohort["training_row_count"]
        and digest(cohort["training_row_keys"]) == cohort["training_row_key_hash"],
        "BUNDLE_COHORT_MISMATCH",
    )
    for model_name in ("c0", "w1"):
        model = read(root / f"{model_name}-artifact.json")
        f.require(model["training_cohort_hash"] == digest(cohort), "BUNDLE_COHORT_MISMATCH")
        for key in ("training_row_count", "training_row_key_hash", "training_label_hash"):
            f.require(model[key] == cohort[key], "BUNDLE_COHORT_MISMATCH")
    f.require(
        {entry["name"] for entry in manifest["files"]}
        == {
            "feature-policy.json",
            "training-cohort-manifest.json",
            "c0-artifact.json",
            "w1-artifact.json",
            "historical-proxy-manifest.json",
            "live-feature-surface-manifest.json",
        },
        "BUNDLE_MEMBER_MISMATCH",
    )
    return cast(dict[str, Any], manifest)


def qualify_live(args: argparse.Namespace) -> None:
    f.require(not args.output.exists(), "OUTPUT_ALREADY_EXISTS")
    provider = f.ECMWFDenseFeatureSurfaceProvider(
        location_authority_path=args.locations, artifact_root=args.cache
    )
    surface = None
    for candidate in provider._candidate_runs(datetime.now(UTC)):
        try:
            surface = provider.capture_feature_surface(issued_at=candidate)
            break
        except WeatherForecastProviderError:
            continue
    f.require(surface is not None, "NO_COMPLETE_W1_LIVE_SURFACE")
    assert surface is not None
    matrices = []
    for _ in range(2):
        replay = provider.capture_feature_surface(
            issued_at=datetime.fromisoformat(surface["issued_at"])
        )
        matrix = [
            {"base_id": base, "features": f.aggregate_ifs(fields)}
            for base, fields in sorted(replay["fields_by_base"].items())
        ]
        matrices.append(matrix)
    f.require(
        matrices[0] == matrices[1] and len(matrices[0]) == 39,
        "LIVE_FEATURE_REPLAY_OR_COVERAGE_MISMATCH",
    )
    args.output.mkdir(parents=True)
    write(args.output / "live-features.json", matrices[0])
    manifest = {
        "schema": "V0_14_LIVE_FEATURE_SURFACE_V1",
        "role": "QUALIFICATION_ONLY",
        "run_id": surface["run_id"],
        "issued_at": surface["issued_at"],
        "base_count": 39,
        "feature_count": 8,
        "feature_policy_hash": digest(f.POLICY),
        "feature_matrix_hash": digest(matrices[0]),
        "raw_manifest_sha256": surface["raw_manifest_sha256"],
        "live_feature_values_equal": True,
        "live_feature_matrix_hash_equal": True,
    }
    write(args.output / "live-feature-surface-manifest.json", manifest)
    write(args.output / "acquisition-receipt.json", surface["acquisition_receipt"])
    print(json.dumps(manifest, sort_keys=True))


def load_hourly(
    path: Path, bases: set[str], lo: datetime, hi: datetime
) -> dict[str, dict[tuple[int, str], Decimal]]:
    index: dict[str, dict[tuple[int, str], Decimal]] = {}
    count = 0
    content = hashlib.sha256()
    units = {"t2m": "degC", "u10": "m s-1", "v10": "m s-1", "tp": "mm", "ssrd": "J m-2"}
    with gzip.open(path, "rb") as stream:
        for line in stream:
            content.update(line)
            count += 1
            row = json.loads(line)
            f.require(row["processing_version"] == f.HOURLY_LAYER, "WRONG_ERA5_LAYER")
            base, variable = row["base_id"], row["native_variable"]
            if base not in bases or variable not in units:
                continue
            valid = datetime.fromisoformat(row["valid_time_utc"])
            if not lo < valid <= hi:
                continue
            f.require(row["normalized_unit"] == units[variable], "WRONG_ERA5_UNIT")
            interval = variable in {"tp", "ssrd"}
            f.require(
                row["temporal_semantics"]
                == (
                    "PROVIDER_DEACCUMULATED_HOURLY_INTERVAL_END" if interval else "INSTANT_AT_START"
                ),
                "WRONG_ERA5_TIME_SEMANTICS",
            )
            start, end = (
                datetime.fromisoformat(row[k]) for k in ("support_start_utc", "support_end_utc")
            )
            f.require(
                end - start == timedelta(hours=1) and valid == (end if interval else start),
                "WRONG_ERA5_INTERVAL",
            )
            key = int(valid.timestamp()), variable
            values = index.setdefault(base, {})
            f.require(key not in values, "DUPLICATE_HOURLY_ROW")
            values[key] = f.decimal(row["normalized_value"])
    f.require(
        count == f.HOURLY_COUNT and content.hexdigest() == f.HOURLY_DATASET_HASH,
        "HISTORICAL_HOURLY_WEATHER_AUTHORITY_MISMATCH",
    )
    return index


def fit(args: argparse.Namespace) -> None:
    f.validate_policy(f.POLICY)
    f.require(not args.output.exists(), "OUTPUT_ALREADY_EXISTS")
    s1 = Path("docs/v0-14/evidence/v0.14-s1-ecmwf-as-issued-surface-qualification-r1.json")
    f.require(sha(s1) == f.S1_SHA, "S1_EVIDENCE_CHANGED")
    paths = {
        "hourly": args.hourly,
        "hourly_manifest": args.hourly.parent / "dataset-manifest.json",
        "identities": args.identities,
        "registry": args.registry,
        "identity": args.identity,
        "members": args.members,
        "2023-2024": args.source23,
        "2024-2025": args.source24,
        "live_features": args.live / "live-features.json",
        "live_manifest": args.live / "live-feature-surface-manifest.json",
    }
    before = {k: identity(v) for k, v in paths.items()}
    f.require(
        before["hourly"]["sha256"] == f.HOURLY_SHA, "HISTORICAL_HOURLY_WEATHER_AUTHORITY_MISMATCH"
    )
    weather_manifest = read(paths["hourly_manifest"])
    for key, expected in {
        "hourly_row_count": f.HOURLY_COUNT,
        "hourly_dataset_hash": f.HOURLY_DATASET_HASH,
        "hourly_artifact_sha256": f.HOURLY_SHA,
        "source_manifest_hash": f.SOURCE_MANIFEST_HASH,
        "raw_artifact_set_hash": f.RAW_SET_HASH,
        "provider_deaccumulation_used": True,
    }.items():
        f.require(
            weather_manifest.get(key) == expected, "HISTORICAL_HOURLY_WEATHER_AUTHORITY_MISMATCH"
        )
    keys = read(args.identities)["fold_b"]["train"]
    f.require(
        len(keys) == PARENT_COUNT and keys == sorted(set(keys)) and digest(keys) == PARENT_HASH,
        "PARENT_TRAIN_UNIVERSE_MISMATCH",
    )
    registry, registry_hash = load_registry(args.registry)
    accepted, candidates, identity_hash, _ = load_identity_mapping(args.identity, args.members)
    f.require(
        registry_hash == "0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85"
        and identity_hash == "850f89d0286825fc61c8165a6b0ef0e23e5fb50a323cfebcb956bc60dd0818b8",
        "TRAINING_IDENTITY_AUTHORITY_MISMATCH",
    )
    for season in f.POLICY["train_seasons"]:
        f.require(
            before[season]["sha256"] == EXPECTED_SOURCE_HASHES[season],
            "TRAINING_SOURCE_HASH_MISMATCH",
        )
    live = read(paths["live_manifest"])
    f.require(
        digest(read(paths["live_features"])) == live["feature_matrix_hash"]
        and live["feature_policy_hash"] == digest(f.POLICY)
        and live["base_count"] == 39,
        "LIVE_FEATURE_AUTHORITY_MISMATCH",
    )
    parsed = [(key, *parse_row_key(key)) for key in keys]
    anchors = {
        origin: f.synthetic_anchor(datetime.fromisoformat(origin)) for _, _, origin, _ in parsed
    }
    hourly = load_hourly(
        args.hourly,
        {base for _, base, _, _ in parsed},
        min(anchors.values()),
        max(anchors.values()) + timedelta(hours=360),
    )
    print("HOURLY_AUTHORITY_AND_INPUT_IDENTITIES_PASS", flush=True)
    proxy: dict[tuple[str, str], dict[str, str] | None] = {}
    reasons = {"PROXY_INCOMPLETE": 0, "WEATHER_BASE_UNAVAILABLE": 0, "OTHER": 0}
    needed = {(s, p) for s in f.STEPS for p in ("t2m", "u10", "v10")} | {
        (s, p) for s in range(1, 361) for p in ("tp", "ssrd")
    }
    bases = {r["base_id"]: r for r in registry["bases"]}
    rows = []
    parent_rows = []
    for key, base, origin, target in parsed:
        year = target.year if target.month >= 7 else target.year - 1
        season = f"{year}-{year + 1}"
        f.require(season in f.POLICY["train_seasons"], "FORBIDDEN_TRAINING_SEASON")
        area = Decimal(str(bases[base]["productive_area_mu"]))
        base_values = _base_feature_values(
            reference_area_mu=area, target_date=target, boundary=business_boundary(season)
        )
        row = RollingTargetRow(
            key,
            base,
            str(bases[base]["canonical_base_name"]),
            season,
            origin,
            target,
            (target - datetime.fromisoformat(origin).date()).days,
            area,
            tuple(sorted(base_values.items())),
            "",
        )
        parent_rows.append(row)
        cache_key = base, origin
        if cache_key not in proxy:
            anchor = int(anchors[origin].timestamp())
            values = {
                (s, p): hourly[base][anchor + s * 3600, p]
                for s, p in needed
                if base in hourly and (anchor + s * 3600, p) in hourly[base]
            }
            proxy[cache_key] = f.aggregate_proxy(values) if set(values) == needed else None
        feature_values = proxy[cache_key]
        if feature_values is None:
            reasons["WEATHER_BASE_UNAVAILABLE" if base not in hourly else "PROXY_INCOMPLETE"] += 1
            continue
        rows.append(
            RollingTargetRow(
                key,
                row.base_id,
                row.base_name,
                row.season,
                row.forecast_origin,
                row.target_date,
                row.lead_day,
                area,
                tuple(sorted({**base_values, **feature_values}.items())),
                digest(feature_values),
            )
        )
    del hourly
    actuals = {}
    for season, path in (("2023-2024", args.source23), ("2024-2025", args.source24)):
        actual = _actual_rows(
            parsed=load_source(path, season),
            season=season,
            accepted=accepted,
            candidates=candidates,
            registry=registry,
        )
        actuals.update(
            {(season, base, day.day): day for base, days in actual.items() for day in days}
        )

    def label(row: RollingTargetRow) -> Decimal:
        actual = actuals.get((row.season, row.base_id, row.target_date))
        f.require(
            actual is not None
            and actual.status in {"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"}
            and actual.quantity_kg is not None,
            "FROZEN_TRAIN_ROW_LABEL_AUTHORITY_MISMATCH",
        )
        assert actual is not None and actual.quantity_kg is not None
        return actual.quantity_kg

    f.require(
        _label_hash([(row, label(row)) for row in parent_rows]) == PARENT_LABEL_HASH,
        "PARENT_TRAINING_LABEL_HASH_MISMATCH",
    )
    labeled = [(row, label(row)) for row in rows]
    row_keys = [row.key for row in rows]
    cohort = {
        "schema": "V0_14_TRAIN_COHORT_V1",
        "parent": "V0_13_FOLD_B_TRAINING_ROW_UNIVERSE",
        "parent_row_count": PARENT_COUNT,
        "parent_row_key_hash": PARENT_HASH,
        "train_seasons": f.POLICY["train_seasons"],
        "training_row_count": len(rows),
        "training_base_count": len({row.base_id for row in rows}),
        "training_row_key_hash": digest(row_keys),
        "training_label_hash": _label_hash(labeled),
        "exclusion_counts": reasons,
        "training_row_keys": row_keys,
    }
    cohort_hash = digest(cohort)
    artifacts = {}
    for name in ("c0", "w1"):
        features = BASE_FEATURES + (f.FEATURE_NAMES if name == "w1" else ())
        trained = fit_ridge_artifact(
            model_id=MODELS[name],
            fold_id="V0_14_PROSPECTIVE_TRAIN",
            rows=labeled,
            feature_names=features,
            training_input_hash=digest(
                {"cohort": cohort_hash, "policy": digest(f.POLICY), "features": features}
            ),
        )
        artifact = {
            "schema": f"V0_14_{name.upper()}_RIDGE_ARTIFACT_V1",
            "model_id": MODELS[name],
            "model_role": "PROSPECTIVE_COMPARATOR" if name == "c0" else "PROSPECTIVE_CANDIDATE",
            "feature_names": list(features),
            "feature_policy_hash": digest(f.POLICY),
            "training_cohort_hash": cohort_hash,
            "training_row_count": len(rows),
            "training_row_key_hash": digest(row_keys),
            "training_label_hash": trained.training_label_hash,
            "training_input_hash": trained.training_input_hash,
            "model_family": "RIDGE_LEAST_SQUARES",
            "alpha": "10.000000",
            "solver": trained.solver,
            "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
            "zero_std_policy": "SCALE_1",
            "intercept_unpenalized": True,
            "nonnegative_output_clip": True,
            "feature_means": list(trained.feature_means),
            "feature_scales": list(trained.feature_scales),
            "coefficients": list(trained.coefficients),
            "intercept": trained.intercept,
            "created_under_version": "0.14.0",
            "prospective_role": name.upper(),
            "production_approved": False,
        }
        artifact["artifact_hash"] = digest(artifact)
        f.verify_artifact(artifact)
        artifacts[name] = artifact
    f.verify_pair(artifacts["c0"], artifacts["w1"])
    args.output.mkdir(parents=True)
    write(args.output / "feature-policy.json", f.POLICY)
    write(args.output / "training-cohort-manifest.json", cohort)
    for name, artifact in artifacts.items():
        write(args.output / f"{name}-artifact.json", artifact)
        f.require(
            f.synthetic_request_check(artifact)
            == f.synthetic_request_check(read(args.output / f"{name}-artifact.json")),
            "SYNTHETIC_REQUEST_RELOAD_PARITY_FAILED",
        )
    proxy_manifest = {
        "schema": "V0_14_HISTORICAL_PROXY_MANIFEST_V1",
        "hourly_dataset_hash": f.HOURLY_DATASET_HASH,
        "hourly_artifact_sha256": f.HOURLY_SHA,
        "proxy_mapping_status": "QUALIFIED_FOR_V0_14_RUN_RELATIVE_PROXY_R1",
        "as_issued": False,
        "known_at_reconstructed": False,
        "domain_shift_exists": True,
        "feature_policy_hash": digest(f.POLICY),
        "context_count": sum(value is not None for value in proxy.values()),
        "proxy_matrix_hash": digest(
            [
                {"base_id": base, "forecast_origin": origin, "features": values}
                for (base, origin), values in sorted(proxy.items())
                if values is not None
            ]
        ),
    }
    write(args.output / "historical-proxy-manifest.json", proxy_manifest)
    write(args.output / "live-feature-surface-manifest.json", live)
    files = [
        {
            "name": p.name,
            "sha256": sha(p),
            "size": p.stat().st_size,
            "role": "OPERATOR_OWNED_PRIVATE_RESEARCH_ARTIFACT",
        }
        for p in sorted(args.output.iterdir())
    ]
    bundle = {
        "schema": "V0_14_PRIVATE_BUNDLE_V1",
        "files": files,
        "bundle_hash": digest(files),
        "immutable": True,
    }
    write(args.output / "bundle-manifest.json", bundle)
    verify_bundle(args.output)
    f.require(before == {k: identity(v) for k, v in paths.items()}, "INPUT_ARTIFACT_CHANGED")
    print(
        json.dumps(
            {
                "feature_policy_hash": digest(f.POLICY),
                "cohort": {k: v for k, v in cohort.items() if k != "training_row_keys"},
                "c0_artifact_hash": artifacts["c0"]["artifact_hash"],
                "w1_artifact_hash": artifacts["w1"]["artifact_hash"],
                "bundle_hash": bundle["bundle_hash"],
                "source_immutability": True,
                "synthetic_request_reload_parity": True,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("live", "fit"))
    parser.add_argument("--output", type=Path, required=True)
    for name in (
        "locations",
        "cache",
        "hourly",
        "identities",
        "registry",
        "identity",
        "members",
        "source23",
        "source24",
        "live",
    ):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args()
    required = (
        ("locations", "cache")
        if args.mode == "live"
        else (
            "hourly",
            "identities",
            "registry",
            "identity",
            "members",
            "source23",
            "source24",
            "live",
        )
    )
    for name in required:
        f.require(getattr(args, name) is not None, f"MISSING_OPERATOR_INPUT:{name}")
    (qualify_live if args.mode == "live" else fit)(args)


if __name__ == "__main__":
    main()
