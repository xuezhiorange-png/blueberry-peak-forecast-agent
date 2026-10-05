"""Offline weather-only semantics projection; no mutation of frozen V0.14."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

START = datetime(2024, 11, 12, tzinfo=UTC)
END = datetime(2026, 4, 16, tzinfo=UTC)


def encoded(body: Any) -> bytes:
    return (
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def availability(
    issue: datetime, cutoff: datetime, documented_available_at: datetime | None = None
) -> bool:
    if issue.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError("AWARE_TIMES_REQUIRED")
    issue = issue.astimezone(UTC)
    if issue.hour not in {0, 12} or any((issue.minute, issue.second, issue.microsecond)):
        raise ValueError("EXACT_00_OR_12_RUN_REQUIRED")
    assumed = issue + timedelta(hours=8)
    if documented_available_at is not None:
        if documented_available_at.tzinfo is None or documented_available_at < issue:
            raise ValueError("INVALID_PUBLICATION_RECEIPT_TIME")
        assumed = max(assumed, documented_available_at)
    return (
        START <= issue < END
        and assumed <= cutoff
        and timedelta(0) <= cutoff - issue <= timedelta(hours=36)
    )


def validate_accumulation(meta: dict[str, Any]) -> None:
    if (
        any(
            meta[k] != v
            for k, v in {
                "shortName": "tp",
                "units": "m",
                "stepType": "accum",
                "startStep": 0,
                "forecastTime": 0,
            }.items()
        )
        or meta["endStep"] <= 0
    ):
        raise ValueError("CONTINUOUS_T0_TP_NOT_PROVEN")


def classify_delta(delta: Decimal, bound: Decimal) -> str:
    if not delta.is_finite() or not bound.is_finite() or bound < 0:
        raise ValueError("INVALID_PACKING_COMPARISON")
    if delta >= 0:
        return "NONNEGATIVE"
    return "PACKING_COMPATIBLE_NOT_PROVEN" if -delta <= bound else "UNKNOWN_EXCEEDS_PACKING_BOUND"


def generate(inputs: Path, prior: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_IMMUTABLE_DIRECTORY")
    previous = (prior / "manifest.json").read_bytes()
    if hashlib.sha256(previous).hexdigest() != (
        "b1345a824b77f144cb8676f3895a649d67a18b92f97dbd81c1046329c60e27b6"
    ):
        raise ValueError("FROZEN_PRIOR_SWEEP_MANIFEST_DRIFT")
    manifest = json.loads(previous)
    for member in manifest["members"]:
        if hashlib.sha256((prior / member["name"]).read_bytes()).hexdigest() != member["sha256"]:
            raise ValueError("FROZEN_PRIOR_SWEEP_MEMBER_DRIFT")
    sources = json.loads((inputs / "official-source-receipts.json").read_bytes())
    audit = json.loads((inputs / "raw-rollback-audit.json").read_bytes())
    if len(sources) != 6:
        raise ValueError("OFFICIAL_SOURCE_SET_INCOMPLETE")
    for receipt in sources:
        snapshot = inputs / (receipt["source_id"] + ".html")
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("OFFICIAL_SOURCE_SNAPSHOT_DRIFT")
        if (
            not receipt["url"].startswith(
                ("https://www.ecmwf.int/", "https://confluence.ecmwf.int/")
            )
            or receipt["http_status"] != 200
        ):
            raise ValueError("UNAPPROVED_OFFICIAL_SOURCE")
    output.mkdir(parents=True, exist_ok=True)
    reports: dict[str, Any] = {}
    reports["ecmwf-official-publication-evidence.json"] = {
        "sources": sources,
        "official_evidence_found": True,
        "historical_schedule_version": "14, 2024-11-11",
        "ifs_00_full_360_nominal_end_utc": "07:34:00",
        "ifs_12_full_360_nominal_end_utc": "19:34:00",
        "open_data_release_relation": "At end of real-time dissemination schedule",
        "per_run_http_publication_receipt_proven": False,
        "mirror_delay_or_outage_upper_bound_proven": False,
    }
    publication = {
        "policy_id": "V0_15_HISTORICAL_IFS_NOMINAL_PLUS_8H_TIER_B_R1",
        "tier": "PIT_EVIDENCE_TIER_B_ASSUMED",
        "business_timezone": "Asia/Shanghai",
        "cutoff_local_time": "17:00:00",
        "eligible_cycles": ["00", "12"],
        "conservative_publication_lag_minutes": 480,
        "lag_derivation": (
            "Official 454-minute full-360 schedule rounded UP to next whole hour;"
            "26-minute conservatism,not fitted from outcomes"
        ),
        "effective_research_issue_start": START.isoformat(),
        "effective_research_issue_end_exclusive": END.isoformat(),
        "max_run_age_hours": 36,
        "same_run_required": True,
        "field_completeness_required": True,
        "deterministic_order": ["issue_time_descending", "run_id_ascending"],
        "frozen": True,
        "conservative": True,
        "result_independent": True,
        "assumptions": [
            "Nominal schedule applied during documented 49r1 interval",
            "Official public replica had no unrecorded delay beyond hour-rounded nominal lag",
        ],
        "known_delay_receipt_overrides_assumption": True,
        "actual_historical_available_at_reconstructed": False,
        "tier_a_equivalence": False,
        "strict_prior_policy_rewritten": False,
        "publication_receipts_required_for_strict_tier_a": True,
        "v014_changed": False,
    }
    publication["policy_hash"] = hashlib.sha256(encoded(publication)).hexdigest()
    reports["historical-run-availability-policy.json"] = publication
    for sample in audit["samples"]:
        for field in sample["fields"]:
            validate_accumulation(field["metadata"])
    reports["precipitation-rollback-audit.json"] = audit
    exceed = sum(p["exceeds_packing_bound_count"] for s in audit["samples"] for p in s["pairs"])
    reports["precipitation-accumulation-semantics.json"] = {
        "raw_product_accumulation": "CONTINUOUS_FROM_T0",
        "start_step_zero_all_downloaded_tp": True,
        "forecast_reset_detected": False,
        "local_spatial_interpolation_executed": False,
        "raw_grid_rollback_detected": True,
        "20260101_cause": "NUMERICAL_PACKING_ARTIFACT_COMPATIBLE_NOT_UNIQUELY_PROVEN",
        "20241113_cause": "UNKNOWN_EXCEEDS_SINGLE_PAIR_PACKING_BOUND",
        "exceeds_single_pair_packing_bound_grid_occurrences": exceed,
        "upstream_regridding_or_prior_quantization_unobservable": True,
        "unpacked_native_model_truth_available": False,
        "encoding": "grid_ccsds; binary quantization still present",
        "causal_semantics_fully_closed": False,
        "do_not_transfer_10_day_ENS_FAQ_fixed_threshold_to_15_day_IFS": True,
    }
    reports["weather8-precipitation-policy.json"] = {
        "policy_id": "V0_15_RESEARCH_TP_ENDPOINT_FAIL_CLOSED_R1",
        "precip_0_168_mm": "tp168 * 1000",
        "precip_168_360_mm": "(tp360 - tp168) * 1000",
        "same_run_same_grid_same_unit_required": True,
        "tp168_nonnegative_required": True,
        "tp360_gte_tp168_required": True,
        "regression_action": "REJECT_NO_NUMERIC_OUTPUT",
        "packing_diagnostic_bound_m": "packingError168 + packingError360",
        "diagnostic_bound_is_correction_tolerance": False,
        "clipping_allowed": False,
        "tolerance_policy_frozen": False,
        "window_policy_frozen": True,
        "numerical_precipitation_semantics_closed": False,
        "raw_evidence_preserved": True,
        "v014_code_or_policy_changed": False,
    }
    with (prior / "historical-ecmwf-run-availability-matrix.csv").open() as f:
        origins = list(csv.DictReader(f))
    assert len(origins) == 847
    diagnostics = []
    for row in origins:
        issue = row["recoverable_issue_time"]
        assumed = bool(
            issue
            and availability(
                datetime.fromisoformat(issue), datetime.fromisoformat(row["forecast_cutoff"])
            )
        )
        diagnostics.append(
            {
                "date": row["date"],
                "archive_run_id": row["recoverable_run_id"],
                "tier_b_nominal_publication_assumed": assumed,
                "full_numerical_weather8_proven": False,
            }
        )
    reports["pit-weather-coverage-recalculation.json"] = {
        "total_origins": 847,
        "archive_field_complete_origins": 422,
        "tier_b_schedule_and_index_eligible_origins": sum(
            r["tier_b_nominal_publication_assumed"] for r in diagnostics
        ),
        "pit_eligible_run_origin_count": None,
        "pit_weather8_complete_origin_count": None,
        "pit_weather8_complete_origin_rate": None,
        "pit_full_base_season_count": None,
        "pit_partial_base_season_count": None,
        "pit_no_admitted_coverage_base_season_count": None,
        "combined_recalculation_gate": "NOT_EXECUTED_AS_ADMISSION_PRECIPITATION_CAUSE_UNCLOSED",
        "diagnostic_projection_not_admission": True,
        "origins": diagnostics,
        "strict_tier_a_publication_count": 0,
        "not_computed_is_not_zero_or_archive_absence": True,
        "area_tier_c_count_unchanged": 117,
        "identity_unresolved_count_unchanged": 44,
    }
    reports["s0-weather-pit-readiness-recommendation.json"] = {
        "result": "PARTIAL",
        "official_publication_evidence_found": True,
        "conservative_publication_lag_defined": True,
        "historical_publication_policy_frozen": True,
        "pit_weather_tier_b_feasible": True,
        "publication_availability_semantics_closed_at_tier_b_only": True,
        "precipitation_accumulation_causal_semantics_closed": False,
        "s0_weather_pit_ready": False,
        "s1_ready": False,
        "s1_authorized": False,
        "next_weather_evidence_needed": (
            "Original native/unpacked or upstream packing/regridding lineage "
            "for364 beyond-bound20241113points; not more years or training"
        ),
        "no_model_training_or_scoring": True,
        "current_actual_or_label_vault_accessed": False,
        "business_and_production_unchanged": True,
    }
    for name, body in reports.items():
        (output / name).write_bytes(encoded(body))
    members = [
        {
            "name": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        }
        for p in sorted(output.glob("*.json"))
    ]
    manifest = {
        "schema": "V0_15_ECMWF_SEMANTICS_CLOSURE_MANIFEST_R1",
        "members": members,
        "prior_sweep_manifest_sha256": hashlib.sha256(
            (prior / "manifest.json").read_bytes()
        ).hexdigest(),
        "source_receipts_sha256": hashlib.sha256(
            (inputs / "official-source-receipts.json").read_bytes()
        ).hexdigest(),
        "raw_audit_sha256": hashlib.sha256(
            (inputs / "raw-rollback-audit.json").read_bytes()
        ).hexdigest(),
    }
    manifest["manifest_hash"] = hashlib.sha256(encoded(manifest)).hexdigest()
    (output / "manifest.json").write_bytes(encoded(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.inputs, args.prior, args.output)
