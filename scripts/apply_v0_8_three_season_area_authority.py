#!/usr/bin/env python3
"""Apply the user's explicit three-season area decision to private ledgers only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from backend.app.area_yield.v08_s4_three_season_area_authority import (
    AREA_AUTHORITY_FIELDS,
    AREA_AUTHORITY_ID,
    BASE_COUNT,
    BUSINESS_CONFIRMATION_ID,
    CONFIRMED_TOTAL_AREA_MU,
    ELIGIBILITY_FIELDS,
    EXPECTED_AREA_SOURCE_SHA256,
    EXPECTED_IDENTITY_AUTHORITY_SHA256,
    EXPECTED_QUANTITY_AUTHORITY_SHA256,
    IDENTITY_AUTHORITY_ID,
    LEGACY_RECONCILIATION_FIELDS,
    OOT_SEASON,
    SEASONS,
    TASK_ID,
    TRAINING_SEASONS,
    build_area_authority_rows,
    build_quantity_eligibility_rows,
    reconcile_legacy_area_evidence,
    serialize_csv_rows,
    validate_area_snapshot,
)

RECOVERED_LINEAGE_SHA256 = "63265f1d1f2ac7b009d3612a3fcdbc7df93415d94b5b774b2c3c9c1c6c31e0c7"
RECOVERY_LEDGER_SHA256 = "be21acb3246d25d176a2a247b65abc1dc3fa581848c89ca0a78ee4a6819597e4"
RECOVERY_MANIFEST_SHA256 = "87fc729ef90d1f6f8a8a6c5a55136a1a4a4e26b6a3e2ef34981143dd944d4bf3"
IDENTITY_MANIFEST_SHA256 = "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"
LEGACY_SOURCE_LEDGER_SHA256 = "ad0f01ca2a9f7a3f17e8cca2f97f55639a34aa7c00bfe1072a073ff1975b3b64"
LEGACY_OVERLAY_SHA256 = "81249ed6e2fc8c38bcb40c50a6fbd5f0d2a23b39067446a38145352577a07c3b"
PRODUCT_AUTHORITY_SHA256 = "231e769ebd004f02267eb4d2402f5745a8cb690ac873bb871f3db0bdb311eed2"
IDENTITY_ACCEPTED_STATUSES = frozenset({"EXACT", "AUTHORIZED_ALIAS", "BUSINESS_CONFIRMED_MAPPING"})
OVERLAY_FIELDS = (
    *AREA_AUTHORITY_FIELDS,
    "business_confirmation_sha256",
    "prior_area_semantics",
    "prior_historical_area_status",
    "quantity_authority_reference_sha256",
    "overlay_only",
)
CONFIRMATION_FIELDS = (
    "decision_id",
    "decision",
    "base_count",
    "total_area_mu",
    "seasons",
    "area_values_same_across_seasons",
    "decision_type",
    "area_estimation",
    "cross_season_inference",
    "original_area_source_sha256",
    "original_season_scope",
    "resolution_basis",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _require_hash(path: Path, expected: str, error_code: str) -> str:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(error_code)
    return actual


def _recovery_source_ids(
    lineage_rows: list[dict[str, str]], recovery_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    for source in lineage_rows:
        matches = [
            row
            for row in recovery_rows
            if row.get("source_file_sha256") == source.get("source_sha256")
            and row.get("source_category") == "USER_ORIGINAL_STRUCTURED_INPUT"
            and row.get("raw_base_name") == source.get("base_name")
            and row.get("raw_area_value") == source.get("area_mu")
            and row.get("source_sheet") == source.get("source_sheet")
            and row.get("source_row") == source.get("source_row")
        ]
        if len(matches) != 1:
            raise ValueError("ORIGINAL_AREA_SOURCE_RECORD_BINDING_NOT_UNIQUE")
        enriched = dict(source)
        enriched["source_record_id"] = matches[0]["recovery_record_id"]
        enriched["original_season_scope"] = source.get("season_or_time_scope", "")
        accepted.append(enriched)
    return accepted


def _canonical_bases(identity_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    pairs = {
        (row.get("canonical_base_id", ""), row.get("canonical_base_name", ""))
        for row in identity_rows
        if row.get("mapping_status") in IDENTITY_ACCEPTED_STATUSES
        and row.get("canonical_base_id")
        and row.get("canonical_base_name")
    }
    by_id: dict[str, str] = {}
    for base_id, base_name in pairs:
        if base_id in by_id and by_id[base_id] != base_name:
            raise ValueError("IDENTITY_AUTHORITY_BASE_ID_CONFLICT")
        by_id[base_id] = base_name
    if len(by_id) != BASE_COUNT:
        raise ValueError("IDENTITY_AUTHORITY_CANONICAL_BASE_COUNT_MISMATCH")
    return [
        {"base_id": base_id, "canonical_base_name": by_id[base_id]} for base_id in sorted(by_id)
    ]


def _legacy_area_rows(
    legacy_rows: list[dict[str, str]], product_authority: dict[str, Any]
) -> list[dict[str, str]]:
    history = product_authority.get("history")
    if not isinstance(history, list):
        raise ValueError("PRODUCT_AREA_HISTORY_MISSING")
    history_keys = {
        (row.get("farm"), row.get("season"), str(row.get("historical_area_mu")))
        for row in history
        if isinstance(row, dict)
    }
    output: list[dict[str, str]] = []
    for row in legacy_rows:
        area = row.get("area_mu", "")
        if (row.get("authority_farm_label"), row.get("season"), area) not in history_keys:
            raise ValueError("LEGACY_AREA_ROW_NOT_BOUND_TO_PRODUCT_AUTHORITY")
        scope = row.get("canonical_base_scope_status")
        if scope == "FULL_CANONICAL_BASE_MEMBERSHIP":
            grain = "BASE"
        elif scope == "PARTIAL_CANONICAL_BASE_MEMBERSHIP":
            grain = "MEMBER"
        else:
            raise ValueError("LEGACY_AREA_SCOPE_NOT_ESTABLISHED")
        output.append(
            {
                "legacy_record_id": row.get("source_record_id", ""),
                "base_id": row.get("canonical_base_id", ""),
                "base_name": row.get("canonical_base_name", ""),
                "season": row.get("season", ""),
                "grain": grain,
                "old_area_mu": area,
                "source_id": row.get("source_record_id", ""),
                "source_sha256": PRODUCT_AUTHORITY_SHA256,
                "referenced_workbook_sha256": row.get("source_workbook_sha256", ""),
                "original_area_document_recovered": "false",
            }
        )
    if len(output) != 2:
        raise ValueError("LEGACY_AREA_ANCHOR_COUNT_MISMATCH")
    return output


def _write_private(directory: Path, name: str, payload: bytes) -> None:
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(payload)
    path.chmod(0o600)


def build_artifacts(args: argparse.Namespace) -> dict[str, Any]:
    pinned_inputs = {
        "recovered_area_lineage": (args.area_lineage, RECOVERED_LINEAGE_SHA256),
        "area_recovery_ledger": (args.recovery_ledger, RECOVERY_LEDGER_SHA256),
        "area_recovery_manifest": (args.recovery_manifest, RECOVERY_MANIFEST_SHA256),
        "identity_authority": (args.identity_authority, EXPECTED_IDENTITY_AUTHORITY_SHA256),
        "identity_manifest": (args.identity_manifest, IDENTITY_MANIFEST_SHA256),
        "quantity_quality_ledger": (args.quantity_ledger, EXPECTED_QUANTITY_AUTHORITY_SHA256),
        "legacy_area_source_ledger": (args.legacy_area_ledger, LEGACY_SOURCE_LEDGER_SHA256),
        "legacy_area_overlay": (args.legacy_overlay, LEGACY_OVERLAY_SHA256),
        "product_authority": (args.product_authority, PRODUCT_AUTHORITY_SHA256),
    }
    input_hashes = {
        key: _require_hash(path, expected, f"{key.upper()}_PINNED_HASH_MISMATCH")
        for key, (path, expected) in pinned_inputs.items()
    }

    recovery_manifest = _read_json(args.recovery_manifest)
    manifest_artifacts = recovery_manifest.get("artifacts", {})
    if (
        manifest_artifacts.get("reference-41335-area-lineage-r1.csv")
        != input_hashes["recovered_area_lineage"]
        or manifest_artifacts.get("original-user-area-source-recovery-ledger-r1.csv")
        != input_hashes["area_recovery_ledger"]
    ):
        raise ValueError("RECOVERED_AREA_MANIFEST_BINDING_MISMATCH")

    lineage_rows = _read_csv(args.area_lineage)
    recovery_rows = _read_csv(args.recovery_ledger)
    source_rows = _recovery_source_ids(lineage_rows, recovery_rows)
    identity_rows = _read_csv(args.identity_authority)
    canonical_bases = _canonical_bases(identity_rows)
    total = validate_area_snapshot(source_rows, canonical_bases)
    quantity_rows = _read_csv(args.quantity_ledger)
    if len(quantity_rows) != 117:
        raise ValueError("QUANTITY_AUTHORITY_ROW_COUNT_MISMATCH")

    decision: dict[str, Any] = {
        "decision_id": BUSINESS_CONFIRMATION_ID,
        "decision": "USE_RECOVERED_39_BASE_41335_MU_FOR_ALL_THREE_SEASONS",
        "base_count": BASE_COUNT,
        "total_area_mu": str(CONFIRMED_TOTAL_AREA_MU),
        "seasons": list(SEASONS),
        "area_values_same_across_seasons": True,
        "decision_type": "EXPLICIT_BUSINESS_CONFIRMATION",
        "area_estimation": False,
        "cross_season_inference": False,
        "original_area_source_sha256": EXPECTED_AREA_SOURCE_SHA256,
        "original_season_scope": "CURRENT/UNSPECIFIED",
        "resolution_basis": "EXPLICIT_BUSINESS_CONFIRMATION",
    }
    confirmation = dict(decision)
    confirmation["confirmation_record_id"] = BUSINESS_CONFIRMATION_ID
    area_rows = build_area_authority_rows(
        source_rows,
        canonical_bases,
        confirmation,
        identity_authority_id=IDENTITY_AUTHORITY_ID,
        identity_authority_sha256=input_hashes["identity_authority"],
        business_confirmation_sha256=None,
    )
    confirmation_payload = _json_bytes(decision)
    confirmation_sha = hashlib.sha256(confirmation_payload).hexdigest()
    for row in area_rows:
        row["business_confirmation_sha256"] = confirmation_sha

    eligibility_rows = build_quantity_eligibility_rows(area_rows, quantity_rows)
    legacy_source_rows = _read_csv(args.legacy_area_ledger)
    product_authority = _read_json(args.product_authority)
    legacy_inputs = _legacy_area_rows(legacy_source_rows, product_authority)
    legacy_rows = reconcile_legacy_area_evidence(legacy_inputs, area_rows)

    quantity_index = {(row["base_id"], row["season"]): row for row in quantity_rows}
    overlay_rows: list[dict[str, str]] = []
    for area in area_rows:
        quantity = quantity_index[(area["base_id"], area["season"])]
        overlay = dict(area)
        overlay["prior_area_semantics"] = quantity.get("area_semantics", "")
        overlay["prior_historical_area_status"] = quantity.get(
            "historical_actual_productive_area_status", ""
        )
        overlay["quantity_authority_reference_sha256"] = input_hashes["quantity_quality_ledger"]
        overlay["overlay_only"] = "true"
        overlay_rows.append(overlay)

    seasonal_totals: dict[str, str] = {}
    for season in SEASONS:
        seasonal_totals[season] = str(
            sum(
                (
                    Decimal(row["historical_actual_area_mu"])
                    for row in area_rows
                    if row["season"] == season
                ),
                Decimal(0),
            )
        )
        if seasonal_totals[season] != str(CONFIRMED_TOTAL_AREA_MU):
            raise ValueError("SEASONAL_AREA_TOTAL_MISMATCH")

    training_area_count = sum(row["season"] in TRAINING_SEASONS for row in area_rows)
    oot_area_count = sum(row["season"] == OOT_SEASON for row in area_rows)
    complete_training_quantity = sum(
        row["season"] in TRAINING_SEASONS and row["quantity_eligible"] == "true"
        for row in eligibility_rows
    )
    complete_oot_quantity = sum(
        row["season"] == OOT_SEASON and row["quantity_eligible"] == "true"
        for row in eligibility_rows
    )
    strict_training = sum(row["strict_training_eligible"] == "true" for row in eligibility_rows)
    strict_oot = sum(row["strict_oot_eligible"] == "true" for row in eligibility_rows)

    legacy_status_counts: dict[str, int] = {}
    for row in legacy_rows:
        key = row["reconciliation_status"]
        legacy_status_counts[key] = legacy_status_counts.get(key, 0) + 1

    summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "result": "PASS_THREE_SEASON_AREA_AUTHORITY_APPLIED",
        "area_authority_id": AREA_AUTHORITY_ID,
        "business_confirmation_id": BUSINESS_CONFIRMATION_ID,
        "business_confirmation_sha256": confirmation_sha,
        "base_count": BASE_COUNT,
        "identity_resolved_base_count": len(canonical_bases),
        "identity_unresolved_base_count": 0,
        "season_count": len(SEASONS),
        "base_season_authority_row_count": len(area_rows),
        "season_area_base_counts": {season: BASE_COUNT for season in SEASONS},
        "season_area_totals_mu": seasonal_totals,
        "base_area_snapshot_total_mu": str(total),
        "historical_actual_area_base_season_count": len(area_rows),
        "training_season_area_qualified_count": training_area_count,
        "oot_season_area_qualified_count": oot_area_count,
        "training_area_authority_still_blocking": False,
        "complete_season_quantity_training_eligible_count": complete_training_quantity,
        "complete_season_quantity_oot_eligible_count": complete_oot_quantity,
        "strict_training_eligible_count": strict_training,
        "strict_oot_eligible_count": strict_oot,
        "quantity_total_authority_still_blocking": strict_training == 0,
        "superseded_prior_area_blocker": True,
        "legacy_area_evidence_reconciliation_status_counts": legacy_status_counts,
        "area_source_sha256": EXPECTED_AREA_SOURCE_SHA256,
        "recovered_area_lineage_sha256": input_hashes["recovered_area_lineage"],
        "identity_authority_id": IDENTITY_AUTHORITY_ID,
        "identity_authority_sha256": input_hashes["identity_authority"],
        "quantity_authority_sha256": input_hashes["quantity_quality_ledger"],
        "area_estimation_executed": False,
        "cross_season_inference_executed": False,
        "canonical_ledger_modified": False,
        "quantity_authority_modified": False,
        "identity_authority_modified": False,
        "model_training_executed": False,
        "model_refit_executed": False,
        "backtest_executed": False,
        "forecast_replay_executed": False,
        "area_overlay_only": True,
    }

    outputs: dict[str, bytes] = {
        "three-season-area-business-confirmation-r1.json": confirmation_payload,
        "three-season-historical-area-authority-r1.csv": serialize_csv_rows(
            area_rows, (*AREA_AUTHORITY_FIELDS, "business_confirmation_sha256")
        ),
        "three-season-area-quantity-training-eligibility-r1.csv": serialize_csv_rows(
            eligibility_rows, ELIGIBILITY_FIELDS
        ),
        "legacy-area-evidence-reconciliation-r1.csv": serialize_csv_rows(
            legacy_rows, LEGACY_RECONCILIATION_FIELDS
        ),
        "v0-8-three-season-area-authority-overlay-r1.csv": serialize_csv_rows(
            overlay_rows, OVERLAY_FIELDS
        ),
        "authority-application-summary-r1.json": _json_bytes(summary),
    }
    output_hashes = {
        name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(outputs.items())
    }
    manifest = {
        "task_id": TASK_ID,
        "area_authority_id": AREA_AUTHORITY_ID,
        "business_confirmation_id": BUSINESS_CONFIRMATION_ID,
        "inputs": dict(sorted(input_hashes.items())),
        "artifacts": output_hashes,
        "deterministic_replay_contract": {
            "timestamps_embedded": False,
            "output_paths_embedded": False,
            "decimal_arithmetic": True,
            "row_sorting": "FIELD_VALUE_LEXICOGRAPHIC",
        },
    }
    outputs["artifact-manifest.json"] = _json_bytes(manifest)

    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    args.output_dir.chmod(0o700)
    for name, payload in outputs.items():
        _write_private(args.output_dir, name, payload)

    manifest_sha = hashlib.sha256(outputs["artifact-manifest.json"]).hexdigest()
    return {
        "result": summary["result"],
        "base_count": BASE_COUNT,
        "base_season_row_count": len(area_rows),
        "season_area_totals_mu": seasonal_totals,
        "training_area_qualified_count": training_area_count,
        "oot_area_qualified_count": oot_area_count,
        "complete_season_quantity_training_eligible_count": complete_training_quantity,
        "complete_season_quantity_oot_eligible_count": complete_oot_quantity,
        "strict_training_eligible_count": strict_training,
        "strict_oot_eligible_count": strict_oot,
        "legacy_area_evidence_reconciliation_status_counts": legacy_status_counts,
        "business_confirmation_sha256": confirmation_sha,
        "authority_sha256": output_hashes["three-season-historical-area-authority-r1.csv"],
        "eligibility_sha256": output_hashes[
            "three-season-area-quantity-training-eligibility-r1.csv"
        ],
        "manifest_sha256": manifest_sha,
        "output_dir_mode": "0700",
        "output_file_mode": "0600",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area-lineage", type=Path, required=True)
    parser.add_argument("--recovery-ledger", type=Path, required=True)
    parser.add_argument("--recovery-manifest", type=Path, required=True)
    parser.add_argument("--identity-authority", type=Path, required=True)
    parser.add_argument("--identity-manifest", type=Path, required=True)
    parser.add_argument("--quantity-ledger", type=Path, required=True)
    parser.add_argument("--legacy-area-ledger", type=Path, required=True)
    parser.add_argument("--legacy-overlay", type=Path, required=True)
    parser.add_argument("--product-authority", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    try:
        result = build_artifacts(parse_args())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
