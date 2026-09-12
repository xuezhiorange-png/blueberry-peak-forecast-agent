"""Read-only source search outcome materialization; never promotes planning proxies."""

import argparse
import csv
import json
from pathlib import Path

from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.forecast_quality.farm_total_area_authority import load_area_authority_package
from scripts.run_prior_shape_r3b import verify


def run(root: Path, output: Path) -> dict:
    source = Path("docs/v0-3/s3/authority/farm_total_area_authority_package.json")
    package = load_area_authority_package(read_json(source))
    previous = root / "shape-r3a-confirmed"
    manifest = read_json(previous / "artifact_manifest.json")
    verify(previous, manifest)
    matrix = read_csv(previous / "farm_season_qualification.csv")
    farms = sorted({r["farm"] for r in matrix})
    bindings = []
    for farm in farms:
        candidates = [r for r in package.rows if farm in r.source_farm_business_keys]
        bindings.append(
            {
                "source_farm_label": farm,
                "canonical_farm": farm,
                "productive_area_mu": "",
                "candidate_proxy_area_mu": ";".join(str(r.area_mu) for r in candidates),
                "area_basis": "UNCONFIRMED_PREVIOUS_SEASON_PROXY" if candidates else "NONE",
                "source_reference": str(source) if candidates else "NONE",
                "source_hash": file_hash(source) if candidates else "",
                "effective_scope": ";".join(
                    ",".join(r.source_farm_business_keys) for r in candidates
                ),
                "binding_status": "AMBIGUOUS" if candidates else "MISSING",
                "exclusion_reason": (
                    "PLANNING_PROXY_NOT_CONFIRMED_PRODUCTIVE_AREA_OR_AGGREGATE_SCOPE"
                )
                if candidates
                else "NO_EXACT_FARM_PRODUCTIVE_AREA_SOURCE_FOUND",
            }
        )
    strict_sets = [
        {r["farm"] for r in matrix if r["season"] == season and r["strict_eligible"] == "True"}
        for season in ("2023-2024", "2024-2025")
    ]
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_csv(output / "farm_area_authority_r4.csv", bindings)
    with (output / "farm_season_yield_r4.csv").open("x", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerow(
            [
                "canonical_farm",
                "season",
                "season_total_harvest_kg",
                "productive_area_mu",
                "yield_kg_per_mu",
                "area_basis",
                "season_completeness",
                "eligible_for_training",
                "eligible_for_validation",
            ]
        )
    (output / "farm_season_yield_r4.csv").chmod(0o600)
    result = {
        "task_id": "NEXT_VERSION_FARM_AREA_YIELD_TOTAL_MODEL_R4",
        "result": "BLOCKED_MISSING_PRODUCTIVE_AREA_VALUES",
        "area_semantics_confirmed": True,
        "season_specific_area_required": False,
        "same_canonical_farm_same_area_across_seasons": True,
        "area_bound_farm_count": 0,
        "area_bound_complete_farm_season_count": 0,
        "cross_season_area_bound_farm_count": 0,
        "training_executed": False,
        "trained_models": [],
        "selected_total_model": None,
        "forecast_example_executed": False,
        "exact_missing_area_farms": sorted(strict_sets[0] & strict_sets[1]),
        "all_strict_training_farms_requiring_area": sorted(strict_sets[0]),
        "all_strict_validation_farms_requiring_area": sorted(strict_sets[1]),
        "audited_farm_count": len(farms),
        "ambiguous_proxy_binding_count": sum(r["binding_status"] == "AMBIGUOUS" for r in bindings),
        "area_package_hash": file_hash(source),
        "area_package_canonical_integrity_verified": True,
        "area_package_original_class": "PREVIOUS_SEASON_PROXY",
        "source_workbook_title": "光筑25产季加工布局规划方案.xlsx",
        "source_workbook_hash": dict(package.source_file_hashes)["source_workbook"],
        "banna_736_disposition": "OLD_DX_ACCEPTANCE_SUBSCOPE_NOT_FARM_DENOMINATOR",
        "model_comparison_status": "NOT_EXECUTED_NO_BOUND_AREA",
        "linear_area_scaling_implemented": True,
        "area_scaling_validated": False,
        "private_output": str(output),
    }
    for name in (
        "training_manifest.json",
        "model_comparison_r4.json",
        "cross_season_total_metrics.json",
    ):
        write_json(output / name, result)
    write_json(
        output / "artifact_manifest.json", {f.name: file_hash(f) for f in sorted(output.iterdir())}
    )
    verify(previous, manifest)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.output), ensure_ascii=False, indent=2))
