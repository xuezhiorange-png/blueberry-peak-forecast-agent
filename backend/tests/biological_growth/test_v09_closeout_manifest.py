"""Verify the public V0.9 closeout manifest and lifecycle boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "docs/v0-9/evidence/v0.9.0-public-artifact-manifest.json"
EVIDENCE_PATH = (
    REPOSITORY_ROOT / "docs/v0-9/evidence/v0.9.0-biological-forecast-foundation-closeout.json"
)
EXCLUDED_PATHS = {
    "backend/tests/area_yield/test_v08_s4_original_user_area_source_recovery.py",
    "docs/v0-8/evidence/s8-canonical-training-and-independent-oot-backtest-r1.json",
    "docs/v0-8/evidence/s9-scale-shape-error-decomposition-and-model-diagnosis-r1.json",
    "scripts/recover_v0_8_original_user_area_sources.py",
    "scripts/run_v0_8_r2c_frozen_shrinkage.py",
}


def test_public_manifest_hashes_all_entries_and_excludes_private_scope() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    paths = [entry["path"] for entry in entries]
    validation = evidence["validation"]

    assert manifest["manifest_self_sha256_excluded"] is True
    assert manifest["private_row_level_artifacts_included"] is False
    assert manifest["machine_specific_private_paths_included"] is False
    assert manifest["artifact_count"] == len(entries)
    assert paths == sorted(set(paths))
    assert not set(paths) & EXCLUDED_PATHS
    assert evidence["artifacts"]["public_artifact_manifest_path"] == str(
        MANIFEST_PATH.relative_to(REPOSITORY_ROOT)
    )
    assert validation["source_and_stage_pins"] == "PASS"
    assert validation["manifest_integrity_test"] == "PASS"
    assert validation["focused_tests"]["status"] == "PASS"
    assert validation["ruff_check"]["status"] == "PASS"
    assert validation["ruff_format"]["v0_9_scope_status"] == "PASS"
    assert validation["mypy_backend_app"]["status"] == "PASS"
    assert evidence["immutable_s3_test_lifecycle"]["status"] == (
        "SKIPPED_BY_VERIFIED_S4_LIFECYCLE_GATE"
    )
    for entry in entries:
        artifact = REPOSITORY_ROOT / entry["path"]
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert actual == entry["sha256"], entry["path"]
        assert not entry["path"].startswith("/")


def test_closeout_keeps_production_and_benchmark_boundaries() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["s2"]["controls_theoretical_model_scope"] is False
    assert evidence["s3"]["production_parameter_count"] == 0
    assert evidence["s3"]["irrigation_stress_physiological_effect_implemented"] is False
    assert evidence["s3"]["nutrition_intervention_physiological_effect_implemented"] is False
    assert evidence["benchmark_2025_2026"]["consumed"] is True
    assert evidence["benchmark_2025_2026"]["allowed_for_model_selection"] is False
    assert evidence["readiness_and_scope"]["model_production_ready"] is False
    assert evidence["readiness_and_scope"]["v0_10_authorized"] is False
