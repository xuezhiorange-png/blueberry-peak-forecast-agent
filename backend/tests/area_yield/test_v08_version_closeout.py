import hashlib
import json
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLOSEOUT_EVIDENCE_PATH = (
    REPOSITORY_ROOT / "docs/v0-8/evidence/v0.8.0-research-closeout.json"
)
R2C_EVIDENCE_PATH = (
    REPOSITORY_ROOT
    / "docs/v0-8/evidence/r2c-frozen-shrinkage-model-and-benchmark-replay-r1.json"
)
STAGE_A_EVIDENCE_PATH = (
    REPOSITORY_ROOT
    / "docs/v0-8/evidence/stage-a-decision-freeze-and-r2c-review-closeout-r1.json"
)
PUBLIC_MANIFEST_PATH = (
    REPOSITORY_ROOT / "docs/v0-8/evidence/v0.8.0-public-artifact-manifest.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v08_closeout_freezes_supported_stage_a_decision() -> None:
    closeout = _load_json(CLOSEOUT_EVIDENCE_PATH)
    r2c = _load_json(R2C_EVIDENCE_PATH)
    stage_a = _load_json(STAGE_A_EVIDENCE_PATH)

    assert closeout["task_id"] == "V0_8_VERSION_CLOSEOUT_R1"
    assert closeout["result"] == "PASS_V0_8_RESEARCH_CLOSEOUT"
    assert closeout["training_and_benchmark"]["training_dataset_row_count"] == 37
    assert closeout["training_and_benchmark"]["benchmark_base_count"] == 39
    assert closeout["stage_a_benchmark"]["r2c_beats_global_baseline"] is False
    assert closeout["stage_a_benchmark"]["r2c_beats_r1"] is True
    assert closeout["stage_a_benchmark"]["reference_baseline"] == "GLOBAL_POOLED_YIELD"
    assert closeout["final_version_conclusion"]["model_production_ready"] is False
    assert closeout["benchmark_lifecycle"]["allowed_for_new_model_selection"] is False
    assert closeout["authorization"]["ready_authorized"] is False
    assert closeout["authorization"]["merge_authorized"] is False
    assert r2c["full39"]["season_total"]["v0_8_r2c"]["wape"] == (
        "0.3585864322241786026216929885"
    )
    assert stage_a["stage_a_decision"]["decision"] == (
        "RETAIN_GLOBAL_POOLED_YIELD_AS_REFERENCE_BASELINE"
    )


def test_v08_closeout_pins_required_prior_public_artifacts() -> None:
    closeout = _load_json(CLOSEOUT_EVIDENCE_PATH)
    task_by_id = {
        item.get("task_id"): item
        for item in closeout["task_chain"]
        if item.get("task_id")
    }

    assert _sha256(R2C_EVIDENCE_PATH) == (
        "ece8cdd7fc5112c1ced831e8820fe99a68e5ed1194c029efd86b85469beba04e"
    )
    assert _sha256(STAGE_A_EVIDENCE_PATH) == (
        "af09d206343abe29d8f55e666f1b1d91467ffe10f473cc8278712e7e9d00c518"
    )
    assert task_by_id[
        "V0_8_S2_CANONICAL_HISTORY_MODEL_RETRAIN_AND_OOT_COMPARISON_R1"
    ]["at_the_time_conclusion_remains_valid"] is True
    assert task_by_id[
        "V0_8_S7_TRAINING_SEASON_SOURCE_IDENTITY_CLOSURE_R1"
    ]["newly_released_samples"] == 0


def test_v08_public_manifest_hashes_only_public_file_artifacts() -> None:
    manifest = _load_json(PUBLIC_MANIFEST_PATH)
    entries = manifest["artifacts"]
    assert manifest["manifest_scope"]["self_hash_excluded"] is True
    assert entries
    artifact_paths = {entry["path"] for entry in entries}
    excluded_evidence = {
        item["path"]: item["sha256"]
        for item in manifest["external_references"]
        if item["lifecycle"] == "REVIEWED_NOT_REPUBLISHED_LOCAL_PRIVATE_PATHS"
    }
    assert excluded_evidence == {
        "docs/v0-8/evidence/s8-canonical-training-and-independent-oot-backtest-r1.json": (
            "98213f283d7366f2bbdad7b5001e0ed60c842dabc4d2f030a727221116780b15"
        ),
        "docs/v0-8/evidence/s9-scale-shape-error-decomposition-and-model-diagnosis-r1.json": (
            "a714ede1ba3ecfeb5dd48896f3f3dbcf72843409d82d9a539f74c87f4ffe29fd"
        ),
    }
    assert not artifact_paths.intersection(excluded_evidence)
    path_bound_drivers = set(
        manifest["manifest_scope"]["local_path_bound_replay_drivers_not_republished"]
    )
    assert path_bound_drivers == {
        "scripts/run_v0_8_r2c_frozen_shrinkage.py",
        "scripts/recover_v0_8_original_user_area_sources.py",
        "backend/tests/area_yield/test_v08_s4_original_user_area_source_recovery.py",
    }
    assert not artifact_paths.intersection(path_bound_drivers)

    for entry in entries:
        path = REPOSITORY_ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert _sha256(path) == entry["sha256"], entry["path"]
        assert path.suffix.lower() not in {".csv", ".xls", ".xlsx", ".parquet"}
        assert (b"/Users/" + b"charles/") not in path.read_bytes(), entry["path"]
