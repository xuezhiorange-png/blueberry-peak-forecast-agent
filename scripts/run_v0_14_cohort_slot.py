"""Operator CLI only. No timer activation and no actual/training/scoring interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.area_yield import v014_cohort_operations as o
from backend.app.area_yield import v014_shadow_issuance as s
from backend.app.area_yield.data import digest
from backend.app.area_yield.v014_future_weather_features import (
    ECMWFDenseFeatureSurfaceProvider,
    aggregate_ifs,
    require,
)
from scripts.run_v0_14_s3_shadow_issuance import capture_latest


def issue_slot(args: argparse.Namespace) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        o.validate_attempt(args.slot_date, started)
    except ValueError:
        if started > o.slot_time(args.slot_date, "18:00:00"):
            return o.record_missed(args.registry, args.slot_date, started)
        if started > o.slot_time(args.slot_date, "17:15:00"):
            # No official attempt is opened after the attempt deadline.
            return o.append_record(
                args.registry,
                o.nonissued(args.slot_date, "MISSED_SLOT", None, "ATTEMPT_START_DEADLINE_MISSED"),
            )
        raise
    o.claim_attempt(args.registry, args.slot_date, started)
    output = args.registry / "slot-packages" / o.slot_id(args.slot_date)
    require(not output.exists(), "RETRY_FORBIDDEN")
    try:
        area = o.read_scope_store(args.scope_store, started, o.slot_origin(args.slot_date))
        models = s.recover_bundle(args.bundle)
        provider = ECMWFDenseFeatureSurfaceProvider(
            location_authority_path=args.locations, artifact_root=args.cache
        )
        surface, attempts = capture_latest(provider, started)
        created = datetime.now(UTC)
        o.validate_created(args.slot_date, created)
        origin = o.slot_origin(args.slot_date)
        s.verify_area_time(area, created, origin)
        s.verify_weather_receipt(surface, created)
        o.verify_freshness(datetime.fromisoformat(surface["issued_at"]), created)
        features = aggregate_ifs(surface["fields_by_base"][s.BASE_ID])
        rows = s.target_rows(area, origin, features)
        metric = s.metric_contract()
        require(digest(metric) == o.METRIC_HASH, "METRIC_CONTRACT_DRIFT")
        receipt = surface["acquisition_receipt"]
        request = {
            "schema": "V0_14_PROSPECTIVE_REQUEST_SNAPSHOT_V1",
            "slot_id": o.slot_id(args.slot_date),
            "operations_policy_hash": o.POLICY_HASH,
            "base_id": s.BASE_ID,
            "canonical_base_name": s.BASE_NAME,
            "target_season": "2026-2027",
            "area_revision_id": area.area_revision_id,
            "area_type": area.area_type,
            "scope_authority_hash": area.payload_hash,
            "issuance_session_started_at": started.isoformat(),
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
            "feature_policy_hash": o.FEATURE_HASH,
            "c0_artifact_hash": s.MODEL_HASHES["c0"],
            "w1_artifact_hash": s.MODEL_HASHES["w1"],
            "metric_contract_hash": o.METRIC_HASH,
        }
        predictions = s.predict_pair(models, rows)
        sealed = datetime.now(UTC)
        s.verify_timing(created, origin, sealed)
        forecast_id = "v014_" + digest(request)[:24]
        seal = s.self_seal(
            {
                "schema": s.SEAL_SCHEMA,
                "cohort_id": s.COHORT_ID,
                "forecast_id": forecast_id,
                "request_hash": digest(request),
                "scope_authority_hash": area.payload_hash,
                "weather_raw_manifest_hash": surface["raw_manifest_sha256"],
                "selected_base_weather_feature_hash": digest(features),
                "feature_policy_hash": o.FEATURE_HASH,
                "c0_artifact_hash": s.MODEL_HASHES["c0"],
                "w1_artifact_hash": s.MODEL_HASHES["w1"],
                "target_row_count": 15,
                "target_row_keys_hash": request["target_row_keys_hash"],
                "c0_prediction_hash": digest(predictions["c0"]),
                "w1_prediction_hash": digest(predictions["w1"]),
                "metric_contract_id": s.METRIC_ID,
                "metric_contract_hash": o.METRIC_HASH,
                "forecast_created_at": created.isoformat(),
                "sealed_at": sealed.isoformat(),
                "actual_read_before_seal": False,
                "scoring_before_seal": False,
                "shadow": True,
                "production": False,
            }
        )
    except Exception as exc:
        code = str(exc)
        status = {
            "NO_VALID_SCOPE_AUTHORITY": "NO_VALID_SCOPE_AUTHORITY",
            "AUTHORITY_CONFLICT": "AUTHORITY_CONFLICT",
            "SELECTED_SCOPE_W1_FEATURE_SURFACE_INCOMPLETE": "NO_COMPLETE_WEATHER_RUN",
            "WEATHER_RUN_TOO_OLD": "WEATHER_RUN_TOO_OLD",
            "LATE_CAPTURE_CUTOFF": "LATE_CAPTURE_CUTOFF",
        }.get(code, "TECHNICAL_FAILURE")
        # Never log exception payloads (may contain private paths or values).
        return o.append_record(
            args.registry,
            o.nonissued(args.slot_date, status, started, status + ";NO_RETRY;NO_ACCEPTED_PACKAGE"),
        )
    # No network, scope reselection or prediction retry is allowed after this point.
    accepted_output = output
    output = args.registry / "attempt-packages" / o.slot_id(args.slot_date)
    output.mkdir(parents=True, exist_ok=False)
    entry = {"cohort_id": s.COHORT_ID, "forecast_id": forecast_id, "seal_hash": seal["seal_hash"]}
    bodies = {
        "scope-authority-snapshot.json": area.model_dump(mode="json"),
        "weather-surface-manifest.json": {
            "raw_manifest_sha256": surface["raw_manifest_sha256"],
            "acquisition_receipt": receipt,
            "run_selection_attempts": attempts,
            "selected_base_features": features,
        },
        "request-snapshot.json": request,
        "metric-contract.json": metric,
        "c0-predictions.json": predictions["c0"],
        "w1-predictions.json": predictions["w1"],
        "prediction-seal.json": seal,
        "cohort-entry.json": entry,
    }
    for name, body in bodies.items():
        if name == "prediction-seal.json":
            # Timestamp is recorded after both prediction files have been persisted.
            seal["sealed_at"] = datetime.now(UTC).isoformat()
            s.verify_timing(created, origin, datetime.fromisoformat(seal["sealed_at"]))
            seal = s.self_seal({k: v for k, v in seal.items() if k != "seal_hash"})
            body = seal
            bodies[name] = seal
            entry["seal_hash"] = seal["seal_hash"]
        s.write_immutable(output / name, body)
    files = [
        {
            "name": name,
            "sha256": hashlib.sha256(s.json_bytes(body)).hexdigest(),
            "size": len(s.json_bytes(body)),
            "role": "PRIVATE_IMMUTABLE_PROSPECTIVE_ARTIFACT",
        }
        for name, body in sorted(bodies.items())
    ]
    s.write_immutable(
        output / "issuance-manifest.json",
        {
            "schema": "V0_14_PRIVATE_ISSUANCE_MANIFEST_V1",
            "files": files,
            "issuance_package_hash": digest(files),
            "immutable": True,
        },
    )
    o.verify_package(output)
    accepted_output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(output, accepted_output)
    return register_package(args.registry, args.slot_date)


def register_package(registry: Path, day: str) -> dict[str, Any]:
    package = o.verify_package(registry / "slot-packages" / o.slot_id(day))
    claim = s.read_json(registry / "attempts" / (o.slot_id(day) + ".json"))
    started = datetime.fromisoformat(claim["attempt_started_at"])
    o.validate_attempt(day, started)
    created = datetime.fromisoformat(package["forecast_created_at"])
    require(
        started <= created and package["issuance_session_started_at"] == started.isoformat(),
        "ATTEMPT_PROVENANCE_INVALID",
    )
    o.validate_created(day, created)
    o.verify_freshness(datetime.fromisoformat(package["provider_issued_at"]), created)
    keys = [
        "forecast_id",
        "area_revision_id",
        "area_type",
        "scope_authority_hash",
        "forecast_created_at",
        "model_forecast_origin",
        "provider_run_id",
        "provider_issued_at",
        "provider_known_at",
        "weather_raw_manifest_hash",
        "feature_policy_hash",
        "c0_artifact_hash",
        "w1_artifact_hash",
        "target_row_keys_hash",
        "c0_prediction_hash",
        "w1_prediction_hash",
        "metric_contract_hash",
        "seal_hash",
        "issuance_package_hash",
    ]
    body = {
        "schema": o.SCHEMA,
        "slot_id": o.slot_id(day),
        "slot_date": day,
        "status": "ISSUED",
        "entry_class": "SCHEDULED_DAILY_SLOT_ENTRY",
        "issuance_identity_keys": keys,
        "attempt_started_at": started.isoformat(),
        **{k: package[k] for k in keys},
    }
    return o.append_record(registry, body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("verify", "issue-slot", "record-missed-slot", "audit-registry")
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--seed-package", type=Path, required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--slot-date")
    parser.add_argument("--reconcile-sealed-package", action="store_true")
    for name in ("scope-store", "bundle", "locations", "cache"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    o.execution_gate(args.mode)
    o.verify_seed_package(args.seed_package)
    if args.reconcile_sealed_package:
        require(
            args.mode == "audit-registry" and args.slot_date is not None,
            "RECONCILE_ONLY_EXISTING_PACKAGE",
        )
        register_package(args.registry, args.slot_date)
    if args.initialize:
        require(args.mode == "verify", "INITIALIZE_ONLY_IN_VERIFY")
        o.initialize(args.registry, o.SEED)
    if args.mode == "issue-slot":
        require(
            args.slot_date is not None
            and all(
                getattr(args, k) is not None
                for k in ("scope_store", "bundle", "locations", "cache")
            ),
            "MISSING_OPERATOR_INPUT",
        )
        result = issue_slot(args)
    elif args.mode == "record-missed-slot":
        require(args.slot_date is not None, "MISSING_SLOT_DATE")
        result = o.record_missed(args.registry, args.slot_date, datetime.now(UTC))
    else:
        records = o.audit_registry(args.registry, args.seed_package)
        result = {
            "registry_hash_chain_valid": True,
            "record_count": len(records),
            "registry_head_hash": records[-1]["record_hash"],
            "operations_policy_hash": o.POLICY_HASH,
            "genesis_record_hash": records[0]["record_hash"],
            "missing_due_slots": o.missing_due_slots(records, datetime.now(UTC)),
        }
    s.validate_public(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
