"""V0.10 public aggregate closeout replay, never training or V0.11 execution."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PUBLIC = Path("artifacts/v0-10-closeout")
RELEASE_FILES = frozenset(
    [
        "artifacts/v0-10-closeout/baseline-metrics.csv",
        "artifacts/v0-10-closeout/extraction-manifest.json",
        "artifacts/v0-10-closeout/public-artifact-manifest.json",
        "artifacts/v0-10-closeout/release-chain-audit.json",
        "artifacts/v0-10-closeout/research-summary.json",
        "artifacts/v0-10-closeout/risk-coverage-width.csv",
        "artifacts/v0-10-closeout/risk-distribution-scores.csv",
        "backend/tests/area_yield/test_v0_10_release_boundary.py",
        "docs/v0-10/evidence/release-lifecycle-boundary-r1.json",
        "docs/v0-10/evidence/v0.10.0-research-closeout.json",
        "docs/v0-10/v0.10-research-experiment-index.md",
        "docs/v0-10/v0.10.0-release-closeout.md",
        "docs/v0-10/v0.10.0-scope-history-and-research-closeout.md",
        "docs/v0-10/v0.10.0-version-plan-and-scope-freeze.md",
        "scripts/replay_v0_10_closeout.py",
    ]
)
FORMAL_TAGS = (
    "v0.1.0",
    "v0.2.0",
    "v0.3.0",
    "v0.3.1",
    "v0.4.0",
    "v0.5.0",
    "v0.5.1",
    "v0.5.2",
    "v0.5.3",
    "v0.6.0",
    "v0.7.0",
    "v0.8.0",
    "v0.9.0",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(root: Path, path: str | Path) -> Any:
    return json.loads((root / path).read_text())


def csv_rows(root: Path, name: str) -> list[dict[str, str]]:
    with (root / PUBLIC / name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def close(a: str | float, b: str | float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def verify_changed_paths(paths: Iterable[str]) -> None:
    require(set(paths).issubset(RELEASE_FILES), "RELEASE_TREE_FOREIGN_CHANGED_FILE")


def verify(root: Path) -> dict[str, Any]:
    manifest = read_json(root, PUBLIC / "public-artifact-manifest.json")
    listed = set()
    for row in manifest["files"]:
        path = Path(row["path"])
        require(not path.is_absolute() and ".." not in path.parts, "PUBLIC_PATH_INVALID")
        require(row["path"] not in listed, "PUBLIC_PATH_DUPLICATE")
        listed.add(row["path"])
        require(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None, "PUBLIC_HASH_INVALID")
        require(file_hash(root / path) == row["sha256"], "PUBLIC_HASH_MISMATCH:" + str(path))
        if path.suffix in {".json", ".csv", ".md"}:
            text = (root / path).read_text()
            require(not any(s in text for s in ("/Users/", "file://", "/tmp/")), "PRIVATE_PATH")
    require(
        listed | {str(PUBLIC / "public-artifact-manifest.json")} == RELEASE_FILES,
        "RELEASE_TREE_MANIFEST",
    )
    require(manifest["private_rows_included"] is False, "PRIVATE_ROWS_NOT_ALLOWED")

    extraction = read_json(root, PUBLIC / "extraction-manifest.json")
    require(set(extraction["release_branch_files"]) == RELEASE_FILES, "RELEASE_TREE_ALLOWLIST")
    classified = extraction["files"]
    require(
        len(classified) == 37 and len({r["source_path"] for r in classified}) == 37,
        "EXTRACTION_SOURCE_LIST",
    )
    require(
        Counter(r["classification"] for r in classified)
        == {
            "V0_10_RELEASE_REQUIRED": 4,
            "SHARED_EVIDENCE_REQUIRED_FOR_V0_10": 4,
            "V0_11_ONLY": 22,
            "NOT_REQUIRED": 7,
        },
        "EXTRACTION_CLASS_COUNTS",
    )
    copied = []
    for row in classified:
        require(
            re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]) is not None, "SOURCE_HASH_INVALID"
        )
        destination = row["destination"]
        if row["classification"] in {"V0_11_ONLY", "NOT_REQUIRED"}:
            require(
                destination is None and row["extraction_mode"] is None, "EXCLUDED_SOURCE_INCLUDED"
            )
        else:
            require(
                destination in RELEASE_FILES and not destination.startswith("docs/v0-11/"),
                "RELEASE_TREE_DESTINATION",
            )
            copied.append(destination)
            if row["extraction_mode"] == "EXACT_COPY":
                require(
                    file_hash(root / destination) == row["source_sha256"], "EXACT_COPY_IDENTITY"
                )
    require(len(copied) == 8 and extraction["extracted_file_count"] == 8, "EXTRACTION_COUNT")

    audit = read_json(root, PUBLIC / "release-chain-audit.json")
    formal = [r for r in audit["versions"] if r["formal_chain_included"]]
    require(tuple(r["tag"] for r in formal) == FORMAL_TAGS, "RELEASE_CHAIN_FORMAL_TAGS")
    require(audit["main_sha"] == "8e886b45984a358125d00e80f4f5d662fab3d8e9", "RELEASE_CHAIN_BASE")
    for row in formal:
        require(
            all(
                row[k] is True
                for k in (
                    "tag_exists",
                    "github_release_exists",
                    "tag_is_ancestor_of_main",
                    "remote_tag_object_matches",
                    "remote_peeled_sha_matches",
                )
            ),
            "RELEASE_CHAIN_IDENTITY",
        )
        require(
            row["release_draft"] is False and row["release_prerelease"] is False,
            "RELEASE_CHAIN_FORMAL",
        )
    planning = next(r for r in audit["versions"] if r["tag"] == "v0.3.0-plan")
    require(
        planning["release_prerelease"] is True and not planning["formal_chain_included"],
        "RELEASE_CHAIN_PLANNING",
    )
    require(
        {r["tag"] for r in formal if r["stale_release_note_text"]} == {"v0.5.0", "v0.6.0"},
        "RELEASE_CHAIN_STALE_NOTES",
    )

    boundary = read_json(root, "docs/v0-10/evidence/release-lifecycle-boundary-r1.json")
    require(
        boundary["VERSION"] == "0.10.0" and boundary["RELEASE_CLASS"] == "RESEARCH_CLOSEOUT",
        "LIFECYCLE_IDENTITY",
    )
    require(boundary["V0_10_LIFECYCLE"] == "CLOSED_WITH_ORIGINAL_GATE_INCOMPLETE", "LIFECYCLE_GATE")
    require(
        boundary["V0_10_ORIGINAL_MECHANISTIC_GATE"] == "NOT_ESTABLISHED", "LIFECYCLE_ORIGINAL_GATE"
    )
    require(boundary["V0_10_HISTORICAL_PROXY_RESEARCH"] == "CLOSED", "LIFECYCLE_RESEARCH")
    require(
        boundary["CURRENT_REFERENCE_BASELINE_ID"] == "M0-ALL-HISTORY-REFERENCE-R1"
        and boundary["CURRENT_REFERENCE_BASELINE_FAMILY"] == "M0_CORRECTED_TASK8_SHARED_SPLINE"
        and boundary["CURRENT_REFERENCE_BASELINE_ROLE"] == "REFERENCE_BASELINE"
        and "CURRENT_CHAMPION" not in boundary
        and "CHAMPION_CHANGED" not in boundary,
        "REFERENCE_BASELINE_IDENTITY",
    )
    require(
        boundary["V0_11_LIFECYCLE"] == "READY_NOT_ISSUED"
        and boundary["V0_11_RELEASE_ACTION"] == "DEFER",
        "LIFECYCLE_V11",
    )
    for key in (
        "V0_10_ORIGINAL_S2_S4_COMPLETE",
        "V0_10_STABLE_PREDICTIVE_GAIN",
        "V0_10_PROSPECTIVE_VALIDATION",
        "V0_10_PRODUCTION_ACCURACY_APPROVED",
        "V0_10_PRODUCTION_USE_APPROVED",
        "ORIGINAL_MECHANISTIC_CALIBRATION_GATE_COMPLETE",
        "REAL_PROSPECTIVE_VALIDATION_COMPLETE",
        "STABLE_PREDICTIVE_GAIN_ESTABLISHED",
        "PRODUCTION_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "PROBABILITY_CALIBRATION_ESTABLISHED",
        "VERSION_COMPLETE",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "REFERENCE_BASELINE_CHANGED",
        "V0_11_TAG_CREATE",
        "V0_11_GITHUB_RELEASE_CREATE",
        "V0_11_CODE_OR_DELIVERY_DOCUMENTS_EXTRACTED",
        "NEW_BACKTEST_EXECUTED",
        "PRIVATE_ROW_LEVEL_DATA_REQUIRED",
        "TAG_CREATED",
        "GITHUB_RELEASE_CREATED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "AUTO_MERGE",
    ):
        require(boundary[key] is False, "LIFECYCLE_UNAUTHORIZED:" + key)
    require(boundary["REAL_FORECAST_COUNT"] == 0, "LIFECYCLE_NO_REAL_FORECAST")
    require(
        boundary["NO_MODEL_TRAINING_EXECUTED"] is True
        and boundary["NO_PARAMETER_SEARCH_EXECUTED"] is True,
        "LIFECYCLE_NO_SEARCH",
    )
    legacy = read_json(root, "docs/v0-10/evidence/v0.10.0-research-closeout.json")
    require(
        legacy["lifecycle"] == boundary["V0_10_LIFECYCLE"] and legacy["complete"] is False,
        "LIFECYCLE_LEGACY",
    )
    require(
        legacy["original_mechanistic_gate"] == "NOT_ESTABLISHED"
        and legacy["stable_predictive_gain"] is False,
        "LIFECYCLE_LEGACY_GATE",
    )
    summary = read_json(root, PUBLIC / "research-summary.json")
    require(
        len(summary["sources"]) == 13 and summary["training_reproduced"] is False,
        "RESEARCH_SUMMARY",
    )
    require(
        sum(s["archive_role"].startswith("SHARED_") for s in summary["sources"]) == 3,
        "RESEARCH_PROJECTION",
    )
    require(
        all(re.fullmatch(r"[0-9a-f]{64}", s["source_sha256"]) for s in summary["sources"]),
        "RESEARCH_SOURCE_HASH",
    )

    rows = csv_rows(root, "baseline-metrics.csv")
    require([int(r["count"]) for r in rows] == [22, 39, 61], "BASELINE_COHORT")
    for row in rows:
        require(row["candidate"] == "FROZEN_M0", "BASELINE_NOT_PROMOTED")
        for metric, numerator in (
            ("WINDOW_TOTAL_WAPE", "total_error_numerator_kg"),
            ("FULL_DAILY_PREDICTION_WAPE", "daily_error_numerator_kg"),
            ("TIMING_SHAPE_MICRO_WAPE", "shape_error_numerator_kg"),
        ):
            require(
                close(row[metric], float(row[numerator]) / float(row["actual_total_kg"]), 1e-12),
                "BASELINE_WAPE",
            )
    for key in (
        "actual_total_kg",
        "daily_error_numerator_kg",
        "total_error_numerator_kg",
        "shape_error_numerator_kg",
    ):
        require(close(rows[2][key], float(rows[0][key]) + float(rows[1][key])), "BASELINE_POOLING")

    coverage = csv_rows(root, "risk-coverage-width.csv")
    scores = csv_rows(root, "risk-distribution-scores.csv")
    require(len(coverage) == len(scores) == 36, "RISK_COHORT")
    for row in coverage:
        n = int(row["valid_count"])
        require(
            n
            == sum(
                int(row[k]) for k in ("covered_count", "below_lower_count", "above_upper_count")
            ),
            "RISK_ACCOUNTING",
        )
        require(close(row["coverage"], int(row["covered_count"]) / n, 1e-12), "RISK_COVERAGE")
        require(
            all(
                math.isfinite(float(row[k])) and float(row[k]) >= 0
                for k in ("mean_width_kg", "median_width_kg", "max_width_kg")
            ),
            "RISK_WIDTH",
        )

    def score_key(row: dict[str, str]) -> tuple[str, str, str, str]:
        return row["fold_id"], row["family"], row["variable"], row["nominal_coverage"]

    score_lookup = {score_key(r): r for r in scores}
    require(len(score_lookup) == 36, "RISK_DUPLICATE")
    require(set(score_lookup) == {score_key(r) for r in coverage}, "RISK_SAME_COHORT")
    for row in scores:
        fold, _, variable, nominal = score_key(row)
        require(int(row["count"]) == (22 if fold == "FORWARD_F1" else 39), "RISK_SCORE_COUNT")
        point = score_lookup[(fold, "M0_SINGLE_POINT", variable, nominal)]
        raw = score_lookup[(fold, "E_RAW", variable, nominal)]
        for metric, prefix in (
            ("mean_crps_kg", "crps"),
            ("mean_interval_score_kg", "interval_score"),
        ):
            require(math.isfinite(float(row[metric])) and float(row[metric]) >= 0, "RISK_SCORE")
            require(
                close(row[prefix + "_delta_vs_M0_kg"], float(row[metric]) - float(point[metric])),
                "RISK_DELTA",
            )
            require(
                close(row[prefix + "_delta_vs_E_RAW_kg"], float(row[metric]) - float(raw[metric])),
                "RISK_DELTA_RAW",
            )
    return {
        "status": "PASS",
        "level": "PUBLIC_AGGREGATE_CLOSEOUT_REPLAY",
        "verified_files": len(listed),
        "formal_releases": 13,
        "extracted_sources": 8,
        "v0_11_only_sources_excluded": 22,
        "private_row_level_data_required": False,
        "model_training_executed": False,
        "parameter_search_executed": False,
        "new_backtest_executed": False,
        "original_rows_or_runner_independently_reproduced": False,
        "tag_or_release_created": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), sort_keys=True))
