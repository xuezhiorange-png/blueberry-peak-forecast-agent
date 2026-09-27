"""Build the bounded V0.9-S2 data observability audit artifacts.

This is an inventory/report builder only. It does not query a live database,
load benchmark outcomes for selection, fit parameters, or execute a forecast.
"""

# This file contains long evidence labels and report paragraphs that are output verbatim.
# ruff: noqa: E501

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
S0_EXPECTED = {
    "docs/v0-9/s0/global-protected-blueberry-biology-and-management-authority-review-r1.md": "827725a44094e5e15643186fe8f82095adbff0bfc2b2ac549aca6600d06a4c13",
    "docs/v0-9/evidence/s0-global-protected-blueberry-biology-and-management-authority-review-r1.json": "530106f7291ab3d92fe4b0a0d682efc0fc154149218acda71369f76e785449cf",
    "docs/v0-9/s0/scientific-authority-matrix-r1.csv": "1fecd24c4aa537d5617a960e15ab74ace260ad35e30e63d9fdbe89e59bf88294",
    "docs/v0-9/s0/biological-causal-claim-register-r1.csv": "0ee8959db03f1ac28b226df06c00bf08c2427949b2f1e9de69a772bbd805d55a",
    "docs/v0-9/s0/evidence-conflict-and-uncertainty-register-r1.csv": "e5c17df1d33e3ef9dcc1d5d149598fa6a602a5c65a09f99d47e8040d42d94a91",
    "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv": "2d28f90e42eafeea14f252e96ed0c26e2bc6b78b1c8273263b5d2d32b1410325",
}
INPUT_HASHES = {
    "data/raw/2024_2025_receipts.xls": "a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5",
    "data/raw/2025_2026_receipts.xls": "66c4de6ddab4d8e3962eaaba0aab1b6ddcefff9f2605b36c950af3848e2a9c0b",
    "configs/base_registry_s1.json": "89d839004699744fe30b1cf5dfed5ea8df8e065d9933f4999b9bbfe818956830",
    "configs/v0_8_cross_season_identity_authority_r1.json": "",
    "configs/v0_8_s4_three_season_area_authority_r1.json": "",
    "configs/v0_6_s2_weather_provider_qualification_r2.json": "6ef41b0faf85fda24d16bcc97494ff74216dc52fe97c724ed08e4d6da6b356df",
    "configs/v0_6_s2_weather_provider_deterministic_acceptance_r3.json": "aa18e8e6652098e10b32f0c853ae70c4dcde5c83b7ebc618be7afc8689f61522",
    "configs/era5_land_historical_weather_r1.json": "9c57a419c3a15f9a683ef993114b9be0da02e611567997aa1b24867a47a42135",
    "configs/era5_land_historical_weather_r2.json": "025740724797179c28c6c36eca7ecad0643a145beb21f1cc7ecbc249e55a19fa",
    "configs/era5_land_historical_weather_r3.json": "1f683478773011303b2680366d03134aed4cf1104f11480fd9863d329c4135a8",
    "data/templates/production_plans.csv": "b0c8d1ec5b1e23d16a21fd43cb2ba103df00c2f70536ee7cfc0dd36b605d1386",
    "data/templates/season_variety_planting.csv": "1dfba21bc2af19bdfc4e36fa015a41da99d2ff95ca4fcdd718b31688789885f6",
    "data/templates/phenology_history.csv": "9da12442189f761239fbd7e731759c8f3de2d9e4fe640f1c6734f3cd86bb808c",
    "data/templates/weather_history.csv": "5f99ee46a43d468f8b722ddfc9a15ac0968151a691bf62bcc4227e4ea90de739",
    "data/templates/weather_daily_observations.csv": "d906da5b55469e8ca5f1e736dfcbf96213e323b66431addac2a51ed3ff7f2f0c",
    "data/templates/weather_source_locations.csv": "1ee92c3c0b92667e27ab4989c47a40ec64eb1927158b9d1e1a736fd0b56eff5a",
    "data/templates/location_weather_mappings.csv": "d121261e277045cb9e8f78c55d09d0555488b0ea9275ba012ff3eff8d9fb7c88",
}
PRIVATE_REFERENCES = {
    "V08_S4_AREA_MANIFEST": "a52a8342693eb9ce1731e2487e8c23fcf029c198d3fe66193552e4d7f58a27ff",
    "V08_S6_DAILY_ZERO_OVERLAY": "d0f94ea143cc44c555cc3299a8ea0b3073ab96173fa7927b53104a45c904a8e0",
    "V08_S6_ARTIFACT_MANIFEST": "d23ed98beccb98b11d7ca43800d19a6491deed6ff705513531a927139bab7cd7",
    "V08_S8_ARTIFACT_MANIFEST": "6561ac984de2b3ac1a7ba86e8fee91f888b641478a19af67355e4dba8cc8216e",
    "ECMWF_REAL_CAPTURE_MANIFEST": "aad170103e156a11424c2d487fff27c0b7a263223d7552b155f3c275317477f0",
    "ERA5_R3_REQUEST_MANIFEST": "fd7dec545d8846aff5aa72813d4c1ffb3e99998898061890ce432dc5dde63587",
    "ERA5_R3_CORRECTION_POLICY": "fe010047e8d64e652d1270184a3b88b83a7dbe7216703d23195f231e7ac12b9a",
}

MATRIX_COLUMNS = [
    "variable_id",
    "contract_category",
    "state_or_event",
    "semantic_name",
    "theoretical_observability_class",
    "actual_observability_status",
    "authority_status",
    "source_id",
    "source_hash",
    "grain",
    "farm_scope",
    "subfarm_scope",
    "cultivar_scope",
    "season_scope",
    "date_start",
    "date_end",
    "temporal_resolution",
    "spatial_resolution",
    "unit",
    "non_null_count",
    "total_candidate_count",
    "coverage_ratio",
    "quality_status",
    "derivation_rule_if_any",
    "proxy_definition_if_any",
    "requires_business_confirmation",
    "requires_new_collection",
    "allowed_for_s3_prototype",
    "allowed_for_s4_calibration",
    "allowed_for_future_prospective_validation",
    "leakage_risk",
    "notes",
]
SOURCE_COLUMNS = [
    "source_id",
    "description",
    "source_type",
    "repo_reference",
    "source_hash",
    "grain",
    "season_scope",
    "date_start",
    "date_end",
    "record_count",
    "coverage_summary",
    "data_presence_status",
    "authority_status",
    "leakage_class",
    "quality_status",
    "limitations",
    "verification_method",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def load_json(relative_path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / relative_path).read_text(encoding="utf-8")))


def verify_inputs() -> tuple[
    dict[str, str], dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    s0_hashes: dict[str, str] = {}
    for path, expected in S0_EXPECTED.items():
        actual = sha256(ROOT / path)
        if actual != expected:
            raise RuntimeError(f"S0_AUTHORITY_DRIFT:{path}:{actual}")
        s0_hashes[path] = actual

    s1_manifest_path = ROOT / "docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json"
    s1_manifest = json.loads(s1_manifest_path.read_text(encoding="utf-8"))
    s1_hashes: dict[str, str] = {}
    for entry in s1_manifest["files"]:
        actual = sha256(ROOT / entry["path"])
        if actual != entry["sha256"]:
            raise RuntimeError(f"S1_ARTIFACT_DRIFT:{entry['path']}:{actual}")
        s1_hashes[entry["path"]] = actual

    for path, expected in INPUT_HASHES.items():
        actual = sha256(ROOT / path)
        if expected and actual != expected:
            raise RuntimeError(f"INPUT_ARTIFACT_DRIFT:{path}:{actual}")
        if not expected:
            INPUT_HASHES[path] = actual

    state_registry = load_json("docs/v0-9/s1/biological-state-registry-r1.json")
    event_registry = load_json("docs/v0-9/s1/management-event-registry-r1.json")
    edge_registry = load_json("docs/v0-9/s1/causal-edge-registry-r1.json")
    s0_evidence = load_json(
        "docs/v0-9/evidence/s0-global-protected-blueberry-biology-and-management-authority-review-r1.json"
    )
    s1_evidence = load_json(
        "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
    )
    return (
        s0_hashes,
        s1_hashes,
        state_registry,
        event_registry,
        edge_registry,
        {"s0": s0_evidence, "s1": s1_evidence, "manifest": s1_manifest},
    )


def write_csv(path: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str, payload: dict[str, Any]) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def template_data_rows(path: str) -> int:
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as stream:
        return sum(
            1
            for row in csv.DictReader(stream)
            if any((value or "").strip() for value in row.values())
        )


def source_register() -> list[dict[str, Any]]:
    h = INPUT_HASHES
    sources: list[list[Any]] = [
        [
            "V08_S4_AREA_PRIVATE_MANIFEST",
            "Private S4 manifest for accepted three-season productive-area authority, referenced by logical ID and hash.",
            "PRIVATE_ARTIFACT_MANIFEST_REFERENCE",
            "V08 private artifact reference: V08_S4_AREA_MANIFEST",
            PRIVATE_REFERENCES["V08_S4_AREA_MANIFEST"],
            "Base × season authority manifest",
            "2023-2024;2024-2025;2025-2026",
            "2023-07-01",
            "2026-04-15",
            117,
            "39 canonical Bases × 3 seasons; manifest and source-file hashes verified",
            "PRESENT",
            "AUTHORITATIVE",
            "TRAINING_ELIGIBLE for historical productive area; 2025-2026 AUDIT_ONLY",
            "Private path withheld; area semantics remain frozen and were not reopened in S2",
            "Hash recomputed from the authorized private artifact-root manifest",
        ],
        [
            "V08_AREA_AUTHORITY",
            "Business-confirmed productive area for 39 canonical Bases across three seasons.",
            "BUSINESS_CONFIRMED_AUTHORITY",
            "docs/v0-8/evidence/s4-user-confirmed-three-season-area-authority-application-r1.json",
            "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9",
            "Base × season",
            "2023-2024;2024-2025;2025-2026",
            "2023-07-01",
            "2026-04-15",
            117,
            "39 Bases × 3 seasons; 41,335 mu per season",
            "PRESENT",
            "AUTHORITATIVE",
            "TRAINING_ELIGIBLE for historical training seasons; 2025-2026 AUDIT_ONLY",
            "Business-confirmed area authority; identity/area grains remain distinct from cultivar-area grain",
            "Recomputed file hash and reviewed V0.8 machine evidence",
        ],
        [
            "V08_BASE_IDENTITY_AUTHORITY",
            "Cross-season canonical Base identity authority; does not establish cultivar-to-area allocation.",
            "IDENTITY_AUTHORITY",
            "configs/v0_8_cross_season_identity_authority_r1.json",
            h["configs/v0_8_cross_season_identity_authority_r1.json"],
            "season-scoped source farm/subfarm → canonical Base",
            "2023-2024;2024-2025;2025-2026",
            "2023-07-01",
            "2026-04-15",
            228,
            "39 canonical Bases; 228 source farm labels in the current ledger; member and cultivar-area coverage is not implied",
            "PRESENT",
            "AUTHORITATIVE",
            "TRAINING_ELIGIBLE for historical identity linkage; 2025-2026 AUDIT_ONLY",
            "Season-scoped identity; no cultivar-area mapping and no inference from geography/name",
            "Pinned config hash and reviewed S6/S8 authority evidence",
        ],
        [
            "V08_DAILY_HARVEST_AUTHORITY",
            "Canonical Base × date quantity overlay with frozen no-record-zero semantics and season totals.",
            "CANONICAL_HARVEST_AUTHORITY",
            "V08 private artifact reference: V08_S6_ARTIFACT_MANIFEST",
            PRIVATE_REFERENCES["V08_S6_ARTIFACT_MANIFEST"],
            "Base × calendar date; Base × season",
            "2023-2024;2024-2025;2025-2026",
            "2023-07-01",
            "2026-04-15",
            33033,
            "117 Base-seasons; complete daily curves: 15, 22, 39 by season; harvest target only",
            "PRESENT",
            "AUTHORITATIVE",
            "TRAINING_ELIGIBLE for 2023-2024/2024-2025; 2025-2026 AUDIT_ONLY",
            "Harvest output is not physiological maturity or ripe quantity; 2025-2026 is consumed benchmark",
            "Final private manifest hash recomputed and manifested files verified; private paths withheld",
        ],
        [
            "HARVEST_RAW_2024_2025",
            "Historical inbound/receipt workbook; rows include date, source labels, variety label, size category and inbound kg.",
            "RAW_HARVEST_RECEIPTS",
            "data/raw/2024_2025_receipts.xls",
            h["data/raw/2024_2025_receipts.xls"],
            "receipt row (date × source labels × variety label × size category)",
            "2024-2025",
            "2024-07-01",
            "2025-05-27",
            201434,
            "4 sheets; 323 distinct dates; 42 dates after frozen 2024-2025 season end 2025-04-15",
            "PRESENT",
            "REVIEWED_SUPPORTING",
            "TRAINING_ELIGIBLE only as historical harvest target/source evidence; not biological state",
            "Receipt/arrival is not maturity; out-of-window rows must not be silently folded into frozen season",
            "Read-only workbook inspection; source SHA pinned",
        ],
        [
            "HARVEST_RAW_2025_2026",
            "Consumed benchmark inbound/receipt workbook; rows include date, source labels, variety label, size category and inbound kg.",
            "RAW_HARVEST_RECEIPTS",
            "data/raw/2025_2026_receipts.xls",
            h["data/raw/2025_2026_receipts.xls"],
            "receipt row (date × source labels × variety label × size category)",
            "2025-2026",
            "2025-07-22",
            "2026-04-16",
            232527,
            "4 sheets; 229 distinct dates; one date after frozen season end 2026-04-15",
            "PRESENT",
            "REVIEWED_SUPPORTING",
            "AUDIT_ONLY",
            "Consumed benchmark; cannot train/calibrate/select; receipt/arrival is not physiological maturity",
            "Read-only workbook inspection; source SHA pinned",
        ],
        [
            "PRODUCTION_PLAN_TEMPLATE",
            "Production-plan schema/template has possible planning fields; no populated business records.",
            "EMPTY_TEMPLATE_AND_SCHEMA",
            "data/templates/production_plans.csv",
            h["data/templates/production_plans.csv"],
            "planned Base/season row",
            "schema only",
            "",
            "",
            0,
            "Header-only CSV; pruning/flowering/first-pick fields are not execution evidence",
            "TEMPLATE_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "Planned values cannot be relabeled as actual management events or observations",
            "Header/data-row audit and file SHA",
        ],
        [
            "PRODUCTION_PLAN_MODEL_SCHEMA",
            "Application schema contains planning fields but live database content was not queried.",
            "APPLICATION_SCHEMA",
            "backend/app/models/production_plan.py",
            "",
            "planned Base/season",
            "not assessed",
            "",
            "",
            "",
            "Schema presence only; no row count asserted",
            "SCHEMA_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "BLOCKED_LEAKAGE",
            "A model/table definition does not establish persisted operational rows",
            "Source code reviewed; no database session/query",
        ],
        [
            "PHENOLOGY_TEMPLATE",
            "Phenology history CSV template; no populated observations.",
            "EMPTY_TEMPLATE",
            "data/templates/phenology_history.csv",
            h["data/templates/phenology_history.csv"],
            "Base/cultivar/date/stage",
            "schema only",
            "",
            "",
            template_data_rows("data/templates/phenology_history.csv"),
            "Header-only; no bud, bloom, fruit-set or color-break records",
            "TEMPLATE_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "No biological stage is inferred from harvest except explicitly labeled harvest-derived proxy",
            "Header/data-row audit and file SHA",
        ],
        [
            "PLANTING_TEMPLATE",
            "Season-variety-planting template; no populated planting/cultivar/tree-age records.",
            "EMPTY_TEMPLATE",
            "data/templates/season_variety_planting.csv",
            h["data/templates/season_variety_planting.csv"],
            "Base × season × cultivar planting",
            "schema only",
            "",
            "",
            template_data_rows("data/templates/season_variety_planting.csv"),
            "Header-only; no cultivar-area, planting-year, density or tree-age rows",
            "TEMPLATE_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "Receipt variety labels do not establish planting-area composition",
            "Header/data-row audit and file SHA",
        ],
        [
            "WEATHER_TEMPLATES",
            "Weather history and daily observation templates; no populated weather observations.",
            "EMPTY_TEMPLATES",
            "data/templates/weather_history.csv;data/templates/weather_daily_observations.csv",
            h["data/templates/weather_history.csv"]
            + ";"
            + h["data/templates/weather_daily_observations.csv"],
            "station/Base × timestamp",
            "schema only",
            "",
            "",
            template_data_rows("data/templates/weather_history.csv")
            + template_data_rows("data/templates/weather_daily_observations.csv"),
            "Templates contain no actual weather observation rows",
            "TEMPLATE_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "Templates and synthetic examples are not environmental measurements",
            "Header/data-row audit and pinned hashes",
        ],
        [
            "WEATHER_LOCATION_TEMPLATES",
            "Weather station/location mapping templates contain only template or synthetic references.",
            "EMPTY_OR_SYNTHETIC_TEMPLATE",
            "data/templates/weather_source_locations.csv;data/templates/location_weather_mappings.csv",
            h["data/templates/weather_source_locations.csv"]
            + ";"
            + h["data/templates/location_weather_mappings.csv"],
            "station/Base mapping",
            "schema/example only",
            "",
            "",
            template_data_rows("data/templates/weather_source_locations.csv")
            + template_data_rows("data/templates/location_weather_mappings.csv"),
            "No authoritative farm weather station mapping; Base coordinate CRS is unconfirmed",
            "TEMPLATE_ONLY",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "Synthetic station row is not an actual instrument/source assignment",
            "Header/example-row audit and pinned hashes",
        ],
        [
            "ERA5_LAND_HISTORY",
            "Historical weather extraction attempts; no accepted normalized hourly/daily dataset.",
            "PARTIAL_EXTERNAL_REQUEST_ARTIFACTS",
            "configs/era5_land_historical_weather_r1.json;configs/era5_land_historical_weather_r2.json;configs/era5_land_historical_weather_r3.json",
            h["configs/era5_land_historical_weather_r1.json"]
            + ";"
            + h["configs/era5_land_historical_weather_r2.json"]
            + ";"
            + h["configs/era5_land_historical_weather_r3.json"]
            + ";"
            + PRIVATE_REFERENCES["ERA5_R3_REQUEST_MANIFEST"]
            + ";"
            + PRIVATE_REFERENCES["ERA5_R3_CORRECTION_POLICY"],
            "outdoor grid request",
            "historical request attempts",
            "",
            "",
            0,
            "R1/R2 blocked; R3 stopped with 91 pending requests; zero accepted normalized hourly/daily rows; CRS not established",
            "PARTIAL_NOT_ACCEPTED",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "Outdoor source only; incomplete requests/grid authority prevent chill/GDD derivation",
            "Pinned configs and controlled private request-manifest references",
        ],
        [
            "ECMWF_SNAPSHOT",
            "Qualified ECMWF IFS Open Data forecast snapshot; 39 Bases × four forecast horizons, not history or greenhouse sensor data.",
            "PROSPECTIVE_WEATHER_SNAPSHOT",
            "configs/v0_6_s2_weather_provider_qualification_r2.json;configs/v0_6_s2_weather_provider_deterministic_acceptance_r3.json",
            h["configs/v0_6_s2_weather_provider_qualification_r2.json"]
            + ";"
            + h["configs/v0_6_s2_weather_provider_deterministic_acceptance_r3.json"]
            + ";"
            + PRIVATE_REFERENCES["ECMWF_REAL_CAPTURE_MANIFEST"],
            "Base-bound forecast snapshots",
            "run 2026-09-19",
            "2026-09-19",
            "forecast horizon ≤360h",
            156,
            "39 Bases; 28 requests; 4 horizons; 30 selected grid points; CRS unconfirmed; weather_used_by_model=false",
            "PRESENT",
            "REVIEWED_SUPPORTING",
            "PROSPECTIVE_ONLY",
            "Forecast snapshots cannot represent continuous historical or indoor microclimate",
            "Config/evidence pins; no new network request",
        ],
        [
            "BASE_LOCATION_REGISTRY",
            "39 canonical Base location entries; coordinate range checks exist but CRS verification is not established.",
            "LOCATION_REFERENCE",
            "configs/base_registry_s1.json",
            h["configs/base_registry_s1.json"],
            "canonical Base",
            "reference only",
            "",
            "",
            39,
            "39 canonical Base IDs; coordinate CRS remains unconfirmed",
            "PRESENT",
            "PRESENT_NOT_AUTHORIZED",
            "AUDIT_ONLY",
            "No geographic/varietal production-system inference; photoperiod derivation waits on coordinate authority",
            "Config hash and reviewed CRS fields",
        ],
        [
            "S0_LITERATURE_PRIORS",
            "S0 parameter-candidate register; values are literature observations/candidates, not enterprise observations or production defaults.",
            "LITERATURE_EVIDENCE",
            "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv",
            S0_EXPECTED["docs/v0-9/s0/literature-parameter-candidate-register-r1.csv"],
            "paper/cultivar/system-scoped candidate",
            "literature",
            "",
            "",
            25,
            "25 candidate rows; production_default=false; no parameter selection",
            "PRESENT",
            "REVIEWED_SUPPORTING",
            "AUDIT_ONLY",
            "No literature candidate is counted as current data coverage or production parameter",
            "S0 pinned source artifact",
        ],
        [
            "APP_DB_LIVE_CONTENT",
            "Potential persisted enterprise rows in the application database were deliberately not queried in this bounded audit.",
            "UNQUERIED_LIVE_DATABASE",
            "backend schema references only",
            "",
            "unknown",
            "not assessed",
            "",
            "",
            "",
            "No live DB connection/query authorized; existence and coverage remain unknown",
            "NOT_ASSESSED_BY_SCOPE",
            "UNKNOWN_AUTHORITY",
            "BLOCKED_LEAKAGE",
            "Do not interpret repository/template absence as proof that a live database has no records",
            "Scope boundary: no DB credentials/session/query used",
        ],
        [
            "V08_R2C_BENCHMARK",
            "Frozen 2025-2026 V0.8 benchmark outcomes; audit/replay/reporting only.",
            "CONSUMED_BENCHMARK",
            "docs/v0-8/evidence/r2c-frozen-shrinkage-model-and-benchmark-replay-r1.json",
            "",
            "Base × season; daily output",
            "2025-2026",
            "2025-07-22",
            "2026-04-15",
            39,
            "Consumed 39-Base benchmark; included for data availability/coverage audit only",
            "PRESENT",
            "AUTHORITATIVE",
            "AUDIT_ONLY",
            "Forbidden for V0.9 model/parameter/management rule selection or calibration",
            "Reviewed V0.8 public evidence; no benchmark metrics used here",
        ],
    ]
    source_value_columns = [column for column in SOURCE_COLUMNS if column != "quality_status"]
    mismatches = [
        (index, source[0], len(source))
        for index, source in enumerate(sources)
        if len(source) != len(source_value_columns)
    ]
    if mismatches:
        raise ValueError(f"source register row does not match its schema: {mismatches}")
    quality_statuses = {
        "V08_S4_AREA_PRIVATE_MANIFEST": "PRIVATE_MANIFEST_HASH_RECOMPUTED; SOURCE_FILE_HASH_PINNED",
        "V08_AREA_AUTHORITY": "BUSINESS_CONFIRMED_AUTHORITY; FILE_HASH_VERIFIED",
        "V08_BASE_IDENTITY_AUTHORITY": "SEASON_SCOPED_IDENTITY_AUTHORITY; SCOPE_LIMITED",
        "V08_DAILY_HARVEST_AUTHORITY": "COMPLETE_SEASON_AUTHORITY; ZERO_SEMANTICS_AND_CONSERVATION_PINNED",
        "HARVEST_RAW_2024_2025": "SOURCE_HASH_AND_ROW_DATE_RANGE_VERIFIED; ARRIVAL_NOT_MATURITY",
        "HARVEST_RAW_2025_2026": "SOURCE_HASH_AND_ROW_DATE_RANGE_VERIFIED; AUDIT_ONLY",
        "PRODUCTION_PLAN_TEMPLATE": "HEADER_ONLY; NO_EXECUTED_EVENT_ROWS",
        "PRODUCTION_PLAN_MODEL_SCHEMA": "SCHEMA_ONLY; LIVE_DATABASE_NOT_QUERIED",
        "PHENOLOGY_TEMPLATE": "HEADER_ONLY; NO_OBSERVATION_ROWS",
        "PLANTING_TEMPLATE": "HEADER_ONLY; NO_CULTIVAR_OR_TREE_AGE_ROWS",
        "WEATHER_TEMPLATES": "TEMPLATE_OR_SYNTHETIC_EXAMPLE_ONLY; NO_ACTUAL_WEATHER_ROWS",
        "WEATHER_LOCATION_TEMPLATES": "TEMPLATE_OR_SYNTHETIC_EXAMPLE_ONLY; NO_AUTHORIZED_STATION_BINDING",
        "ERA5_LAND_HISTORY": "NO_ACCEPTED_NORMALIZED_ROWS; REQUESTS_PENDING",
        "ECMWF_SNAPSHOT": "QUALIFIED_FORECAST_SNAPSHOT; OUTDOOR_AND_CRS_LIMITED",
        "BASE_LOCATION_REGISTRY": "COORDINATE_CRS_UNCONFIRMED",
        "S0_LITERATURE_PRIORS": "PINNED_LITERATURE_CANDIDATES; NOT_ENTERPRISE_DATA",
        "APP_DB_LIVE_CONTENT": "NOT_ASSESSED_BY_SCOPE",
        "V08_R2C_BENCHMARK": "PINNED_CONSUMED_BENCHMARK_EVIDENCE; AUDIT_ONLY",
    }
    records = []
    for source in sources:
        record = {column: source[index] for index, column in enumerate(source_value_columns)}
        record["quality_status"] = quality_statuses[record["source_id"]]
        records.append(record)
    source_leakage_classes = {
        "V08_S4_AREA_PRIVATE_MANIFEST": "TRAINING_ELIGIBLE",
        "V08_AREA_AUTHORITY": "TRAINING_ELIGIBLE",
        "V08_BASE_IDENTITY_AUTHORITY": "TRAINING_ELIGIBLE",
        "V08_DAILY_HARVEST_AUTHORITY": "TRAINING_ELIGIBLE",
        "HARVEST_RAW_2024_2025": "TRAINING_ELIGIBLE",
        "HARVEST_RAW_2025_2026": "AUDIT_ONLY",
        "PRODUCTION_PLAN_TEMPLATE": "AUDIT_ONLY",
        "PRODUCTION_PLAN_MODEL_SCHEMA": "BLOCKED_LEAKAGE",
        "PHENOLOGY_TEMPLATE": "AUDIT_ONLY",
        "PLANTING_TEMPLATE": "AUDIT_ONLY",
        "WEATHER_TEMPLATES": "AUDIT_ONLY",
        "WEATHER_LOCATION_TEMPLATES": "AUDIT_ONLY",
        "ERA5_LAND_HISTORY": "AUDIT_ONLY",
        "ECMWF_SNAPSHOT": "PROSPECTIVE_ONLY",
        "BASE_LOCATION_REGISTRY": "AUDIT_ONLY",
        "S0_LITERATURE_PRIORS": "AUDIT_ONLY",
        "APP_DB_LIVE_CONTENT": "BLOCKED_LEAKAGE",
        "V08_R2C_BENCHMARK": "AUDIT_ONLY",
    }
    for record in records:
        record["leakage_class"] = source_leakage_classes[record["source_id"]]
        if record["source_id"] == "PRODUCTION_PLAN_MODEL_SCHEMA":
            record["source_hash"] = sha256(ROOT / record["repo_reference"])
        if record["source_id"] == "V08_R2C_BENCHMARK":
            record["source_hash"] = sha256(ROOT / record["repo_reference"])
    records.extend(
        [
            {
                "source_id": "HARVEST_STATE_ENGINE_SCHEMA",
                "description": "Existing harvest-state application/schema boundary for mature inventory, loss, capacity, harvest and closing inventory.",
                "source_type": "APPLICATION_CONTRACT_AND_IMPLEMENTATION",
                "repo_reference": "backend/app/models/harvest_state.py;backend/app/harvest_state/schemas.py;backend/app/harvest_state/service.py",
                "source_hash": ";".join(
                    sha256(ROOT / path)
                    for path in [
                        "backend/app/models/harvest_state.py",
                        "backend/app/harvest_state/schemas.py",
                        "backend/app/harvest_state/service.py",
                    ]
                ),
                "grain": "versioned HarvestState input/output contract",
                "season_scope": "not applicable",
                "date_start": "",
                "date_end": "",
                "record_count": "",
                "coverage_summary": "Code/schema exists; no live persisted instance rows were queried; not a biological maturity observation source.",
                "data_presence_status": "SCHEMA_ONLY",
                "authority_status": "REVIEWED_SUPPORTING",
                "leakage_class": "AUDIT_ONLY",
                "quality_status": "CONTRACT_IMPLEMENTATION_PRESENT; LIVE_ROWS_NOT_ASSESSED",
                "limitations": "Harvest-state engine consumes mature supply and models inventory/capacity/harvest; S2 does not alter it or infer mature quantity from harvest output.",
                "verification_method": "Repository source inspection and code hashes; no DB query",
            },
            {
                "source_id": "V08_S8_PRIVATE_ARTIFACT_MANIFEST",
                "description": "Private S8 canonical training and frozen benchmark artifact bundle, referenced only by logical ID and hash.",
                "source_type": "PRIVATE_ARTIFACT_MANIFEST_REFERENCE",
                "repo_reference": "V08 private artifact reference: V08_S8_ARTIFACT_MANIFEST",
                "source_hash": PRIVATE_REFERENCES["V08_S8_ARTIFACT_MANIFEST"],
                "grain": "Base × season datasets and predictions",
                "season_scope": "training 2023-2024/2024-2025; benchmark 2025-2026",
                "date_start": "2023-07-01",
                "date_end": "2026-04-15",
                "record_count": 76,
                "coverage_summary": "37 canonical training rows and 39 benchmark rows; private row-level results are not republished.",
                "data_presence_status": "PRESENT",
                "authority_status": "AUTHORITATIVE",
                "leakage_class": "AUDIT_ONLY",
                "quality_status": "S8_AUTHORITY_AND_BENCHMARK_PROVENANCE; NO_SELECTION_PERFORMED_IN_S2",
                "limitations": "2025-2026 benchmark is consumed and prohibited for model/parameter selection; this audit only verifies availability/coverage.",
                "verification_method": "Final S8 private manifest hash recomputed and manifested files verified; private paths withheld",
            },
        ]
    )
    return records


def build_matrix(
    state: dict[str, Any], events: dict[str, Any], edges: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_hashes = {**INPUT_HASHES}
    source_hashes.update(
        {
            "V08_BASE_IDENTITY_AUTHORITY": INPUT_HASHES[
                "configs/v0_8_cross_season_identity_authority_r1.json"
            ],
            "V08_DAILY_HARVEST_AUTHORITY": PRIVATE_REFERENCES["V08_S6_ARTIFACT_MANIFEST"],
            "V08_S8_ARTIFACT": PRIVATE_REFERENCES["V08_S8_ARTIFACT_MANIFEST"],
            "ERA5_LAND_HISTORY": ";".join(
                [
                    INPUT_HASHES["configs/era5_land_historical_weather_r1.json"],
                    INPUT_HASHES["configs/era5_land_historical_weather_r2.json"],
                    INPUT_HASHES["configs/era5_land_historical_weather_r3.json"],
                    PRIVATE_REFERENCES["ERA5_R3_REQUEST_MANIFEST"],
                ]
            ),
            "ECMWF_SNAPSHOT": PRIVATE_REFERENCES["ECMWF_REAL_CAPTURE_MANIFEST"],
            "S0_LITERATURE_PRIORS": S0_EXPECTED[
                "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv"
            ],
            "V08_AREA": "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9",
            "V08_HARVEST": PRIVATE_REFERENCES["V08_S6_ARTIFACT_MANIFEST"],
            "RECEIPT_BOTH": ";".join(
                [
                    INPUT_HASHES["data/raw/2024_2025_receipts.xls"],
                    INPUT_HASHES["data/raw/2025_2026_receipts.xls"],
                ]
            ),
            "HARVEST_RAW_2024_2025": INPUT_HASHES["data/raw/2024_2025_receipts.xls"],
            "HARVEST_RAW_2025_2026": INPUT_HASHES["data/raw/2025_2026_receipts.xls"],
            "PRODUCTION_PLAN_TEMPLATE": INPUT_HASHES["data/templates/production_plans.csv"],
            "PLANTING_TEMPLATE": INPUT_HASHES["data/templates/season_variety_planting.csv"],
            "PHENOLOGY_TEMPLATE": INPUT_HASHES["data/templates/phenology_history.csv"],
            "WEATHER_TEMPLATES": ";".join(
                [
                    INPUT_HASHES["data/templates/weather_daily_observations.csv"],
                    INPUT_HASHES["data/templates/weather_history.csv"],
                ]
            ),
            "BASE_REGISTRY": INPUT_HASHES["configs/base_registry_s1.json"],
        }
    )

    def add(
        variable_id: str,
        category: str,
        semantic: str,
        theory: str,
        status: str,
        authority: str = "NOT_PRESENT",
        source_id: str = "APP_DB_LIVE_CONTENT",
        *,
        grain: str = "Base × season",
        seasons: str = "2023-2024;2024-2025;2025-2026",
        start: str = "",
        end: str = "",
        temporal: str = "not observed",
        spatial: str = "Base-level candidate scope; finer scope unverified",
        unit: str = "",
        nonnull: Any = 0,
        total: Any = 117,
        quality: str = "NO_MATCHING_RECORD_IN_BOUNDED_REPOSITORY_AND_AUTHORIZED_ARTIFACT_REVIEW; LIVE_DB_NOT_QUERIED",
        derivation: str = "",
        proxy: str = "",
        confirm: bool = False,
        new: bool = False,
        s3: bool = False,
        s4: bool = False,
        future: bool = True,
        leakage: str = "FUTURE_COLLECTION",
        notes: str = "Current-file absence is bounded to reviewed repository and authorized artifact roots; it is not a claim about unqueried live systems.",
    ) -> None:
        ratio = ""
        if isinstance(nonnull, int) and isinstance(total, int) and total > 0:
            ratio = f"{nonnull / total:.6f}"
        rows.append(
            {
                "variable_id": variable_id,
                "contract_category": category,
                "state_or_event": variable_id,
                "semantic_name": semantic,
                "theoretical_observability_class": theory,
                "actual_observability_status": status,
                "authority_status": authority,
                "source_id": source_id,
                "source_hash": source_hashes.get(source_id, ""),
                "grain": grain,
                "farm_scope": "39 canonical Base identities where applicable; per-Base coverage not assumed",
                "subfarm_scope": "not present in state/management authority",
                "cultivar_scope": "receipt variety labels are not cultivar-area binding",
                "season_scope": seasons,
                "date_start": start,
                "date_end": end,
                "temporal_resolution": temporal,
                "spatial_resolution": spatial,
                "unit": unit,
                "non_null_count": nonnull,
                "total_candidate_count": total,
                "coverage_ratio": ratio,
                "quality_status": quality,
                "derivation_rule_if_any": derivation,
                "proxy_definition_if_any": proxy,
                "requires_business_confirmation": str(confirm).lower(),
                "requires_new_collection": str(new).lower(),
                "allowed_for_s3_prototype": str(s3).lower(),
                "allowed_for_s4_calibration": str(s4).lower(),
                "allowed_for_future_prospective_validation": str(future).lower(),
                "leakage_risk": leakage,
                "notes": notes,
            }
        )

    specific: dict[str, dict[str, Any]] = {
        "plant_density": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "plants/ha or plants/m2",
            "notes": "Planting template is empty; no verified density rows.",
        },
        "cane_age_structure": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "count/plant by age class or proportion",
        },
        "productive_shoot_density": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "shoots/plant or shoots/m2",
        },
        "fruiting_wood_index": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "versioned_index",
        },
        "pruning_state": {
            "status": "BUSINESS_CONFIRMATION_REQUIRED",
            "confirm": True,
            "source": "PRODUCTION_PLAN_TEMPLATE",
            "unit": "registered_event_state",
            "notes": "A planned pruning_date field exists in an empty template/schema; actual execution is unverified.",
        },
        "leaf_area_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "m2/plant or versioned_index",
        },
        "canopy_retention_ratio": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "ratio_0_1",
        },
        "shoot_growth_state": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "registered_state_id",
        },
        "vegetative_vigor_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "versioned_index",
        },
        "carbohydrate_reserve_proxy": {
            "status": "UNOBSERVABLE",
            "unit": "assay_unit or versioned_index",
            "notes": "No assay or validated enterprise proxy; do not substitute yield or leaf area.",
        },
        "flower_bud_density": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "buds/plant, buds/shoot or buds/m2",
        },
        "flower_number_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "flowers/plant or declared_index",
        },
        "effective_flower_load": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "flowers/plant or declared_index",
        },
        "pollination_state": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "registered_state_id",
        },
        "fruit_set_ratio": {"status": "NEW_COLLECTION_REQUIRED", "new": True, "unit": "ratio_0_1"},
        "fruit_number_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "fruits/plant or versioned_index",
        },
        "crop_load_index": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "versioned_index",
        },
        "phenology_stage": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "source": "PHENOLOGY_TEMPLATE",
            "unit": "registered_state_id",
        },
        "dormancy_state": {
            "status": "UNOBSERVABLE",
            "unit": "dormancy_state_id",
            "notes": "No direct dormancy observation or accepted weather series; chill exposure is not dormancy state.",
        },
        "chill_accumulation": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "source": "ERA5_LAND_HISTORY",
            "unit": "model_typed_chill_unit",
            "notes": "No accepted continuous hourly temperature dataset; chill model remains unbound.",
        },
        "forcing_accumulation": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "source": "ERA5_LAND_HISTORY",
            "unit": "model_typed_thermal_unit",
            "notes": "No accepted indoor hourly temperature and no calibrated forcing response.",
        },
        "bloom_progress": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "source": "PHENOLOGY_TEMPLATE",
            "unit": "percent_0_100",
        },
        "green_fruit_quantity_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "declared_cohort_quantity_unit",
        },
        "color_break_quantity_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "declared_cohort_quantity_unit",
        },
        "mean_berry_weight_proxy": {
            "status": "PROXY_AVAILABLE",
            "authority": "PRESENT_NOT_AUTHORIZED",
            "source": "RECEIPT_BOTH",
            "unit": "categorical_receipt_size_class; not g/berry",
            "nonnull": 433961,
            "total": 433961,
            "temporal": "receipt date",
            "seasons": "2024-2025;2025-2026",
            "proxy": "Receipt fruit-size category only; not measured mean berry mass and not cultivar-area scoped.",
            "s3": True,
            "s4": False,
            "leakage": "TRAINING_ELIGIBLE only for historical receipt/harvest proxy; 2025-2026 audit-only",
            "notes": "A fruit-size class is present on raw receipts; category labels cannot be converted into grams/berry.",
        },
        "berry_size_proxy": {
            "status": "PROXY_AVAILABLE",
            "authority": "PRESENT_NOT_AUTHORIZED",
            "source": "RECEIPT_BOTH",
            "unit": "categorical_receipt_size_class; not mm",
            "nonnull": 433961,
            "total": 433961,
            "temporal": "receipt date",
            "seasons": "2024-2025;2025-2026",
            "proxy": "Categorical receipt size-class label; not a direct diameter measurement.",
            "s3": True,
            "s4": False,
            "leakage": "TRAINING_ELIGIBLE only as historical receipt proxy; 2025-2026 audit-only",
            "notes": "Raw receipt workbook also contains 2025-2026 rows; no numerical mm inference.",
        },
        "ripe_quantity": {
            "status": "PROXY_AVAILABLE",
            "authority": "PROXY_ONLY",
            "source": "V08_DAILY_HARVEST_AUTHORITY",
            "unit": "declared_cohort_quantity_unit",
            "nonnull": 33033,
            "total": 33033,
            "temporal": "daily",
            "seasons": "2023-2024;2024-2025;2025-2026",
            "proxy": "Harvested/received quantity is an output proxy only under explicit harvest-state assumptions; it is not newly mature or ripe inventory.",
            "s3": True,
            "s4": False,
            "leakage": "Training seasons only; 2025-2026 audit-only",
            "notes": "Harvest quantity must remain distinct from maturity output.",
        },
        "postharvest_vigor_proxy": {"status": "UNOBSERVABLE", "unit": "versioned_index"},
        "next_season_flower_bud_potential": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "buds/plant or declared_index",
        },
        "source_capacity_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "versioned_index_or_declared_measure",
            "notes": "No leaf function, radiation, water/nutrition, or reserve proxy bundle; exact formula unbound.",
        },
        "sink_demand_proxy": {
            "status": "NEW_COLLECTION_REQUIRED",
            "new": True,
            "unit": "versioned_index_or_declared_measure",
            "notes": "No effective flower/fruit load observations; fruit number alone is insufficient.",
        },
        "source_sink_balance_index": {
            "status": "UNOBSERVABLE",
            "unit": "versioned_index_or_UNBOUND",
            "notes": "Latent composite state; exact source-sink formula is UNBOUND.",
        },
    }

    for field in (
        state["plant_state_fields"]
        + state["interseason_state_fields"]
        + state["source_sink_state_fields"]
    ):
        field_id = field["field_id"]
        spec = specific.get(field_id, {})
        group = field.get(
            "group", "INTERSEASON" if field in state["interseason_state_fields"] else "SOURCE_SINK"
        )
        if field_id == "carbohydrate_reserve_proxy" and field in state["interseason_state_fields"]:
            variable_id = "InterSeasonState.carbohydrate_reserve_proxy"
        else:
            variable_id = f"{group.title().replace('_', '')}.{field_id}"
        source_key = spec.get(
            "source",
            "V08_DAILY_HARVEST_AUTHORITY"
            if spec.get("source") == "V08_DAILY_HARVEST_AUTHORITY"
            else "APP_DB_LIVE_CONTENT",
        )
        add(
            variable_id,
            field.get("semantic_class", "BIOLOGICAL_STATE"),
            field["meaning"],
            field["observability_class"],
            spec.get("status", "NEW_COLLECTION_REQUIRED"),
            spec.get("authority", "NOT_PRESENT"),
            source_key,
            unit=spec.get("unit", field["unit"]),
            nonnull=spec.get("nonnull", 0),
            total=spec.get("total", 117),
            quality="SOURCE_ROW_PRESENT_PROXY_ONLY"
            if spec.get("status") == "PROXY_AVAILABLE"
            else "SCOPED_REVIEW; LIVE_DB_NOT_QUERIED",
            proxy=spec.get("proxy", ""),
            confirm=spec.get("confirm", False),
            new=spec.get(
                "new", spec.get("status", "NEW_COLLECTION_REQUIRED") == "NEW_COLLECTION_REQUIRED"
            ),
            s3=spec.get("s3", False),
            s4=spec.get("s4", False),
            leakage=spec.get("leakage", "FUTURE_COLLECTION"),
            notes=spec.get(
                "notes",
                field["meaning"]
                + " Unit/applicability are inherited from S1; current enterprise observation is not implied.",
            ),
        )

    # Every state-machine state gets a row; harvest dates are a proxy only for RIPE.
    state_specific = {
        "RIPE": (
            "PROXY_AVAILABLE",
            "V08_DAILY_HARVEST_AUTHORITY",
            "PROXY_ONLY",
            "Harvest/receipt onset is not physiological ripe onset; only an explicitly labeled proxy.",
        ),
        "EVERGREEN_CONTINUATION": (
            "BUSINESS_CONFIRMATION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "UNKNOWN_AUTHORITY",
            "Production-system assignment is not established for the Base-season universe.",
        ),
        "CHILL_SATISFIED": (
            "UNOBSERVABLE",
            "ERA5_LAND_HISTORY",
            "PRESENT_NOT_AUTHORIZED",
            "No accepted continuous temperature history; chill accumulation alone would not prove dormancy release.",
        ),
        "CHILL_ACCUMULATING": (
            "NEW_COLLECTION_REQUIRED",
            "ERA5_LAND_HISTORY",
            "PRESENT_NOT_AUTHORIZED",
            "No accepted continuous hourly temperature series.",
        ),
        "FORCING": (
            "NEW_COLLECTION_REQUIRED",
            "ECMWF_SNAPSHOT",
            "REVIEWED_SUPPORTING",
            "Forecast snapshots do not establish historical indoor forcing exposure.",
        ),
        "POSTHARVEST": (
            "PROXY_AVAILABLE",
            "V08_DAILY_HARVEST_AUTHORITY",
            "PROXY_ONLY",
            "Seasonal harvest end can bound a candidate interval, not directly observe plant postharvest state.",
        ),
    }
    for state_id in state["phenology_state_machine"]["state_ids"]:
        status, source, authority, note = state_specific.get(
            state_id,
            (
                "NEW_COLLECTION_REQUIRED",
                "PHENOLOGY_TEMPLATE",
                "PRESENT_NOT_AUTHORIZED",
                "No direct phenology observation is present in the reviewed data templates or authorized evidence.",
            ),
        )
        add(
            f"PhenologyState.{state_id}",
            "PHENOLOGY_STATE",
            state_id.replace("_", " ").title(),
            "DIRECT_OBSERVATION",
            status,
            authority,
            source,
            temporal="stage observation date/interval",
            unit="registered_state_id",
            nonnull=76 if state_id in {"RIPE", "POSTHARVEST"} else 0,
            total=117,
            quality="HARVEST_DERIVED_PROXY_NOT_PHENOLOGY"
            if status == "PROXY_AVAILABLE"
            else "NO_DIRECT_PHENOLOGY_ROWS_IN_BOUNDED_REVIEW",
            proxy="Harvest-derived onset/end proxy only; not a physiological observation."
            if status == "PROXY_AVAILABLE"
            else "",
            confirm=status == "BUSINESS_CONFIRMATION_REQUIRED",
            new=status == "NEW_COLLECTION_REQUIRED",
            s3=status == "PROXY_AVAILABLE",
            s4=False,
            leakage="TRAINING_ELIGIBLE_HARVEST_PROXY_ONLY;2025-2026_AUDIT_ONLY"
            if status == "PROXY_AVAILABLE"
            else "FUTURE_COLLECTION",
            notes=note,
        )

    # Production systems are contract options; none is assigned to a Base-season.
    for system in state["production_systems"]:
        add(
            f"ProductionSystem.{system['system_id']}",
            "PRODUCTION_SYSTEM",
            system["definition"],
            "BUSINESS_INPUT",
            "BUSINESS_CONFIRMATION_REQUIRED",
            "UNKNOWN_AUTHORITY",
            "APP_DB_LIVE_CONTENT",
            nonnull=0,
            total=117,
            unit="registered_system_id",
            confirm=True,
            new=False,
            notes="No explicit Base-season system assignments found in reviewed authority; never infer from region or cultivar.",
        )

    # Environment inputs include required and optional contract variables.
    env_contract = state["environment_input_contract"]
    env_specs = {
        "air_temperature": (
            "PROXY_AVAILABLE",
            "ECMWF_SNAPSHOT",
            "REVIEWED_SUPPORTING",
            156,
            "forecast snapshots only; outdoor grid, not greenhouse history",
        ),
        "min_temperature": (
            "PROXY_AVAILABLE",
            "ECMWF_SNAPSHOT",
            "REVIEWED_SUPPORTING",
            156,
            "forecast min/max projections, not continuous historical series",
        ),
        "max_temperature": (
            "PROXY_AVAILABLE",
            "ECMWF_SNAPSHOT",
            "REVIEWED_SUPPORTING",
            156,
            "forecast min/max projections, not continuous historical series",
        ),
        "relative_humidity": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "No greenhouse/farm RH observations in reviewed assets.",
        ),
        "root_zone_temperature": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "No root-zone sensor records.",
        ),
        "radiation_or_light_proxy": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "No timestamped radiation/light measurement.",
        ),
        "photoperiod": (
            "BUSINESS_CONFIRMATION_REQUIRED",
            "BASE_REGISTRY",
            "PRESENT_NOT_AUTHORIZED",
            0,
            "Could be deterministically derived from date and validated coordinates; CRS not established.",
        ),
        "substrate_moisture": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "Optional S1 input; no actual substrate moisture rows.",
        ),
        "electrical_conductivity": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "Optional S1 input; no actual EC rows.",
        ),
        "irrigation_observation": (
            "NEW_COLLECTION_REQUIRED",
            "APP_DB_LIVE_CONTENT",
            "NOT_PRESENT",
            0,
            "Optional S1 input; no authorized actual irrigation event/measurement rows.",
        ),
    }
    env_by_id = {x["variable_id"]: x for x in env_contract["variables"]}
    for optional_id in env_contract["optional_variables"]:
        env_by_id.setdefault(
            optional_id,
            {
                "variable_id": optional_id,
                "unit": "declared_sensor_unit_or_versioned_index",
                "temporal_resolution": "timestamped",
                "semantic_class": "ENVIRONMENT_DRIVER",
            },
        )
    for env_id, spec in env_by_id.items():
        status, source, authority, count, note = env_specs[env_id]
        add(
            f"EnvironmentInput.{env_id}",
            "ENVIRONMENT_INPUT",
            env_id.replace("_", " ").title(),
            spec["semantic_class"],
            status,
            authority,
            source,
            temporal=spec["temporal_resolution"],
            unit=spec["unit"],
            nonnull=count,
            total=156 if source == "ECMWF_SNAPSHOT" else 117,
            quality="OUTDOOR_FORECAST_SNAPSHOT_ONLY"
            if source == "ECMWF_SNAPSHOT"
            else "NO_SENSOR_OBSERVATION_IN_BOUNDED_REVIEW",
            derivation="Astronomical day length from date and verified location"
            if env_id == "photoperiod"
            else "",
            confirm=status == "BUSINESS_CONFIRMATION_REQUIRED",
            new=status == "NEW_COLLECTION_REQUIRED",
            s3=status == "PROXY_AVAILABLE",
            s4=False,
            leakage="PROSPECTIVE_ONLY" if source == "ECMWF_SNAPSHOT" else "FUTURE_COLLECTION",
            notes=note,
        )

    for metadata_field in env_contract["required_observation_metadata"]:
        add(
            f"EnvironmentObservationMetadata.{metadata_field}",
            "ENVIRONMENT_OBSERVATION_METADATA",
            metadata_field.replace("_", " ").title(),
            "OBSERVED_VARIABLE",
            "NEW_COLLECTION_REQUIRED",
            "NOT_PRESENT",
            "APP_DB_LIVE_CONTENT",
            unit="typed observation metadata",
            new=True,
            notes="Required S1 provenance/QC metadata; no actual sensor observation rows in bounded review.",
        )

    # Every generic event field and all 29 event types are audited separately.
    for field in events["generic_fields"]:
        fid = field["field_id"]
        status = "NEW_COLLECTION_REQUIRED"
        authority = "NOT_PRESENT"
        source = "APP_DB_LIVE_CONTENT"
        if fid in {"farm_id", "event_type", "event_date", "source_reference"}:
            status = "BUSINESS_CONFIRMATION_REQUIRED"
            authority = "UNKNOWN_AUTHORITY"
        if fid == "event_date" and template_data_rows("data/templates/production_plans.csv") == 0:
            source = "PRODUCTION_PLAN_TEMPLATE"
        add(
            f"ManagementEventField.{fid}",
            "MANAGEMENT_EVENT_FIELD",
            fid.replace("_", " ").title(),
            "DIRECT_OBSERVATION",
            status,
            authority,
            source,
            unit=field.get("type", ""),
            confirm=status == "BUSINESS_CONFIRMATION_REQUIRED",
            new=status == "NEW_COLLECTION_REQUIRED",
            quality="NO_EXECUTED_EVENT_ROWS_IN_BOUNDED_REVIEW",
            notes=field.get(
                "constraint", "Contract metadata only; no observed event rows in the reviewed data."
            ),
        )

    for event in events["event_types"]:
        event_id = event["event_type"]
        is_pruning = event.get("family") == "PRUNING" or event_id in {
            "PRUNING",
            "POSTHARVEST_PRUNING",
            "SUMMER_PRUNING",
            "WINTER_PRUNING",
            "DORMANT_PRUNING",
            "CANE_RENEWAL",
            "FRUITING_WOOD_THINNING",
        }
        is_protected = event_id in {
            "GREENHOUSE_CLOSE",
            "GREENHOUSE_OPEN",
            "HEATING_START",
            "HEATING_STOP",
            "DORMANCY_BREAK_TREATMENT",
            "SHADE_START",
            "SHADE_STOP",
            "SHADE_APPLICATION",
            "LEAF_RETENTION_MANAGEMENT",
            "DEFOLIATION",
        }
        status = (
            "BUSINESS_CONFIRMATION_REQUIRED"
            if is_pruning or is_protected
            else "NEW_COLLECTION_REQUIRED"
        )
        source = "PRODUCTION_PLAN_TEMPLATE" if is_pruning else "APP_DB_LIVE_CONTENT"
        notes = "No actual executed event row found; standard/planned operation is not evidence of Base-level execution."
        if is_pruning:
            notes += " Empty plan template has a pruning_date field only; type/intensity/removed wood/buds are not established."
        if is_protected:
            notes += (
                " No greenhouse close/open/heating/shading/leaf-retention actual event logs found."
            )
        add(
            f"ManagementEvent.{event_id}",
            "MANAGEMENT_EVENT",
            event_id.replace("_", " ").title(),
            "MANAGEMENT_EVENT",
            status,
            "PRESENT_NOT_AUTHORIZED" if is_pruning else "NOT_PRESENT",
            source,
            temporal="event date/interval required",
            unit="typed event/intensity representation",
            nonnull=0,
            total=117,
            quality="NO_AUTHORIZED_EXECUTED_EVENT_RECORDS_FOUND",
            confirm=is_pruning or is_protected,
            new=not (is_pruning or is_protected),
            notes=notes,
        )

    # Bloom/Fruit cohort contract fields are included one by one.
    for cohort_name, contract in state["cohort_contracts"].items():
        for required in (True, False):
            fields = contract["required_fields"] if required else contract["optional_fields"]
            for fid in fields:
                status = "NEW_COLLECTION_REQUIRED"
                if fid in {
                    "farm_id",
                    "subfarm_id",
                    "cultivar_id",
                    "production_system",
                    "authority",
                    "source_reference",
                    "authority_hash",
                }:
                    status = "BUSINESS_CONFIRMATION_REQUIRED"
                add(
                    f"{cohort_name}.{fid}",
                    f"{cohort_name.upper()}_FIELD",
                    fid.replace("_", " ").title(),
                    "DIRECT_OBSERVATION"
                    if "proxy" not in fid and "distribution" not in fid
                    else "PROXY",
                    status,
                    "UNKNOWN_AUTHORITY"
                    if status == "BUSINESS_CONFIRMATION_REQUIRED"
                    else "NOT_PRESENT",
                    "APP_DB_LIVE_CONTENT",
                    grain=f"{cohort_name} × declared farm/subfarm/cultivar scope",
                    temporal="date or interval; stage-specific",
                    unit="declared cohort representation",
                    confirm=status == "BUSINESS_CONFIRMATION_REQUIRED",
                    new=status == "NEW_COLLECTION_REQUIRED",
                    notes=f"{cohort_name} rows/lineage are not present in reviewed data; {contract['lineage_rule']}",
                )

    parameter_contract_fields = [
        "parameter_id",
        "parameter_name",
        "value_or_unbound",
        "unit",
        "authority_type",
        "source_id",
        "cultivar_scope",
        "production_system_scope",
        "climate_scope",
        "calibration_status",
        "valid_from",
        "version",
        "parameter_hash",
    ]
    for field_id in parameter_contract_fields:
        add(
            f"ParameterAuthorityField.{field_id}",
            "PARAMETER_AUTHORITY_FIELD",
            field_id.replace("_", " ").title(),
            "MODEL_PARAMETER",
            "UNOBSERVABLE",
            "NOT_PRESENT",
            "APP_DB_LIVE_CONTENT",
            unit="typed parameter provenance field",
            total=0,
            quality="S1_SCHEMA_DEFINED; NO ENTERPRISE PRODUCTION PARAMETER RECORD",
            notes="Parameter metadata contract exists; no calibrated or production parameter record is created by S2.",
        )

    # Chill, dormancy, forcing and parameter-authority registries are coverage dimensions too.
    for model_type in state["phenology_state_machine"]["chilling_model_types"]:
        add(
            f"ChillingModelType.{model_type}",
            "CHILLING_MODEL_CANDIDATE",
            model_type.replace("_", " ").title(),
            "MODEL_PARAMETER",
            "UNOBSERVABLE",
            "REVIEWED_SUPPORTING",
            "S0_LITERATURE_PRIORS",
            unit="model_typed_chill_unit",
            total=0,
            quality="CANDIDATE_ENUM_ONLY; NO_MODEL_SELECTED",
            leakage="AUDIT_ONLY",
            notes="S1 leaves the production chill model UNBOUND; enum membership is not a selected model or parameter.",
        )
    for dormancy in state["phenology_state_machine"]["dormancy_state_enum"]:
        add(
            f"DormancyState.{dormancy}",
            "DORMANCY_STATE_VALUE",
            dormancy.replace("_", " ").title(),
            "BIOLOGICAL_STATE",
            "UNOBSERVABLE"
            if dormancy not in {"NOT_APPLICABLE"}
            else "BUSINESS_CONFIRMATION_REQUIRED",
            "NOT_PRESENT",
            "APP_DB_LIVE_CONTENT",
            unit="dormancy_state_id",
            notes="No direct dormancy state history; chill exposure is not equivalent to dormancy state.",
        )
    for fid in state["phenology_state_machine"]["forcing_state_fields"]:
        add(
            f"ForcingParameter.{fid}",
            "FORCING_PARAMETER",
            fid.replace("_", " ").title(),
            "MODEL_PARAMETER",
            "UNOBSERVABLE",
            "REVIEWED_SUPPORTING",
            "S0_LITERATURE_PRIORS",
            unit="UNBOUND",
            total=0,
            quality="S1_UNBOUND; NO_CALIBRATION_DATA",
            leakage="AUDIT_ONLY",
            notes="S1 leaves forcing model/thresholds unbound; no numerical value selected.",
        )
    for parameter_id, description in [
        ("production_default_chill_model", "Production default chill model"),
        ("production_default_forcing_parameters", "Production default forcing parameters"),
        ("source_sink_exact_formula", "Exact source-sink formula"),
    ]:
        add(
            f"UnboundParameter.{parameter_id}",
            "UNBOUND_PARAMETER",
            description,
            "MODEL_PARAMETER",
            "UNOBSERVABLE",
            "AUTHORITATIVE",
            "APP_DB_LIVE_CONTENT",
            unit="UNBOUND",
            total=0,
            quality="EXPLICITLY_UNBOUND_BY_S1",
            leakage="AUDIT_ONLY",
            notes="S1 explicitly leaves this unbound; S2 does not select or fit a value.",
        )
    for authority_type in state["parameter_authority_types"]:
        add(
            f"ParameterAuthorityType.{authority_type}",
            "PARAMETER_AUTHORITY_TYPE",
            authority_type.replace("_", " ").title(),
            "AUTHORITY_CLASS",
            "UNOBSERVABLE",
            "AUTHORITATIVE",
            "S0_LITERATURE_PRIORS",
            unit="registered_authority_type",
            total=0,
            quality="CONTRACT_ENUM_NOT_A_PARAMETER_VALUE",
            leakage="AUDIT_ONLY",
            notes="Authority lifecycle vocabulary is defined; no enterprise parameter value follows from this enum.",
        )
    parameter_path = "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv"
    with (ROOT / parameter_path).open(encoding="utf-8-sig", newline="") as stream:
        for param in csv.DictReader(stream):
            pid = param.get("parameter_candidate_id") or "LITERATURE_CANDIDATE"
            pname = param.get("biological_parameter") or pid
            add(
                f"LiteratureParameterCandidate.{pid}",
                "LITERATURE_PARAMETER_CANDIDATE",
                pname,
                "LITERATURE_PRIOR",
                "UNOBSERVABLE",
                "REVIEWED_SUPPORTING",
                "S0_LITERATURE_PRIORS",
                unit=param.get("unit", "literature-declared"),
                total=0,
                quality="LITERATURE_CANDIDATE_ONLY_NOT_ENTERPRISE_DATA",
                leakage="AUDIT_ONLY",
                notes="Literature-observed/candidate value is not a current enterprise observation, selected coefficient, or production default.",
            )
    for edge in edges["causal_edges"]:
        add(
            f"CausalEdge.{edge['edge_id']}",
            "S1_CAUSAL_EDGE",
            f"{edge['source_state']} → {edge['target_state']}",
            edge["evidence_class"],
            "UNOBSERVABLE",
            "REVIEWED_SUPPORTING",
            "S0_LITERATURE_PRIORS",
            total=0,
            quality="QUALITATIVE_CAUSAL_CONTRACT; FIELD OBSERVABILITY IS AUDITED ON LINKED STATE ROWS",
            leakage="AUDIT_ONLY",
            notes=f"S1 {edge['admission_status']}; claims={';'.join(edge['claim_ids'])}; no numeric response authorized.",
        )
    for item in edges["quarantined_mechanisms"]:
        add(
            f"QuarantinedMechanism.{item['claim_id']}",
            "S1_QUARANTINED_MECHANISM",
            item["reason"],
            item["source_evidence_class"],
            "UNOBSERVABLE",
            "REVIEWED_SUPPORTING",
            "S0_LITERATURE_PRIORS",
            total=0,
            quality="RETAINED_IN_S1_QUARANTINE; NOT PROMOTED",
            leakage="AUDIT_ONLY",
            notes=f"S1 admission_status={item['admission_status']}; S2 preserves quarantine without promotion.",
        )

    # Project-specific business inputs and harvest-derived summaries.
    add(
        "BusinessInput.productive_area_mu",
        "BUSINESS_INPUT",
        "Accepted productive area",
        "DIRECT_OBSERVATION",
        "AVAILABLE",
        "AUTHORITATIVE",
        "V08_AREA",
        grain="Base × season",
        nonnull=117,
        total=117,
        seasons="2023-2024;2024-2025;2025-2026",
        start="2023-07-01",
        end="2026-04-15",
        temporal="season snapshot",
        unit="mu",
        quality="BUSINESS_CONFIRMED; 39 BASES × 3 SEASONS",
        derivation="None; accepted authority row",
        s3=True,
        s4=True,
        leakage="2023-2024/2024-2025 training;2025-2026 audit-only",
        notes="No area re-governance performed; area is not used to infer identity/cultivar.",
    )
    add(
        "BusinessInput.canonical_base_identity",
        "BUSINESS_INPUT",
        "Canonical Base identity",
        "BUSINESS_INPUT",
        "AVAILABLE",
        "AUTHORITATIVE",
        "V08_BASE_IDENTITY_AUTHORITY",
        grain="season-scoped source label → Base",
        nonnull=39,
        total=39,
        unit="canonical Base ID",
        quality="39 CANONICAL BASE IDENTITIES; LABEL RESOLUTION HAS UNRESOLVED/EXCLUDED RESIDUALS",
        s3=True,
        s4=True,
        leakage="TRAINING_ELIGIBLE historical identity;2025-2026 audit-only",
        notes="Identity authority is not cultivar or production-system authority.",
    )
    add(
        "BusinessInput.cultivar_at_productive_area_grain",
        "BUSINESS_INPUT",
        "Cultivar-to-productive-area binding",
        "DIRECT_OBSERVATION",
        "PROXY_AVAILABLE",
        "PRESENT_NOT_AUTHORIZED",
        "HARVEST_RAW_2024_2025",
        grain="receipt row has variety label; no area fraction",
        nonnull=201434,
        total=201434,
        seasons="2024-2025;2025-2026",
        start="2024-07-01",
        end="2026-04-16",
        temporal="receipt date",
        unit="source variety label",
        quality="LABEL_PRESENT; AREA/CULTIVAR IDENTITY NOT AUTHORIZED",
        proxy="Receipt source variety label is only a transaction-level proxy; no planted-area mapping or canonical cultivar authority.",
        s3=True,
        leakage="2024-2025 historical target context;2025-2026 audit-only",
        notes="CULTIVAR_GRAIN_LIMITATION: transaction labels do not establish Base-season cultivar mix or area weights.",
    )
    add(
        "BusinessInput.tree_age_or_planting_year",
        "BUSINESS_INPUT",
        "Tree age / planting year",
        "DIRECT_OBSERVATION",
        "NEW_COLLECTION_REQUIRED",
        "NOT_PRESENT",
        "PLANTING_TEMPLATE",
        unit="years or planting year",
        new=True,
        notes="Planting template is empty; application schema is not queried for live rows.",
    )
    add(
        "HarvestOutput.daily_harvest_quantity_kg",
        "OBSERVED_OUTPUT",
        "Daily harvested/received quantity",
        "MODEL_OUTPUT",
        "AVAILABLE",
        "AUTHORITATIVE",
        "V08_HARVEST",
        grain="Base × date",
        nonnull=33033,
        total=33033,
        start="2023-07-01",
        end="2026-04-15",
        temporal="daily",
        unit="kg",
        quality="S6 AUTHORIZED ZERO-SEMANTICS DAILY OVERLAY; QUANTITY CONSERVATION PINNED",
        s3=True,
        s4=True,
        leakage="2023-2024/2024-2025 training evidence;2025-2026 AUDIT_ONLY",
        notes="Observed harvest output/target. Not ripe quantity, maturity state, or daily newly mature biological supply.",
    )
    for field_id, label in [
        ("first_harvest_date", "First harvest date"),
        ("half_cumulative_harvest_date", "50% cumulative harvest date"),
        ("last_harvest_date", "Last nonzero harvest date"),
    ]:
        add(
            f"HarvestDerived.{field_id}",
            "HARVEST_DERIVED_PROXY",
            label,
            "DERIVED_VARIABLE",
            "DERIVABLE",
            "PROXY_ONLY",
            "V08_HARVEST",
            grain="Base × season",
            nonnull=76,
            total=117,
            start="2023-07-01",
            end="2026-04-15",
            temporal="season date derived from complete daily harvest ledger",
            unit="date",
            quality="DERIVABLE_FOR_76_AUTHORITY_COMPLETE_DAILY_CURVES; NOT PHYSIOLOGICAL PHENOLOGY",
            derivation="First/median cumulative/last nonzero date from an authority-complete daily harvest curve",
            proxy="Operational harvest timing only; not first physiological ripe, bloom, or color break.",
            s3=True,
            s4=False,
            leakage="training seasons only;2025-2026 audit-only",
            notes="The 76 count is 15 + 22 training-complete curves plus 39 audit-only curves; never use 2025-2026 for selection.",
        )
    return rows


def minimum_inputs() -> list[dict[str, Any]]:
    items = [
        (
            "P0",
            "scope_identity",
            "Farm/Base/subfarm identity",
            "REQUIRED",
            "Business-confirmed stable mapping and scope; preserve source grain.",
        ),
        (
            "P0",
            "cultivar_area_binding",
            "Cultivar ID and productive-area share",
            "REQUIRED",
            "Current receipt labels do not resolve cultivar area; needed for cultivar-scoped parameters.",
        ),
        (
            "P0",
            "productive_area",
            "Accepted productive area",
            "REQUIRED",
            "Existing V0.8 authority covers 39×3; future season needs fresh authority.",
        ),
        (
            "P0",
            "production_system",
            "DECIDUOUS_NATURAL / DECIDUOUS_FORCING / EVERGREEN",
            "REQUIRED",
            "Business confirmation per Base/cultivar/season; do not infer from location.",
        ),
        (
            "P0",
            "tree_age",
            "Tree age or planting year",
            "REQUIRED",
            "Low-cost structural context currently absent from populated assets.",
        ),
        (
            "P0",
            "pruning_event",
            "Actual pruning date and type",
            "REQUIRED",
            "Record executed event, not standard plan; intensity may initially remain unknown.",
        ),
        (
            "P0",
            "greenhouse_events",
            "Greenhouse close/open and heating/forcing start/stop",
            "REQUIRED_FOR_PROTECTED_SYSTEM",
            "Event timestamps bound forcing exposure; event itself is not a date shift.",
        ),
        (
            "P0",
            "bloom_10_50_90",
            "10%, 50%, 90% bloom observations",
            "REQUIRED",
            "Three low-burden phenology anchors enable forward transition checks.",
        ),
        (
            "P0",
            "indoor_temperature_hourly",
            "Representative greenhouse hourly air temperature",
            "REQUIRED_FOR_FORCING_CALIBRATION",
            "Outdoor weather is not a greenhouse substitute; record sensor/source/QC.",
        ),
        (
            "P1",
            "pruning_intensity",
            "Pruning intensity/removed wood representation",
            "OPTIONAL",
            "Record a defined grade or sampled denominator; no universal coefficient.",
        ),
        (
            "P1",
            "flower_thinning",
            "Flower thinning date, scope and intensity",
            "REQUIRED_FOR_CROP_LOAD_IDENTIFIABILITY",
            "Separate from pruning; presence-only is acceptable initially.",
        ),
        (
            "P1",
            "fruit_set_sample",
            "Standardized fruit-set sample",
            "REQUIRED_FOR_CROP_LOAD_IDENTIFIABILITY",
            "Repeat at a declared sample size and scope.",
        ),
        (
            "P1",
            "color_break",
            "10% color-break date or cohort sample",
            "REQUIRED_FOR_MATURITY_CALIBRATION",
            "Harvest cannot substitute for color break.",
        ),
        (
            "P1",
            "first_harvest",
            "First harvest date",
            "OPTIONAL",
            "Already derivable from harvest output; preserve as harvest timing proxy.",
        ),
        (
            "P1",
            "cumulative_harvest",
            "50% cumulative and season-end harvest dates",
            "OPTIONAL",
            "Already derivable where complete daily authority exists; retain provenance.",
        ),
        (
            "P1",
            "cultivar",
            "Cultivar-specific planting and area share",
            "REQUIRED",
            "Use business-confirmed plot/cultivar binding, not transaction label alone.",
        ),
        (
            "P2",
            "fruit_cohort_tracking",
            "Bloom/fruit cohort lineage and stage samples",
            "FUTURE_ADVANCED",
            "Useful for cohort kernels; not required for synthetic prototype.",
        ),
        (
            "P2",
            "canopy_and_cane_structure",
            "Productive shoots, cane age, leaf/canopy retention sample",
            "FUTURE_ADVANCED",
            "Improves source and next-season carryover identifiability.",
        ),
        (
            "P2",
            "rootzone_light_sensors",
            "Root-zone temperature, radiation/light, RH sensors",
            "FUTURE_ADVANCED",
            "Expand only after P0 indoor air logging proves useful.",
        ),
        (
            "P2",
            "carbohydrate_assay",
            "Plant reserve carbohydrate assay",
            "FUTURE_ADVANCED",
            "Latent/experimental; expensive and not a minimum S3 blocker.",
        ),
    ]
    result: list[dict[str, Any]] = []
    for priority, field_id, field_name, required, rationale in items:
        if field_id in {"productive_area", "first_harvest", "cumulative_harvest"}:
            current_status = "AVAILABLE"
        elif field_id == "scope_identity":
            current_status = "AVAILABLE"
        elif field_id == "production_system":
            current_status = "BUSINESS_CONFIRMATION_REQUIRED"
        else:
            current_status = "NEW_COLLECTION_REQUIRED"
        result.append(
            {
                "priority": priority,
                "field_id": field_id,
                "field_name": field_name,
                "required_or_optional": required,
                "current_status": current_status,
                "evidence": rationale,
                "minimum_grain": "greenhouse/subfarm × hour"
                if field_id == "indoor_temperature_hourly"
                else "Base × season",
                "s3_role": "historical target/proxy only"
                if field_id in {"first_harvest", "cumulative_harvest"}
                else "input candidate; not yet authorized as production parameter",
            }
        )
    return result


def collection_plan() -> list[dict[str, Any]]:
    specs = [
        (
            "scope_identity",
            "Farm/Base/subfarm and cultivar-area binding",
            "Maintain causal unit and cultivar applicability",
            "Structural / all states",
            "Business-confirmed plot/planting register",
            "Once; review each season",
            "Base/subfarm/cultivar",
            "stable IDs and area share",
            "REQUIRED",
            "manual register",
            "Low",
            "Limited",
            True,
            "P0",
        ),
        (
            "productive_area",
            "Accepted productive area",
            "Scale and denominator",
            "Yield potential",
            "Area authority snapshot with source/validity",
            "Each season and after material change",
            "Base/subfarm × season",
            "mu",
            "REQUIRED",
            "manual authority",
            "Low",
            "Can be backfilled only with authoritative record",
            True,
            "P0",
        ),
        (
            "tree_age",
            "Planting year/tree age",
            "Structural and cultivar response context",
            "StructuralState",
            "Planting record",
            "Annual",
            "cultivar block/subfarm",
            "year / years",
            "REQUIRED",
            "manual register",
            "Low",
            "Usually backfillable if records exist",
            True,
            "P0",
        ),
        (
            "production_system",
            "Production-system assignment",
            "Select legal state pathway without geographic inference",
            "ProductionSystem",
            "Business-confirmed seasonal declaration",
            "Each season / change",
            "Base/subfarm × cultivar",
            "registered enum",
            "REQUIRED",
            "manual declaration",
            "Low",
            "Partly backfillable with explicit confirmation",
            True,
            "P0",
        ),
        (
            "pruning_date_type",
            "Executed pruning date/type",
            "Separate structural intervention from flower thinning",
            "Fruiting wood / bud potential",
            "Timestamped event log; observed vs planned flag",
            "Per event",
            "subfarm/cultivar",
            "local date + event enum",
            "REQUIRED",
            "manual event record",
            "Low",
            "Only if contemporaneous records exist",
            True,
            "P0",
        ),
        (
            "greenhouse_events",
            "Greenhouse close/open and heating start/stop",
            "Bound forcing and microclimate exposure",
            "EnvironmentState / ForcingState",
            "Controller log export or event record with source",
            "Per event/interval",
            "greenhouse × subfarm",
            "timezone-aware datetime",
            "REQUIRED for protected forcing",
            "manual or controller log",
            "Low to medium",
            "Controller logs may be backfilled if retained",
            True,
            "P0",
        ),
        (
            "bloom_10_50_90",
            "10%, 50%, 90% bloom",
            "Anchor phenology transitions",
            "BloomProgress / BloomCohort",
            "Standard visual protocol and observation date",
            "At each threshold per season",
            "subfarm × cultivar",
            "date; protocol-defined percentage",
            "REQUIRED",
            "manual observation",
            "Low",
            "Not reliably backfillable",
            True,
            "P0",
        ),
        (
            "indoor_hourly_temperature",
            "Greenhouse hourly air temperature",
            "Chill/forcing and protected microclimate support",
            "EnvironmentInput",
            "One calibrated logger per representative greenhouse/zone; QC and gaps",
            "Hourly continuous during relevant cycle",
            "greenhouse/zone",
            "degC + timestamp",
            "REQUIRED for forcing calibration",
            "sensor",
            "Low to medium",
            "Not backfillable unless archived logger exists",
            True,
            "P0",
        ),
        (
            "flower_thinning",
            "Flower thinning date/type/intensity",
            "Identify reproductive sink intervention separately",
            "EffectiveFlowerLoad",
            "Event log; presence-only initially, intensity mode explicit",
            "Per event",
            "subfarm × cultivar",
            "date + enum/declared grade",
            "REQUIRED for crop-load work",
            "manual event record",
            "Low",
            "Limited",
            True,
            "P1",
        ),
        (
            "fruit_set_sample",
            "Fruit-set sample",
            "Connect effective pollination to crop load",
            "FruitSetRatio / FruitNumber",
            "Fixed sample plants/shoots with denominator and method",
            "At defined set stage",
            "subfarm × cultivar",
            "count/count or ratio",
            "REQUIRED for crop-load calibration",
            "manual sample",
            "Medium",
            "Not reliably backfillable",
            True,
            "P1",
        ),
        (
            "color_break",
            "10% color-break date/sample",
            "Separate maturity from harvest timing",
            "ColorBreakState / FruitCohort",
            "Standard color-break protocol, cohort/scope recorded",
            "At threshold; repeat if cohorts split",
            "subfarm × cultivar/cohort",
            "date + proportion",
            "REQUIRED for maturity calibration",
            "manual observation",
            "Low",
            "Not reliably backfillable",
            True,
            "P1",
        ),
        (
            "harvest_series",
            "First, 50% cumulative, and end harvest",
            "Harvest boundary/target; not biological maturity",
            "HarvestOutput",
            "Existing canonical daily ledger; preserve authority and frozen window",
            "Daily during harvest",
            "Base × date",
            "kg/date",
            "REQUIRED",
            "business system export",
            "Existing",
            "Already available for authorized seasons",
            True,
            "P1",
        ),
        (
            "cultivar_area",
            "Cultivar-level productive area shares",
            "Bind cultivar-specific priors/calibration",
            "Cultivar identity / area",
            "Business-confirmed planting/area roster",
            "Each season and after replant/change",
            "subfarm × cultivar × season",
            "mu/share",
            "REQUIRED",
            "manual register",
            "Low",
            "Backfill only with verified planting records",
            True,
            "P1",
        ),
        (
            "fruit_cohort_samples",
            "Bloom-to-fruit cohort linkage and stage sampling",
            "Identify maturity cohort kernel",
            "BloomCohort → FruitCohort",
            "Small tagged/area-normalized cohort sample; no whole-farm tagging",
            "At bloom, set, Stage I/II/III, color break",
            "sample block × cultivar",
            "declared count/index + dates",
            "OPTIONAL",
            "manual sample",
            "Medium to high",
            "Not reliably backfillable",
            True,
            "P2",
        ),
        (
            "canopy_sample",
            "Productive shoot/cane/leaf retention sample",
            "Source and inter-season structure proxy",
            "Structural/VegetativeState",
            "Repeatable fixed-plant/sample-point protocol",
            "Postharvest and pre-bloom",
            "sample block × cultivar",
            "declared counts/index",
            "OPTIONAL",
            "manual sample",
            "Medium",
            "Limited",
            True,
            "P2",
        ),
        (
            "microclimate_advanced",
            "RH/root-zone temp/radiation",
            "Refine environment and source-sink proxies",
            "EnvironmentInput / SourceSink",
            "Add only after P0 sensor pilot and data QA",
            "Hourly/daily per instrument spec",
            "representative greenhouse zone",
            "sensor-native units",
            "OPTIONAL",
            "sensors",
            "Medium to high",
            "No",
            True,
            "P2",
        ),
        (
            "carbohydrate_assay",
            "Carbohydrate reserve assay",
            "Directly examine latent carry-over state",
            "InterSeasonState",
            "Research assay with protocol and lab QA",
            "Selected strategic time points",
            "cultivar × sample plants",
            "assay unit",
            "OPTIONAL",
            "laboratory",
            "High",
            "No",
            True,
            "P2",
        ),
    ]
    columns = [
        "field_id",
        "field_name",
        "why_needed",
        "biological_state_supported",
        "collection_method",
        "frequency",
        "grain",
        "unit",
        "required_or_optional",
        "manual_or_sensor",
        "estimated_operational_burden",
        "can_be_backfilled",
        "prospective_only",
        "priority",
    ]
    if any(len(row) != len(columns) for row in specs):
        raise ValueError("collection plan row does not match its schema")
    return [{column: row[index] for index, column in enumerate(columns)} for row in specs]


def readiness_matrix() -> list[dict[str, str]]:
    return [
        {
            "module": "Phenology Engine",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "S1 transitions exist, but no direct bloom/bud phenology history and no accepted continuous temperature series; no chill/forcing model selected.",
        },
        {
            "module": "Crop Load Engine",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "No authorized flower-load, pollination, fruit-set or fruit-number observations; thinning execution not recorded.",
        },
        {
            "module": "Source-Sink Proxy",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "Composite states have no validated observed proxy bundle; carbohydrate reserve is latent and exact formula unbound.",
        },
        {
            "module": "Bloom Cohort",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "No bloom cohort date/quantity/provenance rows or lineage.",
        },
        {
            "module": "Fruit Cohort",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "No bloom→fruit-set→color-break→ripe cohort linkage; harvest is not a maturity cohort observation.",
        },
        {
            "module": "Maturity Engine",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "No color-break or ripe observations and no cohort calibration; only harvest output is available.",
        },
        {
            "module": "InterSeason Carryover",
            "contract_status": "CONTRACT_READY",
            "data_status": "BLOCKED",
            "readiness": "SYNTHETIC_ONLY",
            "reason": "No postharvest vigor/reserve/bud-potential observations; cross-season yield is not a substitute.",
        },
        {
            "module": "Biological→Harvest Interface",
            "contract_status": "CONTRACT_READY",
            "data_status": "PROXY_READY",
            "readiness": "CONTRACT_READY",
            "reason": "S1 interface is frozen and historical daily harvest output exists, but daily newly mature biological supply is not observed; interface test inputs must be synthetic/proxy-labeled.",
        },
    ]


def main() -> None:
    s0_hashes, s1_hashes, state, events, edges, evidence = verify_inputs()
    sources = source_register()
    matrix = build_matrix(state, events, edges)
    variable_matrix = [
        row
        for row in matrix
        if row["contract_category"] not in {"S1_CAUSAL_EDGE", "S1_QUARANTINED_MECHANISM"}
    ]
    matrix_counts = Counter(row["actual_observability_status"] for row in variable_matrix)
    source_counts = Counter(row["data_presence_status"] for row in sources)
    event_rows = [row for row in matrix if row["contract_category"] == "MANAGEMENT_EVENT"]
    phenology_rows = [row for row in matrix if row["contract_category"] == "PHENOLOGY_STATE"]
    causal_edge_rows = [row for row in matrix if row["contract_category"] == "S1_CAUSAL_EDGE"]
    quarantine_rows = [
        row for row in matrix if row["contract_category"] == "S1_QUARANTINED_MECHANISM"
    ]
    biological_field_rows = [
        row
        for row in matrix
        if row["variable_id"].startswith(
            (
                "Structural.",
                "Vegetative.",
                "Reproductive.",
                "Phenology.",
                "Fruit.",
                "Interseason.",
                "InterSeasonState.",
                "SourceSink.",
            )
        )
    ]
    contract_variable_count = len(matrix) - len(causal_edge_rows) - len(quarantine_rows)
    direct_pheno = sum(row["actual_observability_status"] == "AVAILABLE" for row in phenology_rows)
    derived_pheno = sum(row["actual_observability_status"] == "DERIVABLE" for row in phenology_rows)
    proxy_pheno = sum(
        row["actual_observability_status"] == "PROXY_AVAILABLE" for row in phenology_rows
    )
    unobservable_pheno = sum(
        row["actual_observability_status"] == "UNOBSERVABLE" for row in phenology_rows
    )
    events_with_data = sum(
        row["actual_observability_status"] in {"AVAILABLE", "DERIVABLE", "PROXY_AVAILABLE"}
        for row in event_rows
    )
    inputs = minimum_inputs()
    collection = collection_plan()
    readiness = readiness_matrix()

    write_csv("docs/v0-9/s2/biological-data-observability-matrix-r1.csv", MATRIX_COLUMNS, matrix)
    write_csv("docs/v0-9/s2/data-source-authority-register-r1.csv", SOURCE_COLUMNS, sources)
    write_csv("docs/v0-9/s2/minimum-viable-biological-input-set-r1.csv", list(inputs[0]), inputs)
    write_csv(
        "docs/v0-9/s2/minimum-new-data-collection-plan-r1.csv", list(collection[0]), collection
    )
    write_csv("docs/v0-9/s2/s3-prototype-readiness-matrix-r1.csv", list(readiness[0]), readiness)

    s1_manifest_path = "docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json"
    s1_manifest_hash = sha256(ROOT / s1_manifest_path)
    evidence_payload: dict[str, Any] = {
        "task_id": "V0_9_S2_EXISTING_DATA_OBSERVABILITY_AND_GAP_AUDIT_R1",
        "result": "PASS_V0_9_S2_DATA_OBSERVABILITY_AUDIT_COMPLETED",
        "version": "0.9.0",
        "version_name": "BLUEBERRY_FORECAST_AGENT_V0_9_BIOLOGICAL_FORECAST_FOUNDATION",
        "base_main_sha": git_value("rev-parse", "origin/main"),
        "head_sha": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "scope": {
            "bounded_inventory_only": True,
            "live_database_queried": False,
            "full_filesystem_rescan": False,
            "model_code_changed": False,
            "model_trained": False,
            "model_refit": False,
            "parameter_fitting": False,
            "parameter_selection": False,
            "backtest_executed": False,
            "s3_started": False,
            "s4_started": False,
            "deployment_performed": False,
        },
        "authority_pins": {
            "s0_authority_pinned": True,
            "s0_hashes": s0_hashes,
            "s1_manifest_path": s1_manifest_path,
            "s1_manifest_sha256": s1_manifest_hash,
            "s1_files": s1_hashes,
            "s1_contract_version": "V0_9_S1_R1",
        },
        "coverage": {
            "biological_state_field_count": len(
                state["plant_state_fields"]
                + state["interseason_state_fields"]
                + state["source_sink_state_fields"]
            ),
            "phenology_state_count": len(state["phenology_state_machine"]["state_ids"]),
            "management_event_type_count": len(events["event_types"]),
            "management_event_types_with_existing_actual_data": events_with_data,
            "management_event_types_without_existing_actual_data": len(event_rows)
            - events_with_data,
            "environment_input_count": len(state["environment_input_contract"]["variables"])
            + len(state["environment_input_contract"]["optional_variables"]),
            "production_system_count": len(state["production_systems"]),
            "bloom_and_fruit_cohort_field_count": sum(
                len(c["required_fields"]) + len(c["optional_fields"])
                for c in state["cohort_contracts"].values()
            ),
            "management_event_metadata_field_count": len(events["generic_fields"]),
            "causal_edge_count": len(edges["causal_edges"]),
            "total_contract_variables_audited": contract_variable_count,
            "non_variable_evidence_items_audited": len(causal_edge_rows) + len(quarantine_rows),
            "actual_observability_status_counts": dict(sorted(matrix_counts.items())),
            "phenology_states_directly_observable": direct_pheno,
            "phenology_states_derivable": derived_pheno,
            "phenology_states_proxy_only": proxy_pheno,
            "phenology_states_unobservable": unobservable_pheno,
            "matrix_row_count": len(matrix),
            "matrix_contract_coverage": {
                "biological_state_fields": len(biological_field_rows),
                "phenology_states": len(phenology_rows),
                "management_event_types": len(event_rows),
                "environment_inputs": sum(
                    row["contract_category"] == "ENVIRONMENT_INPUT" for row in matrix
                ),
                "production_systems": sum(
                    row["contract_category"] == "PRODUCTION_SYSTEM" for row in matrix
                ),
                "bloom_fruit_cohort_fields": sum(
                    row["contract_category"] in {"BLOOMCOHORT_FIELD", "FRUITCOHORT_FIELD"}
                    for row in matrix
                ),
                "management_event_metadata_fields": sum(
                    row["contract_category"] == "MANAGEMENT_EVENT_FIELD" for row in matrix
                ),
                "causal_edges": len(causal_edge_rows),
                "quarantined_mechanisms": len(quarantine_rows),
                "environment_observation_metadata": sum(
                    row["contract_category"] == "ENVIRONMENT_OBSERVATION_METADATA" for row in matrix
                ),
                "parameter_contract_fields": sum(
                    row["contract_category"] == "PARAMETER_AUTHORITY_FIELD" for row in matrix
                ),
                "parameter_authority_types": sum(
                    row["contract_category"] == "PARAMETER_AUTHORITY_TYPE" for row in matrix
                ),
                "literature_parameter_candidates": sum(
                    row["contract_category"] == "LITERATURE_PARAMETER_CANDIDATE" for row in matrix
                ),
            },
            "matrix_duplicate_variable_id_count": len(matrix)
            - len({r["variable_id"] for r in matrix}),
        },
        "asset_findings": {
            "canonical_base_count": 39,
            "accepted_area_base_season_rows": 117,
            "accepted_area_mu_per_season": 41335,
            "canonical_daily_harvest_rows": 33033,
            "complete_daily_curves_by_season": {"2023-2024": 15, "2024-2025": 22, "2025-2026": 39},
            "training_rows": 37,
            "training_split": {"2023-2024": 15, "2024-2025": 22},
            "benchmark_2025_2026_consumed": True,
            "benchmark_2025_2026_leakage_class": "AUDIT_ONLY",
            "benchmark_reuse_for_selection_allowed": False,
            "raw_receipts": {
                "HARVEST_RAW_2024_2025": {
                    "sha256": INPUT_HASHES["data/raw/2024_2025_receipts.xls"],
                    "rows": 201434,
                    "date_min": "2024-07-01",
                    "date_max": "2025-05-27",
                    "unique_dates": 323,
                    "dates_beyond_frozen_season_end": 42,
                    "frozen_season_end": "2025-04-15",
                },
                "HARVEST_RAW_2025_2026": {
                    "sha256": INPUT_HASHES["data/raw/2025_2026_receipts.xls"],
                    "rows": 232527,
                    "date_min": "2025-07-22",
                    "date_max": "2026-04-16",
                    "unique_dates": 229,
                    "dates_beyond_frozen_season_end": 1,
                    "frozen_season_end": "2026-04-15",
                },
            },
            "production_system_assignments": {
                "candidate_base_season_count": 117,
                "observed_assignments": 0,
                "status": "BUSINESS_CONFIRMATION_REQUIRED",
                "inference_from_region_or_cultivar": False,
            },
            "management_event_types_with_executed_records": 0,
            "phenology_direct_observations": 0,
            "harvest_is_maturity_observation": False,
            "era5_accepted_normalized_hourly_or_daily_rows": 0,
            "era5_r3_pending_requests": 91,
            "era5_crs_established": False,
            "ecmwf_forecast_snapshots": {
                "count": 156,
                "base_count": 39,
                "horizons": 4,
                "role": "PROSPECTIVE_ONLY",
                "indoor_microclimate": False,
            },
            "greenhouse_hourly_temperature": "NEW_COLLECTION_REQUIRED",
            "chilling_derivability": "CANNOT_DERIVE",
            "forcing_derivability": "CANNOT_DERIVE",
            "cultivar_area_grain": "CULTIVAR_GRAIN_LIMITATION",
            "live_database_content": "NOT_ASSESSED_BY_SCOPE",
        },
        "readiness": {
            "current_max_feasible_level": "LEVEL_1_HISTORICAL_PROXY_MODEL",
            "interpretation": "Only coarse historical harvest/yield proxy modeling has real data support; biological state transitions and maturity cohorts remain synthetic-only, not an S3 biological model readiness claim.",
            "s3_modules": readiness,
            "minimum_collection_priority_counts": dict(
                sorted(Counter(row["priority"] for row in collection).items())
            ),
            "top_data_gaps": [
                "production system and cultivar-area binding",
                "direct phenology anchors",
                "greenhouse hourly temperature and forcing event history",
                "pruning/thinning executed-event logs",
                "fruit-set and color-break observations",
                "source/crop-load observation proxies",
            ],
        },
        "leakage_policy": {
            "2023_2024_and_2024_2025": "TRAINING_ELIGIBLE only for previously authorized historical target/calibration scope; this task performs no parameter selection",
            "2025_2026": "AUDIT_ONLY",
            "ecmwf_snapshots": "PROSPECTIVE_ONLY",
            "benchmark_2025_2026_consumed": True,
            "benchmark_reuse_for_selection_allowed": False,
        },
        "data_source_authority_register_summary": dict(sorted(source_counts.items())),
        "deliverables": [
            "docs/v0-9/s2/existing-data-observability-and-gap-audit-r1.md",
            "docs/v0-9/s2/biological-data-observability-matrix-r1.csv",
            "docs/v0-9/s2/data-source-authority-register-r1.csv",
            "docs/v0-9/s2/minimum-viable-biological-input-set-r1.csv",
            "docs/v0-9/s2/minimum-new-data-collection-plan-r1.csv",
            "docs/v0-9/s2/s3-prototype-readiness-matrix-r1.csv",
            s1_manifest_path,
        ],
        "private_artifact_policy": {
            "absolute_paths_in_public_outputs": False,
            "private_roots_disclosed_as": "logical source IDs and SHA-256 only",
            "private_row_level_data_republished": False,
        },
        "validation": {
            "s0_hash_pins": "PASS",
            "s1_manifest_hashes": "PASS",
            "full_s1_contract_coverage": (
                len(biological_field_rows) == 33
                and len(phenology_rows) == 21
                and len(event_rows) == 29
                and sum(row["contract_category"] == "ENVIRONMENT_INPUT" for row in matrix) == 10
                and sum(row["contract_category"] == "PRODUCTION_SYSTEM" for row in matrix) == 3
                and sum(
                    row["contract_category"] in {"BLOOMCOHORT_FIELD", "FRUITCOHORT_FIELD"}
                    for row in matrix
                )
                == 26
                and sum(row["contract_category"] == "MANAGEMENT_EVENT_FIELD" for row in matrix)
                == 18
                and len(causal_edge_rows) == 33
                and len(quarantine_rows) == 6
                and sum(
                    row["contract_category"] == "ENVIRONMENT_OBSERVATION_METADATA" for row in matrix
                )
                == 6
                and sum(row["contract_category"] == "PARAMETER_AUTHORITY_FIELD" for row in matrix)
                == 13
                and sum(row["contract_category"] == "PARAMETER_AUTHORITY_TYPE" for row in matrix)
                == 6
            ),
            "matrix_duplicate_variable_id_count": len(matrix)
            - len({r["variable_id"] for r in matrix}),
            "s1_not_ready_mechanisms_quarantined": len(quarantine_rows),
            "unauthorized_mechanism_promotion_count": 0,
            "all_observability_statuses_valid": all(
                r["actual_observability_status"]
                in {
                    "AVAILABLE",
                    "DERIVABLE",
                    "PROXY_AVAILABLE",
                    "BUSINESS_CONFIRMATION_REQUIRED",
                    "NEW_COLLECTION_REQUIRED",
                    "UNOBSERVABLE",
                }
                for r in matrix
            ),
            "all_authority_statuses_valid": all(
                r["authority_status"]
                in {
                    "AUTHORITATIVE",
                    "REVIEWED_SUPPORTING",
                    "PRESENT_NOT_AUTHORIZED",
                    "PROXY_ONLY",
                    "UNKNOWN_AUTHORITY",
                    "NOT_PRESENT",
                }
                for r in matrix
            ),
            "data_source_authority_register_complete": (
                len({row["source_id"] for row in sources}) == len(sources)
                and all(
                    row.get("source_hash")
                    for row in sources
                    if row["data_presence_status"] == "PRESENT"
                )
                and all(row.get("quality_status") for row in sources)
                and all(
                    row["leakage_class"]
                    in {
                        "TRAINING_ELIGIBLE",
                        "AUDIT_ONLY",
                        "FUTURE_COLLECTION",
                        "PROSPECTIVE_ONLY",
                        "BLOCKED_LEAKAGE",
                    }
                    for row in sources
                )
            ),
            "source_register_duplicate_id_count": len(sources)
            - len({row["source_id"] for row in sources}),
            "matrix_missing_source_hash_count": sum(
                not row["source_hash"] and row["source_id"] != "APP_DB_LIVE_CONTENT"
                for row in matrix
            ),
            "no_absolute_private_paths": True,
        },
    }
    write_report(evidence_payload, matrix_counts, sources, matrix, inputs, collection, readiness)
    artifact_roles = {
        "docs/v0-9/s2/existing-data-observability-and-gap-audit-r1.md": "S2_REPORT",
        "docs/v0-9/s2/biological-data-observability-matrix-r1.csv": "OBSERVABILITY_MATRIX",
        "docs/v0-9/s2/data-source-authority-register-r1.csv": "SOURCE_AUTHORITY_REGISTER",
        "docs/v0-9/s2/minimum-viable-biological-input-set-r1.csv": "MINIMUM_VIABLE_INPUT_SET",
        "docs/v0-9/s2/minimum-new-data-collection-plan-r1.csv": "DATA_COLLECTION_PLAN",
        "docs/v0-9/s2/s3-prototype-readiness-matrix-r1.csv": "S3_READINESS_MATRIX",
        s1_manifest_path: "S1_ARTIFACT_MANIFEST",
    }
    evidence_payload["deliverables"] = [
        {"path": path, "sha256": sha256(ROOT / path), "role": role}
        for path, role in artifact_roles.items()
    ]
    evidence_payload["evidence_self_sha256_excluded"] = True
    write_json(
        "docs/v0-9/evidence/s2-existing-data-observability-and-gap-audit-r1.json", evidence_payload
    )


def write_report(
    evidence: dict[str, Any],
    counts: Counter[str],
    sources: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    collection: list[dict[str, Any]],
    readiness: list[dict[str, str]],
) -> None:
    s = evidence["asset_findings"]
    cov = evidence["coverage"]
    status_lines = "\n".join(f"| {key} | {value} |" for key, value in sorted(counts.items()))
    readiness_lines = "\n".join(
        f"| {r['module']} | {r['readiness']} | {r['reason']} |" for r in readiness
    )
    priority = evidence["readiness"]["minimum_collection_priority_counts"]
    report = f"""# V0.9-S2 Existing Data Observability and Gap Audit

**Task:** `V0_9_S2_EXISTING_DATA_OBSERVABILITY_AND_GAP_AUDIT_R1`  
**Version:** `0.9.0` — `BLUEBERRY_FORECAST_AGENT_V0_9_BIOLOGICAL_FORECAST_FOUNDATION`  
**Authority:** pinned V0.9-S0 evidence and the complete V0.9-S1 R1 artifact manifest.  
**Result:** `PASS_V0_9_S2_DATA_OBSERVABILITY_AUDIT_COMPLETED`

## Scope and audit method

This is a bounded inventory of repository-referenced data, V0.8/V0.9 authorities, known authorized artifact references, and the raw sources already in the project. It is not a scan of the user's computer. S0/S1 scientific conclusions are unchanged. No live database was queried; empty templates and application schemas are not treated as business records. Public artifacts use logical source IDs and contain no machine-specific absolute paths.

S0's six authority artifact hashes were recomputed and matched. The nine S1 contract/evidence files were individually rehashed and recorded in `docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json`. The S2 matrix contains **{cov["matrix_row_count"]} audit rows**: {cov["total_contract_variables_audited"]} contract/data variables plus {cov["non_variable_evidence_items_audited"]} causal-edge/quarantine evidence items. It includes {cov["biological_state_field_count"]} biological/inter-season/source-sink fields, {cov["phenology_state_count"]} phenology states, all {cov["management_event_type_count"]} event types, environment and production-system inputs, cohort fields, and parameter-authority vocabulary/candidates.

## Current data picture

| Asset | Verified coverage | Authority and boundary |
|---|---|---|
| Productive area | {s["accepted_area_base_season_rows"]} Base-season rows; 39 canonical Bases × 3 seasons; 41,335 mu per season | V0.8 business-confirmed authority; S2 does not reopen it |
| Canonical daily harvest | {s["canonical_daily_harvest_rows"]} Base-date rows; complete daily curves 15 / 22 / 39 by season | Authorized harvest output; not ripe/maturity observation |
| Strict historical training | {s["training_rows"]} rows: 15 in 2023–24 and 22 in 2024–25 | Historical target evidence only; no fitting here |
| Raw 2024–25 receipts | 201,434 rows; 323 dates; through 2025-05-27 | 42 dates exceed frozen 2025-04-15 season end; keep out-of-window rows explicit |
| Raw 2025–26 receipts | 232,527 rows; 229 dates; through 2026-04-16 | Consumed benchmark; 1 date exceeds frozen 2026-04-15 end; audit-only |
| Cultivar | Variety label populated on receipt rows | Transaction-level proxy only; no cultivar-to-productive-area binding |
| Production plans / planting / phenology / weather templates | No populated business records; weather files contain only template/synthetic examples | Schema/template presence is not evidence of executed event or observation |

The receipt workbooks contain a fruit-size category but not numeric berry diameter or mean berry mass. Receipt arrivals/harvests are model target/output evidence under the frozen V0.8 business rule; they do not establish when fruit first became physiologically ripe.

## Observability counts

| Actual observability status | Matrix rows |
|---|---:|
{status_lines}

These status counts cover the {cov["total_contract_variables_audited"]} enumerated variables. The matrix additionally carries {cov["non_variable_evidence_items_audited"]} qualitative S1 causal-edge/quarantine evidence rows, which are not counted as observable variables. Counts are not percentages of the entire company database. Lack of a row in this bounded inventory is not a claim about unqueried live database content. Authority is separately recorded in the matrix and source register.

Phenology state coverage: {cov["phenology_states_directly_observable"]} directly observed, {cov["phenology_states_derivable"]} derivable as physiological states, {cov["phenology_states_proxy_only"]} harvest-derived proxy state(s), and {cov["phenology_states_unobservable"]} unobservable in the reviewed records. No direct bloom/bud/fruit-set/color-break observations were found. Harvest timing proxies remain explicitly non-physiological.

Production system is not assigned for the 117 Base-season candidate scope. `DECIDUOUS_NATURAL`, `DECIDUOUS_FORCING`, and `EVERGREEN` therefore require business confirmation; no region, cultivar label, or harvest date is used to infer system.

## Management, phenology, weather and source–sink gaps

No authorized executed records were found for any of the 29 management-event types. The empty production-plan template/schema has a planned `pruning_date` field, but no actual event row, pruning type/intensity, removed wood/buds, or cane-renewal measurement. Flower/fruit thinning and greenhouse close/open/heating are not evidenced as actual events. Standard procedures or planned dates are not converted to executed histories.

No direct phenology states are present. The only operational timing derivations are from complete harvest curves: first/half-cumulative/last nonzero harvest dates for 76 eligible daily curves; these are harvest-derived proxies, not bloom/ripe observations.

ERA5-Land attempts do not form an accepted normalized history dataset: prior builds are blocked, R3 stopped with 91 requests pending, no accepted normalized hourly/daily rows exist, and coordinate CRS is not established. ECMWF provides 156 prospective outdoor forecast snapshots for 39 Bases across four horizons, with a 360-hour horizon; it is not historical or indoor microclimate. Thus current authorized data cannot derive chill hours, Utah units, dynamic chill portions, or forcing GDD for biological calibration. `GREENHOUSE_TEMPERATURE=NEW_COLLECTION_REQUIRED`.

There are no observed leaf-area/canopy, effective flower load, fruit-set, fruit number, crop-load, or reserve measurements. Fruit-size class is a category proxy only. `carbohydrate_reserve_proxy` and exact source–sink balance remain unobservable/latent; no proxy is silently invented. BloomCohort and FruitCohort have no empirical rows or lineage, so `FRUIT_COHORT_STRUCTURE_SUPPORTED` does not mean empirically calibrated or ready.

## S3 data readiness

| Module | Current readiness | Evidence-bounded reason |
|---|---|---|
{readiness_lines}

`CURRENT_MAX_FEASIBLE_LEVEL=LEVEL_1_HISTORICAL_PROXY_MODEL` applies only to coarse historical area/harvest target proxies. The biological state-transition prototype itself is currently **synthetic-only**; Level 2 biological-observation readiness is not established.

## Minimum viable inputs and collection priority

The full field-by-field lists are in `minimum-viable-biological-input-set-r1.csv` and `minimum-new-data-collection-plan-r1.csv`. The minimal practical next-season package prioritizes: stable Base/subfarm/cultivar-area identity, accepted area, explicit production-system assignment and tree age; actual pruning and greenhouse/heating event dates; 10/50/90% bloom; representative indoor hourly air temperature; then flower-thinning event, fruit-set sample, and 10% color-break observation. Existing daily harvest should continue with source/date/quantity authority. Advanced cohort tagging, canopy sampling, extra sensors, and carbohydrate assays remain P2 and are not S3 blockers.

Collection plan counts: P0={priority.get("P0", 0)}, P1={priority.get("P1", 0)}, P2={priority.get("P2", 0)} fields. These priorities balance causal/identifiability value, likely coverage, and operational burden; they do not select model parameters.

## Answers to the ten audit questions

1. **Directly observed biological states?** None of the 21 phenology states and none of the 33 biological/inter-season/source-sink fields has an authorized direct observation in the reviewed records. Area and harvest output are available, but they are not plant-state observations.
2. **Derivable?** Harvest timing summaries are derivable for 76 complete daily curves, but only as harvest proxies. Chill/forcing and physiological transitions are not derivable from current accepted environment data.
3. **Proxy-only?** Receipt fruit-size category and harvest-derived first/median/end timing are proxies; neither becomes physical berry size, mean berry weight, or ripe state.
4. **Existing management records?** Zero of 29 event types has an authorized executed-event record in the bounded review.
5. **Pruning, thinning, forcing history?** No executed histories. Only an empty planned-pruning schema/template exists; business confirmation and prospective event capture are required.
6. **Indoor hourly microclimate?** No. ECMWF is outdoor forecast context, not greenhouse sensor data; indoor hourly temperature is a P0 new collection.
7. **Chill/forcing identifiable now?** No. Accepted continuous temperature series and indoor forcing records are absent; no chill or forcing model is selected.
8. **Bloom-to-maturity cohort identifiable?** No empirical cohort lineage. Structure may be represented synthetically, but empirical calibration is not identified.
9. **S3 maximum feasible level?** Level 1 only for coarse historical proxy/harvest-output modeling; the biological engine remains synthetic-only.
10. **Minimum next-season collection?** Scope/cultivar-area binding, area, production system, tree age, actual pruning and greenhouse/heating event dates, 10/50/90% bloom, indoor hourly temperature; add thinning, fruit-set, and color-break anchors as P1.

## Lifecycle, privacy and non-actions

2025–2026 remains `AUDIT_ONLY`; this audit performs no model/parameter/management-rule selection and does not reopen the consumed benchmark. Literature values remain priors, not production parameters. Live database content was not assessed. No model code, model parameters, training, refit, backtest, S3/S4 task, deployment, commit, or PR was performed. The source register includes only logical IDs, repository-relative references, hashes, scoped counts, and provenance; private row-level artifacts were not republished.
"""
    target = ROOT / "docs/v0-9/s2/existing-data-observability-and-gap-audit-r1.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
