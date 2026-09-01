"""S3-A2 reviewed grain identity-set closeout R1 tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s3_daily_rowset.binding import BindingClassification, BindingReasonCode
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    land_replay_identity_origin_into_sync_session,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
    ReviewedSetCloseoutReasonCode,
)
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
    assert_forecast_artifact_py_historical_blob_pinned,
)
from backend.tests.s3_daily_rowset.test_s3_a2_live_catalog_execution import (
    TEST_CATALOG_ARTIFACT_PY_BLOB,
    _in_season_rows,
    _patch_official_counts,
    _session_maker_with_rows,
)

CLASSIFIER_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py"
)
AVAILABLE_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
)
BINDABLE_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py")
CONSTRUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py"
)
OBTAIN_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
BINDING_PY = Path("backend/app/s3_daily_rowset/binding.py")
TEST_CATALOG_PY = Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")
GRAIN_PY = Path(
    "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
)
CONTENT_PY = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
ALEMBIC_PY = Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
CONSTRUCTION_MODULE_BLOB = "39b3a06bc768b728e5b283c1720a8f38ed5ff71a"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
ALIGNMENT_EVIDENCE_PY = Path(
    "backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-reviewed-grain-identity-set-closeout-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-reviewed-grain-identity-set-closeout-authorization.json"
)
R1_WORKPAPER = Path("docs/v0-3/s3/workpapers/s3-a2-reviewed-grain-identity-set-closeout-r1.md")
R1_EVIDENCE = Path("docs/v0-3/s3/evidence/s3-a2-reviewed-grain-identity-set-closeout-r1.json")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "d2a2d3fcfa685599f8eef24941d43927ef0917e5c65e36c2722348e5da26df81"
)
PARENT_GRANT_MERGE = "1bbdc5a71c362f4e7fa41338a9af97f78a14af48"
PARENT_GRANT_COMMIT = "8d0577a145d2abe36947c096f79a36f3cd9bc1bf"
PARENT_CONTRACT_COMMIT = "aac0f7bef83d1dfa45b5f822175338abfa009328"
PARENT_CONTRACT_MERGE = "a66d30cc3d2d8940eef7737819e0729da3b8f17a"
PARENT_GRANT_WORKPAPER_BLOB = "3d1a9ffc4425f90736a7896fb4ea86d4000b9663"
PARENT_GRANT_EVIDENCE_BLOB = "872a1ea0f187c4a11bde993bd655738110f72b69"
UNIQUE_FLIP = "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED"
FORBIDDEN_PROSE_TOKENS = (
    "localhost",
    "5432",
    "psycopg",
    "content_bytes",
    "postgresql://",
    "greenlet",
    "MissingGreenlet",
    "OSError",
)


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _assert_harvest_replay_and_provider_remain_empty() -> None:
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_classifier_module_does_not_land_or_embed_connection_strings() -> None:
    source = CLASSIFIER_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "land_replay_identity_origin" not in source
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "content_bytes" not in source
    assert "sqlalchemy" not in lowered
    assert "dsn" not in lowered


def test_frozen_blobs_unchanged() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(GRAIN_PY) == GRAIN_IDENTITY_SET_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(ALEMBIC_PY) == ALEMBIC_BLOB
    assert _git_blob(OBTAIN_MODULE) == OBTAIN_MODULE_BLOB
    assert _git_blob(CONSTRUCTION_MODULE) == CONSTRUCTION_MODULE_BLOB
    assert _git_blob(BINDABLE_MODULE) == BINDABLE_REPOSITORY_PY_BLOB
    assert _git_blob(AVAILABLE_MODULE) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert_forecast_artifact_py_historical_blob_pinned(FORECAST_ARTIFACT_PY_BLOB)
    assert _git_blob(ALIGNMENT_EVIDENCE_PY) == ALIGNMENT_EVIDENCE_PY_BLOB
    assert _git_blob(GRANT_WORKPAPER) == PARENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(GRANT_EVIDENCE) == PARENT_GRANT_EVIDENCE_BLOB


def test_fail_closed_when_session_maker_unavailable() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        result = ReviewedGrainIdentitySetCloseoutClassifier().classify()
    assert result.reason_code is ReviewedSetCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert result.catalog_produced is False
    assert result.catalog_identity_sha256 is None
    assert result.available_closeout_reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert (
        result.bindable_repository_reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    )
    assert result.coordinator_reviewed_identity_set_exists is False
    assert result.live_origin_grains_are_reviewed_set is False
    assert result.reviewed_identity_set_member_count == 0
    assert result.no_reviewed_grain_identity_set_in_repository is True
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    _assert_harvest_replay_and_provider_remain_empty()


def test_patched_session_maker_classifies_produced_catalog_preconditions_not_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    train_rows, validation_rows = _in_season_rows()
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    async def _land() -> None:
        async with session_maker() as session:
            await session.run_sync(land_replay_identity_origin_into_sync_session)

    asyncio.run(_land())

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        result = ReviewedGrainIdentitySetCloseoutClassifier().classify()

    assert result.reason_code is (
        ReviewedSetCloseoutReasonCode.REVIEWED_SET_CLOSEOUT_PRECONDITIONS_NOT_MET
    )
    assert result.catalog_produced is True
    assert result.catalog_identity_sha256 is not None
    assert result.catalog_entry_count == 6
    assert (
        result.available_closeout_reason_code
        is AvailableCloseoutReasonCode.AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET
    )
    assert result.bindable_repository_reason_code is BindableRepositoryReasonCode.NOT_BINDABLE
    assert result.binding_classification is BindingClassification.NOT_BINDABLE
    assert result.binding_reason_code is BindingReasonCode.NOT_BINDABLE
    assert result.in_memory_structural_acceptance is True
    assert result.coordinator_reviewed_identity_set_exists is False
    assert result.live_origin_grains_are_reviewed_set is False
    assert result.reviewed_identity_set_member_count == 0
    assert result.no_reviewed_grain_identity_set_in_repository is True
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert SOURCE_002_ROW_LEVEL_READ is True
    _assert_harvest_replay_and_provider_remain_empty()


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"]["S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED"]
    assert payload["flags"][UNIQUE_FLIP] is False
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED"]
    assert r1["flags"]["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert r1["flags"]["WEATHER_UNAVAILABLE"] is True
    assert r1["flags"]["PLANS_UNAVAILABLE"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_WEATHER"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_PLANS"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is True
    assert r1["flags"]["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert r1["flags"]["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert r1["flags"]["DEFAULT_HARVEST_OBTAIN_EMPTY"] is True
    assert r1["flags"]["AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP"] is True
    assert r1["flags"]["FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET"] is True
    assert r1["flags"]["FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002"] is True
    assert GRANT_WORKPAPER.is_file()
    assert R1_WORKPAPER.is_file()


def test_r1_evidence_sha256_payload_matches_embedded_digest() -> None:
    from backend.app.rolling_backtest.canonical import sha256_payload

    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_r1_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert UNIQUE_FLIP + "=true" in live_intro
    assert "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=true" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    assert "s3-a2-reviewed-grain-identity-set-closeout-r1.md" in plan
    assert "## 183." in amendment
    assert "## 182." in amendment
    assert "## 181." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in plan
    grant_snapshot = amendment.split("## 182.", 1)[1]
    if "## 183." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 183.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-reviewed-grain-identity-set-closeout-r1.md" in contract_pointer


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper


def test_official_live_reviewed_set_closeout_fail_closed_or_preconditions_not_met() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
)
result = ReviewedGrainIdentitySetCloseoutClassifier().classify()
clear_v0_2_live_postgres_session_provider()
print(json.dumps({
    "reason_code": result.reason_code.value,
    "catalog_produced": result.catalog_produced,
    "catalog_identity_sha256": result.catalog_identity_sha256,
    "catalog_entry_count": result.catalog_entry_count,
    "available_closeout_reason_code": (
        result.available_closeout_reason_code.value
        if result.available_closeout_reason_code else None
    ),
    "bindable_repository_reason_code": (
        result.bindable_repository_reason_code.value
        if result.bindable_repository_reason_code else None
    ),
    "binding_classification": (
        result.binding_classification.value if result.binding_classification else None
    ),
    "completeness_verified": result.current_s3_daily_rowset_completeness_verified,
    "no_reviewed": result.no_reviewed_grain_identity_set_in_repository,
    "no_bindable": result.no_bindable_catalog_in_repository,
    "registry_available": result.evaluation_instance_registry_available,
    "coordinator_reviewed_identity_set_exists": (
        result.coordinator_reviewed_identity_set_exists
    ),
    "live_origin_grains_are_reviewed_set": result.live_origin_grains_are_reviewed_set,
    "reviewed_identity_set_member_count": result.reviewed_identity_set_member_count,
    "default_harvest_after": S2IdentityAlignmentHarvestSource().obtain() == (),
    "default_replay_after": IncumbentForecastReplaySource().obtain() == (),
    "bindable_after": read_bindable_replay_identity_rows() == (),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload["no_reviewed"] is True
    assert payload["no_bindable"] is True
    assert payload["registry_available"] is False
    assert payload["completeness_verified"] is False
    assert payload["coordinator_reviewed_identity_set_exists"] is False
    assert payload["live_origin_grains_are_reviewed_set"] is False
    assert payload["reviewed_identity_set_member_count"] == 0
    assert payload["default_harvest_after"] is True
    assert payload["default_replay_after"] is True
    assert payload["bindable_after"] is True
    if payload["reason_code"] == "REVIEWED_SET_CLOSEOUT_PRECONDITIONS_NOT_MET":
        assert payload["catalog_produced"] is True
        assert payload["catalog_identity_sha256"]
        assert payload["catalog_entry_count"] > 0
        assert payload["catalog_entry_count"] % 3 == 0
        assert payload["available_closeout_reason_code"] == (
            "AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET"
        )
        assert payload["bindable_repository_reason_code"] == "NOT_BINDABLE"
        assert payload["binding_classification"] == "NOT_BINDABLE"
        assert OFFICIAL_TRAIN_ROW_COUNT == 16224
        assert OFFICIAL_VALIDATION_ROW_COUNT == 8006
    else:
        assert payload["reason_code"] == "CATALOG_NOT_PRODUCED"
        assert payload["catalog_produced"] is False
        assert payload["catalog_identity_sha256"] is None


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert CLASSIFIER_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
