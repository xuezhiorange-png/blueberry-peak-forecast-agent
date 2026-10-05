"""Issue one pair or audit its immutable package; no actual or fitting interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.area_yield import v014_shadow_issuance as s
from backend.app.area_yield.data import digest
from backend.app.area_yield.v014_future_weather_features import (
    POLICY,
    REQUIRED_FIELDS,
    STEPS,
    ECMWFDenseFeatureSurfaceProvider,
    aggregate_ifs,
    require,
)
from backend.app.pit.ecmwf_open_data_provider import _find_index, _parameter_rows, _write_immutable
from backend.app.pit.shadow_forecast import WeatherForecastProviderError

BASE_SHA = "1b7868aa47b08f442149a70f239adf0cecbab73d"


def no_network(*args: Any, **kwargs: Any) -> Any:
    raise ValueError("AUDIT_NETWORK_FORBIDDEN")


def capture_latest(
    provider: ECMWFDenseFeatureSurfaceProvider, session: datetime
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    attempts = []
    for issued in provider._candidate_runs(session):
        run_id = provider._run_id(issued)
        root = provider._artifact_path(run_id, "feature-surface")
        complete = True
        # Probe the full dense index surface, longest horizon first. No GRIB is
        # downloaded for incomplete runs; absence is not substituted/imputed.
        for step in (360, 168) + tuple(x for x in STEPS if x not in {360, 168}):
            url = f"{provider._run_url(issued)}/{run_id}-{step}h-oper-fc.index"
            try:
                raw = provider._request(url)
            except WeatherForecastProviderError as exc:
                if isinstance(exc.__cause__, urllib.error.HTTPError) and exc.__cause__.code == 404:
                    complete = False
                    break
                raise
            rows = _parameter_rows(raw)
            needed = [p for st, p in REQUIRED_FIELDS if st == step]
            if any(_find_index(rows, step, p) is None for p in needed):
                complete = False
                break
            _write_immutable(root / f"{step:03d}h.index", raw)
        attempts.append(
            {"run_id": run_id, "status": "COMPLETE" if complete else "UNAVAILABLE_OR_INCOMPLETE"}
        )
        if complete:
            return provider.capture_feature_surface(issued_at=issued), attempts
    raise ValueError("SELECTED_SCOPE_W1_FEATURE_SURFACE_INCOMPLETE")


def audit(args: argparse.Namespace, models: dict[str, Any], area: Any) -> dict[str, Any]:
    root = args.output
    manifest = s.read_json(root / "issuance-manifest.json")
    require(digest(manifest["files"]) == manifest["issuance_package_hash"], "PACKAGE_HASH_MISMATCH")
    expected_names = {
        "scope-authority-snapshot.json",
        "weather-surface-manifest.json",
        "request-snapshot.json",
        "metric-contract.json",
        "c0-predictions.json",
        "w1-predictions.json",
        "prediction-seal.json",
        "cohort-entry.json",
    }
    require({e["name"] for e in manifest["files"]} == expected_names, "PACKAGE_MEMBER_MISMATCH")
    for e in manifest["files"]:
        raw = (root / e["name"]).read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == e["sha256"] and len(raw) == e["size"],
            "PACKAGE_MEMBER_TAMPER",
        )
    request = s.read_json(root / "request-snapshot.json")
    seal = s.read_json(root / "prediction-seal.json")
    weather = s.read_json(root / "weather-surface-manifest.json")
    s.verify_seal(seal)
    require(
        seal["schema"] == s.SEAL_SCHEMA
        and seal["cohort_id"] == s.COHORT_ID
        and seal["target_row_count"] == 15
        and seal["metric_contract_id"] == s.METRIC_ID
        and seal["scope_authority_hash"] == area.payload_hash
        and seal["feature_policy_hash"] == request["feature_policy_hash"] == digest(POLICY)
        and seal["actual_read_before_seal"] is False
        and seal["scoring_before_seal"] is False
        and seal["shadow"] is True
        and seal["production"] is False,
        "SEAL_CONTRACT_DRIFT",
    )
    for role in models:
        require(
            seal[f"{role}_artifact_hash"]
            == request[f"{role}_artifact_hash"]
            == models[role]["artifact_hash"],
            "SEALED_MODEL_IDENTITY_DRIFT",
        )
    require(
        digest(request) == seal["request_hash"]
        and seal["forecast_id"] == "v014_" + digest(request)[:24],
        "REQUEST_HASH_MISMATCH",
    )
    require(
        s.read_json(root / "scope-authority-snapshot.json") == area.model_dump(mode="json"),
        "SCOPE_SNAPSHOT_DRIFT",
    )
    require(
        s.read_json(root / "metric-contract.json") == s.metric_contract()
        and digest(s.metric_contract()) == seal["metric_contract_hash"],
        "METRIC_CONTRACT_DRIFT",
    )
    provider = ECMWFDenseFeatureSurfaceProvider(
        location_authority_path=args.locations, artifact_root=args.cache, urlopen=no_network
    )
    surface = provider.capture_feature_surface(
        issued_at=datetime.fromisoformat(request["provider_issued_at"])
    )
    require(
        surface["raw_manifest_sha256"]
        == weather["raw_manifest_sha256"]
        == seal["weather_raw_manifest_hash"],
        "WEATHER_MANIFEST_DRIFT",
    )
    features = aggregate_ifs(surface["fields_by_base"][s.BASE_ID])
    require(digest(features) == seal["selected_base_weather_feature_hash"], "WEATHER_FEATURE_DRIFT")
    origin = datetime.fromisoformat(request["model_forecast_origin"])
    created = datetime.fromisoformat(request["forecast_created_at"])
    s.verify_area_time(area, created, origin)
    s.verify_weather_receipt(surface, created)
    s.verify_timing(created, origin, datetime.fromisoformat(seal["sealed_at"]))
    rows = s.target_rows(area, origin, features)
    require(
        digest([r["key"] for r in rows]) == seal["target_row_keys_hash"], "TARGET_ROW_HASH_DRIFT"
    )
    predictions = s.predict_pair(models, rows)
    for role in models:
        require(
            predictions[role] == s.read_json(root / f"{role}-predictions.json")
            and digest(predictions[role]) == seal[f"{role}_prediction_hash"],
            "PREDICTION_HASH_TAMPER",
        )
    entry = s.read_json(root / "cohort-entry.json")
    require(
        entry["forecast_id"] == seal["forecast_id"]
        and entry["seal_hash"] == seal["seal_hash"]
        and entry["cohort_id"] == s.COHORT_ID,
        "COHORT_ENTRY_DRIFT",
    )
    return {
        "audit_replay": "PASS",
        "forecast_id": seal["forecast_id"],
        "c0_prediction_hash": seal["c0_prediction_hash"],
        "w1_prediction_hash": seal["w1_prediction_hash"],
        "prediction_seal_hash": seal["seal_hash"],
        "target_row_keys_hash_parity": "PASS",
        "selected_base_weather_feature_hash_parity": "PASS",
        "c0_prediction_hash_parity": "PASS",
        "w1_prediction_hash_parity": "PASS",
        "seal_self_hash_valid": True,
        "issuance_package_hash": manifest["issuance_package_hash"],
    }


def issue(args: argparse.Namespace, models: dict[str, Any], area: Any) -> dict[str, Any]:
    if args.output.exists():
        # Fixed request package identity is reused, not a second issuance.
        return {
            **audit(args, models, area),
            "idempotent_reissuance_gate": "PASS_REUSED_EXISTING_IDENTITY",
        }
    session = datetime.now(UTC)
    print("ISSUANCE_SESSION_STARTED", flush=True)
    provider = ECMWFDenseFeatureSurfaceProvider(
        location_authority_path=args.locations, artifact_root=args.cache
    )
    surface, attempts = capture_latest(provider, session)
    features = aggregate_ifs(surface["fields_by_base"][s.BASE_ID])
    created = datetime.now(UTC)
    origin = s.model_origin(created)
    s.verify_area_time(area, created, origin)
    s.verify_weather_receipt(surface, created)
    rows = s.target_rows(area, origin, features)
    metric = s.metric_contract()
    receipt = surface["acquisition_receipt"]
    request = {
        "schema": "V0_14_PROSPECTIVE_REQUEST_SNAPSHOT_V1",
        "base_id": s.BASE_ID,
        "canonical_base_name": s.BASE_NAME,
        "target_season": "2026-2027",
        "area_revision_id": area.area_revision_id,
        "area_type": area.area_type,
        "scope_authority_hash": area.payload_hash,
        "issuance_session_started_at": session.isoformat(),
        "forecast_created_at": created.isoformat(),
        "model_forecast_origin": origin.isoformat(),
        "target_start_date": rows[0]["target_date"],
        "target_end_date": rows[-1]["target_date"],
        "target_row_keys_hash": digest([r["key"] for r in rows]),
        "provider": "ECMWF_IFS_OPEN_DATA",
        "provider_run_id": surface["run_id"],
        "provider_issued_at": surface["issued_at"],
        "provider_fetched_at": receipt["fetched_at"],
        "provider_known_at": receipt["known_at"],
        "feature_policy_hash": digest(POLICY),
        "c0_artifact_hash": models["c0"]["artifact_hash"],
        "w1_artifact_hash": models["w1"]["artifact_hash"],
        "metric_contract_hash": digest(metric),
    }
    request_hash = digest(request)
    forecast_id = "v014_" + request_hash[:24]
    predictions = s.predict_pair(models, rows)
    args.output.mkdir(parents=True, exist_ok=False)
    private_weather = {
        "raw_manifest_sha256": surface["raw_manifest_sha256"],
        "raw_manifest": surface["raw_manifest"],
        "acquisition_receipt": receipt,
        "selected_base_features": features,
        "selected_base_weather_feature_hash": digest(features),
        "run_selection_attempts": attempts,
    }
    for name, body in {
        "scope-authority-snapshot.json": area.model_dump(mode="json"),
        "weather-surface-manifest.json": private_weather,
        "request-snapshot.json": request,
        "metric-contract.json": metric,
        "c0-predictions.json": predictions["c0"],
        "w1-predictions.json": predictions["w1"],
    }.items():
        s.write_immutable(args.output / name, body)
    sealed = datetime.now(UTC)
    s.verify_timing(created, origin, sealed)
    seal = s.self_seal(
        {
            "schema": s.SEAL_SCHEMA,
            "cohort_id": s.COHORT_ID,
            "forecast_id": forecast_id,
            "request_hash": request_hash,
            "scope_authority_hash": area.payload_hash,
            "weather_raw_manifest_hash": surface["raw_manifest_sha256"],
            "weather_feature_matrix_hash": digest({s.BASE_ID: features}),
            "selected_base_weather_feature_hash": digest(features),
            "feature_policy_hash": digest(POLICY),
            "c0_artifact_hash": models["c0"]["artifact_hash"],
            "w1_artifact_hash": models["w1"]["artifact_hash"],
            "target_row_count": 15,
            "target_row_keys_hash": request["target_row_keys_hash"],
            "c0_prediction_hash": digest(predictions["c0"]),
            "w1_prediction_hash": digest(predictions["w1"]),
            "metric_contract_id": s.METRIC_ID,
            "metric_contract_hash": digest(metric),
            "forecast_created_at": created.isoformat(),
            "sealed_at": sealed.isoformat(),
            "actual_read_before_seal": False,
            "scoring_before_seal": False,
            "shadow": True,
            "production": False,
        }
    )
    s.verify_seal(seal)
    s.write_immutable(args.output / "prediction-seal.json", seal)
    entry = {
        **{
            k: request[k]
            for k in (
                "base_id",
                "target_season",
                "forecast_created_at",
                "model_forecast_origin",
                "provider_run_id",
                "provider_issued_at",
                "provider_known_at",
                "scope_authority_hash",
                "c0_artifact_hash",
                "w1_artifact_hash",
            )
        },
        "cohort_id": s.COHORT_ID,
        "forecast_id": forecast_id,
        "weather_manifest_hash": surface["raw_manifest_sha256"],
        "c0_prediction_hash": seal["c0_prediction_hash"],
        "w1_prediction_hash": seal["w1_prediction_hash"],
        "seal_hash": seal["seal_hash"],
    }
    s.write_immutable(args.output / "cohort-entry.json", entry)
    files = [
        {
            "name": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
            "role": "PRIVATE_IMMUTABLE_PROSPECTIVE_ISSUANCE_ARTIFACT",
        }
        for p in sorted(args.output.iterdir())
    ]
    s.write_immutable(
        args.output / "issuance-manifest.json",
        {
            "schema": "V0_14_PRIVATE_ISSUANCE_MANIFEST_V1",
            "files": files,
            "issuance_package_hash": digest(files),
            "immutable": True,
        },
    )
    print("PREDICTIONS_SEALED", flush=True)
    return {
        "forecast_id": forecast_id,
        "prediction_seal_hash": seal["seal_hash"],
        "real_issuance_count": 1,
        "issuance_package_hash": digest(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("issue", "audit"))
    for name in ("area", "scope-store", "bundle", "locations", "cache", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    area = s.recover_area(args.area, args.scope_store)
    models = s.recover_bundle(args.bundle)
    print("SCOPE_AND_S2_BUNDLE_VERIFIED", flush=True)
    print(
        json.dumps((issue if args.mode == "issue" else audit)(args, models, area), sort_keys=True)
    )


if __name__ == "__main__":
    main()
