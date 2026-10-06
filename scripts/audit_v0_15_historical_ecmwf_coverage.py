"""Offline, label-free coverage projection from real official archive receipts.

No database, training, scoring, network, or V0.14 runtime capability. Archive
recoverability and historical PIT admission are deliberately different columns.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

POLICY_HASH = "f61a31c49bb3dab63a6a9ac3aff8f474dce51b6b46e93bf4267ef32db219e49c"
SHANGHAI = ZoneInfo("Asia/Shanghai")
STEPS = tuple(range(3, 145, 3)) + tuple(range(150, 361, 6))


def validate_run_evidence(run: dict[str, Any]) -> None:
    allowed = {"RUN_AVAILABLE", "RUN_INCOMPLETE", "RUN_ACCESS_ERROR", "RUN_NOT_FOUND"}
    if run["status"] not in allowed:
        raise ValueError("UNSUPPORTED_RUN_STATUS")
    if run["status"] != "RUN_AVAILABLE":
        return
    products = [p for p in run["products"] if p["status"] == "RUN_AVAILABLE"]
    if not products:
        raise ValueError("COMPLETE_PRODUCT_EVIDENCE_MISSING")
    for product in products:
        if product["resolution"] != "0p25" or "/ifs/0p25/oper" not in product["namespace"]:
            raise ValueError("IFS_GRID_OR_PRODUCT_NOT_EQUIVALENT")
        fields = product["fields"]
        if len(fields) != 84 or {r["step"] for r in fields} != set(STEPS):
            raise ValueError("COMPLETE_NATIVE_STEPS_NOT_PROVEN")
        versions = set()
        for row in fields:
            step = row["step"]
            wanted = {"2t", "10u", "10v"} | ({"tp", "ssrd"} if step in {168, 360} else set())
            entries = row.get("entries", [])
            if (
                row["status"] != "INDEX_FIELDS_COMPLETE"
                or row["receipt"]["status"] != 200
                or len(entries) != len(wanted)
                or {x["param"] for x in entries} != wanted
            ):
                raise ValueError("COMPLETE_INDEX_FIELDS_NOT_PROVEN")
            for entry in entries:
                identity = {
                    "class": "od",
                    "stream": "oper",
                    "type": "fc",
                    "levtype": "sfc",
                    "date": run["run_id"][:8],
                    "time": run["run_id"][8:12],
                    "step": str(step),
                }
                if any(str(entry.get(k)) != v for k, v in identity.items()):
                    raise ValueError("INDEX_RUN_IDENTITY_MISMATCH")
                if int(entry.get("_offset", -1)) < 0 or int(entry.get("_length", 0)) <= 0:
                    raise ValueError("INDEX_RANGE_INVALID")
                versions.add(entry.get("expver"))
        if len(versions) != 1 or None in versions:
            raise ValueError("MIXED_OR_MISSING_EXPERIMENT_VERSION")


def encoded(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def freeze_policy(policy: dict[str, Any]) -> None:
    body = {k: v for k, v in policy.items() if k != "policy_hash"}
    # The prior policy uses compact canonical JSON without a trailing newline.
    actual = sha(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
    if actual != POLICY_HASH or policy.get("policy_hash") != POLICY_HASH:
        raise ValueError("FROZEN_RUN_POLICY_CHANGED")


def calendar(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in sorted(rows, key=lambda r: (r["base_id"], r["season"])):
        if not row["training_candidate"]:
            continue
        identity = (row["base_id"], row["season"])
        if identity in seen:
            raise ValueError("DUPLICATE_CANDIDATE_BASE_SEASON")
        seen.add(identity)
        if row["season"] not in {"2023-2024", "2024-2025", "2025-2026"}:
            raise ValueError("COMPLETED_HISTORICAL_SEASON_REQUIRED")
        start = date.fromisoformat(row["target_start_date"])
        end = date.fromisoformat(row["target_end_date"])
        if start > end or end >= date(2026, 7, 1):
            raise ValueError("HISTORICAL_DATE_RANGE_REQUIRED")
        current = start
        while current <= end:
            origin = datetime.combine(current, datetime.min.time(), SHANGHAI).replace(hour=17)
            result.append(
                {
                    "base_id": identity[0],
                    "season": identity[1],
                    "forecast_origin": origin.isoformat(),
                    "forecast_cutoff": origin.isoformat(),
                    "date": current.isoformat(),
                }
            )
            current += timedelta(days=1)
    return result


def eligible_issues(cutoff: datetime) -> list[str]:
    if cutoff.tzinfo is None:
        raise ValueError("AWARE_CUTOFF_REQUIRED")
    utc = cutoff.astimezone(UTC)
    anchor = utc.replace(hour=12 if utc.hour >= 12 else 0, minute=0, second=0, microsecond=0)
    result = []
    while utc - anchor <= timedelta(hours=36):
        result.append(anchor.strftime("%Y%m%d%H%M%S"))
        anchor -= timedelta(hours=12)
    return result


def coverage_class(statuses: list[str], location_valid: bool) -> str:
    if not location_valid:
        return "INVALID_LOCATION"
    if not statuses:
        raise ValueError("EMPTY_BASE_SEASON_UNIVERSE")
    if all(s == "WEATHER8_COMPLETE" for s in statuses):
        return "FULL_WEATHER_COVERAGE"
    if any(s in {"WEATHER8_COMPLETE", "WEATHER8_PARTIAL"} for s in statuses):
        return "PARTIAL_WEATHER_COVERAGE"
    return "NO_WEATHER_COVERAGE"


def project_origin(row: dict[str, Any], runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    allowed = eligible_issues(datetime.fromisoformat(row["forecast_cutoff"]))
    inspected = row["inspected_runs"]
    if not inspected or inspected != allowed[: len(inspected)]:
        raise ValueError("RUN_ORDER_OR_CUTOFF_MUTATED")
    if any(r not in runs for r in inspected):
        raise ValueError("RUN_RECEIPT_MISSING")
    recoverable = next((r for r in inspected if runs[r]["status"] == "RUN_AVAILABLE"), None)
    if row["recoverable_run_id"] != recoverable:
        raise ValueError("RECOVERABILITY_SELECTION_MISMATCH")
    # Current listings/LastModified and today's retrieval do not establish the
    # historical publication receipt required by the already-frozen policy.
    if row.get("strict_selected_run_id") is not None:
        raise ValueError("UNPROVEN_HISTORICAL_AVAILABILITY")
    if any(
        runs[r]["historical_availability_status"]
        != "NOT_PIT_ADMISSIBLE_MISSING_PUBLICATION_EVIDENCE"
        for r in inspected
    ):
        raise ValueError("HISTORICAL_AVAILABILITY_EVIDENCE_REQUIRES_REVIEW")
    errors = any(runs[r]["status"] == "RUN_ACCESS_ERROR" for r in inspected)
    physical = (
        "INDEX_COMPLETE"
        if recoverable
        else "ACCESS_ERROR"
        if errors
        else "OBJECTS_OR_FIELDS_INCOMPLETE"
        if any(runs[r]["status"] == "RUN_INCOMPLETE" for r in inspected)
        else "RUN_NOT_FOUND"
    )
    return {
        "date": row["date"],
        "forecast_cutoff": row["forecast_cutoff"],
        "selected_ecmwf_issue_time": "",
        "selected_cycle": "",
        "recoverable_run_id": recoverable or "",
        "recoverable_issue_time": runs[recoverable]["issue_time"] if recoverable else "",
        "recoverable_cycle": runs[recoverable]["cycle"] if recoverable else "",
        "run_status": "POLICY_NO_ELIGIBLE_RUN",
        "weather8_status": "WEATHER8_UNAVAILABLE",
        "0_168_status": "NOT_PIT_ADMISSIBLE",
        "168_360_status": "NOT_PIT_ADMISSIBLE",
        "recoverability_status": physical,
        "reason_code": "MISSING_HISTORICAL_PUBLICATION_EVIDENCE",
        "transport_error_present": errors,
        "source_hash": sha(encoded([runs[r] for r in inspected])),
        "inspected_run_ids": "|".join(inspected),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("EMPTY_REPORT_MATRIX")
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def numerical_status(base_id: str, sample: dict[str, Any] | None) -> str:
    if sample is None:
        return "NOT_PER_ORIGIN_VALIDATED"
    if base_id in sample.get("fail_closed_errors", {}):
        return "FAIL_CLOSED_" + str(sample["fail_closed_errors"][base_id])
    if base_id in sample["feature_hashes"]:
        return "REAL_GRIB_WEATHER8_RECONSTRUCTED"
    return "NOT_PER_ORIGIN_VALIDATED"


def build(candidate_path: Path, policy_path: Path, sweep: Path, output: Path) -> dict[str, Any]:
    policy = json.loads(policy_path.read_bytes())
    freeze_policy(policy)
    source = json.loads(candidate_path.read_bytes())
    if len(source["rows"]) != 117 or source["training_candidate_count"] != 76:
        raise ValueError("FROZEN_BUSINESS_CANDIDATE_COUNT_CHANGED")
    universe = calendar(source["rows"])
    unique_dates = sorted({row["date"] for row in universe})
    observations = json.loads((sweep / "origin-results.json").read_bytes())
    by_date = {r["date"]: r for r in observations}
    if len(by_date) != len(observations) or sorted(by_date) != unique_dates:
        raise ValueError("REQUIRED_ORIGIN_AUDIT_INCOMPLETE")
    runs = {p.stem: json.loads(p.read_bytes()) for p in sorted((sweep / "runs").glob("*.json"))}
    for run in runs.values():
        validate_run_evidence(run)
    locations = json.loads((sweep / "location-validation.json").read_bytes())
    valid_bases = set(locations["feature_hashes"])
    spatial_samples = {
        json.loads(p.read_bytes())["raw_run_id"]: json.loads(p.read_bytes())
        for p in sweep.glob("location-validation*.json")
    }
    grib_validation = json.loads((sweep / "stratified-validation.json").read_bytes())
    network = json.loads((sweep / "network-accounting.json").read_bytes())
    origin_rows = [project_origin(by_date[d], runs) for d in unique_dates]
    origin_map = {r["date"]: r for r in origin_rows}
    full_matrix = [
        {
            "base_id": r["base_id"],
            "season": r["season"],
            "forecast_origin": r["forecast_origin"],
            **origin_map[r["date"]],
            "location_status": "VALIDATED_REAL_GRIB" if r["base_id"] in valid_bases else "INVALID",
            "numerical_weather8_status": numerical_status(
                r["base_id"], spatial_samples.get(origin_map[r["date"]]["recoverable_run_id"])
            ),
        }
        for r in universe
    ]
    base_season = []
    for base_id, season in sorted({(r["base_id"], r["season"]) for r in universe}):
        subset = [r for r in full_matrix if r["base_id"] == base_id and r["season"] == season]
        recoverable_count = sum(r["recoverability_status"] == "INDEX_COMPLETE" for r in subset)
        base_season.append(
            {
                "base_id": base_id,
                "season": season,
                "required_origins": len(subset),
                "weather8_complete_origins": 0,
                "weather8_partial_origins": 0,
                "weather8_missing_origins": len(subset),
                "coverage_class": coverage_class(
                    [r["weather8_status"] for r in subset], base_id in valid_bases
                ),
                "index_complete_recoverable_origins": recoverable_count,
                "recoverability_class": (
                    "FULL_INDEX_RECOVERABILITY"
                    if recoverable_count == len(subset)
                    else "PARTIAL_INDEX_RECOVERABILITY"
                    if recoverable_count
                    else "NO_EXACT_V014_INDEX_RECOVERABILITY"
                ),
                "historical_publication_evidence": "NOT_PIT_ADMISSIBLE",
            }
        )
    counts = Counter(r["recoverability_status"] for r in origin_rows)
    recoverable = [runs[r["recoverable_run_id"]] for r in origin_rows if r["recoverable_run_id"]]
    available_runs = [r for r in runs.values() if r["status"] == "RUN_AVAILABLE"]
    periods = {}
    for season in sorted({r["season"] for r in universe}):
        required = sorted({r["date"] for r in universe if r["season"] == season})
        complete = sum(origin_map[d]["recoverability_status"] == "INDEX_COMPLETE" for d in required)
        periods[season] = {
            "unique_required_origins": len(required),
            "index_complete_origins": complete,
            "index_incomplete_origins": len(required) - complete,
            "strict_pit_admitted_origins": 0,
        }
    summary = {
        "schema": "V0_15_HISTORICAL_ECMWF_COVERAGE_SWEEP_V1",
        "result": "PARTIAL",
        "training_candidate_base_season_count": 76,
        "total_required_forecast_origin_count": len(universe),
        "unique_required_forecast_origin_count": len(unique_dates),
        "unique_ecmwf_run_count": len(runs),
        "eligible_run_found_origin_count": 0,
        "weather8_complete_origin_count": 0,
        "weather8_partial_origin_count": 0,
        "weather8_missing_origin_count": len(unique_dates),
        "weather8_complete_origin_rate": "0",
        "coverage_denominator": "UNIQUE_FORECAST_CUTOFF_DATES_STRICT_FROZEN_POLICY",
        "index_complete_recoverable_origin_count": counts["INDEX_COMPLETE"],
        "index_complete_recoverable_origin_rate": str(
            (Decimal(counts["INDEX_COMPLETE"]) / Decimal(len(unique_dates))).quantize(
                Decimal("0.000000000001")
            )
        ),
        "required_period_coverage": periods,
        "index_access_error_origin_count": counts["ACCESS_ERROR"],
        "recoverability_counts": dict(sorted(counts.items())),
        "full_weather_coverage_base_season_count": 0,
        "partial_weather_coverage_base_season_count": 0,
        "no_weather_coverage_base_season_count": sum(
            r["coverage_class"] == "NO_WEATHER_COVERAGE" for r in base_season
        ),
        "invalid_location_base_season_count": sum(
            r["coverage_class"] == "INVALID_LOCATION" for r in base_season
        ),
        "earliest_recoverable_forecast_run": min(
            (r["run_id"] for r in available_runs), default=None
        ),
        "latest_recoverable_forecast_run": max((r["run_id"] for r in available_runs), default=None),
        "earliest_origin_recoverable_run": min((r["run_id"] for r in recoverable), default=None),
        "latest_origin_recoverable_run": max((r["run_id"] for r in recoverable), default=None),
        "base_weather_location_valid_count": locations["valid_location_count"],
        "base_weather_location_invalid_count": locations["invalid_location_count"],
        "index_recoverability_base_season_classes": dict(
            sorted(Counter(r["recoverability_class"] for r in base_season).items())
        ),
        "run_selection_policy_hash": POLICY_HASH,
        "candidate_source_sha256": sha(candidate_path.read_bytes()),
        "policy_source_sha256": sha(policy_path.read_bytes()),
        "historical_ecmwf_coverage_audited": True,
        "s0_weather_coverage_ready": False,
        "s1_ready": False,
        "s1_authorized": False,
        "historical_publication_evidence_reconstructed": False,
        "today_retrieval_time_backdated": False,
        "policy_changed": False,
        "real_grib_validation_sample_count": grib_validation["sample_count"],
        "distinct_model_cycle_validated_count": grib_validation[
            "documented_deployment_cycle_strata_count"
        ],
        "model_cycle_count_basis": "DOCUMENTED_DEPLOYMENT_INFERENCE_NOT_ENCODED_LITERAL_CYCLE",
        "encoded_literal_cycle_validated_count": grib_validation[
            "encoded_literal_cycle_validated_count"
        ],
        "numerical_gate_failure_base_origin_count": sum(
            str(r["numerical_weather8_status"]).startswith("FAIL_CLOSED") for r in full_matrix
        ),
        "full_weather8_reconstructed_base_origin_count": sum(
            r["numerical_weather8_status"] == "REAL_GRIB_WEATHER8_RECONSTRUCTED"
            for r in full_matrix
        ),
        "per_origin_numerical_reconstruction_complete": False,
        "network_accounting": network,
        "full_definition": "ALL_REQUIRED_ORIGINS_PASS_NOT_95_PERCENT",
        "calendar_definition": (
            "Each inclusive frozen candidate date at Asia/Shanghai17:00; "
            "no H15 tail trimming, no training admission decision."
        ),
        "limitations": [
            "INDEX_COMPLETE is recoverability, not per-origin dense GRIB decode "
            "or historical PIT admission.",
            "Archive LastModified is not the immutable historical publication receipt "
            "required by the frozen policy.",
            "Representative GRIB strata must be evaluated before interpreting index recovery "
            "as semantic Weather8 coverage.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "historical-ecmwf-required-origin-universe.json").write_bytes(
        encoded(
            {
                "candidate_source_sha256": summary["candidate_source_sha256"],
                "run_policy_hash": POLICY_HASH,
                "definition": summary["calendar_definition"],
                "total_count": len(universe),
                "unique_count": len(unique_dates),
                "candidate_base_season_count": 76,
                "unique_dates": unique_dates,
                "base_season_ranges": [
                    {k: r[k] for k in ("base_id", "season", "target_start_date", "target_end_date")}
                    for r in source["rows"]
                    if r["training_candidate"]
                ],
            }
        )
    )
    write_csv(output / "historical-ecmwf-run-availability-matrix.csv", origin_rows)
    write_csv(output / "historical-base-season-weather-coverage.csv", base_season)
    write_csv(output / "historical-base-season-origin-weather-matrix.csv", full_matrix)
    (output / "historical-weather8-origin-coverage.json").write_bytes(
        encoded(
            {"denominator": len(unique_dates), "origins": origin_rows, "policy_hash": POLICY_HASH}
        )
    )
    (output / "historical-weather-location-validation.json").write_bytes(encoded(locations))
    (output / "historical-model-cycle-grib-validation.json").write_bytes(encoded(grib_validation))
    (output / "audit-source-manifest.json").write_bytes(
        encoded(json.loads((sweep / "audit-source-manifest.json").read_bytes()))
    )
    (output / "numeric-failure-native-recheck.json").write_bytes(
        encoded(json.loads((sweep / "numeric-failure-native-recheck.json").read_bytes()))
    )
    (output / "historical-ecmwf-coverage-summary.json").write_bytes(encoded(summary))
    (output / "s0-weather-coverage-readiness-recommendation.json").write_bytes(
        encoded(
            {
                "s1_ready": False,
                "s1_authorized": False,
                "s0_weather_coverage_ready": False,
                "next_authorization_not_implied": True,
                "reason": (
                    "Separate index recoverability from actual publication-time PIT eligibility; "
                    "retain business audit unchanged."
                ),
                "business_area_tier_a_count": 0,
                "business_area_tier_b_count": 0,
                "business_area_tier_c_count": 117,
                "identity_unresolved_count": 44,
                "model_training_executed": False,
                "scoring_executed": False,
                "current_2026_2027_actual_accessed": False,
            }
        )
    )
    members = [
        {"name": p.name, "sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
        for p in sorted(output.iterdir())
        if p.is_file() and p.name != "manifest.json"
    ]
    manifest = {
        "schema": "V0_15_WEATHER_COVERAGE_EVIDENCE_MANIFEST_V1",
        "members": members,
        "candidate_source_sha256": summary["candidate_source_sha256"],
        "policy_hash": POLICY_HASH,
        "prior_evidence_mutated": False,
        "raw_grib_committed": False,
        "weather_values_disclosed": False,
        "coordinates_disclosed": False,
    }
    manifest["manifest_hash"] = sha(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-matrix", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.candidate_matrix, args.policy, args.sweep_root, args.output)))


if __name__ == "__main__":
    main()
