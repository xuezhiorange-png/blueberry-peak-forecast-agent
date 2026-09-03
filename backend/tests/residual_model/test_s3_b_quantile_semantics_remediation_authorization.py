"""S3-B quantile semantics remediation implementation authorization fence tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.app.rolling_backtest.canonical import sha256_payload

PARENT_CONTRACT_PATH = Path("docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md")
PARENT_CONTRACT_WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-contract-r1.md"
)
PARENT_CONTRACT_EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-contract-r1.json"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-authorization.json"
)
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "46f1e2b9ffccf9998ab73ca92e450f049cab00d9"
BASE_MAIN_TREE_SHA = "088b4aae37cba7ac8d365b32f5f770666517d86b"
PARENT_CONTRACT_PR = 535
PARENT_CONTRACT_HEAD = "36a06c2408c0645d61532e3651decadb99070a75"
PARENT_CONTRACT_MERGE = "46f1e2b9ffccf9998ab73ca92e450f049cab00d9"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad"
)
PARENT_CONTRACT_DOC_BLOB = "e15679aab10b1112c88779faec0cd5ac30773771"
PARENT_CONTRACT_WORKPAPER_BLOB = "ddbf38af7c8f353f14f9169e2d65fb7b1c8a28c0"
PARENT_CONTRACT_EVIDENCE_BLOB = "b145ebb1c6972257310210d47387b2e8aa7f74a6"
GRANT_EVIDENCE_JSON_SHA256 = "78137b0a227853ad1449787efaee0ef3d2776e97a54f1faeec0dad0720fd3498"

GRANT_POINTER_HEADING = (
    "#### S3-B quantile semantics remediation implementation authorization pointer"
)
CONTRACT_POINTER_HEADING = "#### S3-B quantile semantics remediation contract pointer"

AUTHORIZED_FUTURE_PRODUCTION_CHANGE_ALLOWLIST = [
    "backend/app/residual_model/dataset.py",
    "backend/app/residual_model/model.py",
    "backend/app/residual_model/service.py",
    "backend/app/residual_model/projection.py",
    "backend/app/residual_model/config.py",
    "backend/app/residual_model/training_manifest.py",
    "backend/app/residual_model/schemas.py",
    "backend/app/residual_model/persistence.py",
    "backend/app/residual_model/replay_training_authority.py",
    "backend/app/residual_model/application.py",
    "backend/app/core_forecast/service.py",
]

FORBIDDEN_FUTURE_PRODUCTION_CHANGE_LIST = [
    "backend/app/models/residual_model.py",
    "backend/app/api/rolling_backtest_replay_trained.py",
    "backend/app/api/residual_model.py",
    "backend/app/harvest_state/service.py",
    "backend/app/maturity/model.py",
    "backend/app/maturity/service.py",
    "backend/app/maturity/calibration.py",
    "backend/alembic/**",
    "alembic/**",
    "sql/**",
]


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def test_grant_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert embedded == GRANT_EVIDENCE_JSON_SHA256


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    assert PARENT_CONTRACT_PATH.is_file()


def test_parent_contract_pins_and_blobs_exact() -> None:
    assert _git_blob(PARENT_CONTRACT_PATH) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(PARENT_CONTRACT_WORKPAPER_PATH) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(PARENT_CONTRACT_EVIDENCE_PATH) == PARENT_CONTRACT_EVIDENCE_BLOB
    payload = json.loads(PARENT_CONTRACT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == PARENT_CONTRACT_EVIDENCE_JSON_SHA256


def test_grant_evidence_authorization_metadata() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["artifact_id"] == (
        "V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_AUTHORIZATION"
    )
    assert payload["task_id"] == "V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_R1"
    assert payload["task_class"] == "IMPLEMENTATION_AUTHORIZATION_ISSUANCE_ONLY"
    assert payload["authorization_scope"] == (
        "S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_ONLY"
    )
    assert payload["user_gate"] == "授权"
    assert payload["interpreted_gate"] == (
        "S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_AUTHORING_ONLY"
    )
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["parent_contract_head"] == PARENT_CONTRACT_HEAD
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_workpaper_blob"] == PARENT_CONTRACT_WORKPAPER_BLOB
    assert payload["parent_contract_evidence_blob"] == PARENT_CONTRACT_EVIDENCE_BLOB
    assert payload["canonical_option"] == "FINAL_TARGET_DIRECT_QUANTILE_MODEL"
    assert payload["final_target_y"] == "model_harvested_marketable_quantity_kg"
    assert payload["final_target_actual_label"] == "actual_harvest_quantity_kg"
    assert (
        payload["final_target_actuals_authority"]
        == "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION"
    )
    assert payload["prediction_target_kind"] == "FINAL_TARGET_QUANTILE"
    assert payload["quantile_levels"] == ["0.50", "0.80", "0.90"]
    assert (
        payload["quantile_crossing_policy"]
        == "DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION"
    )
    assert (
        payload["fallback_quantile_semantics_policy"] == "FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT"
    )
    assert (
        payload["final_target_manifest_persistence_policy"] == "TRAINING_RUN_MANIFEST_SNAPSHOT_JSON"
    )
    assert payload["legacy_residual_manifest_row_policy"] == "LEGACY_RECEIPT_RESIDUAL_LANE_ONLY"
    assert payload["final_target_rows_write_legacy_residual_model_manifest_row"] is False
    assert payload["migration_required"] is False
    assert payload["authorized_future_production_change_allowlist"] == (
        AUTHORIZED_FUTURE_PRODUCTION_CHANGE_ALLOWLIST
    )
    assert payload["forbidden_future_production_change_list"] == (
        FORBIDDEN_FUTURE_PRODUCTION_CHANGE_LIST
    )
    assert payload["train_and_validation_only"] is True
    assert payload["test_remains_sealed"] is True
    scope = payload["implementation_scope_granted"]
    assert scope["s3_b_quantile_semantics_remediation_implementation_scope_granted"] is True
    assert payload["implementation_r1_user_gate_satisfied"] is False
    assert payload["implementation_execution_authorized_now"] is False
    assert payload["current_p50_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["current_p80_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["current_p90_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["s3_b_coverage_execution_authorized"] is False
    assert payload["current_s3_daily_rowset_completeness_verified"] is False
    assert payload["current_v0_3_s3_complete"] is False
    assert payload["v0_3_s4_authorized"] is False
    assert payload["grant_review_ready"] is True
    assert payload["ready_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["next_task_authorized"] is False
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_implementation_r1"] is True


def test_grant_workpaper_tokens() -> None:
    workpaper = GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=授权" in workpaper
    assert (
        "INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_AUTHORING_ONLY"
        in workpaper
    )
    assert "GRANT_ONLY=true" in workpaper
    assert "THIS_PR_IS_NOT_IMPLEMENTATION_R1=true" in workpaper
    assert "CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL" in workpaper
    assert "MIGRATION_REQUIRED=false" in workpaper
    assert "S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_SCOPE_GRANTED=true" in workpaper
    assert "IMPLEMENTATION_R1_USER_GATE_SATISFIED=false" in workpaper
    assert "CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED" in workpaper
    assert f"EVIDENCE_JSON_SHA256={GRANT_EVIDENCE_JSON_SHA256}" in workpaper
    assert f"PARENT_CONTRACT_PR={PARENT_CONTRACT_PR}" in workpaper
    assert f"PARENT_CONTRACT_MERGE={PARENT_CONTRACT_MERGE}" in workpaper


def test_grant_pointer_appended_to_development_plan() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    assert plan.count(CONTRACT_POINTER_HEADING) == 1
    assert plan.count(GRANT_POINTER_HEADING) == 1
    grant_snapshot = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if "### 4.5" in grant_snapshot:
        grant_snapshot = grant_snapshot.split("### 4.5", 1)[0]
    assert GRANT_EVIDENCE_JSON_SHA256 in grant_snapshot
    assert PARENT_CONTRACT_EVIDENCE_JSON_SHA256 in grant_snapshot
    assert "S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_SCOPE_GRANTED=true" in grant_snapshot
    assert "S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AUTHORIZED=true" in grant_snapshot
    assert "IMPLEMENTATION_R1_USER_GATE_SATISFIED=false" in grant_snapshot
    assert "IMPLEMENTATION_EXECUTION_AUTHORIZED_NOW=false" in grant_snapshot
    assert "CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED" in grant_snapshot
    assert "S3_B_COVERAGE_EXECUTION_AUTHORIZED=false" in grant_snapshot
    assert "TEST_REMAINS_SEALED=true" in grant_snapshot
    assert "CURRENT_V0_3_S3_COMPLETE=false" in grant_snapshot
    assert "V0_3_S4_AUTHORIZED=false" in grant_snapshot
    assert "READY_AUTHORIZED=false" in grant_snapshot
    assert "MERGE_AUTHORIZED=false" in grant_snapshot
    assert "NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_REVIEW" in grant_snapshot
