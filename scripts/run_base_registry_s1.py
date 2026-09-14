"""V0.5 data-only runner. Existing R1-R7/product artifacts stay byte-identical.

Writes private canonical artifacts exclusively; no production forecast or fit calls.
With --enrichment-from, repeat without networking using previously hashed snapshots.
"""

import argparse
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest, fixed
from backend.app.area_yield.experiment import file_hash, read_json, write_csv, write_json
from backend.app.base_registry.business import audit_season, map_farms
from backend.app.base_registry.intake import fetch_elevation, fetch_region_screen, import_workbook
from scripts.run_frozen_evidence_expansion_r6 import intake


def tree_hashes(root: Path, excluded: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): file_hash(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_relative_to(excluded)
    }


def verify_snapshot(value: dict[str, Any]) -> None:
    if value["hash"] != digest({k: v for k, v in value.items() if k != "hash"}):
        raise ValueError("enrichment hash mismatch")


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(args.config)
    if args.output.exists():
        raise ValueError("append-only new output directory required")
    before = tree_hashes(args.history_root, args.output)
    registry = import_workbook(
        args.workbook, config["workbook_sha256"], config["expected_base_count"]
    )
    args.output.mkdir(parents=True, mode=0o700)
    write_json(args.output / "old_artifact_hashes.json", before)
    if args.enrichment_from:
        elevation = read_json(args.enrichment_from / "elevation-enrichment.json")
        region = read_json(args.enrichment_from / "region-screen.json")
    else:
        elevation, region = fetch_elevation(registry), fetch_region_screen(registry)
    for value in (elevation, region):
        verify_snapshot(value)
    write_json(args.output / "elevation-enrichment.json", elevation)
    write_json(args.output / "region-screen.json", region)
    indexed_elevation = {r["base_id"]: r for r in elevation["rows"]}
    indexed_region = {r["base_id"]: r for r in region["rows"]}
    for b in registry["bases"]:
        e = indexed_elevation.get(b["base_id"])
        if e:
            if (e["longitude"], e["latitude"]) != (b["longitude"], b["latitude"]):
                raise ValueError("enrichment coordinate mismatch")
            b.update(
                elevation_m=e["elevation_m"],
                elevation_source=elevation["hash"],
                elevation_review_status=e["status"],
            )
        b["region_scope"] = indexed_region[b["base_id"]]["region_scope"]
        b["provenance"]["region_screen_hash"] = region["hash"]
    historical = read_json(Path(config["history_config"]))["sources"]
    spec3 = {
        **read_json(Path(config["third_season_config"]))["source"],
        "path": str(args.source_25_26),
    }
    sources = historical + [spec3]
    aliases = {k: tuple(v) for k, v in config["aliases"].items()}
    results, profiles = [], []
    all_identities: set[str] = set()
    for spec in sources:
        if spec["legacy_sealed_test"] is not False or not spec["authorization_reference"]:
            raise ValueError("nonsealed authorization required")
        rows, profile = intake(args.history_root, spec)
        # Accepted R3 profiles must not conceal unresolved source-grain defects.
        if any(
            profile.get(k, 0)
            for k in (
                "invalid_date_count",
                "null_quantity_row_count",
                "negative_quantity_row_count",
                "duplicate_row_count",
            )
        ):
            raise ValueError("source defect needs row-level qualification before aggregation")
        profiles.append(profile)
        all_identities.update(r["canonical_farm_id"] for r in rows)
        result = audit_season(registry, {**spec, "rows": rows}, aliases)
        result["season"] = spec["season"]
        results.append(result)
    audits = [r for result in results for r in result["audit"]]
    mapping = map_farms(registry, all_identities, aliases)
    for b in registry["bases"]:
        relevant = [r for r in audits if r["base_id"] == b["base_id"]]
        b["historical_seasons"] = [r["season"] for r in relevant if r["raw_first_harvest_date"]]
        b["historical_season_count"] = len(b["historical_seasons"])
        b["data_completeness_level"] = (
            "COMPLETE_SAMPLES_AVAILABLE"
            if any(r["yield_eligible"] for r in relevant)
            else "PARTIAL_OR_BLOCKED"
        )
    registry["enrichment_hashes"] = {"elevation": elevation["hash"], "region": region["hash"]}
    registry["hash"] = digest({k: v for k, v in registry.items() if k != "hash"})
    mapping_authority = {
        "version": config.get("mapping_authority_version", "BASE_MEMBER_MAPPING_R1"),
        "workbook_hash": config["workbook_sha256"],
        "aliases": config["aliases"],
        "policy": "EXACT_FIRST_EXPLICIT_ALIAS_ONLY_NO_FUZZY_NO_MULTI_ASSIGNMENT",
    }
    mapping_authority_hash = digest(mapping_authority)
    write_json(
        args.output / "mapping-authority.json",
        {**mapping_authority, "hash": mapping_authority_hash},
    )
    write_json(args.output / "base-registry-v1.json", registry)
    write_csv(args.output / "base-registry-normalized.csv", registry["bases"])
    write_json(
        args.output / "source-manifest.json",
        {"workbook_hash": config["workbook_sha256"], "sources": profiles, "configuration": config},
    )
    write_csv(args.output / "member-farm-mapping.csv", mapping)
    write_csv(args.output / "business-season-boundary-audit.csv", audits)
    write_csv(
        args.output / "base-daily-ledger.csv", [r for result in results for r in result["daily"]]
    )
    member_rows = []
    for b in registry["bases"]:
        resolved_names = {
            r["normalized_identity"] for r in mapping if r["matched_base_id"] == b["base_id"]
        }
        for f in b["covered_farms"]:
            targets = [x for x in registry["bases"] if f in x["covered_farms"]]
            status = (
                "AMBIGUOUS"
                if len(targets) > 1
                else "RESOLVED"
                if f in resolved_names
                else "UNRESOLVED"
            )
            member_rows.append({"base_id": b["base_id"], "member": f, "status": status})
    write_csv(args.output / "member-coverage.csv", member_rows)
    with localcontext() as ctx:
        ctx.prec = 50
        pre = sum((Decimal(r["pre_cutoff_total_kg"]) for r in audits), Decimal(0))
        post = sum((Decimal(r["post_cutoff_total_kg"]) for r in audits), Decimal(0))
        for result in results:
            subtotal = sum(
                (
                    Decimal(r["pre_cutoff_total_kg"]) + Decimal(r["post_cutoff_total_kg"])
                    for r in result["audit"]
                ),
                Decimal(0),
            )
            if subtotal + Decimal(result["excluded_total_kg"]) != Decimal(
                result["source_recorded_total_kg"]
            ):
                raise ValueError("source/assigned/excluded reconciliation failed")
        summary = {
            "task_id": config["task_id"],
            "correction_task_id": config.get("correction_task_id"),
            "mapping_authority_hash": mapping_authority_hash,
            "registry_hash": registry["hash"],
            "workbook_hash": config["workbook_sha256"],
            "total_base_count": len(registry["bases"]),
            "region_counts": dict(Counter(b["region_scope"] for b in registry["bases"])),
            "elevation_established_count": sum(
                b["elevation_m"] is not None for b in registry["bases"]
            ),
            "elevation_pending_count": sum(b["elevation_m"] is None for b in registry["bases"]),
            "coordinate_crs_status": "NOT_ESTABLISHED_DEM_QUERY_ASSUMPTION_REQUIRES_REVIEW",
            "member_identity_count": len(member_rows),
            "member_status_counts": dict(Counter(r["status"] for r in member_rows)),
            "historical_identity_count": len(all_identities),
            "historical_mapping_counts": dict(Counter(r["match_status"] for r in mapping)),
            "base_season_audit_count": len(audits),
            "coverage_counts": dict(Counter(r["coverage_status"] for r in audits)),
            "pre_cutoff_total_kg_all_bases": fixed(pre),
            "post_cutoff_total_kg_all_bases": fixed(post),
            "post_cutoff_ratio_all_bases": fixed(post / (pre + post)) if pre + post else None,
            "totals_semantics": (
                "MAPPED_RECORDED_SUBTOTALS_INCLUDE_PARTIAL_BASES_NOT_COMPLETE_YIELD_LABELS"
            ),
            "bases_post_cutoff_peak_exceeds_business_peak": sorted(
                {
                    r["canonical_base_name"]
                    for r in audits
                    if r["post_cutoff_peak_exceeds_business_peak"]
                }
            ),
            "source_reconciliation": [
                {
                    "season": r["season"],
                    "source_total_kg": r["source_recorded_total_kg"],
                    "excluded_unresolved_kg": r["excluded_total_kg"],
                }
                for r in results
            ],
            "old_artifacts_unchanged": before == tree_hashes(args.history_root, args.output),
            "climate_zone_mapping_frozen": False,
            "model_execution": False,
        }
    if not summary["old_artifacts_unchanged"]:
        raise ValueError("historical artifact mutation")
    write_json(args.output / "summary.json", summary)
    write_json(
        args.output / "artifact-manifest.json",
        {p.name: file_hash(p) for p in sorted(args.output.iterdir()) if p.is_file()},
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base_registry_s1.json"))
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--source-25-26", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enrichment-from", type=Path)
    print(run(parser.parse_args()))


if __name__ == "__main__":
    main()
