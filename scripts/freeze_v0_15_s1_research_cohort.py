"""Freeze S1 from committed metadata only. No database, network, or label input."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_research_cohort import (
    admit_base,
    assert_same_rowset,
    canonical,
    digest,
    past_features,
    split_roles,
    target_dates,
)

BASE_SHA = "122529c9aa4bcb32e32da6f9d016684a110e561d"
PUBLICATION_HASH = "896e19617c0d12579fa33cf9ed17e81e6ed2e4337866c10de00c3932918565c7"
PRECIP_HASH = "dd84aa464912cb93a1e40506488a39c7b5bc5b82f2b73b67216e0be2563cda2b"
FEATURE_HASH = "ac1f76a07b422420bbe9164802d419d531a7457ec5976d353af5d99cfc498059"
BUSINESS = "docs/v0-15/evidence/business-data-closure-r1"
WEATHER = "docs/v0-15/evidence/precipitation-packing-policy-closure-r1"
PUBLICATION = (
    "docs/v0-15/evidence/ecmwf-publication-precipitation-closure-r1/"
    "historical-run-availability-policy.json"
)
EXPOSURE = "docs/v0-8/evidence/v0.8.0-research-closeout.json"


def load_sources(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Authenticate inherited manifests before reading admission metadata."""
    pins = {
        f"{BUSINESS}/report-manifest.json": (
            "cb325c3147f9e9640052a2c6828bc06043794a00b9517887f29899dd53af07fa"
        ),
        f"{WEATHER}/manifest.json": (
            "1e86c38eb916cba7fac7c52a396ecb7c4325188d9460680046c9f8f36a9881f3"
        ),
    }
    values: dict[str, Any] = {}
    for path, expected in list(pins.items()):
        content = (root / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("S0_MANIFEST_DRIFT")
        manifest = json.loads(content)
        parent = str(Path(path).parent)
        if "files" in manifest:
            pins.update({f"{parent}/{name}": sha for name, sha in manifest["files"].items()})
        else:
            pins.update({f"{parent}/{m['name']}": m["sha256"] for m in manifest["members"]})
    for path, expected in pins.items():
        content = (root / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("S0_SOURCE_DRIFT")
        if path.endswith(".json"):
            values[path] = json.loads(content)
    for path in (PUBLICATION, EXPOSURE):
        content = (root / path).read_bytes()
        expected = {
            PUBLICATION: "7deb408a4ddd89419d06ba1c5472134eac59fbfee582d79495e4c412e58a9fd1",
            EXPOSURE: "e0b83f0f229cd422f719094f4b6930650bfa1a62f05853f460c76258ce5018ce",
        }[path]
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("PUBLICATION_OR_EXPOSURE_SOURCE_DRIFT")
        pins[path] = hashlib.sha256(content).hexdigest()
        values[path] = json.loads(content)
    publication = values[PUBLICATION]
    precip = values[f"{WEATHER}/precipitation-packing-artifact-policy.json"]
    if (
        publication["policy_hash"] != PUBLICATION_HASH
        or precip["policy_hash"] != PRECIP_HASH
        or precip["threshold_selected_mm"] != "0.08"
    ):
        raise ValueError("WEATHER_POLICY_DRIFT")
    return values, pins


def leakage_proof() -> dict[str, Any]:
    origin = "2025-02-01T17:00:00+08:00"
    rows = [
        {
            "base_id": "synthetic",
            "season": "2024-2025",
            "business_date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "zone": "FEATURE_ZONE",
            "state": "VALID_OBSERVED",
            "quantity_kg": Decimal(i + 1),
        }
        for i in range(31)
    ]
    initial = digest(past_features(rows, origin, "synthetic", "2024-2025", "2025-01-01"))
    results = []
    for label, day in [
        ("D+1", "2025-02-02"),
        ("D+7", "2025-02-08"),
        ("D+15", "2025-02-16"),
        ("SEASON_FINAL", "2025-04-15"),
    ]:
        modified = rows + [
            {
                "base_id": "synthetic",
                "season": "2024-2025",
                "business_date": day,
                "zone": "LABEL_ZONE",
                "state": "VALID_OBSERVED",
                "quantity_kg": Decimal("999999999"),
            }
        ]
        after = digest(past_features(modified, origin, "synthetic", "2024-2025", "2025-01-01"))
        if after != initial:
            raise ValueError("FUTURE_ACTUAL_LEAKAGE")
        results.append({"mutation": label, "feature_hash": after, "feature_hash_unchanged": True})
    return {
        "fixture": "SYNTHETIC_ONLY",
        "result": "PASS",
        "baseline_feature_hash": initial,
        "cases": results,
        "historical_actual_quantities_read": False,
    }


def derive(root: Path) -> dict[str, Any]:
    sources, pins = load_sources(root)
    matrix = sources[f"{BUSINESS}/base-season-training-readiness-matrix.json"]["rows"]
    roles = split_roles([r["season"] for r in matrix])
    area_rows = sources[f"{BUSINESS}/area-pit-evidence-reclassification.json"]["rows"]
    areas = {(r["base_id"], r["season"]): r for r in area_rows}
    identities: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in sources[f"{BUSINESS}/identity-authority-closure-report.json"]["rows"]:
        if r["base_id"] and r["closure_status"] == "ACCEPTED_RETROSPECTIVE":
            identities.setdefault((r["base_id"], r["season"]), []).append(r)
    weather_rows = sources[f"{WEATHER}/historical-base-season-origin-weather-pit-matrix.json"][
        "rows"
    ]
    weather = {(r["base_id"], r["season"], r["forecast_origin"]): r for r in weather_rows}
    if len(weather) != len(weather_rows):
        raise ValueError("DUPLICATE_SOURCE_ORIGIN")
    policy: dict[str, Any] = {
        "policy_version": "V0_15_S1_RETROSPECTIVE_RESEARCH_ADMISSION_R1",
        "strict_pit": False,
        "retrospective_authority_used": True,
        "prospective_claim_allowed": False,
        "base_admission": (
            "Complete frozen business window; accepted explicit retrospective identity; "
            "existing area; no UNKNOWN/PARTIAL/MISSING/CONFLICTING/INVALID"
        ),
        "weather_admission": (
            "Base admission AND same-origin S0 qualified Weather8 AND complete D1-D15 "
            "within frozen business window"
        ),
        "origin_cutoff": "17:00 Asia/Shanghai",
        "target_leads": list(range(1, 16)),
        "publication_policy_hash": PUBLICATION_HASH,
        "precipitation_policy_hash": PRECIP_HASH,
        "feature_policy_hash": FEATURE_HASH,
        "precipitation_threshold_mm": "0.08",
        "weather_evidence_level": "TIER_B_ASSUMED",
        "full_numeric_weather_materialized_in_s1": False,
        "unknown_is_zero": False,
        "partial_is_complete": False,
        "current_season_excluded": "2026-2027",
        "source_base_sha": BASE_SHA,
        "source_hashes": pins,
    }
    policy["policy_hash"] = digest(policy)
    cohort = []
    ledger = []
    admitted: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(matrix, key=lambda r: (r["season"], r["base_id"])):
        key = row["base_id"], row["season"]
        allowed, reasons = admit_base(row)
        if key not in areas or areas[key]["tier"] != row["area_pit_tier"]:
            raise ValueError("AREA_LINEAGE_MISMATCH")
        mapping = sorted(identities.get(key, []), key=lambda r: r["source_farm_label"])
        if allowed and not mapping:
            raise ValueError("IDENTITY_LINEAGE_MISSING")
        # Public closeout explicitly covers ALL canonical latest-season Bases.
        # Earlier 37 training rows are reported only in aggregate; without a
        # per-Base membership receipt, retain UNKNOWN rather than infer from counts.
        known = (
            row["season"] == "2025-2026"
            and sources[EXPOSURE]["benchmark_lifecycle"]["benchmark_2025_2026_consumed"]
        )
        exposure = "KNOWN_EXPOSED" if known else "UNKNOWN_EXPOSURE"
        ledger.append(
            {
                "base_id": key[0],
                "season": key[1],
                "exposure_status": exposure,
                "benchmark_exposure_status": "PREVIOUSLY_EXPOSED_BENCHMARK"
                if known
                else "UNKNOWN_EXPOSURE",
                "dataset_artifact": "V0_8_39_CANONICAL_BASE_BENCHMARK"
                if known
                else "PER_BASE_TRAINING_MEMBERSHIP_NOT_PUBLICLY_BOUND",
                "model_version": "V0.8 S8/S9/R2C" if known else "UNKNOWN_PER_BASE",
                "metric_benchmark": "Daily/season/peak historical benchmark"
                if known
                else "UNKNOWN_PER_BASE",
                "source_hash": pins[EXPOSURE],
            }
        )
        entry = {
            "base_id": key[0],
            "season": key[1],
            "area_authority_id": areas[key]["area_authority_id"],
            "area_evidence_level": row["area_pit_tier"],
            "area_source_hash": areas[key]["source_hash"],
            "identity_mapping_id": f"retrospective_mapping_{digest(mapping)[:24]}"
            if mapping
            else None,
            "identity_evidence_level": "RETROSPECTIVE_USABLE"
            if mapping and row["identity_status"] == "ACCEPTED_RETROSPECTIVE"
            else "UNRESOLVED",
            "identity_mapping_hash": digest(mapping),
            "label_completeness": "COMPLETE" if allowed else "PARTIAL",
            "exposure_status": exposure,
            "temporal_role": roles[key[1]],
            "base_research_eligible": allowed,
            "research_admission_status": "ADMITTED" if allowed else "EXCLUDED",
            "exclusion_reason": reasons,
            "business_start": row["target_start_date"],
            "business_end": row["target_end_date"],
            "strict_pit": False,
            "retrospective_authority_used": True,
            "prospective_claim_allowed": False,
        }
        cohort.append(entry)
        if allowed:
            admitted[key] = entry
    origins = []
    for key, entry in sorted(admitted.items()):
        start, end = (
            date.fromisoformat(entry["business_start"]),
            date.fromisoformat(entry["business_end"]),
        )
        for offset in range((end - start).days + 1):
            origin = f"{(start + timedelta(days=offset)).isoformat()}T17:00:00+08:00"
            w = weather.get((*key, origin))
            if w is None:
                raise ValueError("S0_WEATHER_ORIGIN_MISSING")
            targets = target_dates(origin, end.isoformat())
            available = bool(
                w["weather8_coverage_complete"]
                and w["tier_b_publication_eligible"]
                and w["tp_endpoints_audited"]
                and w["precipitation_policy_pass"]
            )
            item = {
                "base_id": key[0],
                "season": key[1],
                "forecast_origin": origin,
                "forecast_horizon": "D1-D15",
                "target_dates": targets,
                "area_authority_id": entry["area_authority_id"],
                "area_evidence_level": entry["area_evidence_level"],
                "identity_mapping_id": entry["identity_mapping_id"],
                "identity_evidence_level": entry["identity_evidence_level"],
                "weather_available": available,
                "weather_evidence_level": "TIER_B_ASSUMED" if available else "UNAVAILABLE",
                "weather_policy_version": "V0_14_RUNREL_168_360_WEATHER_R1",
                "publication_policy_hash": PUBLICATION_HASH,
                "precipitation_policy_hash": PRECIP_HASH,
                "selected_run_id": w["selected_run_id"],
                "label_status": "COMPLETE" if targets else "OUTSIDE_FULL_H15_BUSINESS_WINDOW",
                "exposure_status": entry["exposure_status"],
                "temporal_role": entry["temporal_role"],
                "base_research_eligible": bool(targets),
                "weather_comparable_eligible": bool(targets) and available,
                "exclusion_reason": []
                if targets and available
                else (["H15_TAIL_EXCLUDED"] if not targets else ["S0_WEATHER_NOT_QUALIFIED"]),
                "retrospective_authority_used": True,
                "strict_pit": False,
                "source_weather_row_hash": digest(w),
                "source_business_row_hash": digest(entry),
                "label_projection_hash": sources[
                    f"{BUSINESS}/canonical-logical-harvest-record-report.json"
                ]["logical_projection_hash"],
                "numeric_weather_materialization_required": True,
            }
            item["row_hash"] = digest(item)
            origins.append(item)
    origins.sort(key=lambda r: (r["season"], r["base_id"], r["forecast_origin"]))
    base_origins = [r for r in origins if r["base_research_eligible"]]
    common = [r for r in origins if r["weather_comparable_eligible"]]
    common_hashes = [r["row_hash"] for r in common]
    assert_same_rowset({model: common_hashes for model in ("Ridge", "CatBoost", "LightGBM")})
    weather_keys = {(r["base_id"], r["season"]) for r in common}
    weather_cohort = [
        {
            **r,
            "weather_evidence_level": "TIER_B_ASSUMED",
            "weather_comparable_origin_count": sum(
                x["base_id"] == r["base_id"] and x["season"] == r["season"] for x in common
            ),
        }
        for key, r in sorted(admitted.items())
        if key in weather_keys
    ]
    splits = {}
    for season, role in roles.items():
        splits[role] = {
            "season": season,
            "base_season_count": sum(r["season"] == season for r in admitted.values()),
            "forecast_origin_count": sum(r["season"] == season for r in base_origins),
            "weather_base_season_count": sum(r["season"] == season for r in weather_cohort),
            "weather_forecast_origin_count": sum(r["season"] == season for r in common),
        }
    boundary = {
        "contract_id": "V0_15_S1_FEATURE_LABEL_BOUNDARY_R1",
        "feature_zone": {
            "application_path": "past_features / future feature-only reader",
            "harvest_business_date": "date < forecast_origin Asia/Shanghai local date",
            "management_event_time": "event_time < forecast_origin",
            "management_available_at": (
                "If unproven, retrospective grade must be retained; no fabricated available_at"
            ),
            "allowed_projection": ["base_id", "season", "business_date", "state", "quantity_kg"],
            "forbidden": [
                "target_actual",
                "future_season_total",
                "future_peak_date",
                "future_H7",
                "future_H15",
                "future_cumulative_harvest",
            ],
            "incomplete_past_window": "NULL plus availability mask; not zero",
        },
        "label_zone": {
            "application_path": "future target-only reader; never supplied to feature builder",
            "target_leads": list(range(1, 16)),
            "complete_daily_states": sorted(COMPLETE_LABEL_STATES),
            "unknown_partial_conflicting_invalid_missing": (
                "EXCLUDE_OR_MASK; NEVER_ZERO; incomplete target windows excluded"
            ),
            "H7": "D1-D7 complete",
            "H15": "D1-D15 complete",
            "single_day_peak": "max daily quantity; earliest date tie",
            "rolling7_peak": "9 complete windows; earliest start tie",
            "partial_denominator_allowed": False,
            "prediction_seal_before_evaluation_label_unlock": True,
            "evaluation_label_unlock_authorized_in_s1": False,
            "exposed_oot_is_blind": False,
        },
        "current_season_actual_access": False,
        "strict_pit": False,
    }
    exposure_counts = dict(Counter(r["exposure_status"] for r in ledger))
    recommendation = {
        "s1_contract_ready": True,
        "s2_authorized": False,
        "model_training_executed": False,
        "scoring_executed": False,
        "total_base_season_count": len(cohort),
        "base_research_base_season_count": len(admitted),
        "weather_comparable_base_season_count": len(weather_cohort),
        "total_research_forecast_origin_count": len(base_origins),
        "origin_universe_row_count_including_excluded_tails": len(origins),
        "weather_comparable_forecast_origin_count": len(common),
        "exposure_counts": exposure_counts,
        "splits": splits,
        "weather_benchmark_training_ready": splits["TRAIN"]["weather_forecast_origin_count"] > 0,
        "limitations": [
            "No Weather8 origins in earliest TRAIN split; do not silently alter temporal split",
            "All numeric Weather8 vectors still require isolated future materialization",
            "Earlier 37-row training exposure is aggregate, not per-Base proof: "
            "UNKNOWN_EXPOSURE preserved",
            "Retrospective area/identity are not contemporaneous PIT authority",
            "Labels/quantities were not read; completeness inherited from hashed S0 evidence",
        ],
        "s2_ready_for_separately_authorized_data_quality_work": True,
        "strict_pit": False,
        "prospective_claim_allowed": False,
        "2025_2026_previously_exposed": True,
        "2026_2027_reserved_for_prospective": True,
    }
    output = {
        "retrospective-research-admission-policy.json": policy,
        "retrospective-base-research-cohort.json": {
            "cohort_id": "RETROSPECTIVE_BASE_RESEARCH_COHORT",
            "admitted_rows": list(admitted.values()),
            "all_base_season_decisions": cohort,
        },
        "retrospective-weather-comparable-cohort.json": {
            "cohort_id": "RETROSPECTIVE_WEATHER_COMPARABLE_COHORT",
            "rows": weather_cohort,
        },
        "research-forecast-origin-universe.json": {"rows": origins},
        "retrospective-research-split-manifest.json": {
            "policy_hash": policy["policy_hash"],
            "splits": splits,
            "strict_pit": False,
            "prospective_claim_allowed": False,
            "random_split_allowed": False,
            "same_base_season_multiple_roles_allowed": False,
            "train_seasons": [s for s, role in roles.items() if role == "TRAIN"],
            "validation_seasons": [s for s, role in roles.items() if role == "VALIDATION"],
            "exposed_oot_seasons": [s for s, role in roles.items() if role == "EXPOSED_OOT"],
        },
        "benchmark-exposure-ledger.json": {
            "rows": ledger,
            "aggregate_prior_training_evidence": sources[EXPOSURE]["training_and_benchmark"],
            "aggregate_counts_do_not_prove_per_base_exposure": True,
        },
        "feature-label-boundary-contract.json": boundary,
        "common-comparison-rowset-contract.json": {
            "models": ["Ridge", "CatBoost", "LightGBM"],
            "ordered_row_hashes": common_hashes,
            "row_count": len(common_hashes),
            "rowset_hash": digest(common_hashes),
            "same_labels_horizon_weather_mask_denominator_required": True,
            "materialization_gate": (
                "Require finite eight-value weather hash and target-label hash for every row; "
                "algorithms must share exact hashes. Not executed in S1."
            ),
            "extra_rows": "EXPLORATORY_ONLY_NOT_COMMON_BENCHMARK",
        },
        "leakage-test-report.json": leakage_proof(),
        "s1-readiness-recommendation.json": recommendation,
    }
    manifest = {
        "schema": "V0_15_S1_RESEARCH_FREEZE_MANIFEST_R1",
        "source_base_sha": BASE_SHA,
        "source_hashes": pins,
        "members": [
            {
                "name": name,
                "sha256": hashlib.sha256(canonical(value)).hexdigest(),
                "size": len(canonical(value)),
            }
            for name, value in sorted(output.items())
        ],
    }
    manifest["manifest_hash"] = digest(manifest)
    output["manifest.json"] = manifest
    return output


COMPLETE_LABEL_STATES = {"VALID_OBSERVED", "REAL_ZERO"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = derive(args.repo_root)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("NONEMPTY_OUTPUT_REFUSED")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in sorted(reports.items()):
        (args.output / name).write_bytes(canonical(value))
    print(json.dumps(reports["s1-readiness-recommendation.json"], sort_keys=True))


if __name__ == "__main__":
    main()
