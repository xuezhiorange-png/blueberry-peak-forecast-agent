"""Offline historical-only precipitation policy; never patches live V0.14."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.audit_v0_15_ecmwf_semantics import availability, encoded

CANDIDATES = (Decimal("0.04"), Decimal("0.08"))


def select_threshold(max_negative_magnitude_mm: Decimal) -> Decimal:
    if not max_negative_magnitude_mm.is_finite() or max_negative_magnitude_mm < 0:
        raise ValueError("INVALID_NEGATIVE_MAGNITUDE")
    for threshold in CANDIDATES:
        if max_negative_magnitude_mm < threshold:
            return threshold
    raise ValueError("FAIL_REQUIRES_FURTHER_INVESTIGATION")


def window_precip(raw_delta_mm: Decimal, threshold_mm: Decimal) -> Decimal:
    if threshold_mm not in CANDIDATES or not raw_delta_mm.is_finite():
        raise ValueError("INVALID_PRECIP_POLICY_INPUT")
    if raw_delta_mm <= -threshold_mm:
        raise ValueError("ANOMALY_OUTSIDE_VALIDATED_THRESHOLD")
    return Decimal(0) if raw_delta_mm < threshold_mm else raw_delta_mm


def quantile(values: list[Decimal], probability: Decimal) -> str | None:
    if not values:
        return None
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return str(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def generate(inputs: Path, sweep: Path, publication_path: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    publication = json.loads(publication_path.read_bytes())
    if (
        publication["policy_hash"]
        != "896e19617c0d12579fa33cf9ed17e81e6ed2e4337866c10de00c3932918565c7"
    ):
        raise ValueError("PUBLICATION_POLICY_CHANGED")
    body = {k: v for k, v in publication.items() if k != "policy_hash"}
    if hashlib.sha256(encoded(body)).hexdigest() != publication["policy_hash"]:
        raise ValueError("PUBLICATION_POLICY_SELF_HASH_INVALID")
    previous_manifest = (sweep / "manifest.json").read_bytes()
    if (
        hashlib.sha256(previous_manifest).hexdigest()
        != "b1345a824b77f144cb8676f3895a649d67a18b92f97dbd81c1046329c60e27b6"
    ):
        raise ValueError("FROZEN_ORIGIN_UNIVERSE_CHANGED")
    for row in json.loads(previous_manifest)["members"]:
        if hashlib.sha256((sweep / row["name"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("FROZEN_SWEEP_MEMBER_CHANGED")
    with (sweep / "historical-base-season-origin-weather-matrix.csv").open() as f:
        matrix = list(csv.DictReader(f))
    required = [r for r in matrix if r["recoverability_status"] == "INDEX_COMPLETE"]
    run_ids = {r["recoverable_run_id"] for r in required}
    if len(run_ids) != 422 or len(required) != 13840:
        raise ValueError("FROZEN_REQUIRED_PRECIP_UNIVERSE_CHANGED")
    runs = {
        p.stem: json.loads(p.read_bytes()) for p in sorted((inputs / "private-runs").glob("*.json"))
    }
    if set(runs) != run_ids or any(r["status"] != "AUDITED" for r in runs.values()):
        raise ValueError("ALL_422_RUNS_NOT_AUDITED")
    envelope = json.loads((inputs / "audit-envelope.json").read_bytes())
    if (
        envelope["threshold_candidates_mm"] != ["0.04", "0.08"]
        or envelope["ssrd_threshold_applied"]
    ):
        raise ValueError("PRE_AUDIT_DECISION_ENVELOPE_CHANGED")
    negative: list[Decimal] = []
    positive: list[Decimal] = []
    raw_by_row: dict[tuple[str, str], Decimal] = {}
    negative_a = 0
    for row in required:
        run = runs[row["recoverable_run_id"]]
        if not run["same_grid"] or not run["all_global_values_finite"]:
            raise ValueError("PRECIP_GRID_OR_FINITE_VALIDATION_FAILED")
        for meta, step in zip(run["metadata"], (168, 360), strict=True):
            if (
                meta["shortName"] != "tp"
                or meta["units"] != "m"
                or meta["stepType"] != "accum"
                or meta["startStep"] != 0
                or meta["endStep"] != step
            ):
                raise ValueError("PRECIP_ACCUMULATION_SEMANTICS_CHANGED")
        values = run["base_values_m"][row["base_id"]]
        a, b = Decimal(values["168"]) * 1000, Decimal(values["360"]) * 1000
        if not a.is_finite() or not b.is_finite():
            raise ValueError("NONFINITE_POINT")
        negative_a += a < 0
        delta = b - a
        raw_by_row[row["base_id"], row["forecast_origin"]] = delta
        if delta < 0:
            negative.append(-delta)
        if delta > 0:
            positive.append(delta)
    max_negative = max(negative, default=Decimal(0))
    if len(raw_by_row) != len(required):
        raise ValueError("DUPLICATE_REQUIRED_BASE_ORIGIN")
    try:
        threshold: Decimal | None = select_threshold(max_negative)
    except ValueError:
        threshold = None
    closed = threshold is not None and negative_a == 0
    policies: dict[str, Any] = {}
    official_receipts = json.loads((inputs / "official-source-receipt.json").read_bytes())
    policies["ecmwf-packing-threshold-source.json"] = {
        "source_receipt": official_receipts,
        "official_candidates_mm": ["0.04", "0.08"],
        "official_strategy": "Zero subtraction totals below positive trace threshold",
        "official_example_scope": "10-day ENS analysis;point-rainfall example uses0.04",
        "historical_15day_ifs_adaptation_owner_authorized": True,
        "not_a_universal_ecmwf15day_threshold_guarantee": True,
    }
    policy = {
        "policy_id": "V0_15_HISTORICAL_TP_TRACE_004_008_CANDIDATES_R1",
        "scope": "V0_15_HISTORICAL_IFS_WEATHER8_REPLAY_ONLY",
        "threshold_candidates_mm": ["0.04", "0.08"],
        "threshold_selected_mm": str(threshold) if threshold is not None else None,
        "threshold_source": "ECMWF_OFFICIAL",
        "official_source_scope_limit": (
            "Official example is10-day ENS;15-day IFS candidate-Base adaptation "
            "is Owner-authorized and validated here,not universal ECMWF guarantee"
        ),
        "selection_rule": envelope["selection_rule"],
        "selection_envelope_sha256": hashlib.sha256(
            (inputs / "audit-envelope.json").read_bytes()
        ).hexdigest(),
        "result_independent_of_labels_and_accuracy": True,
        "weather_diagnostic_driven_selection": True,
        "block_a_mm": "tp168 * 1000;nonnegative endpoint required;NO trace threshold",
        "block_b_raw_mm": "(tp360 - tp168) * 1000",
        "block_b_rule": "if raw <= -threshold:reject;else if raw < threshold:0;else raw",
        "same_run_and_grid_required": True,
        "ssrd_temperature_wind_threshold_applied": False,
        "full_grid_global_domain_validated_for_policy": False,
        "applicability": (
            "Frozen422origins and corresponding candidate Base locations only;"
            "un-audited future domains require validation"
        ),
        "frozen": closed,
        "v014_changed": False,
        "publication_policy_hash": publication["policy_hash"],
        "threshold_does_not_prove_each_negative_is_physically_spurious": True,
    }
    policy["policy_hash"] = hashlib.sha256(encoded(policy)).hexdigest()
    policies["precipitation-packing-artifact-policy.json"] = policy
    policies["precipitation-full-origin-audit.json"] = {
        "archive_field_complete_origin_count": 422,
        "precip_origin_audited_count": len(runs),
        "required_base_origin_count": len(required),
        "negative_delta_count": len(negative),
        "negative_delta_min_mm": str(-max_negative),
        "negative_delta_max_magnitude_mm": str(max_negative),
        "negative_delta_p50_magnitude_mm": quantile(negative, Decimal(".5")),
        "negative_delta_p95_magnitude_mm": quantile(negative, Decimal(".95")),
        "negative_delta_p99_magnitude_mm": quantile(negative, Decimal(".99")),
        "negative_delta_p50_signed_mm": quantile([-v for v in negative], Decimal(".5")),
        "negative_delta_p95_signed_mm": quantile([-v for v in negative], Decimal(".95")),
        "negative_delta_p99_signed_mm": quantile([-v for v in negative], Decimal(".99")),
        "small_positive_0_to_004_count": sum(v < Decimal(".04") for v in positive),
        "small_positive_0_to_008_count": sum(v < Decimal(".08") for v in positive),
        "zero_raw_delta_count": len(required) - len(negative) - len(positive),
        "negative_block_a_endpoint_count": negative_a,
        "negative_magnitude_at_least004_count": sum(v >= Decimal(".04") for v in negative),
        "negative_magnitude_at_least008_count": sum(v >= Decimal(".08") for v in negative),
        "quantile_method": "linear interpolation(sorted Decimal values,index=(n-1)*p)",
        "global_grid_negative_max_magnitude_mm_diagnostic_only": max(
            r["global_negative_max_magnitude_mm"] for r in runs.values()
        ),
        "scope_is_candidate_points_not_entire_world_grid": True,
        "same_run_metadata_and_actual_native_decode_all422": True,
        "raw_evidence_preserved": True,
    }
    projected: list[dict[str, Any]] = []
    for row in matrix:
        issue = row["recoverable_issue_time"]
        eligible = bool(
            issue
            and availability(
                datetime.fromisoformat(issue), datetime.fromisoformat(row["forecast_cutoff"])
            )
        )
        tp_ok = False
        if eligible and closed:
            raw = raw_by_row[row["base_id"], row["forecast_origin"]]
            treated = window_precip(raw, threshold)  # type: ignore[arg-type]
            tp_ok = treated >= 0
        projected.append(
            {
                "base_id": row["base_id"],
                "season": row["season"],
                "forecast_origin": row["forecast_origin"],
                "selected_run_id": row["recoverable_run_id"],
                "tier_b_publication_eligible": eligible,
                "tp_endpoints_audited": bool(issue),
                "precipitation_policy_pass": tp_ok,
                "weather8_coverage_complete": eligible
                and tp_ok
                and row["location_status"] == "VALIDATED_REAL_GRIB",
                "reason": "TIER_B_INDEX_AND_TP_VALIDATED"
                if eligible and tp_ok
                else "ARCHIVE_INCOMPLETE_OR_PRECIP_POLICY_UNCLOSED",
            }
        )
    policies["historical-base-season-origin-weather-pit-matrix.json"] = {
        "rows": projected,
        "point_weather_values_disclosed": False,
    }
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_origin: dict[str, list[dict[str, Any]]] = {}
    for row in projected:
        by_pair.setdefault((row["base_id"], row["season"]), []).append(row)
        by_origin.setdefault(row["forecast_origin"], []).append(row)
    counts: Counter[str] = Counter()
    pairs = []
    for (base_id, season), subset in sorted(by_pair.items()):
        count = sum(r["weather8_coverage_complete"] for r in subset)
        status = (
            "FULL_WEATHER_COVERAGE"
            if count == len(subset)
            else "PARTIAL_WEATHER_COVERAGE"
            if count
            else "NO_WEATHER_COVERAGE"
        )
        counts[status] += 1
        pairs.append(
            {
                "base_id": base_id,
                "season": season,
                "required_origin_count": len(subset),
                "covered_origin_count": count,
                "status": status,
            }
        )
    complete_count = sum(
        all(r["weather8_coverage_complete"] for r in subset) for subset in by_origin.values()
    )
    policies["pit-weather-coverage-finalization.json"] = {
        "total_required_origin_count": len(by_origin),
        "pit_eligible_run_origin_count": sum(
            any(r["tier_b_publication_eligible"] for r in subset) for subset in by_origin.values()
        ),
        "pit_weather8_complete_origin_count": complete_count,
        "pit_weather8_complete_origin_rate": str(Decimal(complete_count) / Decimal(len(by_origin))),
        "pit_full_base_season_count": counts["FULL_WEATHER_COVERAGE"],
        "pit_partial_base_season_count": counts["PARTIAL_WEATHER_COVERAGE"],
        "pit_no_coverage_base_season_count": counts["NO_WEATHER_COVERAGE"],
        "base_season_rows": pairs,
        "coverage_grade": (
            "TIER_B_ASSUMED_PUBLICATION_PLUS_ALL256_OFFICIAL_INDEX_FIELDS_PLUS_REAL_TP_ENDPOINTS"
        ),
        "all_eight_numerical_features_reconstructed_every_origin": False,
        "other_parameters_numerical_validation": (
            "Prior five real GRIB strata samples;not every256field message downloaded"
        ),
        "strict_tier_a_publication_ready_count": 0,
        "full_definition": "ALL required origins;no95percent criterion",
        "area_tier_c_count_unchanged": 117,
        "identity_unresolved_count_unchanged": 44,
    }
    policies["real-tp-endpoint-retrieval-and-metadata-manifest.json"] = {
        "runs": [
            {k: v for k, v in runs[run].items() if k not in {"base_values_m"}}
            for run in sorted(runs)
        ],
        "private_run_report_hashes": {
            run: hashlib.sha256(
                (inputs / "private-runs" / (run + ".json")).read_bytes()
            ).hexdigest()
            for run in sorted(runs)
        },
        "location_authority_sha256": (
            "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
        ),
    }
    ledger = [json.loads(line) for line in (inputs / "network.jsonl").read_bytes().splitlines()]
    policies["retrieval-network-accounting.json"] = {
        "network_request_count": len(ledger),
        "downloaded_response_bytes": sum(r["byte_size"] for r in ledger),
        "raw_field_count": 844,
        "immutable_raw_cache_reuse_count": sum(
            f["cache_reused"] for r in runs.values() for f in r["fields"]
        ),
        "no_repeated_global_run_per_base": True,
        "source_ledger_sha256": hashlib.sha256((inputs / "network.jsonl").read_bytes()).hexdigest(),
    }
    policies["s0-weather-pit-readiness-recommendation.json"] = {
        "result": "PASS" if closed else "PARTIAL",
        "all422_field_complete_origins_precip_audited": True,
        "precipitation_accumulation_semantics_closed": closed,
        "closure_is_operational_threshold_rule_not_proof_of_each_artifact_cause": True,
        "precipitation_window_policy_frozen": closed,
        "historical_publication_policy_frozen": True,
        "pit_weather_coverage_recomputed": True,
        "s0_weather_pit_ready_at_reported_coverage_grade": closed,
        "all_numeric_weather8_vectors_dataset_materialized": False,
        "full_business_dataset_pit_ready": False,
        "s1_ready": False,
        "s1_authorized": False,
        "model_training_or_scoring_executed": False,
        "current_actual_or_label_vault_accessed": False,
        "v014_or_production_changed": False,
        "negative_artifact_collapsed_to_zero": closed and bool(negative),
        "small_positive_collapsed_to_zero": (
            closed and threshold is not None and any(v < threshold for v in positive)
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, report in policies.items():
        (output / name).write_bytes(encoded(report))
    manifest = {
        "schema": "V0_15_PRECIP_PACKING_POLICY_CLOSURE_MANIFEST_R1",
        "members": [
            {
                "name": p.name,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "size": p.stat().st_size,
            }
            for p in sorted(output.glob("*.json"))
        ],
        "source_envelope_sha256": hashlib.sha256(
            (inputs / "audit-envelope.json").read_bytes()
        ).hexdigest(),
        "parent_publication_policy_hash": publication["policy_hash"],
    }
    manifest["manifest_hash"] = hashlib.sha256(encoded(manifest)).hexdigest()
    (output / "manifest.json").write_bytes(encoded(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--sweep", type=Path, required=True)
    parser.add_argument("--publication-policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.inputs, args.sweep, args.publication_policy, args.output)
