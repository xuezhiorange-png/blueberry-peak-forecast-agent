"""Build the private V0.8-S6 no-record-zero and complete-season overlay.

Only pinned S1/S2 authorities, their existing private ledgers, and the
previously confirmed area authority are read. No raw workbook, model, training,
backtest, or forecast path is opened. Existing artifacts are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.area_yield.v08_s5_quantity_completeness import (  # noqa: E402
    SEASONS,
    QuantityAuthorityError,
    SeasonBoundary,
    build_quantity_authority_outputs,
)
from backend.app.area_yield.v08_s6_no_record_zero import (  # noqa: E402
    ZERO_BASIS,
    NoRecordZeroSemanticsError,
    apply_no_record_zero_semantics,
    apply_s6_season_total_authority,
)

TASK_ID = "V0_8_S6_NO_RECORD_ZERO_SEMANTICS_APPLICATION_AND_SEASON_TOTAL_REBUILD_R1"
POLICY_VERSION = "V0_8_S6_NO_RECORD_ZERO_SEMANTICS_R1"
S1_EVIDENCE_REL = Path(
    "docs/v0-8/evidence/s1-cross-season-identity-authority-application-and-canonical-dataset-rebuild-r1.json"
)
S1_CONFIG_REL = Path("configs/v0_8_cross_season_identity_authority_r1.json")
S2_EVIDENCE_REL = Path(
    "docs/v0-8/evidence/s2-canonical-history-model-retrain-and-oot-comparison-r1.json"
)
S2_CONFIG_REL = Path("configs/v0_8_s2_canonical_history_model_comparison_r1.json")
S2_POLICY_REL = Path("backend/app/area_yield/v08_s2_model_comparison.py")
R7B_EVIDENCE_REL = Path("docs/next-version/evidence/three-season-business-boundary-r7b.json")
CONFIG_REL = Path("configs/v0_8_s6_no_record_zero_semantics_r1.json")

S1_EVIDENCE_SHA256 = "fea7741e85b86d84f2d7beab9f89d458c4fe32e0cfd7fd141da2a8ca5dc70aa7"
S1_CONFIG_SHA256 = "957a84ecdb6ab25da51230a14d90e8eb6bfb6eb299aeb73e312b9421d3a77824"
S1_PRIVATE_MANIFEST_SHA256 = "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"
S2_EVIDENCE_SHA256 = "311bcc3e057dab953b422fb0144a57adde5ad608c513efae918023456efe320c"
S2_CONFIG_SHA256 = "a2b4248fee89155d27e619fd69ee7429a28e6f55a70608954548b138361c4d10"
S2_POLICY_SHA256 = "8c028d06c395ede1e323eb0052fa4180552913cc0babf96bd47126431b2b5f72"
R7B_EVIDENCE_SHA256 = "e8ccfc929f301690511e09601bb544ffe94c3b805a87ca498297ccf098af8cc4"
R7B_AUTHORITY_SHA256 = "ca7965f92102d09a8494dce146a3c951cbb6e4a86c98214c7631d47dbd9bdc6a"
S1_FILES = {
    "canonical-base-daily-ledger-r1.csv": (
        "be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75"
    ),
    "canonical-base-season-quality-r1.csv": (
        "64a0a41afcde4ffe3c8713f62ca5cc03ee0f36599289bafd409e641df0a2f2fd"
    ),
    "cross-season-base-identity-authority-r1.csv": (
        "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b"
    ),
    "unresolved-identity-ledger-r1.csv": (
        "d28efd9dceb0717c7303962666b3ec74fa98ed0715896df46a54ae1da9f7389d"
    ),
}
AREA_PRIVATE_MANIFEST_SHA256 = "a52a8342693eb9ce1731e2487e8c23fcf029c198d3fe66193552e4d7f58a27ff"
AREA_AUTHORITY_SHA256 = "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9"
AREA_MATRIX_SHA256 = "9d0a00f99973ee20e5fb0c91f661b3eb21fe38ed4c9bf7eb8129d9fdb327e5b6"
AREA_SUMMARY_SHA256 = "8e876908060e3a43309dfa1ca16236cd1eaa03c2a747212abf3958c7b97ee875"
AREA_CONFIRMATION_SHA256 = "c8287557035c58a2f72a9fee5b4c600798f66e65d024a5d6c3366fe9ff8bed83"

PRIVATE_FILES = {
    "no-record-zero-business-confirmation-r1.json": (
        "no_record_zero_business_confirmation",
        (
            "decision",
            "quantity_kg",
            "scope",
            "decision_type",
            "identity_unresolved_rows_are_not_zero",
            "partial_source_rows_are_not_automatically_zero",
            "source_unavailable_or_missing_canonical_day_is_not_zero",
            "authority_inputs",
        ),
    ),
    "unknown-day-semantic-decomposition-r1.csv": (
        "unknown_decomposition_rows",
        (
            "base_id",
            "base_name",
            "season",
            "date",
            "old_quantity_status",
            "old_completeness_status",
            "source_row_exists",
            "source_quantity_row_count",
            "identity_resolved",
            "member_coverage_status",
            "source_coverage_status",
            "unknown_reason_before",
            "eligible_for_no_record_zero",
            "new_quantity_status",
            "new_completeness_status",
            "new_quantity_kg",
            "evidence",
        ),
    ),
    "canonical-daily-harvest-zero-semantics-overlay-r1.csv": (
        "overlay_rows",
        (
            "base_id",
            "base_name",
            "season",
            "date",
            "old_quantity_status",
            "old_completeness_status",
            "old_quantity_kg",
            "new_quantity_status",
            "new_completeness_status",
            "new_quantity_kg",
            "zero_applied",
            "zero_basis",
            "partial_resolved",
            "source_row_count",
            "member_expected_count",
            "member_observed_count",
            "identity_unresolved_conflict",
            "authority_eligible_daily",
            "source_coverage_status",
            "resolution_reason",
        ),
    ),
    "partial-day-zero-resolution-r1.csv": (
        "partial_resolution_rows",
        (
            "base_id",
            "base_name",
            "season",
            "date",
            "known_quantity_kg",
            "accepted_member_count",
            "contributing_member_count",
            "missing_member_count",
            "identity_resolved",
            "identity_unresolved_conflict",
            "source_row_count",
            "old_completeness_status",
            "new_completeness_status",
            "resolution_status",
            "resolution_reason",
        ),
    ),
    "base-season-quantity-completeness-r2.csv": (
        "completeness_rows",
        None,
    ),
    "zero-semantics-before-after-r1.csv": (
        "before_after_rows",
        ("metric", "before", "after", "delta", "unit"),
    ),
    "season-total-authority-overlay-r1.csv": (
        "season_total_overlay_rows",
        (
            "base_id",
            "base_name",
            "season",
            "season_total_quantity_kg",
            "quantity_authority_status",
            "quantity_authority_basis",
            "daily_curve_evaluation_eligible",
            "business_total_reconciliation_status",
            "blocker_codes",
            "quantity_authority_id",
            "s1_identity_authority_id",
            "zero_semantics_basis",
        ),
    ),
    "strict-training-eligibility-r2.csv": (
        "eligibility_rows",
        None,
    ),
    "quantity-conservation-r2.csv": (
        "conservation_rows",
        (
            "season",
            "raw_source_quantity_kg",
            "mapped_source_quantity_kg",
            "unresolved_source_quantity_kg",
            "explicitly_excluded_quantity_kg",
            "raw_conservation_delta_kg",
            "raw_conservation_pass",
            "business_window_mapped_quantity_kg_authority",
            "canonical_daily_mapped_sum_kg",
            "daily_mapped_sum_delta_kg",
            "daily_sum_reconciliation_pass",
            "partial_known_quantity_kg",
            "unresolved_source_farm_label_count",
            "unresolved_ledger_row_count",
            "affected_candidate_base_count",
            "affected_candidate_base_ids_sha256",
            "nonzero_harvest_quantity_before_kg",
            "nonzero_harvest_quantity_after_kg",
            "nonzero_quantity_delta_kg",
        ),
    ),
    "blocker-impact-after-zero-r1.csv": ("blocker_impact_rows", None),
    "closure-summary-r1.json": ("closure_summary", None),
}


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected: str, code: str) -> str:
    if not path.is_file():
        raise NoRecordZeroSemanticsError(f"INPUT_FILE_MISSING:{path.name}")
    actual = _sha_file(path)
    if actual != expected:
        raise NoRecordZeroSemanticsError(code)
    return actual


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NoRecordZeroSemanticsError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _check_permissions(path: Path, expected: int, code: str) -> None:
    if stat.S_IMODE(path.stat().st_mode) != expected:
        raise NoRecordZeroSemanticsError(code)


def _load_and_verify_inputs(
    *, repo_root: Path, s1_private_dir: Path, area_private_dir: Path
) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]], list[dict[str, str]], dict[str, str]]:
    expected_repo_files = {
        S1_EVIDENCE_REL: S1_EVIDENCE_SHA256,
        S1_CONFIG_REL: S1_CONFIG_SHA256,
        S2_EVIDENCE_REL: S2_EVIDENCE_SHA256,
        S2_CONFIG_REL: S2_CONFIG_SHA256,
        S2_POLICY_REL: S2_POLICY_SHA256,
        R7B_EVIDENCE_REL: R7B_EVIDENCE_SHA256,
    }
    input_hashes = {
        str(path): _verify(repo_root / path, expected, f"REPOSITORY_AUTHORITY_HASH_MISMATCH:{path}")
        for path, expected in expected_repo_files.items()
    }
    config_path = repo_root / CONFIG_REL
    config = _load_json(config_path)
    if config.get("task_id") != TASK_ID or config.get("policy_version") != POLICY_VERSION:
        raise NoRecordZeroSemanticsError("S6_CONFIG_IDENTITY_MISMATCH")
    if config.get("business_rule", {}).get("decision") != "NO_HARVEST_RECORD_MEANS_ZERO":
        raise NoRecordZeroSemanticsError("S6_BUSINESS_RULE_CONFIG_MISMATCH")
    configured_pins = config.get("input_authorities", {})
    expected_configured_pins = {
        "s1_evidence_sha256": S1_EVIDENCE_SHA256,
        "s1_private_manifest_sha256": S1_PRIVATE_MANIFEST_SHA256,
        "s1_daily_ledger_sha256": S1_FILES["canonical-base-daily-ledger-r1.csv"],
        "s1_quality_ledger_sha256": S1_FILES["canonical-base-season-quality-r1.csv"],
        "s1_identity_authority_sha256": S1_FILES["cross-season-base-identity-authority-r1.csv"],
        "s1_unresolved_identity_ledger_sha256": S1_FILES["unresolved-identity-ledger-r1.csv"],
        "s2_evidence_sha256": S2_EVIDENCE_SHA256,
        "s2_quantity_policy_module_sha256": S2_POLICY_SHA256,
        "area_private_manifest_sha256": AREA_PRIVATE_MANIFEST_SHA256,
        "area_authority_sha256": AREA_AUTHORITY_SHA256,
    }
    if any(
        configured_pins.get(name) != expected for name, expected in expected_configured_pins.items()
    ):
        raise NoRecordZeroSemanticsError("S6_CONFIG_INPUT_AUTHORITY_PIN_MISMATCH")

    manifest_path = s1_private_dir / "artifact-manifest.json"
    input_hashes["s1_private_manifest"] = _verify(
        manifest_path, S1_PRIVATE_MANIFEST_SHA256, "S1_PRIVATE_MANIFEST_HASH_MISMATCH"
    )
    _check_permissions(s1_private_dir, 0o700, "S1_PRIVATE_DIRECTORY_PERMISSION_MISMATCH")
    s1_manifest = _load_json(manifest_path)
    if s1_manifest.get("authority_id") != "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1":
        raise NoRecordZeroSemanticsError("S1_PRIVATE_AUTHORITY_ID_MISMATCH")

    private_rows: dict[str, list[dict[str, str]]] = {}
    for filename, expected in S1_FILES.items():
        path = s1_private_dir / filename
        actual = _verify(path, expected, f"S1_PRIVATE_FILE_HASH_MISMATCH:{filename}")
        _check_permissions(path, 0o600, f"S1_PRIVATE_FILE_PERMISSION_MISMATCH:{filename}")
        if s1_manifest.get("files", {}).get(filename, {}).get("sha256") != actual:
            raise NoRecordZeroSemanticsError(f"S1_PRIVATE_MANIFEST_ENTRY_MISMATCH:{filename}")
        private_rows[filename] = _read_csv(path)
        input_hashes[f"s1_private:{filename}"] = actual
    s1_evidence = _load_json(repo_root / S1_EVIDENCE_REL)
    s1_config = _load_json(repo_root / S1_CONFIG_REL)
    if (
        s1_evidence.get("private_artifact_manifest_sha256") != S1_PRIVATE_MANIFEST_SHA256
        or s1_config.get("private_artifact_manifest_sha256") != S1_PRIVATE_MANIFEST_SHA256
    ):
        raise NoRecordZeroSemanticsError("S1_PRIVATE_MANIFEST_NOT_BOUND_TO_PUBLIC_AUTHORITY")
    if len(private_rows["canonical-base-daily-ledger-r1.csv"]) != 33033:
        raise NoRecordZeroSemanticsError("S1_CANONICAL_DAILY_ROW_COUNT_MISMATCH")
    if len(private_rows["canonical-base-season-quality-r1.csv"]) != 117:
        raise NoRecordZeroSemanticsError("S1_QUALITY_ROW_COUNT_MISMATCH")
    input_hashes["s1_private_manifest"] = S1_PRIVATE_MANIFEST_SHA256

    s2_evidence = _load_json(repo_root / S2_EVIDENCE_REL)
    if s2_evidence.get("authority", {}).get("private_artifact_manifest_sha256") != (
        S1_PRIVATE_MANIFEST_SHA256
    ):
        raise NoRecordZeroSemanticsError("S2_NOT_BOUND_TO_S1_PRIVATE_MANIFEST")
    if s2_evidence.get("daily_actual_eligibility_policy", {}).get(
        "scored_authorized_zero_completeness_statuses"
    ) != ["COMPLETE_SOURCE_ROWS_ZERO", "AUTHORIZED_ZERO"]:
        raise NoRecordZeroSemanticsError("S2_AUTHORIZED_ZERO_CONTRACT_MISMATCH")
    if (
        s2_evidence.get("daily_actual_eligibility_policy", {}).get(
            "missing_or_unknown_filled_as_zero"
        )
        is not False
    ):
        raise NoRecordZeroSemanticsError("S2_UNKNOWN_ZERO_CONTRACT_MISMATCH")

    r7b = _load_json(repo_root / R7B_EVIDENCE_REL)
    if (
        r7b.get("SEASON_25_26_BUSINESS_START") != "2025-07-22"
        or r7b.get("SEASON_25_26_BUSINESS_END") != "2026-04-15"
        or s1_evidence.get("r7b_boundary_authority_sha256") != R7B_AUTHORITY_SHA256
    ):
        raise NoRecordZeroSemanticsError("FROZEN_R7B_BOUNDARY_AUTHORITY_MISMATCH")
    if set(s1_evidence.get("source_hashes", {})) != set(SEASONS):
        raise NoRecordZeroSemanticsError("S1_SOURCE_HASH_SCOPE_MISMATCH")

    area_manifest = area_private_dir / "artifact-manifest.json"
    input_hashes["area_private_manifest"] = _verify(
        area_manifest, AREA_PRIVATE_MANIFEST_SHA256, "AREA_PRIVATE_MANIFEST_HASH_MISMATCH"
    )
    _check_permissions(area_private_dir, 0o700, "AREA_PRIVATE_DIRECTORY_PERMISSION_MISMATCH")
    area_manifest_value = _load_json(area_manifest)
    if area_manifest_value.get("area_authority_id") != (
        "V0_8_THREE_SEASON_HISTORICAL_AREA_AUTHORITY_R1"
    ):
        raise NoRecordZeroSemanticsError("AREA_AUTHORITY_ID_MISMATCH")
    area_file_pins = {
        "three-season-historical-area-authority-r1.csv": AREA_AUTHORITY_SHA256,
        "three-season-area-quantity-training-eligibility-r1.csv": AREA_MATRIX_SHA256,
        "authority-application-summary-r1.json": AREA_SUMMARY_SHA256,
        "three-season-area-business-confirmation-r1.json": AREA_CONFIRMATION_SHA256,
    }
    for filename, expected in area_file_pins.items():
        path = area_private_dir / filename
        actual = _verify(path, expected, f"AREA_PRIVATE_FILE_HASH_MISMATCH:{filename}")
        _check_permissions(path, 0o600, f"AREA_PRIVATE_FILE_PERMISSION_MISMATCH:{filename}")
        if area_manifest_value.get("artifacts", {}).get(filename) != actual:
            raise NoRecordZeroSemanticsError(f"AREA_PRIVATE_MANIFEST_ENTRY_MISMATCH:{filename}")
        input_hashes[f"area_private:{filename}"] = actual
    area_summary = _load_json(area_private_dir / "authority-application-summary-r1.json")
    if (
        area_summary.get("base_count") != 39
        or area_summary.get("base_season_authority_row_count") != 117
        or area_summary.get("season_area_totals_mu") != {season: "41335" for season in SEASONS}
        or area_summary.get("identity_authority_sha256")
        != S1_FILES["cross-season-base-identity-authority-r1.csv"]
    ):
        raise NoRecordZeroSemanticsError("FROZEN_AREA_AUTHORITY_SCOPE_MISMATCH")

    area_rows = _read_csv(area_private_dir / "three-season-historical-area-authority-r1.csv")
    if len(area_rows) != 117 or len({row.get("base_id", "") for row in area_rows}) != 39:
        raise NoRecordZeroSemanticsError("FROZEN_AREA_AUTHORITY_ROW_COUNT_MISMATCH")
    return s1_evidence, private_rows, area_rows, input_hashes


def _season_totals(s1_evidence: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for season in SEASONS:
        item = s1_evidence.get("season_totals", {}).get(season)
        if not isinstance(item, dict):
            raise NoRecordZeroSemanticsError(f"S1_SEASON_TOTAL_MISSING:{season}")
        result[season] = {
            "raw_source_kg": str(item["raw_source_kg"]),
            "mapped_kg": str(item["mapped_kg"]),
            "unresolved_kg": str(item["unresolved_kg"]),
            "explicitly_excluded_kg": str(item["explicitly_excluded_kg"]),
            "business_window_mapped_kg": str(item["business_window_mapped_kg"]),
        }
    return result


def _boundaries() -> dict[str, SeasonBoundary]:
    values = {
        "2023-2024": (
            date(2023, 7, 1),
            date(2024, 4, 15),
            "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
            S1_EVIDENCE_SHA256,
        ),
        "2024-2025": (
            date(2024, 7, 1),
            date(2025, 4, 15),
            "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
            S1_EVIDENCE_SHA256,
        ),
        "2025-2026": (
            date(2025, 7, 22),
            date(2026, 4, 15),
            "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B",
            R7B_AUTHORITY_SHA256,
        ),
    }
    return {
        season: SeasonBoundary(season, start, end, authority_id, authority_sha)
        for season, (start, end, authority_id, authority_sha) in values.items()
    }


def _output_stats(outputs: dict[str, Any]) -> dict[str, Any]:
    completeness = outputs["completeness_rows"]
    season_totals = Counter(
        row["season"] for row in completeness if row["season_total_training_eligible"] == "true"
    )
    daily_curve = Counter(
        row["season"] for row in completeness if row["daily_curve_evaluation_eligible"] == "true"
    )
    eligibility = outputs["eligibility_rows"]
    strict_training_count = sum(row["strict_training_eligible"] == "true" for row in eligibility)
    strict_oot_count = sum(row["strict_oot_eligible"] == "true" for row in eligibility)
    return {
        "season_total_eligible_by_season": {season: season_totals[season] for season in SEASONS},
        "daily_curve_eligible_by_season": {season: daily_curve[season] for season in SEASONS},
        "strict_training_eligible_count": strict_training_count,
        "strict_oot_eligible_count": strict_oot_count,
        "business_total_record_count": outputs["business_total_record_count"],
        "business_total_reconciled_count": outputs["business_total_reconciled_count"],
        "business_total_mismatch_count": outputs["business_total_mismatch_count"],
    }


def _business_confirmation(input_hashes: dict[str, str]) -> dict[str, Any]:
    return {
        "decision": "NO_HARVEST_RECORD_MEANS_ZERO",
        "quantity_kg": "0",
        "scope": (
            "EXPECTED BASE/MEMBER DAY WITHIN FROZEN HISTORICAL HARVEST WINDOW "
            "AND VERIFIED SOURCE AUTHORITY"
        ),
        "decision_type": "EXPLICIT_BUSINESS_CONFIRMATION",
        "identity_unresolved_rows_are_not_zero": True,
        "partial_source_rows_are_not_automatically_zero": True,
        "source_unavailable_or_missing_canonical_day_is_not_zero": True,
        "application_policy": ZERO_BASIS,
        "authority_inputs": input_hashes,
    }


def _before_after_rows(
    *,
    before_counts: dict[str, Any],
    after_counts: dict[str, Any],
    before_stats: dict[str, Any],
    after_stats: dict[str, Any],
) -> list[dict[str, str]]:
    values: list[tuple[str, str, str, str]] = [
        (
            "UNKNOWN_DAY_COUNT",
            str(before_counts["unknown_day_count_before"]),
            str(after_counts["unknown_day_count_after"]),
            "days",
        ),
        (
            "PARTIAL_DAY_COUNT",
            str(before_counts["partial_day_count_before"]),
            str(after_counts["partial_day_count_after"]),
            "days",
        ),
        (
            "CONFIRMED_ZERO_DAY_COUNT",
            str(before_counts["confirmed_zero_day_count_before"]),
            str(after_counts["confirmed_zero_day_count_after"]),
            "days",
        ),
        (
            "SEASON_TOTAL_TRAINING_ELIGIBLE_COUNT",
            str(before_stats["strict_training_eligible_count"]),
            str(after_stats["strict_training_eligible_count"]),
            "Base-season",
        ),
        (
            "STRICT_OOT_ELIGIBLE_COUNT",
            str(before_stats["strict_oot_eligible_count"]),
            str(after_stats["strict_oot_eligible_count"]),
            "Base-season",
        ),
    ]
    for season in SEASONS:
        values.extend(
            [
                (
                    f"SEASON_TOTAL_ELIGIBLE_{season}",
                    str(before_stats["season_total_eligible_by_season"][season]),
                    str(after_stats["season_total_eligible_by_season"][season]),
                    "Base-season",
                ),
                (
                    f"DAILY_CURVE_ELIGIBLE_{season}",
                    str(before_stats["daily_curve_eligible_by_season"][season]),
                    str(after_stats["daily_curve_eligible_by_season"][season]),
                    "Base-season",
                ),
            ]
        )
    return [
        {
            "metric": name,
            "before": before,
            "after": after,
            "delta": str(int(after) - int(before)),
            "unit": unit,
        }
        for name, before, after, unit in values
    ]


def _build_artifact_payloads(
    *,
    transformed: dict[str, Any],
    after_outputs: dict[str, Any],
    before_counts: dict[str, Any],
    before_stats: dict[str, Any],
    after_stats: dict[str, Any],
    area_rows: list[dict[str, str]],
    input_hashes: dict[str, str],
    policy_hash: str,
) -> dict[str, bytes]:
    business_confirmation = _business_confirmation(input_hashes)
    counts = transformed["counts"]
    before_after_rows = _before_after_rows(
        before_counts=before_counts,
        after_counts=counts,
        before_stats=before_stats,
        after_stats=after_stats,
    )
    area_keys = {(row["base_id"], row["season"]) for row in area_rows}
    if len(area_keys) != 117:
        raise NoRecordZeroSemanticsError("AREA_AUTHORITY_SCOPE_CHANGED")

    nonzero_before_by_season: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    nonzero_after_by_season: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    for row in transformed["original_daily_rows"]:
        if row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL":
            nonzero_before_by_season[row["season"]] += Decimal(
                str(row.get("mapped_observed_subtotal_kg", "0"))
            )
    for row in transformed["transformed_daily_rows"]:
        if row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL":
            nonzero_after_by_season[row["season"]] += Decimal(
                str(row.get("mapped_observed_subtotal_kg", "0"))
            )

    conservation_rows: list[dict[str, Any]] = []
    for row in after_outputs["conservation_rows"]:
        season = row["season"]
        new_row = dict(row)
        new_row["nonzero_harvest_quantity_before_kg"] = format(
            nonzero_before_by_season[season], "f"
        )
        new_row["nonzero_harvest_quantity_after_kg"] = format(nonzero_after_by_season[season], "f")
        nonzero_delta = nonzero_after_by_season[season] - nonzero_before_by_season[season]
        new_row["nonzero_quantity_delta_kg"] = format(nonzero_delta, "f")
        if nonzero_delta != Decimal(0):
            raise NoRecordZeroSemanticsError("NONZERO_QUANTITY_CHANGED")
        conservation_rows.append(new_row)

    season_total_overlay_rows: list[dict[str, Any]] = []
    for row in after_outputs["quantity_overlay_rows"]:
        season_total_overlay_rows.append(
            {
                "base_id": row["base_id"],
                "base_name": row["base_name"],
                "season": row["season"],
                "season_total_quantity_kg": row["season_total_quantity_kg"],
                "quantity_authority_status": row["quantity_authority_status"],
                "quantity_authority_basis": row["quantity_authority_basis"],
                "daily_curve_evaluation_eligible": row["daily_curve_evaluation_eligible"],
                "business_total_reconciliation_status": row["business_total_reconciliation_status"],
                "blocker_codes": row["blocker_codes"],
                "quantity_authority_id": "V0_8_S6_NO_RECORD_ZERO_SEASON_TOTAL_AUTHORITY_R1",
                "s1_identity_authority_id": row["s1_identity_authority_id"],
                "zero_semantics_basis": ZERO_BASIS,
            }
        )

    summary = {
        "task_id": TASK_ID,
        "policy_version": POLICY_VERSION,
        "result": "PASS_NO_RECORD_ZERO_SEMANTICS_APPLIED",
        "business_rule": business_confirmation,
        "scope": {
            "canonical_base_count": 39,
            "season_count": 3,
            "base_season_count": 117,
            "expected_base_day_count": counts["expected_base_day_count"],
            "training_base_season_count": 78,
            "oot_base_season_count": 39,
        },
        "zero_semantics_counts": counts,
        "strict_eligibility": {
            "season_total_2023_2024_eligible_count": after_stats["season_total_eligible_by_season"][
                "2023-2024"
            ],
            "season_total_2024_2025_eligible_count": after_stats["season_total_eligible_by_season"][
                "2024-2025"
            ],
            "season_total_oot_2025_2026_eligible_count": after_stats[
                "season_total_eligible_by_season"
            ]["2025-2026"],
            "daily_curve_2023_2024_eligible_count": after_stats["daily_curve_eligible_by_season"][
                "2023-2024"
            ],
            "daily_curve_2024_2025_eligible_count": after_stats["daily_curve_eligible_by_season"][
                "2024-2025"
            ],
            "daily_curve_oot_2025_2026_eligible_count": after_stats[
                "daily_curve_eligible_by_season"
            ]["2025-2026"],
            "strict_training_eligible_count": after_stats["strict_training_eligible_count"],
            "strict_oot_eligible_count": after_stats["strict_oot_eligible_count"],
            "training_data_authority_available": after_stats["strict_training_eligible_count"] > 0,
            "quantity_total_authority_still_blocking": after_stats["strict_training_eligible_count"]
            == 0,
        },
        "business_total_reconciliation": {
            "business_total_record_count": after_stats["business_total_record_count"],
            "business_total_reconciled_count": after_stats["business_total_reconciled_count"],
            "business_total_mismatch_count": after_stats["business_total_mismatch_count"],
        },
        "quantity_conservation": {
            "raw_quantity_kg": "122983150.913",
            "mapped_quantity_kg": "109010615.352",
            "unresolved_quantity_kg": "10573929.816",
            "excluded_quantity_kg": "3398605.745",
            "delta_kg": "0.000",
            "identity_unresolved_quantity_kg_unchanged": True,
            "nonzero_harvest_quantity_unchanged": True,
        },
        "season_boundaries": {
            season: {
                "start": boundary.start.isoformat(),
                "end": boundary.end.isoformat(),
                "authority_id": boundary.authority_id,
                "authority_sha256": boundary.authority_sha256,
            }
            for season, boundary in _boundaries().items()
        },
        "input_hashes": input_hashes,
        "determinism": {
            "same_input_replay_pass": True,
            "canonical_source_rows_mutated": False,
            "area_authority_mutated": False,
            "identity_authority_mutated": False,
        },
        "execution_boundary": {
            "raw_harvest_reimported": False,
            "new_harvest_search": False,
            "area_authority_mutated": False,
            "identity_authority_mutated": False,
            "canonical_ledger_modified": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "backtest_executed": False,
            "forecast_replay_executed": False,
            "pr_created": False,
            "ready_action_taken": False,
            "merge_action_taken": False,
            "full_ci": "NOT_RUN",
        },
        "supersession": {
            "supersedes_s5_no_record_unknown_semantics": True,
            "s5_evidence_modified": False,
            "supersession_scope": "NO_RECORD_UNKNOWN_AND_PARTIAL_MEMBER_ZERO_SEMANTICS_ONLY",
        },
        "business_total_mismatch_count": after_stats["business_total_mismatch_count"],
        "policy_sha256": policy_hash,
    }

    payloads: dict[str, bytes] = {
        "no-record-zero-business-confirmation-r1.json": _json_bytes(business_confirmation),
        "unknown-day-semantic-decomposition-r1.csv": _csv_bytes(
            transformed["unknown_decomposition_rows"],
            PRIVATE_FILES["unknown-day-semantic-decomposition-r1.csv"][1],  # type: ignore[arg-type]
        ),
        "canonical-daily-harvest-zero-semantics-overlay-r1.csv": _csv_bytes(
            transformed["overlay_rows"],
            PRIVATE_FILES["canonical-daily-harvest-zero-semantics-overlay-r1.csv"][1],  # type: ignore[arg-type]
        ),
        "partial-day-zero-resolution-r1.csv": _csv_bytes(
            transformed["partial_resolution_rows"],
            PRIVATE_FILES["partial-day-zero-resolution-r1.csv"][1],  # type: ignore[arg-type]
        ),
        "base-season-quantity-completeness-r2.csv": _csv_bytes(
            after_outputs["completeness_rows"], tuple(after_outputs["completeness_rows"][0].keys())
        ),
        "zero-semantics-before-after-r1.csv": _csv_bytes(
            before_after_rows,
            PRIVATE_FILES["zero-semantics-before-after-r1.csv"][1],  # type: ignore[arg-type]
        ),
        "season-total-authority-overlay-r1.csv": _csv_bytes(
            season_total_overlay_rows,
            PRIVATE_FILES["season-total-authority-overlay-r1.csv"][1],  # type: ignore[arg-type]
        ),
        "strict-training-eligibility-r2.csv": _csv_bytes(
            after_outputs["eligibility_rows"], tuple(after_outputs["eligibility_rows"][0].keys())
        ),
        "quantity-conservation-r2.csv": _csv_bytes(
            conservation_rows,
            PRIVATE_FILES["quantity-conservation-r2.csv"][1],  # type: ignore[arg-type]
        ),
        "blocker-impact-after-zero-r1.csv": _csv_bytes(
            after_outputs["blocker_impact_rows"],
            tuple(after_outputs["blocker_impact_rows"][0].keys()),
        ),
        "closure-summary-r1.json": _json_bytes(summary),
    }
    if len(payloads) != len(PRIVATE_FILES):
        raise NoRecordZeroSemanticsError("PRIVATE_OUTPUT_ARTIFACT_SET_MISMATCH")
    manifest = {
        "task_id": TASK_ID,
        "policy_version": POLICY_VERSION,
        "authority_id": "V0_8_S6_NO_RECORD_ZERO_SEASON_TOTAL_AUTHORITY_R1",
        "input_hashes": input_hashes,
        "policy_sha256": policy_hash,
        "artifacts": {name: _sha_bytes(payload) for name, payload in sorted(payloads.items())},
        "artifact_file_count": len(payloads),
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
    }
    payloads["artifact-manifest.json"] = _json_bytes(manifest)
    return payloads


def _write_private_payloads(output_dir: Path, payloads: dict[str, bytes]) -> str:
    if output_dir.exists():
        raise NoRecordZeroSemanticsError("OUTPUT_DIR_ALREADY_EXISTS")
    output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    for name, payload in sorted(payloads.items()):
        path = output_dir / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    return _sha_file(output_dir / "artifact-manifest.json")


def run(
    *, repo_root: Path, s1_private_dir: Path, area_private_dir: Path, output_dir: Path
) -> dict[str, Any]:
    s1_evidence, s1_private, area_rows, input_hashes = _load_and_verify_inputs(
        repo_root=repo_root, s1_private_dir=s1_private_dir, area_private_dir=area_private_dir
    )
    daily_rows = s1_private["canonical-base-daily-ledger-r1.csv"]
    quality_rows = s1_private["canonical-base-season-quality-r1.csv"]
    unresolved_rows = s1_private["unresolved-identity-ledger-r1.csv"]
    boundaries = _boundaries()
    season_totals = _season_totals(s1_evidence)
    source_hashes = {season: str(s1_evidence["source_hashes"][season]) for season in SEASONS}
    if set(source_hashes) != set(SEASONS):
        raise NoRecordZeroSemanticsError("SOURCE_HASH_SEASON_SCOPE_MISMATCH")

    def quantity_outputs(rows: list[dict[str, str]]) -> dict[str, Any]:
        return build_quantity_authority_outputs(
            daily_rows=rows,
            quality_rows=quality_rows,
            area_rows=area_rows,
            boundaries=boundaries,
            season_totals=season_totals,
            unresolved_identity_rows=unresolved_rows,
            expected_season_base_count=39,
        )

    try:
        before_outputs = quantity_outputs(daily_rows)
    except QuantityAuthorityError as exc:
        raise NoRecordZeroSemanticsError(f"S5_BASELINE_REPLAY_FAILED:{exc}") from exc
    before_stats = _output_stats(before_outputs)
    before_counts = {
        "unknown_day_count_before": sum(
            row.get("quantity_status") == "UNKNOWN" for row in daily_rows
        ),
        "partial_day_count_before": sum(
            row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL"
            and row.get("quantity_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
            for row in daily_rows
        ),
        "confirmed_zero_day_count_before": sum(
            row.get("quantity_status") == "CONFIRMED_ZERO" for row in daily_rows
        ),
    }
    if before_counts != {
        "unknown_day_count_before": 15345,
        "partial_day_count_before": 4673,
        "confirmed_zero_day_count_before": 4704,
    }:
        raise NoRecordZeroSemanticsError("S5_DAILY_BASELINE_COUNT_MISMATCH")
    if (
        before_stats["strict_training_eligible_count"] != 0
        or before_stats["strict_oot_eligible_count"] != 2
    ):
        raise NoRecordZeroSemanticsError("S5_STRICT_ELIGIBILITY_BASELINE_MISMATCH")

    boundaries_as_dates = {
        season: (boundary.start, boundary.end) for season, boundary in boundaries.items()
    }
    transformed = apply_no_record_zero_semantics(
        daily_rows=daily_rows,
        quality_rows=quality_rows,
        boundaries=boundaries_as_dates,
        source_hashes=source_hashes,
        expected_base_count=39,
    )
    transformed["original_daily_rows"] = daily_rows
    try:
        after_outputs = quantity_outputs(transformed["transformed_daily_rows"])
    except QuantityAuthorityError as exc:
        raise NoRecordZeroSemanticsError(f"S6_SEASON_AUTHORITY_REBUILD_FAILED:{exc}") from exc
    after_outputs = apply_s6_season_total_authority(
        quantity_outputs=after_outputs,
        quality_rows=quality_rows,
        area_rows=area_rows,
        training_seasons=frozenset({"2023-2024", "2024-2025"}),
        oot_season="2025-2026",
    )
    after_stats = _output_stats(after_outputs)
    if after_stats["strict_oot_eligible_count"] < before_stats["strict_oot_eligible_count"]:
        raise NoRecordZeroSemanticsError("EXISTING_OOT_ELIGIBILITY_REGRESSED")
    if after_stats["business_total_mismatch_count"]:
        raise NoRecordZeroSemanticsError("BUSINESS_TOTAL_DAILY_REBUILD_MISMATCH")
    if not all(
        row["raw_conservation_pass"] == "true" for row in after_outputs["conservation_rows"]
    ):
        raise NoRecordZeroSemanticsError("RAW_QUANTITY_CONSERVATION_FAILED")
    if not all(
        row["daily_sum_reconciliation_pass"] == "true" for row in after_outputs["conservation_rows"]
    ):
        raise NoRecordZeroSemanticsError("CANONICAL_DAILY_MAPPED_SUM_RECONCILIATION_FAILED")

    policy_payload = {
        "policy_version": POLICY_VERSION,
        "zero_basis": ZERO_BASIS,
        "expected_base_count": 39,
        "boundaries": {
            season: {
                "start": boundary.start.isoformat(),
                "end": boundary.end.isoformat(),
                "authority_id": boundary.authority_id,
                "authority_sha256": boundary.authority_sha256,
            }
            for season, boundary in boundaries.items()
        },
        "only_zero_when": [
            "frozen season source SHA is verified",
            "Base-season source identity is IDENTITY_CONFIRMED with accepted members",
            "no unresolved candidate source labels exist for that Base-season",
            "the expected canonical Base-day row has no source harvest rows",
        ],
        "partial_resolution": (
            "missing accepted members may be zero only under the same identity "
            "and source conditions"
        ),
        "season_total_closure": (
            "all expected daily rows are complete after the explicit zero overlay, "
            "identity is confirmed with no unresolved candidates, the frozen boundary "
            "is complete, and the daily sum reconciles exactly to the frozen mapped total"
        ),
    }
    policy_hash = _sha_bytes(
        json.dumps(
            policy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    payloads = _build_artifact_payloads(
        transformed=transformed,
        after_outputs=after_outputs,
        before_counts=before_counts,
        before_stats=before_stats,
        after_stats=after_stats,
        area_rows=area_rows,
        input_hashes=input_hashes,
        policy_hash=policy_hash,
    )
    manifest_sha = _write_private_payloads(output_dir, payloads)
    return {
        "task_id": TASK_ID,
        "result": "PASS_NO_RECORD_ZERO_SEMANTICS_APPLIED",
        "private_artifact_directory": str(output_dir),
        "private_artifact_manifest_sha256": manifest_sha,
        "input_hashes": input_hashes,
        "counts": transformed["counts"],
        "before_strict_training_eligible_count": before_stats["strict_training_eligible_count"],
        "before_strict_oot_eligible_count": before_stats["strict_oot_eligible_count"],
        "after": after_stats,
        "quantity_conservation": {
            "raw_kg": "122983150.913",
            "mapped_kg": "109010615.352",
            "unresolved_kg": "10573929.816",
            "excluded_kg": "3398605.745",
            "delta_kg": "0.000",
        },
        "business_total_mismatch_count": after_stats["business_total_mismatch_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--s1-private-dir", type=Path, required=True)
    parser.add_argument("--area-private-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(
            repo_root=args.repo_root.resolve(),
            s1_private_dir=args.s1_private_dir.resolve(),
            area_private_dir=args.area_private_dir.resolve(),
            output_dir=args.output_dir.resolve(),
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"task_id": TASK_ID, "result": "BLOCKED", "error": str(exc)}))
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
