"""Non-live contract tests for the fixed C04 real-validation adapter."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from backend.app.s4_candidate_04_controlled_real_validation import (
    FROZEN_PARAMETER_MANIFEST_HASH,
    FROZEN_RUN_PARAMETER_MANIFEST_HASHES,
    build_frozen_manifest,
    mask_target_actuals,
)
from backend.app.s4_local_engineering import (
    build_v2_historical_evaluation_authority,
    load_frozen_engineering_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_c04_controlled_manifest_replays_frozen_identity() -> None:
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    authority = build_v2_historical_evaluation_authority(dataset)
    manifest = build_frozen_manifest(authority, REPO_ROOT)
    assert manifest.manifest_hash == FROZEN_PARAMETER_MANIFEST_HASH
    assert tuple(run.parameter_manifest_hash for run in manifest.runs) == (
        FROZEN_RUN_PARAMETER_MANIFEST_HASHES
    )
    assert tuple(manifest.parameter_values) == tuple(
        Decimal(value) for value in ("3.802757", "4.961884", "5.182238", "4.152099")
    )


def test_c04_target_actuals_are_masked_before_prediction() -> None:
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    authority = build_v2_historical_evaluation_authority(dataset)
    masked = mask_target_actuals(authority.evaluation_rows)
    assert len(masked) == len(authority.evaluation_rows) == 688
    assert all(row.actual_harvest_quantity_kg == Decimal("0") for row in masked)
    assert any(
        original.actual_harvest_quantity_kg != Decimal("0")
        for original in authority.evaluation_rows
    )


def test_c04_masking_does_not_change_target_identity_fields() -> None:
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    authority = build_v2_historical_evaluation_authority(dataset)
    original, masked = (
        authority.evaluation_rows[0],
        mask_target_actuals(authority.evaluation_rows)[0],
    )
    assert replace(original, actual_harvest_quantity_kg=Decimal("0")) == masked
