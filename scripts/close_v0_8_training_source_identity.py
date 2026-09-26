#!/usr/bin/env python3
"""Build a private, targeted S7 source-identity closure audit from frozen inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.area_yield.v08_s7_training_source_identity_closure import (  # noqa: E402
    ACCEPTED_RESOLUTION_BY_MAPPING_STATUS,
    TRAINING_SEASONS,
    TrainingSourceIdentityClosureError,
    _base_ids,
    _decimal,
    _decimal_text,
    build_target_base_seasons,
    resolve_source_identity,
    validate_eligibility_preservation,
)

TASK_ID = "V0_8_S7_TRAINING_SEASON_SOURCE_IDENTITY_CLOSURE_R1"
EXPECTED_BASE_MAIN_SHA = "5c66d8d8565eb87e1434e61de2939dcce4d7df75"
EXPECTED_BASE_MAIN_TREE_SHA = "e215758b42b2ccc0b654d5975e9715a5ab0746dd"
EXPECTED_S6_MANIFEST_SHA256 = "d23ed98beccb98b11d7ca43800d19a6491deed6ff705513531a927139bab7cd7"
EXPECTED_S1_MANIFEST_SHA256 = "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6"
EXPECTED_HISTORICAL_MANIFEST_SHA256 = (
    "b95454505a12f22509f871f5430e35a088521f8d6a5fe85cc2ff4212f4ba895c"
)
EXPECTED_DECISION_MANIFEST_SHA256 = (
    "d4414c70bdb1ad92cd2c9d54f63485579979686344c59047619e8348a364f327"
)
EXPECTED_BUSINESS_PACKAGE_MANIFEST_SHA256 = (
    "bb38dbea3748948f0b72d7f5e192591805155eda79c46541c992b6a1d88cc0fd"
)
EXPECTED_S6_FILES = {
    "no-record-zero-business-confirmation-r1.json": (
        "51e4afba778efde0754534a57a4c05e74397ee0057d343b3759caf2c7c263607"
    ),
    "canonical-daily-harvest-zero-semantics-overlay-r1.csv": (
        "d0f94ea143cc44c555cc3299a8ea0b3073ab96173fa7927b53104a45c904a8e0"
    ),
    "season-total-authority-overlay-r1.csv": (
        "e774fd3254e965bcccbc5f18b67446c65f52e19ded8509c5c250e017fc1cbfcb"
    ),
    "strict-training-eligibility-r2.csv": (
        "22ea38dac6afa917677fb87d555a3f53b1894096ec257ae4310aad96d121b494"
    ),
    "quantity-conservation-r2.csv": (
        "d9fe0def1f51df6c4f71d36ff13d029b0136fbc87fb0a8e89a2c914662c88d0e"
    ),
}
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
    "cross-season-subfarm-parent-authority-r1.csv": (
        "ca5e949301f981c92c3e9d95375e5f0bef58627854c2ff054527cc5a57308f49"
    ),
    "unresolved-identity-ledger-r1.csv": (
        "d28efd9dceb0717c7303962666b3ec74fa98ed0715896df46a54ae1da9f7389d"
    ),
}
S6_ARTIFACT_NAMES = (
    "base-season-quantity-completeness-r2.csv",
    "unknown-day-semantic-decomposition-r1.csv",
    "partial-day-zero-resolution-r1.csv",
)
IDENTITY_FIELDS = (
    "source_label",
    "source_member_label",
    "season",
    "affected_base_season_candidates",
    "current_identity_status",
    "current_candidate_base_id",
    "historical_identity_status",
    "historical_base_id",
    "alias_evidence",
    "business_confirmation_evidence",
    "revision_evidence",
    "proposed_resolution_status",
    "proposed_base_id",
    "proposed_member_id",
    "resolution_basis",
    "resolution_evidence_ids",
    "conflict_status",
    "affected_quantity_kg",
    "affected_day_count",
)
OVERLAY_FIELDS = (
    "season",
    "source_label",
    "source_member_label",
    "old_status",
    "new_status",
    "canonical_base_id",
    "canonical_member_id_or_null",
    "resolution_basis",
    "evidence_refs",
    "affected_quantity_kg",
)
TARGET_FIELDS = (
    "base_id",
    "base_name",
    "season",
    "s6_strict_training_eligible",
    "s6_blocker_codes",
    "no_accepted_source_identity",
    "unresolved_source_identity_conflict",
    "partial_days_present",
    "unresolved_source_label_count",
    "unresolved_quantity_kg",
    "target_for_s7",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_JSON_OBJECT:{path.name}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _unique_index(
    rows: list[dict[str, str]], key_fields: tuple[str, ...], code: str
) -> dict[tuple[str, ...], dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row.get(field, "").strip() for field in key_fields)
        if not all(key) or key in result:
            raise ValueError(code)
        result[key] = row
    return result


def _verify_manifest_files(
    root: Path, manifest_name: str, expected_manifest_hash: str
) -> dict[str, Any]:
    manifest_path = root / manifest_name
    actual_manifest_hash = _sha256(manifest_path)
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError(f"FROZEN_MANIFEST_HASH_MISMATCH:{manifest_name}")
    manifest = _read_json(manifest_path)
    file_entries = manifest.get("files", manifest.get("artifacts", {}))
    if not isinstance(file_entries, dict):
        raise ValueError(f"MANIFEST_FILE_MAP_INVALID:{manifest_name}")
    for name, metadata in file_entries.items():
        expected = metadata.get("sha256") if isinstance(metadata, dict) else metadata
        if not expected:
            raise ValueError(f"MANIFEST_FILE_HASH_MISSING:{name}")
        path = root / name
        if _sha256(path) != expected:
            raise ValueError(f"MANIFEST_FILE_HASH_MISMATCH:{name}")
    return manifest


def _verify_frozen_inputs(args: argparse.Namespace) -> dict[str, Any]:
    s6_manifest = _verify_manifest_files(
        args.s6_root, "artifact-manifest.json", EXPECTED_S6_MANIFEST_SHA256
    )
    s6_pins = s6_manifest.get("artifacts", {})
    for name, expected in EXPECTED_S6_FILES.items():
        if s6_pins.get(name) != expected or _sha256(args.s6_root / name) != expected:
            raise ValueError(f"S6_INPUT_HASH_MISMATCH:{name}")
    s1_manifest = _verify_manifest_files(
        args.s1_root, "artifact-manifest.json", EXPECTED_S1_MANIFEST_SHA256
    )
    s1_pins = s1_manifest.get("files", {})
    for name, expected in EXPECTED_S1_FILES.items():
        metadata = s1_pins.get(name, {})
        if metadata.get("sha256") != expected or _sha256(args.s1_root / name) != expected:
            raise ValueError(f"S1_INPUT_HASH_MISMATCH:{name}")
    if s1_manifest.get("authority_id") != "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1":
        raise ValueError("S1_AUTHORITY_ID_MISMATCH")
    s1_verified_inputs = s1_manifest.get("inputs", {}).get("verified_input_hashes", {})
    if not isinstance(s1_verified_inputs, dict):
        raise ValueError("S1_VERIFIED_INPUT_HASHES_MISSING")

    historical_manifest = _verify_manifest_files(
        args.historical_identity_root,
        "artifact_manifest.json",
        EXPECTED_HISTORICAL_MANIFEST_SHA256,
    )
    historical_name = "historical_farm_identity_mapping.csv"
    historical_hash = historical_manifest.get("files", {}).get(historical_name, {}).get("sha256")
    if historical_hash != "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044":
        raise ValueError("HISTORICAL_IDENTITY_MAPPING_PIN_MISMATCH")

    decision_manifest = _verify_manifest_files(
        args.decision_root, "artifact-manifest.json", EXPECTED_DECISION_MANIFEST_SHA256
    )
    decision_name = "business-identity-confirmation-decisions-r1.csv"
    decision_hash = decision_manifest.get("files", {}).get(decision_name, {}).get("sha256")
    if decision_hash != "8730b4f3be9a33b86db4f057c31259ec0302d525d8a635aa4f98893558101089":
        raise ValueError("BUSINESS_DECISION_HASH_PIN_MISMATCH")

    package_manifest = _verify_manifest_files(
        args.business_package_root,
        "artifact-manifest.json",
        EXPECTED_BUSINESS_PACKAGE_MANIFEST_SHA256,
    )
    group_name = "business-identity-confirmation-grouped.csv"
    group_hash = package_manifest.get("files", {}).get(group_name, {}).get("sha256")
    if group_hash != "953a0cb8e779513cc2b73d8d673dc27cf1055357bbd8d41b7bf4a75eeed8b15e":
        raise ValueError("BUSINESS_CONFIRMATION_GROUP_HASH_PIN_MISMATCH")

    previous_identities = s1_verified_inputs.get("previous_identity_authorities", {})
    linked_hashes = {
        "historical_identity_mapping": (
            previous_identities.get("historical_identity_mapping")
            if isinstance(previous_identities, dict)
            else None
        ),
        "business_confirmation_package_manifest": s1_verified_inputs.get(
            "business_confirmation_package_manifest"
        ),
        "business_decision_capture_manifest": s1_verified_inputs.get(
            "business_decision_capture_manifest"
        ),
        "business_decisions": s1_verified_inputs.get("business_decisions"),
    }
    if linked_hashes != {
        "historical_identity_mapping": historical_hash,
        "business_confirmation_package_manifest": EXPECTED_BUSINESS_PACKAGE_MANIFEST_SHA256,
        "business_decision_capture_manifest": EXPECTED_DECISION_MANIFEST_SHA256,
        "business_decisions": decision_hash,
    }:
        raise ValueError("S1_FROZEN_EVIDENCE_CROSS_LINK_MISMATCH")

    s6_summary_path = args.s6_root / "closure-summary-r1.json"
    s6_summary_hash = s6_manifest.get("artifacts", {}).get(s6_summary_path.name)
    if not s6_summary_hash or _sha256(s6_summary_path) != s6_summary_hash:
        raise ValueError("S6_CLOSURE_SUMMARY_MANIFEST_MISMATCH")
    s6_summary = _read_json(s6_summary_path)
    strict = s6_summary.get("strict_eligibility", {})
    zero_counts = s6_summary.get("zero_semantics_counts", {})
    conserved = s6_summary.get("quantity_conservation", {})
    expected_summary = {
        "task_id": "V0_8_S6_NO_RECORD_ZERO_SEMANTICS_APPLICATION_AND_SEASON_TOTAL_REBUILD_R1",
        "scope": {
            "canonical_base_count": 39,
            "training_base_season_count": 78,
            "oot_base_season_count": 39,
            "base_season_count": 117,
        },
        "strict_eligibility": {
            "season_total_2023_2024_eligible_count": 15,
            "season_total_2024_2025_eligible_count": 22,
            "season_total_oot_2025_2026_eligible_count": 39,
            "strict_training_eligible_count": 37,
            "strict_oot_eligible_count": 39,
        },
        "zero_semantics_counts": {
            "unknown_day_count_after": 10642,
            "partial_day_count_after": 1231,
        },
        "quantity_conservation": {
            "raw_quantity_kg": "122983150.913",
            "mapped_quantity_kg": "109010615.352",
            "unresolved_quantity_kg": "10573929.816",
            "excluded_quantity_kg": "3398605.745",
            "delta_kg": "0.000",
        },
    }
    observed_summary = {
        "task_id": s6_summary.get("task_id"),
        "scope": {
            field: s6_summary.get("scope", {}).get(field) for field in expected_summary["scope"]
        },
        "strict_eligibility": {
            field: strict.get(field) for field in expected_summary["strict_eligibility"]
        },
        "zero_semantics_counts": {
            field: zero_counts.get(field) for field in expected_summary["zero_semantics_counts"]
        },
        "quantity_conservation": {
            field: conserved.get(field) for field in expected_summary["quantity_conservation"]
        },
    }
    if observed_summary != expected_summary:
        raise ValueError("S6_BASELINE_SUMMARY_MISMATCH")

    return {
        "s6_manifest_sha256": EXPECTED_S6_MANIFEST_SHA256,
        "s6_closure_summary_sha256": s6_summary_hash,
        "s1_manifest_sha256": EXPECTED_S1_MANIFEST_SHA256,
        "historical_identity_manifest_sha256": EXPECTED_HISTORICAL_MANIFEST_SHA256,
        "historical_identity_mapping_sha256": historical_hash,
        "decision_manifest_sha256": EXPECTED_DECISION_MANIFEST_SHA256,
        "business_decisions_sha256": decision_hash,
        "business_package_manifest_sha256": EXPECTED_BUSINESS_PACKAGE_MANIFEST_SHA256,
        "business_confirmation_group_sha256": group_hash,
        "s6_artifacts": dict(EXPECTED_S6_FILES),
        "s1_artifacts": dict(EXPECTED_S1_FILES),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _put_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    path.chmod(0o600)


def _mapped_rows_for_s7(
    *,
    unresolved_rows: list[dict[str, str]],
    targets: list[dict[str, str]],
    current_identity_rows: list[dict[str, str]],
    historical_identity_rows: list[dict[str, str]],
    parent_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    decision_group_rows: list[dict[str, str]],
    quality_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    target_keys = {(row["base_id"], row["season"]) for row in targets}
    current_by_key = _unique_index(
        current_identity_rows,
        ("season", "source_farm_label"),
        "DUPLICATE_CURRENT_IDENTITY_KEY",
    )
    historical_by_key = _unique_index(
        historical_identity_rows,
        ("season", "source_farm_label"),
        "DUPLICATE_HISTORICAL_IDENTITY_KEY",
    )
    parent_rows_with_member = [
        row for row in parent_rows if row.get("source_subfarm_label", "").strip()
    ]
    parent_by_key = _unique_index(
        parent_rows_with_member,
        ("season", "source_farm_label", "source_subfarm_label"),
        "DUPLICATE_PARENT_RELATION_KEY",
    )
    decisions = {row["question_number"]: row for row in decision_rows}
    if len(decisions) != len(decision_rows):
        raise ValueError("DUPLICATE_BUSINESS_DECISION_QUESTION")
    groups = {
        row["question_number"]: row for row in decision_group_rows if row.get("question_number")
    }
    if len(groups) != sum(bool(row.get("question_number")) for row in decision_group_rows):
        raise ValueError("DUPLICATE_BUSINESS_DECISION_GROUP")
    base_name_to_id: dict[str, str] = {}
    for row in quality_rows:
        name = row.get("canonical_base_name", "").strip()
        base_id = row.get("base_id", "").strip()
        if name and base_id:
            previous = base_name_to_id.get(name)
            if previous and previous != base_id:
                raise ValueError("CANONICAL_BASE_NAME_NOT_UNIQUE")
            base_name_to_id[name] = base_id

    resolution_rows: list[dict[str, str]] = []
    overlay_rows: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for source in unresolved_rows:
        season = source.get("season", "").strip()
        source_farm = source.get("source_farm_label", "").strip()
        source_subfarm = source.get("source_subfarm_label", "").strip()
        pair_key = (season, source_farm, source_subfarm)
        if pair_key in seen_pairs:
            raise ValueError("DUPLICATE_UNRESOLVED_SOURCE_IDENTITY_ROW")
        seen_pairs.add(pair_key)
        candidates = _base_ids(source.get("candidate_base_ids"))
        affected = tuple(
            sorted((base_id, season) for base_id in candidates if (base_id, season) in target_keys)
        )
        if not affected:
            continue
        current = current_by_key.get((season, source_farm))
        historical = historical_by_key.get((season, source_farm))
        parent = parent_by_key.get((season, source_farm, source_subfarm))
        resolution = resolve_source_identity(
            season=season,
            source_farm_label=source_farm,
            source_subfarm_label=source_subfarm,
            candidate_base_ids=candidates,
            current_identity=current,
            historical_identity=historical,
            parent_relation=parent,
            decision_rows=decisions,
            decision_groups=groups,
            base_name_to_id=base_name_to_id,
        )
        if current and current.get("mapping_status") in ACCEPTED_RESOLUTION_BY_MAPPING_STATUS:
            resolution = type(resolution)(
                "CONFLICTING_EVIDENCE",
                basis="UNRESOLVED_LEDGER_CONTRADICTS_ACCEPTED_CURRENT_MAPPING",
                conflict_status="UNRESOLVED_LEDGER_VS_ACCEPTED_MAPPING",
            )
        if resolution.status.startswith("ACCEPTED_"):
            overlay_rows.append(
                {
                    "season": season,
                    "source_label": source_farm,
                    "source_member_label": source_subfarm,
                    "old_status": source.get("mapping_status", "UNRESOLVED"),
                    "new_status": resolution.status,
                    "canonical_base_id": resolution.base_id,
                    "canonical_member_id_or_null": "",
                    "resolution_basis": resolution.basis,
                    "evidence_refs": _json(list(resolution.evidence_ids)),
                    "affected_quantity_kg": source.get("business_window_quantity_kg", ""),
                }
            )
        historical_candidate = _base_ids((historical or {}).get("candidate_base_id"))
        current_candidate = _base_ids((current or {}).get("candidate_base_ids"))
        hist_days = (historical or {}).get("source_observed_day_count", "")
        resolution_rows.append(
            {
                "source_label": source_farm,
                "source_member_label": source_subfarm,
                "season": season,
                "affected_base_season_candidates": _json(
                    [{"base_id": base_id, "season": key_season} for base_id, key_season in affected]
                ),
                "current_identity_status": (current or {}).get(
                    "mapping_status", "NO_CURRENT_IDENTITY_ROW"
                ),
                "current_candidate_base_id": ";".join(current_candidate or candidates),
                "historical_identity_status": (historical or {}).get(
                    "mapping_status", "NO_HISTORICAL_ROW"
                ),
                "historical_base_id": ";".join(historical_candidate),
                "alias_evidence": (current or {}).get("mapping_evidence", "")
                or (historical or {}).get("evidence", ""),
                "business_confirmation_evidence": (current or {}).get("business_decisions", ""),
                "revision_evidence": (current or {}).get("identity_revision_id", ""),
                "proposed_resolution_status": resolution.status,
                "proposed_base_id": resolution.base_id,
                "proposed_member_id": "",
                "resolution_basis": resolution.basis,
                "resolution_evidence_ids": _json(list(resolution.evidence_ids)),
                "conflict_status": resolution.conflict_status,
                "affected_quantity_kg": source.get("business_window_quantity_kg", "0"),
                "affected_day_count": hist_days,
            }
        )

    target_quality = {(row.get("base_id", ""), row.get("season", "")): row for row in quality_rows}
    represented = {
        (base_id, season)
        for row in resolution_rows
        for item in json.loads(row["affected_base_season_candidates"])
        for base_id, season in [(item["base_id"], item["season"])]
    }
    for target in targets:
        key = (target["base_id"], target["season"])
        quality = target_quality[key]
        if key in represented or not target["no_accepted_source_identity"] == "true":
            continue
        resolution_rows.append(
            {
                "source_label": "",
                "source_member_label": "",
                "season": target["season"],
                "affected_base_season_candidates": _json(
                    [{"base_id": target["base_id"], "season": target["season"]}]
                ),
                "current_identity_status": "NO_ACCEPTED_SOURCE_ROWS",
                "current_candidate_base_id": "",
                "historical_identity_status": "NO_TARGET_LINKED_HISTORICAL_SOURCE_LABEL",
                "historical_base_id": "",
                "alias_evidence": "",
                "business_confirmation_evidence": "",
                "revision_evidence": quality.get("identity_authority_sha256", ""),
                "proposed_resolution_status": "UNRESOLVED_NO_EVIDENCE",
                "proposed_base_id": "",
                "proposed_member_id": "",
                "resolution_basis": "NO_SOURCE_LABEL_LINKED_TO_TARGET_BASE_SEASON",
                "resolution_evidence_ids": _json(["S1_QUALITY_LEDGER", "S6_TRAINING_ELIGIBILITY"]),
                "conflict_status": "NO_TARGET_LINKED_SOURCE_LABEL",
                "affected_quantity_kg": "0",
                "affected_day_count": "",
            }
        )
    resolution_rows.sort(
        key=lambda row: (
            row["season"],
            row["source_label"],
            row["source_member_label"],
            row["proposed_resolution_status"],
        )
    )
    overlay_rows.sort(
        key=lambda row: (row["season"], row["source_label"], row["source_member_label"])
    )
    return resolution_rows, overlay_rows


def _yield_distribution_rows(eligibility_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    samples_by_season: dict[str, list[Decimal]] = defaultdict(list)
    for row in eligibility_rows:
        if (
            row.get("season") not in TRAINING_SEASONS
            or row.get("strict_training_eligible") != "true"
        ):
            continue
        area = _decimal(row.get("area_mu"), field="area_mu")
        quantity = _decimal(row.get("season_total_quantity_kg"), field="season_total_quantity_kg")
        if area <= 0:
            raise ValueError("STRICT_TRAINING_AREA_NOT_POSITIVE")
        samples_by_season[row["season"]].append(quantity / area)
    all_samples = [
        value for season in sorted(samples_by_season) for value in samples_by_season[season]
    ]

    def summarize(scope: str, values: list[Decimal]) -> dict[str, str]:
        ordered = sorted(values)
        if not ordered:
            return {
                "scope": scope,
                "sample_count": "0",
                "min_yield_kg_per_mu": "",
                "p25_yield_kg_per_mu": "",
                "median_yield_kg_per_mu": "",
                "p75_yield_kg_per_mu": "",
                "p90_yield_kg_per_mu": "",
                "max_yield_kg_per_mu": "",
                "quantile_method": "NEAREST_RANK;MEDIAN_MIDPOINT",
            }

        def nearest_rank(q: int, d: int) -> Decimal:
            index = max(0, (len(ordered) * q + d - 1) // d - 1)
            return ordered[index]

        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / Decimal(2)
        )
        return {
            "scope": scope,
            "sample_count": str(len(ordered)),
            "min_yield_kg_per_mu": _decimal_text(ordered[0]),
            "p25_yield_kg_per_mu": _decimal_text(nearest_rank(1, 4)),
            "median_yield_kg_per_mu": _decimal_text(median),
            "p75_yield_kg_per_mu": _decimal_text(nearest_rank(3, 4)),
            "p90_yield_kg_per_mu": _decimal_text(nearest_rank(9, 10)),
            "max_yield_kg_per_mu": _decimal_text(ordered[-1]),
            "quantile_method": "NEAREST_RANK;MEDIAN_MIDPOINT",
        }

    rows = [summarize(season, samples_by_season[season]) for season in sorted(samples_by_season)]
    rows.append(summarize("TRAINING_ALL", all_samples))
    return rows


def _artifact_payloads(args: argparse.Namespace) -> tuple[dict[str, bytes], dict[str, Any]]:
    input_hashes = _verify_frozen_inputs(args)
    eligibility = _read_csv(args.s6_root / "strict-training-eligibility-r2.csv")
    completeness = _read_csv(args.s6_root / "base-season-quantity-completeness-r2.csv")
    unknown_rows = _read_csv(args.s6_root / "unknown-day-semantic-decomposition-r1.csv")
    partial_rows = _read_csv(args.s6_root / "partial-day-zero-resolution-r1.csv")
    conservation = _read_csv(args.s6_root / "quantity-conservation-r2.csv")
    quality = _read_csv(args.s1_root / "canonical-base-season-quality-r1.csv")
    current_identity = _read_csv(args.s1_root / "cross-season-base-identity-authority-r1.csv")
    parent = _read_csv(args.s1_root / "cross-season-subfarm-parent-authority-r1.csv")
    unresolved = _read_csv(args.s1_root / "unresolved-identity-ledger-r1.csv")
    historical = _read_csv(args.historical_identity_root / "historical_farm_identity_mapping.csv")
    decisions = _read_csv(args.decision_root / "business-identity-confirmation-decisions-r1.csv")
    groups = _read_csv(args.business_package_root / "business-identity-confirmation-grouped.csv")

    target_rows = build_target_base_seasons(
        s6_eligibility_rows=eligibility,
        quality_rows=quality,
        completeness_rows=completeness,
        unresolved_rows=unresolved,
    )
    target_keys = {(row["base_id"], row["season"]) for row in target_rows}
    if len(eligibility) != 117 or len(target_rows) != 41:
        raise ValueError("S6_ELIGIBILITY_OR_TARGET_POPULATION_COUNT_MISMATCH")
    eligible_by_season = Counter(
        row["season"]
        for row in eligibility
        if row.get("season") in TRAINING_SEASONS
        and row.get("strict_training_eligible", "").lower() == "true"
    )
    target_by_season = Counter(row["season"] for row in target_rows)
    if eligible_by_season != Counter({"2023-2024": 15, "2024-2025": 22}):
        raise ValueError("S6_TRAINING_SEASON_ELIGIBILITY_BASELINE_MISMATCH")
    if target_by_season != Counter({"2023-2024": 24, "2024-2025": 17}):
        raise ValueError("S7_TARGET_SEASON_DISTRIBUTION_MISMATCH")
    identity_status_by_target = Counter(
        next(
            row["source_identity_status"]
            for row in quality
            if (row["base_id"], row["season"]) == (target["base_id"], target["season"])
        )
        for target in target_rows
    )
    if identity_status_by_target != Counter(
        {
            "NO_ACCEPTED_SOURCE_ROWS": 21,
            "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES": 15,
            "IDENTITY_UNRESOLVED": 5,
        }
    ):
        raise ValueError("S7_TARGET_IDENTITY_BLOCKER_DISTRIBUTION_MISMATCH")
    resolution_rows, overlay_rows = _mapped_rows_for_s7(
        unresolved_rows=unresolved,
        targets=target_rows,
        current_identity_rows=current_identity,
        historical_identity_rows=historical,
        parent_rows=parent,
        decision_rows=decisions,
        decision_group_rows=groups,
        quality_rows=quality,
    )
    if overlay_rows:
        raise ValueError(
            "TARGETED_DAILY_SOURCE_DETAIL_UNAVAILABLE_FOR_IDENTITY_REBUILD:"
            "S1 frozen ledgers have no per-day rows for unresolved labels; raw replay is prohibited"
        )

    quality_by_key = _unique_index(quality, ("base_id", "season"), "DUPLICATE_S1_QUALITY_KEY")
    _unique_index(completeness, ("base_id", "season"), "DUPLICATE_S6_COMPLETENESS_KEY")
    eligibility_by_key = _unique_index(
        eligibility, ("base_id", "season"), "DUPLICATE_S6_ELIGIBILITY_KEY"
    )
    unknown_after = [
        row
        for row in unknown_rows
        if (row.get("base_id", ""), row.get("season", "")) in target_keys
        and row.get("new_quantity_status") == "UNKNOWN"
    ]
    partial_after = [
        row
        for row in partial_rows
        if (row.get("base_id", ""), row.get("season", "")) in target_keys
        and row.get("new_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
    ]
    unknown_by_identity_status = Counter(
        quality_by_key[(row["base_id"], row["season"])].get("source_identity_status", "")
        for row in unknown_after
    )
    partial_by_identity_status = Counter(
        quality_by_key[(row["base_id"], row["season"])].get("source_identity_status", "")
        for row in partial_after
    )
    unknown_out: list[dict[str, str]] = []
    for row in unknown_after:
        quality_row = quality_by_key[(row["base_id"], row["season"])]
        unknown_out.append(
            {
                **row,
                "s7_resolved": "false",
                "s7_resolution_status": "UNRESOLVED_NO_EVIDENCE",
                "s7_resolution_basis": (
                    "NO_ACCEPTED_SOURCE_LABEL_FOR_TARGET"
                    if quality_row.get("source_identity_status") == "NO_ACCEPTED_SOURCE_ROWS"
                    else "NO_AUTHORIZED_IDENTITY_EVIDENCE"
                ),
            }
        )
    partial_out = [
        {
            **row,
            "s7_resolved": "false",
            "s7_resolution_status": "UNRESOLVED_NO_EVIDENCE",
            "s7_resolution_basis": "IDENTITY_UNRESOLVED_PARTIAL_MEMBER_COVERAGE_PRESERVED",
        }
        for row in partial_after
    ]

    identity_count_by_key: Counter[tuple[str, str]] = Counter()
    target_row_by_key = {(row["base_id"], row["season"]): row for row in target_rows}
    candidate_kg_by_key = {
        key: _decimal(row["unresolved_quantity_kg"], field="unresolved_quantity_kg")
        for key, row in target_row_by_key.items()
    }
    completeness_out: list[dict[str, str]] = []
    eligibility_out: list[dict[str, str]] = []
    for row in sorted(
        (item for item in completeness if item.get("season") in TRAINING_SEASONS),
        key=lambda item: (item["season"], item["base_id"]),
    ):
        key = (row["base_id"], row["season"])
        old_eligibility = eligibility_by_key[key]
        candidate_unresolved = candidate_kg_by_key.get(key, Decimal(0))
        extra = {
            "s6_eligible": old_eligibility.get("strict_training_eligible", "false"),
            "s7_eligible": old_eligibility.get("strict_training_eligible", "false"),
            "unknown_days_before": row.get("unknown_day_count", "0"),
            "unknown_days_after": row.get("unknown_day_count", "0"),
            "partial_days_before": row.get("partial_known_subtotal_day_count", "0"),
            "partial_days_after": row.get("partial_known_subtotal_day_count", "0"),
            "unresolved_quantity_before": _decimal_text(candidate_unresolved),
            "unresolved_quantity_after": _decimal_text(candidate_unresolved),
            "identity_resolution_count": str(identity_count_by_key[key]),
            "strict_training_eligible": old_eligibility.get("strict_training_eligible", "false"),
            "remaining_blockers": row.get("blocker_codes", ""),
        }
        completeness_out.append({**row, **extra})
        eligibility_out.append(
            {
                "base_id": row["base_id"],
                "base_name": row.get("base_name", ""),
                "season": row["season"],
                "s6_eligible": old_eligibility.get("strict_training_eligible", "false"),
                "s7_eligible": old_eligibility.get("strict_training_eligible", "false"),
                "season_total_quantity_kg": old_eligibility.get("season_total_quantity_kg", ""),
                "season_total_quantity_authority": old_eligibility.get(
                    "season_total_quantity_authority", ""
                ),
                "identity_resolution_count": "0",
                "remaining_blockers": row.get("blocker_codes", ""),
                "strict_training_eligible": old_eligibility.get(
                    "strict_training_eligible", "false"
                ),
                "strict_oot_eligible": old_eligibility.get("strict_oot_eligible", "false"),
            }
        )

    target_unknown_count = len(unknown_out)
    target_partial_count = len(partial_out)
    target_identity_status = Counter(
        quality_by_key[key].get("source_identity_status", "") for key in target_keys
    )
    resolution_status_counts = Counter(
        row["proposed_resolution_status"] for row in resolution_rows if row["source_label"]
    )
    decision_basis_counts = Counter(
        row["resolution_basis"]
        for row in resolution_rows
        if row["resolution_basis"].startswith("BUSINESS_DECISION_")
    )
    newly_released = sum(
        row.get("s6_eligible") == "false" and row.get("s7_eligible") == "true"
        for row in eligibility_out
    )
    regression = validate_eligibility_preservation(
        before_rows=eligibility,
        after_rows=eligibility_out
        + [row for row in eligibility if row.get("season") == "2025-2026"],
    )
    if (
        regression["previously_eligible_regression_count"]
        or regression["oot_eligibility_regression_count"]
    ):
        raise ValueError("ELIGIBILITY_REGRESSION_DETECTED")

    training_before = sum(
        row.get("strict_training_eligible") == "true" and row.get("season") in TRAINING_SEASONS
        for row in eligibility
    )
    training_after = sum(
        row.get("strict_training_eligible") == "true" and row.get("season") in TRAINING_SEASONS
        for row in eligibility_out
    )
    oot_before = sum(row.get("strict_oot_eligible") == "true" for row in eligibility)
    oot_after = sum(
        row.get("strict_oot_eligible") == "true"
        for row in eligibility
        if row.get("season") == "2025-2026"
    )
    season_eligible = Counter(
        row["season"]
        for row in eligibility
        if row.get("season") in TRAINING_SEASONS and row.get("strict_training_eligible") == "true"
    )
    season_blocked = Counter(row["season"] for row in target_rows)
    partial_base_seasons = sum(
        row.get("season") in TRAINING_SEASONS
        and int(row.get("partial_known_subtotal_day_count", "0") or "0") > 0
        for row in completeness
    )

    conservation_out: list[dict[str, str]] = []
    for row in conservation:
        mapped = _decimal(row.get("mapped_source_quantity_kg"), field="mapped_source_quantity_kg")
        unresolved_quantity = _decimal(
            row.get("unresolved_source_quantity_kg"), field="unresolved_source_quantity_kg"
        )
        raw = _decimal(row.get("raw_source_quantity_kg"), field="raw_source_quantity_kg")
        excluded = _decimal(
            row.get("explicitly_excluded_quantity_kg"), field="explicitly_excluded_quantity_kg"
        )
        if raw != mapped + unresolved_quantity + excluded:
            raise ValueError(f"S6_QUANTITY_CONSERVATION_FAILURE:{row.get('season')}")
        conservation_out.append(
            {
                **row,
                "mapped_source_quantity_before_kg": _decimal_text(mapped),
                "mapped_source_quantity_after_kg": _decimal_text(mapped),
                "unresolved_source_quantity_before_kg": _decimal_text(unresolved_quantity),
                "unresolved_source_quantity_after_kg": _decimal_text(unresolved_quantity),
                "unresolved_quantity_resolved_kg": "0",
                "excluded_quantity_before_kg": _decimal_text(excluded),
                "excluded_quantity_after_kg": _decimal_text(excluded),
                "raw_conservation_delta_after_kg": _decimal_text(
                    raw - mapped - unresolved_quantity - excluded
                ),
            }
        )

    counts_by_status: dict[str, dict[str, Any]] = {}
    for status in sorted(resolution_status_counts):
        rows_for_status = [
            row
            for row in resolution_rows
            if row["source_label"] and row["proposed_resolution_status"] == status
        ]
        unique_labels = {
            (row["season"], row["source_label"]) for row in rows_for_status if row["source_label"]
        }
        counts_by_status[status] = {
            "ledger_row_count": len(rows_for_status),
            "source_label_count": len(unique_labels),
            "quantity_kg_not_reassigned": _decimal_text(
                sum(
                    (
                        _decimal(row["affected_quantity_kg"], field="affected_quantity_kg")
                        for row in rows_for_status
                    ),
                    Decimal(0),
                )
            ),
            "day_count_resolved": 0,
            "base_season_count_released": 0,
        }

    if training_after > training_before:
        raise ValueError("S7_CANNOT_EMIT_TRAINING_DATASET_WITHOUT_DAILY_REBUILD")

    source_rows_count = sum(1 for row in resolution_rows if row["source_label"])
    source_label_count = len(
        {(row["season"], row["source_label"]) for row in resolution_rows if row["source_label"]}
    )
    raw_total = sum(
        (
            _decimal(row.get("raw_source_quantity_kg"), field="raw_source_quantity_kg")
            for row in conservation
        ),
        Decimal(0),
    )
    mapped_total = sum(
        (
            _decimal(row.get("mapped_source_quantity_kg"), field="mapped_source_quantity_kg")
            for row in conservation
        ),
        Decimal(0),
    )
    unresolved_total = sum(
        (
            _decimal(
                row.get("unresolved_source_quantity_kg"), field="unresolved_source_quantity_kg"
            )
            for row in conservation
        ),
        Decimal(0),
    )
    excluded_total = sum(
        (
            _decimal(
                row.get("explicitly_excluded_quantity_kg"), field="explicitly_excluded_quantity_kg"
            )
            for row in conservation
        ),
        Decimal(0),
    )
    if raw_total != mapped_total + unresolved_total + excluded_total:
        raise ValueError("S7_GLOBAL_QUANTITY_CONSERVATION_FAILURE")

    impact_rows = [
        {
            "resolution_type": status,
            "source_label_count": values["source_label_count"],
            "quantity_kg_resolved": "0",
            "day_count_resolved": "0",
            "base_season_count_released": "0",
            "ledger_row_count": values["ledger_row_count"],
            "quantity_kg_not_reassigned": values["quantity_kg_not_reassigned"],
        }
        for status, values in sorted(counts_by_status.items())
    ]
    impact_rows.extend(
        [
            {
                "resolution_type": "NO_ACCEPTED_SOURCE_IDENTITY_FOR_BASE_SEASON",
                "source_label_count": "0",
                "quantity_kg_resolved": "0",
                "day_count_resolved": "0",
                "base_season_count_released": "0",
                "ledger_row_count": str(target_identity_status["NO_ACCEPTED_SOURCE_ROWS"]),
                "quantity_kg_not_reassigned": "0",
            },
            {
                "resolution_type": "ACCEPTED_AUTHORIZED_RESOLUTION",
                "source_label_count": "0",
                "quantity_kg_resolved": "0",
                "day_count_resolved": "0",
                "base_season_count_released": "0",
                "ledger_row_count": "0",
                "quantity_kg_not_reassigned": "0",
            },
        ]
    )

    summary = {
        "task_id": TASK_ID,
        "result": "BLOCKED_TRAINING_SOURCE_IDENTITY_CLOSURE",
        "baseline": {
            "base_main_sha": EXPECTED_BASE_MAIN_SHA,
            "base_main_tree_sha": EXPECTED_BASE_MAIN_TREE_SHA,
            "head_sha": EXPECTED_BASE_MAIN_SHA,
            "branch": "codex/v0-8-s7-training-season-source-identity-closure-r1",
            "pr_number": None,
            "pr_state": "LOCAL_ONLY",
        },
        "scope": {
            "training_seasons": sorted(TRAINING_SEASONS),
            "training_base_season_count": 78,
            "s7_target_base_season_count": len(target_rows),
            "strict_training_eligible_before": training_before,
            "strict_training_eligible_after": training_after,
            "newly_released_training_base_season_count": newly_released,
            "remaining_blocked_training_base_season_count": len(target_rows) - newly_released,
            "strict_oot_eligible_before": oot_before,
            "strict_oot_eligible_after": oot_after,
            "strict_oot_base_season_count": 39,
            "target_source_identity_status_counts": dict(sorted(target_identity_status.items())),
            "target_candidate_identity_ledger_row_count": source_rows_count,
            "target_candidate_unique_source_farm_season_count": source_label_count,
            "target_resolution_status_counts": dict(sorted(resolution_status_counts.items())),
            "target_decision_basis_counts": dict(sorted(decision_basis_counts.items())),
            "target_candidate_source_quantity_kg_not_reassigned": _decimal_text(
                sum(
                    (
                        _decimal(row["affected_quantity_kg"], field="affected_quantity_kg")
                        for row in resolution_rows
                        if row["source_label"]
                    ),
                    Decimal(0),
                )
            ),
            "partial_training_base_season_count_before_after": partial_base_seasons,
            "unknown_day_count_before_after": sum(
                row.get("new_quantity_status") == "UNKNOWN" for row in unknown_rows
            ),
            "partial_day_count_before_after": sum(
                row.get("new_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
                for row in partial_rows
            ),
            "unknown_identity_resolution_count": 0,
            "partial_identity_resolution_count": 0,
            "previously_eligible_regression_count": regression[
                "previously_eligible_regression_count"
            ],
            "oot_eligibility_regression_count": regression["oot_eligibility_regression_count"],
            "season_eligible_counts_before_after": {
                "2023-2024": int(season_eligible["2023-2024"]),
                "2024-2025": int(season_eligible["2024-2025"]),
                "2025-2026": oot_after,
            },
            "season_blocked_counts_before_after": {
                "2023-2024": int(season_blocked["2023-2024"]),
                "2024-2025": int(season_blocked["2024-2025"]),
            },
            "training_dataset_candidate_row_count": 0,
            "training_dataset_candidate_generated": False,
            "ready_for_v0_8_retrain_technical_gate": bool(training_after > 0 and oot_after == 39),
        },
        "quantity_conservation": {
            "raw_quantity_kg": _decimal_text(raw_total),
            "mapped_quantity_before_kg": _decimal_text(mapped_total),
            "mapped_quantity_after_kg": _decimal_text(mapped_total),
            "unresolved_quantity_before_kg": _decimal_text(unresolved_total),
            "unresolved_quantity_resolved_kg": "0",
            "unresolved_quantity_after_kg": _decimal_text(unresolved_total),
            "excluded_quantity_before_kg": _decimal_text(excluded_total),
            "excluded_quantity_after_kg": _decimal_text(excluded_total),
            "conservation_delta_kg": "0",
            "mapped_increase_equals_unresolved_decrease": True,
            "excluded_bucket_unchanged": True,
        },
        "identity_audit": {
            "targeted_identity_closure_only": True,
            "authorized_identity_resolution_count": len(overlay_rows),
            "identity_overlay_applied": False,
            "business_yes_all_without_explicit_target_resolved": False,
            "candidate_only_identity_promoted": False,
            "fuzzy_mapping_used": False,
            "cross_season_identity_propagation": False,
            "per_day_rows_for_unresolved_labels_available_in_frozen_inputs": False,
            "raw_harvest_reimported": False,
            "reason_blocked": (
                "NO_AUTHORIZED_EXACT_IDENTITY_EVIDENCE_AND_NO_FROZEN_DAILY_ROWS_"
                "FOR_UNRESOLVED_LABELS"
            ),
            "resolution_counts": dict(sorted(resolution_status_counts.items())),
            "impact_rows": impact_rows,
            "target_unknown_day_count": target_unknown_count,
            "target_partial_day_count": target_partial_count,
            "target_unknown_identity_status_counts": dict(
                sorted(unknown_by_identity_status.items())
            ),
            "target_partial_identity_status_counts": dict(
                sorted(partial_by_identity_status.items())
            ),
            "no_accepted_source_identity_target_count": int(
                target_identity_status["NO_ACCEPTED_SOURCE_ROWS"]
            ),
            "unresolved_candidate_target_count": int(
                target_identity_status["IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES"]
                + target_identity_status["IDENTITY_UNRESOLVED"]
            ),
            "identity_resolution_ledger_row_count": len(resolution_rows),
            "authorized_identity_overlay_row_count": len(overlay_rows),
            "explicit_yes_all_not_applied_ledger_row_count": sum(
                row["resolution_basis"] == "BUSINESS_DECISION_YES_ALL_HAS_NO_EXPLICIT_TARGET"
                for row in resolution_rows
            ),
            "business_yes_all_reason_counts": dict(sorted(decision_basis_counts.items())),
        },
        "input_hashes": input_hashes,
        "non_actions": {
            "area_authority_modified": False,
            "identity_authority_modified": False,
            "canonical_quantity_ledger_modified": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "backtest_executed": False,
            "forecast_replay_executed": False,
            "ready_action_taken": False,
            "merge_action_taken": False,
            "pr_created": False,
        },
    }

    completeness_fields = tuple(
        dict.fromkeys(
            [
                *completeness[0].keys(),
                "s6_eligible",
                "s7_eligible",
                "unknown_days_before",
                "unknown_days_after",
                "partial_days_before",
                "partial_days_after",
                "unresolved_quantity_before",
                "unresolved_quantity_after",
                "identity_resolution_count",
                "strict_training_eligible",
                "remaining_blockers",
            ]
        )
    )
    eligibility_fields = (
        "base_id",
        "base_name",
        "season",
        "s6_eligible",
        "s7_eligible",
        "season_total_quantity_kg",
        "season_total_quantity_authority",
        "identity_resolution_count",
        "remaining_blockers",
        "strict_training_eligible",
        "strict_oot_eligible",
    )
    resolution_fields = IDENTITY_FIELDS
    unknown_source_fields = tuple(unknown_out[0].keys()) if unknown_out else ()
    partial_source_fields = tuple(partial_out[0].keys()) if partial_out else ()
    unknown_fields = tuple(
        dict.fromkeys(
            [*unknown_source_fields, "s7_resolved", "s7_resolution_status", "s7_resolution_basis"]
        )
    )
    partial_fields = tuple(
        dict.fromkeys(
            [*partial_source_fields, "s7_resolved", "s7_resolution_status", "s7_resolution_basis"]
        )
    )
    conservation_fields = tuple(
        dict.fromkeys(
            [
                *conservation[0].keys(),
                "mapped_source_quantity_before_kg",
                "mapped_source_quantity_after_kg",
                "unresolved_source_quantity_before_kg",
                "unresolved_source_quantity_after_kg",
                "unresolved_quantity_resolved_kg",
                "excluded_quantity_before_kg",
                "excluded_quantity_after_kg",
                "raw_conservation_delta_after_kg",
            ]
        )
    )
    impact_fields = (
        "resolution_type",
        "source_label_count",
        "quantity_kg_resolved",
        "day_count_resolved",
        "base_season_count_released",
        "ledger_row_count",
        "quantity_kg_not_reassigned",
    )
    payloads = {
        "s7-target-base-season-ledger-r1.csv": _csv_bytes(target_rows, TARGET_FIELDS),
        "target-source-identity-resolution-ledger-r1.csv": _csv_bytes(
            resolution_rows, resolution_fields
        ),
        "training-season-source-identity-overlay-r1.csv": _csv_bytes(overlay_rows, OVERLAY_FIELDS),
        "identity-closure-impact-summary-r1.csv": _csv_bytes(impact_rows, impact_fields),
        "unknown-identity-resolution-r1.csv": _csv_bytes(unknown_out, unknown_fields),
        "partial-identity-resolution-r1.csv": _csv_bytes(partial_out, partial_fields),
        "training-base-season-quantity-completeness-s7-r1.csv": _csv_bytes(
            completeness_out, completeness_fields
        ),
        "strict-training-eligibility-s7-r1.csv": _csv_bytes(eligibility_out, eligibility_fields),
        "yield-distribution-audit-r1.csv": _csv_bytes(
            _yield_distribution_rows(eligibility),
            (
                "scope",
                "sample_count",
                "min_yield_kg_per_mu",
                "p25_yield_kg_per_mu",
                "median_yield_kg_per_mu",
                "p75_yield_kg_per_mu",
                "p90_yield_kg_per_mu",
                "max_yield_kg_per_mu",
                "quantile_method",
            ),
        ),
        "quantity-conservation-s7-r1.csv": _csv_bytes(conservation_out, conservation_fields),
    }
    payloads["closure-summary-r1.json"] = _json_bytes(summary)
    manifest = {
        "task_id": TASK_ID,
        "authority_id": "V0_8_S7_TRAINING_SEASON_SOURCE_IDENTITY_CLOSURE_R1",
        "directory_mode": "0700",
        "file_mode": "0600",
        "private_row_level_artifacts": True,
        "raw_source_workbooks_read": False,
        "inputs": input_hashes,
        "artifacts": {
            name: hashlib.sha256(content).hexdigest() for name, content in sorted(payloads.items())
        },
        "row_counts": {
            "s7-target-base-season-ledger-r1.csv": len(target_rows),
            "target-source-identity-resolution-ledger-r1.csv": len(resolution_rows),
            "training-season-source-identity-overlay-r1.csv": len(overlay_rows),
            "identity-closure-impact-summary-r1.csv": len(impact_rows),
            "unknown-identity-resolution-r1.csv": len(unknown_out),
            "partial-identity-resolution-r1.csv": len(partial_out),
            "training-base-season-quantity-completeness-s7-r1.csv": len(completeness_out),
            "strict-training-eligibility-s7-r1.csv": len(eligibility_out),
            "yield-distribution-audit-r1.csv": len(_yield_distribution_rows(eligibility)),
            "quantity-conservation-s7-r1.csv": len(conservation_out),
        },
    }
    payloads["artifact-manifest.json"] = _json_bytes(manifest)
    return payloads, summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.output_dir.exists():
        raise ValueError("OUTPUT_DIRECTORY_ALREADY_EXISTS_REFUSING_OVERWRITE")
    payloads, summary = _artifact_payloads(args)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    args.output_dir.chmod(0o700)
    try:
        for name, content in sorted(payloads.items()):
            _put_private(args.output_dir / name, content)
        if stat.S_IMODE(args.output_dir.stat().st_mode) != 0o700:
            raise ValueError("PRIVATE_DIRECTORY_PERMISSION_MISMATCH")
        if any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path in args.output_dir.iterdir()):
            raise ValueError("PRIVATE_FILE_PERMISSION_MISMATCH")
        return {
            "summary": summary,
            "artifact_manifest_sha256": _sha256(args.output_dir / "artifact-manifest.json"),
            "artifact_hashes": _read_json(args.output_dir / "artifact-manifest.json")["artifacts"],
            "output_directory": str(args.output_dir),
        }
    except Exception:
        # Keep a created directory as an auditable failed run; never overwrite it.
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s6-root", type=Path, required=True)
    parser.add_argument("--s1-root", type=Path, required=True)
    parser.add_argument("--historical-identity-root", type=Path, required=True)
    parser.add_argument("--decision-root", type=Path, required=True)
    parser.add_argument("--business-package-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args)
    except (OSError, ValueError, TrainingSourceIdentityClosureError) as error:
        print(f"S7_CLOSURE_STOPPED:{error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "result": result["summary"]["result"],
                "target_count": result["summary"]["scope"]["s7_target_base_season_count"],
                "strict_training_eligible_after": result["summary"]["scope"][
                    "strict_training_eligible_after"
                ],
                "newly_released": result["summary"]["scope"][
                    "newly_released_training_base_season_count"
                ],
                "private_artifact_manifest_sha256": result["artifact_manifest_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
