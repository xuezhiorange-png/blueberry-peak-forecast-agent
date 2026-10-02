"""Frozen integration contracts only; no private data or research execution."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/v0-12/evidence/v0.12-s1-area-model-r1-integration.json"
SOURCE_FILES = (
    "backend/app/area_yield/area_size_r1.py",
    "backend/tests/test_next_area_size_r1.py",
    "configs/next_area_size_experiment_20261002_r1.json",
    "docs/next-version/evidence/next-area-size-20261002-r1.json",
    "docs/next-version/next-area-size-training-backtest-20261002-r1.md",
    "scripts/run_next_area_size_r1.py",
)
pytestmark = pytest.mark.contract


def manifest() -> dict[str, Any]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_source_commit_identity_and_separate_integration_base() -> None:
    data = manifest()
    assert data["SOURCE_PR"] == 659
    assert data["SOURCE_HEAD"] == "76b9e86c24cdd99be23b20e15eb895173ac26671"
    assert data["SOURCE_COMMIT_1"] == "fd0ed2c7789d6ab0f240e0e4b5995724cbb549f7"
    assert data["SOURCE_COMMIT_2"] == data["SOURCE_HEAD"]
    assert data["RESEARCH_EXECUTION_ID"] == "NEXT_AREA_SIZE_20261002_R1"
    assert data["RESEARCH_EXECUTION_BASE_SHA"] == "8e886b45984a358125d00e80f4f5d662fab3d8e9"
    assert data["V0_12_S1_INTEGRATION_BASE_SHA"] == "1b4da8f95e96fde69db1b5b2afe6dfe6681adac1"
    assert data["S0_POST_MERGE_CI_RUN"] == 36993293292
    assert data["S0_POST_MERGE_CI"] == "SUCCESS"
    assert data["SOURCE_FILE_COUNT"] == 6
    assert data["SOURCE_FILE_HASH_PARITY"] == "PASS"
    assert data["COMPATIBILITY_ADAPTATION_COUNT"] == 0
    assert data["CONFLICT_COUNT"] == 0
    assert {item["path"] for item in data["source_files"]} == set(SOURCE_FILES)


@pytest.mark.parametrize("path", SOURCE_FILES)
def test_source_content_and_git_blob_exact_parity(path: str) -> None:
    item = next(item for item in manifest()["source_files"] if item["path"] == path)
    content = (ROOT / path).read_bytes()
    assert hashlib.sha256(content).hexdigest() == item["source_sha256"]
    assert item["integrated_sha256"] == item["source_sha256"]
    header = f"blob {len(content)}\0".encode()
    assert hashlib.sha1(header + content).hexdigest() == item["source_blob"]
    assert item["integrated_blob"] == item["source_blob"]
    assert item["parity"] == "PASS"


def test_historical_evidence_is_not_rewritten_as_new_execution() -> None:
    data = manifest()
    original = json.loads((ROOT / SOURCE_FILES[3]).read_text())
    config = json.loads((ROOT / SOURCE_FILES[2]).read_text())
    assert original["base_sha"] == data["RESEARCH_EXECUTION_BASE_SHA"]
    assert original["execution_id"] == data["RESEARCH_EXECUTION_ID"]
    assert original["fold"]["train_seasons"] == ["2023-2024"]
    assert original["fold"]["test_season"] == "2024-2025"
    assert original["fold"]["train_sample_count"] == 15
    assert original["fold"]["test_sample_count"] == 22
    assert data["BACKTEST_FOLD_COUNT"] == 1
    assert original["metrics"] == data["frozen_metrics"]
    assert config["candidate_penalty"] == 1.0
    assert config["search"] is False
    assert config["holdout_refitted_into_final_artifact"] is False
    assert original["fold"]["artifact_file_hashes"] == data["artifact_file_hashes"]


def test_role_mapping_does_not_reseal_or_promote_artifact() -> None:
    data = manifest()
    assert data["V0_12_R1_MODEL_ROLE"] == "RESEARCH_CANDIDATE"
    assert data["V0_12_COMPARATOR_BASELINE"] == "V0_12_COMPARATOR_BASELINE"
    assert data["ORIGINAL_CANDIDATE_MODEL_ID"] == "NEXT_AREA_SIZE_20261002_R1_CANDIDATE"
    assert data["ARTIFACT_IDENTITY_REWRITTEN"] is False
    assert data["CANDIDATE_PROMOTED"] is False


@pytest.mark.parametrize(
    "field",
    [
        "SCIENTIFIC_RESULT_CHANGED",
        "MODEL_RETRAINED",
        "NEW_BACKTEST_EXECUTED",
        "NEW_FOLD_EXECUTED",
        "NEW_MODEL_SEARCH_EXECUTED",
        "NEW_HYPERPARAMETER_SEARCH_EXECUTED",
        "NEW_PRIVATE_DATA_READ",
        "NEW_REAL_PREDICTION",
        "TEMPORAL_SHAPE_GAIN",
        "SINGLE_PEAK_DATE_GAIN",
        "ROLLING_7DAY_PEAK_DATE_GAIN",
        "PR_659_STABLE_GAIN",
        "PR_659_NEW_BLIND_VALIDATION",
        "PR_659_PROSPECTIVE_VALIDATION",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "V0_12_VERSION_COMPLETE",
        "V0_12_S2_AUTHORIZED",
        "PR_659_MODIFIED",
        "S1_READY_AUTHORIZED",
        "S1_MERGE_AUTHORIZED",
        "TAG_CREATED",
        "RELEASE_CREATED",
        "AUTO_MERGE",
    ],
)
def test_no_new_science_or_follow_on_authorization(field: str) -> None:
    assert manifest()[field] is False


def test_s0_snapshot_is_preserved_and_s1_has_new_authority() -> None:
    data = manifest()
    s0 = json.loads((ROOT / "docs/v0-12/evidence/v0.12.0-scope-freeze-r1.json").read_text())
    assert s0["V0_12_S1_AUTHORIZED"] is False
    assert data["V0_12_S1_AUTHORIZED"] is True
    assert data["PARENT_TASK_ID"] == "V0_12_S0_MERGE_AND_S1_FROZEN_R1_INTEGRATION"
    assert data["V0_12_S0_COMPLETE"] is True
    assert data["V0_12_S1_COMPLETE"] is True
    assert data["INTEGRATION_DELIVERY_STATUS"] == "DRAFT_REVIEW_PENDING_NOT_MERGED"
    assert data["PR_659_SINGLE_FOLD_GAIN_OBSERVED"] is True
    assert data["NEXT_GATE"] == "V0.12-S2_REQUIRES_NEW_INFORMATION_AND_SEPARATE_AUTHORIZATION"
