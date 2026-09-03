"""S3-B quantile semantics remediation grant amendment authorization fence tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.harvest_state.canonical import sha256_hex
from backend.app.rolling_backtest.canonical import sha256_payload

PARENT_CONTRACT_EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-contract-r1.json"
)
PARENT_GRANT_EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-authorization.json"
)
CONTRACT_AMENDMENT_EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-contract-amendment-r1.json"
)
GRANT_AMENDMENT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-authorization-amendment-r1.md"
)
GRANT_AMENDMENT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-authorization-amendment-r1.json"
)
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "e3ba3b4fdd1f4c625f342fd55b96826728a1afc9"
BASE_MAIN_TREE_SHA = "801c2ff83c29bdb7df95bec3b2e65bd20612ea1b"
PARENT_CONTRACT_PR = 535
PARENT_CONTRACT_MERGE = "46f1e2b9ffccf9998ab73ca92e450f049cab00d9"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad"
)
PARENT_GRANT_PR = 536
PARENT_GRANT_MERGE = "c74cd2c541fe48b78b5a84de87ef10c16eee976e"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "78137b0a227853ad1449787efaee0ef3d2776e97a54f1faeec0dad0720fd3498"
)
PARENT_CONTRACT_AMENDMENT_PR = 538
PARENT_CONTRACT_AMENDMENT_HEAD = "eff8848baf5f3da37328b59fad9c4edaca418836"
PARENT_CONTRACT_AMENDMENT_MERGE = "e3ba3b4fdd1f4c625f342fd55b96826728a1afc9"
PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256 = (
    "61ffb33d466aa8b3b4221793976481b8bac5448956b3a143c8cbde3bad7d2642"
)
BLOCKED_IMPLEMENTATION_PR = 537
BLOCKED_IMPLEMENTATION_HEAD = "43dbe2a3aec80086cba0c3d96b33795c906619de"
EXPECTED_ALEMBIC_HEAD = "e8b2c4d6f1a3"
AUTHORIZED_NEW_MIGRATION_PATH = (
    "backend/alembic/versions/f3a9b2c8d1e4_s3_b_final_target_quantile_prediction_lane.py"
)
AUTHORIZED_MIGRATION_DOWN_REVISION = "e8b2c4d6f1a3"

PARENT_GRANT_ALLOWLIST = [
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

AMENDMENT_ADDITIONS = [
    "backend/app/models/residual_model.py",
    "backend/app/residual_model/enums.py",
    AUTHORIZED_NEW_MIGRATION_PATH,
]

EFFECTIVE_FUTURE_PRODUCTION_CHANGE_ALLOWLIST = PARENT_GRANT_ALLOWLIST + AMENDMENT_ADDITIONS

GRANT_AMENDMENT_POINTER_HEADING = (
    "#### S3-B quantile semantics remediation implementation grant amendment R1 pointer"
)


def test_grant_amendment_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded


def test_parent_contract_evidence_pins_and_digest() -> None:
    payload = json.loads(PARENT_CONTRACT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == PARENT_CONTRACT_EVIDENCE_JSON_SHA256


def test_parent_grant_evidence_pins_and_digest() -> None:
    payload = json.loads(PARENT_GRANT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == PARENT_GRANT_EVIDENCE_JSON_SHA256


def test_contract_amendment_evidence_pins_and_digest() -> None:
    payload = json.loads(CONTRACT_AMENDMENT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_hex(stripped) == PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256
    assert payload["blocked_implementation_pr"] == BLOCKED_IMPLEMENTATION_PR
    assert payload["migration_required"] is True


def test_grant_amendment_evidence_base_main_pins() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA
    assert payload["audited_repository_sha"] == BASE_MAIN_SHA
    assert payload["audited_repository_tree_sha"] == BASE_MAIN_TREE_SHA


def test_grant_amendment_evidence_authorization_metadata() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["artifact_id"] == (
        "V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_AMENDMENT"
    )
    assert payload["task_id"] == "V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_R1"
    assert payload["task_class"] == "IMPLEMENTATION_GRANT_AMENDMENT_AUTHORIZATION_ISSUANCE_ONLY"
    assert payload["authorization_scope"] == (
        "S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_ONLY"
    )
    assert payload["user_gate"] == "授权"
    assert payload["interpreted_gate"] == (
        "S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_AUTHORING_ONLY"
    )
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_grant_pr"] == PARENT_GRANT_PR
    assert payload["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert payload["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_amendment_pr"] == PARENT_CONTRACT_AMENDMENT_PR
    assert payload["parent_contract_amendment_head"] == PARENT_CONTRACT_AMENDMENT_HEAD
    assert payload["parent_contract_amendment_merge"] == PARENT_CONTRACT_AMENDMENT_MERGE
    assert (
        payload["parent_contract_amendment_evidence_json_sha256"]
        == PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256
    )
    assert payload["blocked_implementation_pr"] == BLOCKED_IMPLEMENTATION_PR
    assert payload["blocked_implementation_head"] == BLOCKED_IMPLEMENTATION_HEAD
    assert payload["pr_537_blocker"] == (
        "FINAL_TARGET_PREDICTION_PERSISTENCE_SCHEMA_CONTRACT_MISMATCH"
    )
    assert payload["ci_success_does_not_override_contract_blocker"] is True


def test_migration_required_and_alembic_head() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["migration_required"] is True
    assert payload["alembic_head_count"] == 1
    assert payload["alembic_heads"] == [EXPECTED_ALEMBIC_HEAD]


def test_single_authorized_migration_path() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["authorized_new_migration_count"] == 1
    assert payload["authorized_new_migration_path"] == AUTHORIZED_NEW_MIGRATION_PATH
    assert payload["authorized_migration_down_revision"] == AUTHORIZED_MIGRATION_DOWN_REVISION
    assert payload["other_migration_files_authorized"] is False
    assert (
        payload["effective_future_production_change_allowlist"].count(AUTHORIZED_NEW_MIGRATION_PATH)
        == 1
    )


def test_effective_allowlist_includes_models_and_enums() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    allowlist = payload["effective_future_production_change_allowlist"]
    assert allowlist == EFFECTIVE_FUTURE_PRODUCTION_CHANGE_ALLOWLIST
    assert "backend/app/models/residual_model.py" in allowlist
    assert "backend/app/residual_model/enums.py" in allowlist
    assert payload["parent_grant_allowlist"] == PARENT_GRANT_ALLOWLIST
    for path in PARENT_GRANT_ALLOWLIST:
        assert path in allowlist


def test_parent_grant_allowlist_not_revoked() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_grant_allowlist"] == PARENT_GRANT_ALLOWLIST
    assert payload["amendment_additions"] == AMENDMENT_ADDITIONS
    assert set(PARENT_GRANT_ALLOWLIST).issubset(
        set(payload["effective_future_production_change_allowlist"])
    )


def test_final_target_task9_and_mode_semantics() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["task9_run_id_nullable"] is True
    assert payload["task9_result_hash_nullable"] is True
    assert payload["final_target_task9_run_id"] is None
    assert payload["final_target_task9_result_hash"] is None
    assert payload["fake_task9_authority_for_final_target"] is False
    assert payload["task9_run_id_zero_sentinel_forbidden"] is True
    assert payload["task9_result_hash_all_zero_sentinel_forbidden"] is True
    assert payload["final_target_prediction_mode"] == "final_target_quantile"
    assert payload["final_target_quantile_uses_residual_corrected_mode"] is False


def test_distinct_grain_count_and_lane_consistency() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["distinct_grain_count_column_required"] is True
    assert payload["db_lane_consistency_constraint_required"] is True
    assert payload["final_target_grain_count_stored_as_factory_count"] is False
    assert (
        payload["final_target_distinct_grain_count"]
        == "count_distinct_farm_subfarm_variety_in_train_rows"
    )


def test_amendment_change_required_flags() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    required = payload["amendment_change_required"]
    assert required["backend/app/models/residual_model.py"] is True
    assert required["backend/app/residual_model/enums.py"] is True
    assert required["backend/app/residual_model/service.py"] is True
    assert required["backend/app/residual_model/schemas.py"] is True
    assert required["backend/app/residual_model/persistence.py"] is True
    assert required["backend/app/residual_model/replay_training_authority.py"] is True
    assert required["backend/app/residual_model/application.py"] is True
    assert required["alembic_new_migration"] is True
    assert required["backend/app/residual_model/config.py"] is False
    assert required["backend/app/core_forecast/service.py"] is False


def test_governance_flags_remain_failed_and_sealed() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["test_remains_sealed"] is True
    assert payload["test_evaluation_authorized"] is False
    assert payload["s3_b_coverage_execution_authorized"] is False
    assert payload["current_p50_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["current_p80_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["current_p90_semantics_status"] == "VERIFICATION_FAILED"
    assert payload["current_v0_3_s3_complete"] is False
    assert payload["v0_3_s4_authorized"] is False


def test_implementation_and_migration_not_authorized_now() -> None:
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["implementation_authorized"] is False
    assert payload["migration_implementation_authorized"] is False
    assert payload["model_change_execution_authorized"] is False
    assert payload["training_authorized"] is False
    assert payload["ready_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["new_implementation_gate_required_after_grant_amendment_merge"] is True
    assert payload["old_implementation_gate_does_not_authorize_amended_scope"] is True


def test_grant_amendment_workpaper_tokens() -> None:
    workpaper = GRANT_AMENDMENT_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=授权" in workpaper
    assert (
        "INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_AUTHORING_ONLY"
        in workpaper
    )
    assert "GRANT_AMENDMENT_ONLY=true" in workpaper
    assert "NEW_MIGRATION_REQUIRED=true" in workpaper
    assert f"AUTHORIZED_NEW_MIGRATION_PATH={AUTHORIZED_NEW_MIGRATION_PATH}" in workpaper
    assert "CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED" in workpaper
    assert f"PARENT_GRANT_PR={PARENT_GRANT_PR}" in workpaper
    assert f"PARENT_CONTRACT_AMENDMENT_PR={PARENT_CONTRACT_AMENDMENT_PR}" in workpaper


def test_grant_amendment_pointer_appended_to_development_plan() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    assert plan.count(GRANT_AMENDMENT_POINTER_HEADING) == 1
    snapshot = plan.split(GRANT_AMENDMENT_POINTER_HEADING, 1)[1]
    if "### 4.5" in snapshot:
        snapshot = snapshot.split("### 4.5", 1)[0]
    payload = json.loads(GRANT_AMENDMENT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] in snapshot
    assert PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256 in snapshot
    assert PARENT_GRANT_EVIDENCE_JSON_SHA256 in snapshot
    assert "NEW_MIGRATION_REQUIRED=true" in snapshot
    assert "IMPLEMENTATION_AUTHORIZED=false" in snapshot
    assert "MIGRATION_IMPLEMENTATION_AUTHORIZED=false" in snapshot
    assert "READY_AUTHORIZED=false" in snapshot
    assert "MERGE_AUTHORIZED=false" in snapshot
    assert "NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_REVIEW" in snapshot
