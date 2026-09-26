"""Create a private V0.8-S5 quantity-completeness and eligibility overlay.

Only pinned S1/S2 authority and the already-confirmed S4 area snapshot are
read. No raw harvest workbook, model, prediction, fitting, or backtest path is
opened by this runner.
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

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# noqa comments preserve direct-script execution after adding the repository root.
from backend.app.area_yield.data import digest  # noqa: E402
from backend.app.area_yield.v08_s5_quantity_completeness import (  # noqa: E402
    OOT_SEASON,
    SEASONS,
    TRAINING_SEASONS,
    QuantityAuthorityError,
    SeasonBoundary,
    build_quantity_authority_outputs,
    decimal_text,
)

TASK_ID = "V0_8_S5_EXISTING_HISTORICAL_QUANTITY_COMPLETE_SEASON_AUTHORITY_CLOSURE_R1"
S1_EVIDENCE_REL = Path(
    "docs/v0-8/evidence/s1-cross-season-identity-authority-application-and-canonical-dataset-rebuild-r1.json"
)
S1_CONFIG_REL = Path("configs/v0_8_cross_season_identity_authority_r1.json")
S2_EVIDENCE_REL = Path(
    "docs/v0-8/evidence/s2-canonical-history-model-retrain-and-oot-comparison-r1.json"
)
S2_CONFIG_REL = Path("configs/v0_8_s2_canonical_history_model_comparison_r1.json")
S2_POLICY_MODULE_REL = Path("backend/app/area_yield/v08_s2_model_comparison.py")
R7B_EVIDENCE_REL = Path("docs/next-version/evidence/three-season-business-boundary-r7b.json")

EXPECTED_S1_EVIDENCE_SHA256 = "fea7741e85b86d84f2d7beab9f89d458c4fe32e0cfd7fd141da2a8ca5dc70aa7"
EXPECTED_S1_CONFIG_SHA256 = "957a84ecdb6ab25da51230a14d90e8eb6bfb6eb299aeb73e312b9421d3a77824"
EXPECTED_S1_MANIFEST_SHA256 = "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"
EXPECTED_S2_EVIDENCE_SHA256 = "311bcc3e057dab953b422fb0144a57adde5ad608c513efae918023456efe320c"
EXPECTED_S2_CONFIG_SHA256 = "a2b4248fee89155d27e619fd69ee7429a28e6f55a70608954548b138361c4d10"
EXPECTED_S2_POLICY_MODULE_SHA256 = (
    "8c028d06c395ede1e323eb0052fa4180552913cc0babf96bd47126431b2b5f72"
)
EXPECTED_R7B_EVIDENCE_SHA256 = "e8ccfc929f301690511e09601bb544ffe94c3b805a87ca498297ccf098af8cc4"
EXPECTED_R7B_AUTHORITY_SHA256 = "ca7965f92102d09a8494dce146a3c951cbb6e4a86c98214c7631d47dbd9bdc6a"
EXPECTED_S1_FILES = {
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
EXPECTED_AREA_MANIFEST_SHA256 = "a52a8342693eb9ce1731e2487e8c23fcf029c198d3fe66193552e4d7f58a27ff"
EXPECTED_AREA_AUTHORITY_SHA256 = "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9"
EXPECTED_PRIOR_AREA_QUANTITY_MATRIX_SHA256 = (
    "9d0a00f99973ee20e5fb0c91f661b3eb21fe38ed4c9bf7eb8129d9fdb327e5b6"
)
EXPECTED_AREA_SUMMARY_SHA256 = "8e876908060e3a43309dfa1ca16236cd1eaa03c2a747212abf3958c7b97ee875"
EXPECTED_AREA_CONFIRMATION_SHA256 = (
    "c8287557035c58a2f72a9fee5b4c600798f66e65d024a5d6c3366fe9ff8bed83"
)
EXPECTED_QUANTITY_AUTHORITY_ID = "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
EXPECTED_AREA_AUTHORITY_ID = "V0_8_THREE_SEASON_HISTORICAL_AREA_AUTHORITY_R1"

BOUNDARIES = {
    "2023-2024": SeasonBoundary(
        season="2023-2024",
        start=date(2023, 7, 1),
        end=date(2024, 4, 15),
        authority_id="FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
        authority_sha256=EXPECTED_S1_EVIDENCE_SHA256,
    ),
    "2024-2025": SeasonBoundary(
        season="2024-2025",
        start=date(2024, 7, 1),
        end=date(2025, 4, 15),
        authority_id="FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
        authority_sha256=EXPECTED_S1_EVIDENCE_SHA256,
    ),
    "2025-2026": SeasonBoundary(
        season="2025-2026",
        start=date(2025, 7, 22),
        end=date(2026, 4, 15),
        authority_id="USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B",
        authority_sha256=EXPECTED_R7B_AUTHORITY_SHA256,
    ),
}

CSV_FIELDS: dict[str, tuple[str, ...]] = {
    "base-season-quantity-completeness-r1.csv": (
        "base_id",
        "base_name",
        "season",
        "season_start_date",
        "season_end_date",
        "season_boundary_authority",
        "season_boundary_authority_sha256",
        "expected_calendar_day_count",
        "observed_or_authorized_day_count",
        "complete_mapped_member_day_count",
        "partial_known_subtotal_day_count",
        "unknown_day_count",
        "confirmed_zero_day_count",
        "excluded_day_count",
        "missing_canonical_daily_row_count",
        "first_quantity_date",
        "last_quantity_date",
        "mapped_quantity_kg",
        "complete_daily_sum_kg",
        "partial_known_quantity_kg",
        "unknown_quantity_kg_or_null",
        "business_total_quantity_kg_or_null",
        "daily_coverage_complete",
        "member_coverage_complete",
        "season_boundary_complete",
        "quality_ledger_mapped_quantity_kg",
        "daily_mapped_sum_delta_kg",
        "season_total_reconcilable",
        "complete_season_total_quantity_kg",
        "quantity_authority_status",
        "quantity_authority_basis",
        "existing_business_total_status",
        "season_total_complete",
        "business_total_reconciliation_status",
        "source_identity_status",
        "accepted_source_label_count",
        "unresolved_member_label_count",
        "daily_curve_evaluation_eligible",
        "season_total_training_eligible",
        "strict_quantity_eligible",
        "blocker_codes",
    ),
    "quantity-day-gap-ledger-r1.csv": (
        "base_id",
        "base_name",
        "season",
        "date",
        "daily_quantity_status",
        "daily_completeness_status",
        "known_quantity_kg_or_null",
        "missing_member_count",
        "unresolved_member_labels",
        "partial_reason",
        "unknown_reason",
        "source_refs",
        "blocker_code",
    ),
    "business-total-authority-gap-analysis-r1.csv": (
        "base_id",
        "base_name",
        "season",
        "business_total_coverage_status",
        "season_total_complete",
        "business_total_authority_present",
        "business_total_quantity_kg_or_null",
        "daily_mapped_quantity_kg",
        "daily_complete_sum_kg",
        "daily_coverage_complete",
        "daily_curve_evaluation_eligible",
        "quantity_authority_status",
        "quantity_authority_basis",
        "prior_gate_gap_classification",
        "blocker_codes",
    ),
    "quantity-complete-season-authority-overlay-r1.csv": (
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
    ),
    "v0-8-strict-training-eligibility-r1.csv": (
        "base_id",
        "base_name",
        "season",
        "area_mu",
        "area_eligible",
        "season_total_quantity_kg",
        "season_total_quantity_authority",
        "season_total_training_eligible",
        "daily_curve_evaluation_eligible",
        "strict_training_eligible",
        "strict_oot_eligible",
        "exclusion_reason",
    ),
    "quantity-conservation-r1.csv": (
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
    ),
    "blocker-impact-summary-r1.csv": (
        "blocker_code",
        "training_base_season_count",
        "oot_base_season_count",
        "all_base_season_count",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QuantityAuthorityError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _verify_sha(path: Path, expected: str, *, code: str) -> str:
    if not path.is_file():
        raise QuantityAuthorityError(f"INPUT_FILE_MISSING:{path.name}")
    actual = _sha256(path)
    if actual != expected:
        raise QuantityAuthorityError(code)
    return actual


def _verify_s1_private(private_root: Path) -> tuple[dict[str, list[dict[str, str]]], str]:
    manifest_path = private_root / "artifact-manifest.json"
    _verify_sha(
        manifest_path,
        EXPECTED_S1_MANIFEST_SHA256,
        code="S1_PRIVATE_MANIFEST_HASH_MISMATCH",
    )
    manifest = _json_load(manifest_path)
    if manifest.get("authority_id") != EXPECTED_QUANTITY_AUTHORITY_ID:
        raise QuantityAuthorityError("S1_PRIVATE_MANIFEST_AUTHORITY_MISMATCH")
    loaded: dict[str, list[dict[str, str]]] = {}
    for filename, expected in EXPECTED_S1_FILES.items():
        path = private_root / filename
        actual = _verify_sha(path, expected, code=f"S1_PRIVATE_FILE_HASH_MISMATCH:{filename}")
        manifest_entry = manifest.get("files", {}).get(filename)
        if not isinstance(manifest_entry, dict) or manifest_entry.get("sha256") != actual:
            raise QuantityAuthorityError(f"S1_PRIVATE_MANIFEST_ENTRY_MISMATCH:{filename}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise QuantityAuthorityError(f"S1_PRIVATE_FILE_PERMISSION_MISMATCH:{filename}")
        loaded[filename] = _read_csv(path)
    if stat.S_IMODE(private_root.stat().st_mode) != 0o700:
        raise QuantityAuthorityError("S1_PRIVATE_DIRECTORY_PERMISSION_MISMATCH")
    return loaded, _sha256(manifest_path)


def _verify_area_private(private_root: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    manifest_path = private_root / "artifact-manifest.json"
    _verify_sha(
        manifest_path,
        EXPECTED_AREA_MANIFEST_SHA256,
        code="AREA_PRIVATE_MANIFEST_HASH_MISMATCH",
    )
    manifest = _json_load(manifest_path)
    if (
        manifest.get("area_authority_id") != EXPECTED_AREA_AUTHORITY_ID
        or manifest.get("business_confirmation_id")
        != "V0_8_S4_USER_CONFIRMED_THREE_SEASON_AREA_AUTHORITY_APPLICATION_R1"
    ):
        raise QuantityAuthorityError("AREA_PRIVATE_MANIFEST_AUTHORITY_MISMATCH")
    filenames = {
        "three-season-historical-area-authority-r1.csv": EXPECTED_AREA_AUTHORITY_SHA256,
        "three-season-area-quantity-training-eligibility-r1.csv": (
            EXPECTED_PRIOR_AREA_QUANTITY_MATRIX_SHA256
        ),
        "authority-application-summary-r1.json": EXPECTED_AREA_SUMMARY_SHA256,
        "three-season-area-business-confirmation-r1.json": EXPECTED_AREA_CONFIRMATION_SHA256,
    }
    verified: dict[str, str] = {}
    for filename, expected in filenames.items():
        path = private_root / filename
        actual = _verify_sha(path, expected, code=f"AREA_PRIVATE_FILE_HASH_MISMATCH:{filename}")
        if manifest.get("artifacts", {}).get(filename) != actual:
            raise QuantityAuthorityError(f"AREA_PRIVATE_MANIFEST_ENTRY_MISMATCH:{filename}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise QuantityAuthorityError(f"AREA_PRIVATE_FILE_PERMISSION_MISMATCH:{filename}")
        verified[filename] = actual
    if stat.S_IMODE(private_root.stat().st_mode) != 0o700:
        raise QuantityAuthorityError("AREA_PRIVATE_DIRECTORY_PERMISSION_MISMATCH")
    area_summary = _json_load(private_root / "authority-application-summary-r1.json")
    if (
        area_summary.get("base_count") != 39
        or area_summary.get("base_season_authority_row_count") != 117
        or area_summary.get("season_area_totals_mu") != {season: "41335" for season in SEASONS}
        or area_summary.get("identity_authority_sha256")
        != EXPECTED_S1_FILES["cross-season-base-identity-authority-r1.csv"]
    ):
        raise QuantityAuthorityError("AREA_AUTHORITY_SUMMARY_MISMATCH")
    area_rows = _read_csv(private_root / "three-season-historical-area-authority-r1.csv")
    if len(area_rows) != 117 or len({row.get("base_id", "") for row in area_rows}) != 39:
        raise QuantityAuthorityError("AREA_AUTHORITY_ROW_OR_BASE_COUNT_MISMATCH")
    area_by_base_season = {
        (row.get("base_id", ""), row.get("season", "")): row for row in area_rows
    }
    if len(area_by_base_season) != 117:
        raise QuantityAuthorityError("DUPLICATE_OR_MISSING_BASE_SEASON_AREA_ROW")
    for season in SEASONS:
        season_rows = [row for row in area_rows if row.get("season") == season]
        total = sum((Decimal(row["historical_actual_area_mu"]) for row in season_rows), Decimal(0))
        if len(season_rows) != 39 or total != Decimal("41335"):
            raise QuantityAuthorityError(f"AREA_SEASON_TOTAL_MISMATCH:{season}")
    for base_id in {row["base_id"] for row in area_rows}:
        values = {
            Decimal(area_by_base_season[(base_id, season)]["historical_actual_area_mu"])
            for season in SEASONS
        }
        if len(values) != 1:
            raise QuantityAuthorityError(f"CONFIRMED_AREA_DIFFERS_ACROSS_SEASONS:{base_id}")
    return area_rows, verified


def _verify_repository_authorities(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    evidence_path = repo_root / S1_EVIDENCE_REL
    config_path = repo_root / S1_CONFIG_REL
    s2_evidence_path = repo_root / S2_EVIDENCE_REL
    s2_config_path = repo_root / S2_CONFIG_REL
    s2_policy_path = repo_root / S2_POLICY_MODULE_REL
    r7b_path = repo_root / R7B_EVIDENCE_REL
    evidence_hash = _verify_sha(
        evidence_path, EXPECTED_S1_EVIDENCE_SHA256, code="S1_EVIDENCE_HASH_MISMATCH"
    )
    config_hash = _verify_sha(
        config_path, EXPECTED_S1_CONFIG_SHA256, code="S1_CONFIG_HASH_MISMATCH"
    )
    s2_evidence_hash = _verify_sha(
        s2_evidence_path, EXPECTED_S2_EVIDENCE_SHA256, code="S2_EVIDENCE_HASH_MISMATCH"
    )
    s2_config_hash = _verify_sha(
        s2_config_path, EXPECTED_S2_CONFIG_SHA256, code="S2_CONFIG_HASH_MISMATCH"
    )
    s2_policy_hash = _verify_sha(
        s2_policy_path,
        EXPECTED_S2_POLICY_MODULE_SHA256,
        code="S2_QUANTITY_POLICY_HASH_MISMATCH",
    )
    r7b_hash = _verify_sha(
        r7b_path, EXPECTED_R7B_EVIDENCE_SHA256, code="R7B_BOUNDARY_EVIDENCE_HASH_MISMATCH"
    )
    s1_evidence = _json_load(evidence_path)
    s1_config = _json_load(config_path)
    s2_evidence = _json_load(s2_evidence_path)
    r7b = _json_load(r7b_path)
    if s1_evidence.get("authority_id") != EXPECTED_QUANTITY_AUTHORITY_ID:
        raise QuantityAuthorityError("S1_AUTHORITY_ID_MISMATCH")
    if s1_config.get("authority_id") != EXPECTED_QUANTITY_AUTHORITY_ID:
        raise QuantityAuthorityError("S1_CONFIG_AUTHORITY_ID_MISMATCH")
    if s2_evidence.get("correction_result") != "PASS_WITH_INSUFFICIENT_EVIDENCE":
        raise QuantityAuthorityError("S2_CORRECTION_EVIDENCE_STATUS_MISMATCH")
    if (
        s2_evidence.get("daily_actual_eligibility_policy", {}).get(
            "missing_or_unknown_filled_as_zero"
        )
        is not False
    ):
        raise QuantityAuthorityError("S2_UNKNOWN_ZERO_POLICY_MISMATCH")
    if s2_evidence.get("daily_actual_eligibility_policy", {}).get(
        "scored_authorized_zero_completeness_statuses"
    ) != ["COMPLETE_SOURCE_ROWS_ZERO", "AUTHORIZED_ZERO"]:
        raise QuantityAuthorityError("S2_AUTHORIZED_ZERO_POLICY_MISMATCH")
    if (
        r7b.get("SEASON_25_26_BUSINESS_START") != "2025-07-22"
        or r7b.get("SEASON_25_26_BUSINESS_END") != "2026-04-15"
    ):
        raise QuantityAuthorityError("R7B_BOUNDARY_MISMATCH")
    if s1_evidence.get("r7b_boundary_authority_sha256") != EXPECTED_R7B_AUTHORITY_SHA256:
        raise QuantityAuthorityError("R7B_BOUNDARY_AUTHORITY_HASH_MISMATCH")
    hashes = {
        "s1_evidence": evidence_hash,
        "s1_config": config_hash,
        "s2_evidence": s2_evidence_hash,
        "s2_config": s2_config_hash,
        "s2_policy_module": s2_policy_hash,
        "r7b_boundary_evidence": r7b_hash,
    }
    return s1_evidence, s2_evidence, r7b, hashes


def _season_totals(evidence: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for season in SEASONS:
        source = evidence.get("season_totals", {}).get(season)
        if not isinstance(source, dict):
            raise QuantityAuthorityError(f"S1_SEASON_TOTAL_EVIDENCE_MISSING:{season}")
        if season in {"2023-2024", "2024-2025"}:
            if source.get("business_boundary_authority") != "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1":
                raise QuantityAuthorityError(f"S1_SEASON_BOUNDARY_AUTHORITY_MISMATCH:{season}")
        else:
            if source.get("business_boundary_authority") != (
                "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B"
            ):
                raise QuantityAuthorityError(f"S1_SEASON_BOUNDARY_AUTHORITY_MISMATCH:{season}")
        boundary = BOUNDARIES[season]
        if (
            source.get("business_start") != boundary.start.isoformat()
            or source.get("business_end") != boundary.end.isoformat()
        ):
            raise QuantityAuthorityError(f"S1_SEASON_BOUNDARY_DATES_MISMATCH:{season}")
        result[season] = {
            "raw_source_kg": str(source["raw_source_kg"]),
            "mapped_kg": str(source["mapped_kg"]),
            "unresolved_kg": str(source["unresolved_kg"]),
            "explicitly_excluded_kg": str(source["explicitly_excluded_kg"]),
            "business_window_mapped_kg": str(source["business_window_mapped_kg"]),
        }
    return result


def _validate_source_unresolved_totals(
    unresolved_rows: list[dict[str, str]], season_totals: dict[str, dict[str, str]]
) -> None:
    for season in SEASONS:
        quantity = sum(
            (
                Decimal(row["raw_source_quantity_kg"])
                for row in unresolved_rows
                if row.get("season") == season
            ),
            Decimal(0),
        )
        if quantity != Decimal(season_totals[season]["unresolved_kg"]):
            raise QuantityAuthorityError(f"UNRESOLVED_SOURCE_CONSERVATION_MISMATCH:{season}")


def _policy_payload() -> dict[str, Any]:
    return {
        "policy_version": "V0_8_S5_QUANTITY_COMPLETENESS_R1",
        "daily_actual_eligibility": {
            "complete_mapped": "KNOWN_MAPPED_SUBTOTAL+COMPLETE_MAPPED_MEMBERS",
            "authorized_zero": [
                "CONFIRMED_ZERO+COMPLETE_SOURCE_ROWS_ZERO",
                "CONFIRMED_ZERO+AUTHORIZED_ZERO",
            ],
            "partial_excluded": "KNOWN_MAPPED_SUBTOTAL+PARTIAL_KNOWN_SUBTOTAL",
            "unknown_is_null_not_zero": True,
        },
        "season_total_sources": [
            "S1_BUSINESS_TOTAL_AUTHORITY_ELIGIBLE+SEASON_TOTAL_COMPLETE",
            "ALL_DATES_IN_FROZEN_BUSINESS_WINDOW_DAILY_COMPLETE_AND_IDENTITY_BOUND",
        ],
        "business_total_daily_comparison": (
            "COMPARE_ONLY_WHEN_DAILY_WINDOW_IS_COMPLETE; mismatch fails closed; "
            "an independently authorized total remains usable when daily coverage "
            "is incomplete"
        ),
        "season_boundaries": {
            season: {
                "start": boundary.start.isoformat(),
                "end": boundary.end.isoformat(),
                "authority_id": boundary.authority_id,
                "authority_sha256": boundary.authority_sha256,
            }
            for season, boundary in BOUNDARIES.items()
        },
        "training_seasons": sorted(TRAINING_SEASONS),
        "oot_season": OOT_SEASON,
        "daily_and_total_eligibility_are_separate": True,
        "area_identity_quantity_authorities_mutated": False,
    }


def _file_sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=list(fields), lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _build_public_summary(
    *,
    outputs: dict[str, Any],
    area_rows: list[dict[str, str]],
    season_totals: dict[str, dict[str, str]],
    input_hashes: dict[str, str],
    policy_hash: str,
) -> dict[str, Any]:
    completeness = outputs["completeness_rows"]
    eligibility = outputs["eligibility_rows"]
    conservation = outputs["conservation_rows"]
    blockers = outputs["blocker_impact_rows"]
    by_season: dict[str, dict[str, int]] = {}
    for season in SEASONS:
        rows = [row for row in completeness if row["season"] == season]
        by_season[season] = {
            "base_season_count": len(rows),
            "season_total_eligible_count": sum(
                row["season_total_training_eligible"] == "true" for row in rows
            ),
            "daily_curve_evaluation_eligible_count": sum(
                row["daily_curve_evaluation_eligible"] == "true" for row in rows
            ),
            "blocked_base_season_count": sum(
                row["season_total_training_eligible"] != "true" for row in rows
            ),
            "unknown_day_count": sum(int(row["unknown_day_count"]) for row in rows),
            "partial_day_count": sum(int(row["partial_known_subtotal_day_count"]) for row in rows),
            "confirmed_zero_day_count": sum(int(row["confirmed_zero_day_count"]) for row in rows),
            "business_total_authority_count": sum(
                row["existing_business_total_status"] == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                and row["season_total_complete"] == "true"
                for row in rows
            ),
        }
    training = [row for row in eligibility if row["season"] in TRAINING_SEASONS]
    oot = [row for row in eligibility if row["season"] == OOT_SEASON]
    strict_training = sum(row["strict_training_eligible"] == "true" for row in training)
    strict_oot = sum(row["strict_oot_eligible"] == "true" for row in oot)
    training_total_eligible = sum(
        row["season_total_training_eligible"] == "true" for row in training
    )
    daily_curve_training = sum(row["daily_curve_evaluation_eligible"] == "true" for row in training)
    daily_curve_oot = sum(row["daily_curve_evaluation_eligible"] == "true" for row in oot)
    raw_total = sum((Decimal(item["raw_source_quantity_kg"]) for item in conservation), Decimal(0))
    mapped_total = sum(
        (Decimal(item["mapped_source_quantity_kg"]) for item in conservation), Decimal(0)
    )
    unresolved_total = sum(
        (Decimal(item["unresolved_source_quantity_kg"]) for item in conservation), Decimal(0)
    )
    excluded_total = sum(
        (Decimal(item["explicitly_excluded_quantity_kg"]) for item in conservation), Decimal(0)
    )
    conservation_pass = all(row["raw_conservation_pass"] == "true" for row in conservation)
    daily_sum_pass = all(row["daily_sum_reconciliation_pass"] == "true" for row in conservation)
    impact_by_code = {row["blocker_code"]: row for row in blockers}
    training_blocker_rank = (
        "UNKNOWN_DAYS_PRESENT",
        "BUSINESS_TOTAL_AUTHORITY_MISSING",
        "SOURCE_COVERAGE_INCOMPLETE",
        "MEMBER_COVERAGE_INCOMPLETE",
        "PARTIAL_KNOWN_SUBTOTAL_DAYS_PRESENT",
        "IDENTITY_UNRESOLVED",
        "SEASON_BOUNDARY_NOT_ESTABLISHED",
        "BUSINESS_TOTAL_MISMATCH",
        "DAILY_SUM_NOT_RECONCILED",
    )
    ranked = sorted(
        (
            (int(impact_by_code.get(code, {}).get("training_base_season_count", 0)), code)
            for code in training_blocker_rank
        ),
        key=lambda item: (-item[0], training_blocker_rank.index(item[1])),
    )
    ranked = [item for item in ranked if item[0] > 0]
    top_blockers = [
        {"blocker_code": code, "affected_training_base_season_count": count}
        for count, code in ranked[:3]
    ]
    training_unknowns = sum(by_season[season]["unknown_day_count"] for season in TRAINING_SEASONS)
    training_partials = sum(by_season[season]["partial_day_count"] for season in TRAINING_SEASONS)
    training_partial_quantity = sum(
        (
            Decimal(row["partial_known_quantity_kg"])
            for row in conservation
            if row["season"] in TRAINING_SEASONS
        ),
        Decimal(0),
    )
    result = (
        "PASS_COMPLETE_SEASON_QUANTITY_AUTHORITY_CLOSED"
        if strict_training > 0
        else "PARTIAL_COMPLETE_SEASON_QUANTITY_AUTHORITY_RECOVERED"
        if training_total_eligible + strict_oot > 0
        else "BLOCKED_COMPLETE_SEASON_QUANTITY_AUTHORITY_NOT_ESTABLISHED"
    )
    area_counts = Counter(row["season"] for row in area_rows)
    area_totals: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    for row in area_rows:
        area_totals[row["season"]] += Decimal(row["historical_actual_area_mu"])
    return {
        "task_id": TASK_ID,
        "result": result,
        "area_authority": {
            "work_complete": True,
            "base_count": len({row["base_id"] for row in area_rows}),
            "base_season_area_qualified_count": sum(
                row["area_eligible"] == "true" for row in eligibility
            ),
            "training_area_qualified_count": sum(
                row["area_eligible"] == "true" and row["season"] in TRAINING_SEASONS
                for row in eligibility
            ),
            "oot_area_qualified_count": sum(
                row["area_eligible"] == "true" and row["season"] == OOT_SEASON
                for row in eligibility
            ),
            "season_base_counts": {season: area_counts[season] for season in SEASONS},
            "season_area_totals_mu": {
                season: decimal_text(area_totals[season]) for season in SEASONS
            },
            "area_authority_sha256": input_hashes["area_authority"],
            "area_authority_mutated": False,
        },
        "scope": {
            "base_season_count": len(completeness),
            "training_base_season_count": len(training),
            "oot_base_season_count": len(oot),
            "daily_curve_training_evaluation_eligible_count": daily_curve_training,
            "daily_curve_oot_evaluation_eligible_count": daily_curve_oot,
            "season_total_training_eligible_count": training_total_eligible,
            "season_total_training_eligible_by_season": {
                season: by_season[season]["season_total_eligible_count"]
                for season in sorted(TRAINING_SEASONS)
            },
            "season_total_oot_eligible_count": by_season[OOT_SEASON]["season_total_eligible_count"],
            "strict_training_eligible_count": strict_training,
            "strict_oot_eligible_count": strict_oot,
            "quantity_total_authority_still_blocking": strict_training == 0,
            "season_summary": by_season,
        },
        "daily_completeness": {
            "unknown_day_count": sum(int(row["unknown_day_count"]) for row in completeness),
            "partial_day_count": sum(
                int(row["partial_known_subtotal_day_count"]) for row in completeness
            ),
            "confirmed_zero_day_count": sum(
                int(row["confirmed_zero_day_count"]) for row in completeness
            ),
            "complete_mapped_member_day_count": sum(
                int(row["complete_mapped_member_day_count"]) for row in completeness
            ),
            "partial_known_quantity_kg": decimal_text(
                sum(
                    (Decimal(row["partial_known_quantity_kg"]) for row in completeness),
                    Decimal(0),
                )
            ),
            "training_unknown_day_count": training_unknowns,
            "training_partial_day_count": training_partials,
            "training_partial_known_quantity_kg": decimal_text(training_partial_quantity),
            "unknown_is_zero": False,
            "missing_or_partial_subtotals_aggregated_as_complete": False,
        },
        "business_total_authority": {
            "record_count": outputs["business_total_record_count"],
            "reconciled_with_daily_sum_count": outputs["business_total_reconciled_count"],
            "mismatch_count": outputs["business_total_mismatch_count"],
            "existing_total_policy": (
                "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE AND season_total_complete=true"
            ),
            "daily_sum_comparison_only_when_daily_coverage_complete": True,
        },
        "raw_source_conservation": {
            "raw_quantity_kg": decimal_text(raw_total),
            "mapped_quantity_kg": decimal_text(mapped_total),
            "unresolved_quantity_kg": decimal_text(unresolved_total),
            "explicitly_excluded_quantity_kg": decimal_text(excluded_total),
            "delta_kg": decimal_text(raw_total - mapped_total - unresolved_total - excluded_total),
            "pass": conservation_pass,
            "daily_mapped_sum_reconciliation_pass": daily_sum_pass,
            "by_season": conservation,
        },
        "unresolved_identity": {
            "unresolved_quantity_by_season_kg": {
                row["season"]: row["unresolved_source_quantity_kg"] for row in conservation
            },
            "unresolved_source_farm_label_count_by_season": {
                row["season"]: row["unresolved_source_farm_label_count"] for row in conservation
            },
            "affected_candidate_base_count_by_season": {
                row["season"]: row["affected_candidate_base_count"] for row in conservation
            },
            "unresolved_quantity_allocated_to_candidate_bases": False,
        },
        "blockers": {
            "top_training_blockers": top_blockers,
            "impact_rows": blockers,
            "prior_gate_reason": (
                "S1 had no frozen business total in either training season; every training "
                "Base-season also has UNKNOWN days, and 28 have PARTIAL_KNOWN_SUBTOTAL days. "
                "No training season "
                "can be derived from incomplete daily rows."
            ),
            "minimum_closure_path": (
                "For each exact training Base-season, establish an independently authorized "
                "complete business total, or close every frozen-window daily date with complete "
                "member coverage "
                "and authorized zeros; never sum partial or unknown days."
            ),
        },
        "supersession": {
            "supersedes_prior_zero_quantity_eligibility": (
                by_season[OOT_SEASON]["season_total_eligible_count"] > 1
            ),
            "prior_s4_strict_training_eligible_count": 0,
            "prior_s4_strict_oot_eligible_count": 1,
            "current_training_eligible_count": strict_training,
            "current_oot_eligible_count": strict_oot,
            "scope": (
                "Adds only an S5 complete-daily-window total for one 2025-2026 OOT Base; "
                "the prior zero training-season quantity eligibility remains zero."
            ),
            "s1_s2_evidence_modified": False,
        },
        "determinism_policy": {
            "policy_hash": policy_hash,
            "decimal_arithmetic": True,
            "canonical_sorting": "season,base_id,date; fixed field order for CSV",
            "timestamps_embedded": False,
            "randomness_used": False,
        },
        "input_hashes": input_hashes,
        "boundaries": {
            season: {
                "start": BOUNDARIES[season].start.isoformat(),
                "end": BOUNDARIES[season].end.isoformat(),
                "expected_calendar_day_count": BOUNDARIES[season].expected_day_count,
                "authority_id": BOUNDARIES[season].authority_id,
                "authority_sha256": BOUNDARIES[season].authority_sha256,
            }
            for season in SEASONS
        },
        "operations": {
            "new_harvest_search": False,
            "raw_harvest_reimport": False,
            "full_filesystem_rescan": False,
            "area_authority_mutated": False,
            "identity_authority_mutated": False,
            "canonical_quantity_ledger_mutated": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "backtest_executed": False,
            "forecast_replay_executed": False,
        },
    }


def _write_private_artifacts(
    *,
    output_dir: Path,
    outputs: dict[str, Any],
    summary: dict[str, Any],
    input_hashes: dict[str, str],
    policy_hash: str,
) -> str:
    if output_dir.exists():
        raise QuantityAuthorityError("PRIVATE_OUTPUT_DIRECTORY_ALREADY_EXISTS")
    if not output_dir.parent.is_dir():
        raise QuantityAuthorityError("PRIVATE_OUTPUT_PARENT_MISSING")
    output_dir.mkdir(mode=0o700)
    os.chmod(output_dir, 0o700)
    rows_by_file = {
        "base-season-quantity-completeness-r1.csv": outputs["completeness_rows"],
        "quantity-day-gap-ledger-r1.csv": outputs["gap_rows"],
        "business-total-authority-gap-analysis-r1.csv": outputs["gap_analysis_rows"],
        "quantity-complete-season-authority-overlay-r1.csv": outputs["quantity_overlay_rows"],
        "v0-8-strict-training-eligibility-r1.csv": outputs["eligibility_rows"],
        "quantity-conservation-r1.csv": outputs["conservation_rows"],
        "blocker-impact-summary-r1.csv": outputs["blocker_impact_rows"],
    }
    artifact_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    for filename, rows in rows_by_file.items():
        payload = _csv_bytes(rows, CSV_FIELDS[filename])
        path = output_dir / filename
        with path.open("xb") as stream:
            stream.write(payload)
        os.chmod(path, 0o600)
        artifact_hashes[filename] = _file_sha_bytes(payload)
        row_counts[filename] = len(rows)
    summary_payload = _json_bytes(summary)
    summary_path = output_dir / "closure-summary-r1.json"
    with summary_path.open("xb") as stream:
        stream.write(summary_payload)
    os.chmod(summary_path, 0o600)
    artifact_hashes[summary_path.name] = _file_sha_bytes(summary_payload)
    row_counts[summary_path.name] = 1
    manifest = {
        "task_id": TASK_ID,
        "quantity_authority_id": "V0_8_COMPLETE_SEASON_QUANTITY_AUTHORITY_OVERLAY_R1",
        "input_hashes": dict(sorted(input_hashes.items())),
        "policy_hash": policy_hash,
        "artifacts": dict(sorted(artifact_hashes.items())),
        "row_counts": dict(sorted(row_counts.items())),
        "permissions": {"directory": "0700", "files": "0600"},
        "deterministic_replay_contract": {
            "decimal_arithmetic": True,
            "timestamps_embedded": False,
            "randomness_used": False,
        },
    }
    manifest_payload = _json_bytes(manifest)
    manifest_path = output_dir / "artifact-manifest.json"
    with manifest_path.open("xb") as stream:
        stream.write(manifest_payload)
    os.chmod(manifest_path, 0o600)
    os.chmod(output_dir, 0o700)
    if stat.S_IMODE(output_dir.stat().st_mode) != 0o700 or any(
        stat.S_IMODE(path.stat().st_mode) != 0o600 for path in output_dir.iterdir()
    ):
        raise QuantityAuthorityError("PRIVATE_OUTPUT_PERMISSION_MISMATCH")
    return _file_sha_bytes(manifest_payload)


def run(
    *, repo_root: Path, s1_private_dir: Path, area_private_dir: Path, output_dir: Path
) -> dict[str, Any]:
    for relative, expected, code in (
        (S1_EVIDENCE_REL, EXPECTED_S1_EVIDENCE_SHA256, "S1_EVIDENCE_HASH_MISMATCH"),
        (S1_CONFIG_REL, EXPECTED_S1_CONFIG_SHA256, "S1_CONFIG_HASH_MISMATCH"),
        (S2_EVIDENCE_REL, EXPECTED_S2_EVIDENCE_SHA256, "S2_EVIDENCE_HASH_MISMATCH"),
    ):
        _verify_sha(repo_root / relative, expected, code=code)
    s1_evidence, s2_evidence, _r7b, repo_hashes = _verify_repository_authorities(repo_root)
    s1_private, s1_manifest_hash = _verify_s1_private(s1_private_dir)
    area_rows, area_hashes = _verify_area_private(area_private_dir)
    s1_config = _json_load(repo_root / S1_CONFIG_REL)
    if s1_config.get("private_artifact_manifest_sha256") != s1_manifest_hash:
        raise QuantityAuthorityError("S1_PRIVATE_MANIFEST_NOT_BOUND_TO_CONFIG")
    if s1_evidence.get("private_artifact_manifest_sha256") != s1_manifest_hash:
        raise QuantityAuthorityError("S1_PRIVATE_MANIFEST_NOT_BOUND_TO_EVIDENCE")
    if s2_evidence.get("authority", {}).get("private_artifact_manifest_sha256") != s1_manifest_hash:
        raise QuantityAuthorityError("S2_PRIVATE_MANIFEST_NOT_BOUND_TO_EVIDENCE")

    area_summary = _json_load(area_private_dir / "authority-application-summary-r1.json")
    prior_area_quantity_rows = _read_csv(
        area_private_dir / "three-season-area-quantity-training-eligibility-r1.csv"
    )
    previous_training = sum(
        row.get("strict_training_eligible") == "true" for row in prior_area_quantity_rows
    )
    previous_oot = sum(row.get("strict_oot_eligible") == "true" for row in prior_area_quantity_rows)
    if previous_training != 0 or previous_oot != 1:
        raise QuantityAuthorityError("PRIOR_S4_QUANTITY_ELIGIBILITY_MISMATCH")

    daily_rows = s1_private["canonical-base-daily-ledger-r1.csv"]
    quality_rows = s1_private["canonical-base-season-quality-r1.csv"]
    unresolved_rows = s1_private["unresolved-identity-ledger-r1.csv"]
    if len(daily_rows) != 33033 or len(quality_rows) != 117:
        raise QuantityAuthorityError("S1_PRIVATE_ROW_COUNT_MISMATCH")
    if len(area_rows) != 117 or len(prior_area_quantity_rows) != 117:
        raise QuantityAuthorityError("S4_PRIVATE_AREA_ROW_COUNT_MISMATCH")
    season_totals = _season_totals(s1_evidence)
    _validate_source_unresolved_totals(unresolved_rows, season_totals)
    outputs = build_quantity_authority_outputs(
        daily_rows=daily_rows,
        quality_rows=quality_rows,
        area_rows=area_rows,
        boundaries=BOUNDARIES,
        season_totals=season_totals,
        unresolved_identity_rows=unresolved_rows,
        expected_season_base_count=39,
    )
    if not all(row["raw_conservation_pass"] == "true" for row in outputs["conservation_rows"]):
        raise QuantityAuthorityError("RAW_SEASON_QUANTITY_CONSERVATION_FAILED")
    if not all(
        row["daily_sum_reconciliation_pass"] == "true" for row in outputs["conservation_rows"]
    ):
        raise QuantityAuthorityError("FROZEN_DAILY_LEDGER_SUM_RECONCILIATION_FAILED")
    input_hashes = {
        "s1_evidence": repo_hashes["s1_evidence"],
        "s1_config": repo_hashes["s1_config"],
        "s1_private_manifest": s1_manifest_hash,
        "canonical_daily_ledger": EXPECTED_S1_FILES["canonical-base-daily-ledger-r1.csv"],
        "canonical_quality_ledger": EXPECTED_S1_FILES["canonical-base-season-quality-r1.csv"],
        "identity_authority": EXPECTED_S1_FILES["cross-season-base-identity-authority-r1.csv"],
        "unresolved_identity_ledger": EXPECTED_S1_FILES["unresolved-identity-ledger-r1.csv"],
        "s2_evidence": repo_hashes["s2_evidence"],
        "s2_config": repo_hashes["s2_config"],
        "s2_daily_policy_module": repo_hashes["s2_policy_module"],
        "r7b_boundary_evidence": repo_hashes["r7b_boundary_evidence"],
        "area_private_manifest": EXPECTED_AREA_MANIFEST_SHA256,
        "area_authority": area_hashes["three-season-historical-area-authority-r1.csv"],
        "prior_area_quantity_matrix": area_hashes[
            "three-season-area-quantity-training-eligibility-r1.csv"
        ],
        "area_application_summary": area_hashes["authority-application-summary-r1.json"],
        "business_confirmation": area_hashes["three-season-area-business-confirmation-r1.json"],
    }
    policy_hash = digest(_policy_payload())
    summary = _build_public_summary(
        outputs=outputs,
        area_rows=area_rows,
        season_totals=season_totals,
        input_hashes=input_hashes,
        policy_hash=policy_hash,
    )
    summary["supersession"]["prior_s4_strict_training_eligible_count"] = previous_training
    summary["supersession"]["prior_s4_strict_oot_eligible_count"] = previous_oot
    summary["input_hashes"]["s2_evidence"] = repo_hashes["s2_evidence"]
    manifest_hash = _write_private_artifacts(
        output_dir=output_dir,
        outputs=outputs,
        summary=summary,
        input_hashes=input_hashes,
        policy_hash=policy_hash,
    )
    summary_hash = _sha256(output_dir / "closure-summary-r1.json")
    return {
        "task_id": TASK_ID,
        "result": summary["result"],
        "base_season_count": summary["scope"]["base_season_count"],
        "season_total_training_eligible_count": summary["scope"][
            "season_total_training_eligible_count"
        ],
        "season_total_training_eligible_by_season": summary["scope"][
            "season_total_training_eligible_by_season"
        ],
        "season_total_oot_eligible_count": summary["scope"]["season_total_oot_eligible_count"],
        "daily_curve_training_evaluation_eligible_count": summary["scope"][
            "daily_curve_training_evaluation_eligible_count"
        ],
        "daily_curve_oot_evaluation_eligible_count": summary["scope"][
            "daily_curve_oot_evaluation_eligible_count"
        ],
        "strict_training_eligible_count": summary["scope"]["strict_training_eligible_count"],
        "strict_oot_eligible_count": summary["scope"]["strict_oot_eligible_count"],
        "quantity_total_authority_still_blocking": summary["scope"][
            "quantity_total_authority_still_blocking"
        ],
        "unknown_day_count": summary["daily_completeness"]["unknown_day_count"],
        "partial_day_count": summary["daily_completeness"]["partial_day_count"],
        "confirmed_zero_day_count": summary["daily_completeness"]["confirmed_zero_day_count"],
        "partial_known_quantity_kg": summary["daily_completeness"]["partial_known_quantity_kg"],
        "raw_quantity_kg": summary["raw_source_conservation"]["raw_quantity_kg"],
        "mapped_quantity_kg": summary["raw_source_conservation"]["mapped_quantity_kg"],
        "unresolved_quantity_kg": summary["raw_source_conservation"]["unresolved_quantity_kg"],
        "excluded_quantity_kg": summary["raw_source_conservation"][
            "explicitly_excluded_quantity_kg"
        ],
        "conservation_delta_kg": summary["raw_source_conservation"]["delta_kg"],
        "business_total_record_count": outputs["business_total_record_count"],
        "business_total_reconciled_count": outputs["business_total_reconciled_count"],
        "business_total_mismatch_count": outputs["business_total_mismatch_count"],
        "area_summary_status": area_summary.get("result"),
        "input_hashes": input_hashes,
        "policy_hash": policy_hash,
        "private_output_directory": str(output_dir),
        "private_artifact_manifest_sha256": manifest_hash,
        "closure_summary_sha256": summary_hash,
        "top_blockers": summary["blockers"]["top_training_blockers"],
        "supersedes_prior_zero_quantity_eligibility": summary["supersession"][
            "supersedes_prior_zero_quantity_eligibility"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
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
        parser.exit(2, f"BLOCKED:{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
