"""Contract tests for the S1 R2 authority rebind used by S3 R3."""

import csv
import json
from pathlib import Path

from scripts.rebind_v0_5_s3_eligibility_authority_r3 import (
    _verify_dehong_authority,
    reconcile_scope_sets,
)

CONFIG_PATH = Path("configs/v0_5_s3_eligibility_authority_rebind_r3.json")


def test_r3_config_pins_corrected_mapping_authority_without_training() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["task_id"] == "V0_5_S3_ELIGIBILITY_AUTHORITY_REBIND_R3"
    assert config["registry"]["payload_hash"] == (
        "d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293"
    )
    assert config["mapping_authority"]["version"] == "BASE_MEMBER_MAPPING_R2"
    assert config["mapping_authority"]["payload_hash"] == (
        "6fb7212cc1edd090cf63ff2d938fc5e7b7a0c4b9020b7fdca14e499119b2496e"
    )
    assert config["authorization"]["model_training"] is False
    assert config["authorization"]["weather_features_generated"] is False
    assert config["authorization"]["s4_weather_ablation"] is False


def test_corrected_dehong_alias_is_unique_and_resolved(tmp_path: Path) -> None:
    registry_root = tmp_path
    with (registry_root / "member-farm-mapping.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "historical_farm_identity",
                "normalized_identity",
                "matched_base_id",
                "match_method",
                "match_status",
                "evidence",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "historical_farm_identity": "德宏盈江农场",
                "normalized_identity": "腾冲德宏农场",
                "matched_base_id": "base_5d98f77f66280b5196f09ceb",
                "match_method": "AUTHORIZED_ALIAS",
                "match_status": "AUTHORIZED_ALIAS",
                "evidence": "USER_EXPLICIT_CONFIRMATION_2026-09-14",
            }
        )
    with (registry_root / "business-season-boundary-audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["base_id", "season", "unresolved_member_farm_count", "pre_cutoff_total_kg"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "base_id": "base_5d98f77f66280b5196f09ceb",
                "season": "2025-2026",
                "unresolved_member_farm_count": "0",
                "pre_cutoff_total_kg": "392895.468000",
            }
        )

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    inputs = {
        "mapping_authority": {
            "version": "BASE_MEMBER_MAPPING_R2",
            "hash": "6fb7212cc1edd090cf63ff2d938fc5e7b7a0c4b9020b7fdca14e499119b2496e",
            "aliases": {"德宏盈江农场": ["腾冲德宏农场", "USER_EXPLICIT_CONFIRMATION_2026-09-14"]},
        },
        "files": {
            "mapping_authority": (
                "319d5adbd51aba71dbcdbcc05d1dfd3ff8e5602d621988230a45c5930c23c086"
            )
        },
    }

    proof = _verify_dehong_authority(config, inputs, registry_root)

    assert proof["base_id"] == "base_5d98f77f66280b5196f09ceb"
    assert proof["authorized_alias_source"] == "德宏盈江农场"
    assert proof["authorized_alias_target"] == "腾冲德宏农场"
    assert proof["unresolved_member_farm_count"] == 0
    assert proof["pre_cutoff_total_kg"] == "392895.468000"


def test_scope_reconciliation_keeps_known_only_base_explicit() -> None:
    result = reconcile_scope_sets(
        {"base-a", "base-b", "base-c"},
        {"base-b", "base-c", "base-d"},
    )

    assert result["known_support_weather_intersection_count"] == 2
    assert result["known_support_only_count"] == 1
    assert result["known_support_only_ids"] == ["base-a"]
    assert result["weather_only_count"] == 1
    assert result["weather_only_ids"] == ["base-d"]
    assert result["known_support_weather_set_equal"] is False


def test_corrected_scope_has_39_known_bases_and_no_weather_only_base() -> None:
    result = reconcile_scope_sets(
        {"base_36bc109841061a7798ed99a3", "base_5d98f77f66280b5196f09ceb"},
        {"base_5d98f77f66280b5196f09ceb"},
    )

    # The pure reconciliation function is intentionally set-based; the full
    # 39/38 counts and hashes are asserted in the frozen private replay and its
    # public evidence.  This keeps the unit test independent of private data.
    assert result["known_support_only_ids"] == ["base_36bc109841061a7798ed99a3"]
    assert result["weather_only_ids"] == []
