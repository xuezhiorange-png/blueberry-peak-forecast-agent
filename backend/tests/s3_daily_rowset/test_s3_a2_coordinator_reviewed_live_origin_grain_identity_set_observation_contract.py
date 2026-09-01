"""S3-A2 coordinator-reviewed live-origin grain identity-set observation contract freeze tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ORIGIN_MODEL_ID,
    ORIGIN_QUANTILES,
    last_legal_cutoff_before_test,
    replay_identity_origin_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
    reviewed_grain_identity_set_artifact_available,
)
from backend.app.s3_daily_rowset.registry import V0_3_S3_FORECASTS_AUTHORITY
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_closeout import (
    CompletenessPassCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_CUTOFF_BUSINESS_DATE,
    REVIEW_MEMBER_COUNT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    load_coordinator_reviewed_live_origin_grain_identity_set,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
    DefaultCatalogBindableRepositoryClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
    EvaluationInstanceRegistryAvailableCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
    ReviewedSetCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.window import cutoff_business_date
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import assert_forecast_artifact_py_historical_blob_pinned

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
CONSTRUCTION_MODULE_BLOB = "39b3a06bc768b728e5b283c1720a8f38ed5ff71a"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
REVIEWED_SET_CLOSEOUT_PY_BLOB = "ab9e2edf2e157b80dca5e230129374f5ac97810c"
COMPLETENESS_PY_BLOB = "06b778b75710a0de30035569d15c8e3d87b095d4"
COMPLETENESS_PASS_CLOSEOUT_PY_BLOB = "d1a6654b7f584c6e944628ecc63265ab8f9a1e7e"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
IDENTITY_SET_LANDING_PY_BLOB = "2ce94233f153f8e5297e4b978243323ca917dcf8"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB = "07335abbf900611c2c7f990bc7a0b92a485e111d"
PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB = "f46e0d7330b022185b55dbea31d381d1a9757d04"
PARENT_IDENTITY_SET_CONTRACT_DOC_BLOB = "ea729fc2e31d305a5f40baf2cbf028e9645d5745"
PARENT_IDENTITY_SET_CONTRACT_WORKPAPER_BLOB = "48bdd85f6bbcf5aebe225e8bbb0296090e6d10db"
PARENT_IDENTITY_SET_CONTRACT_EVIDENCE_BLOB = "c37aaf9c2de67e7c2ee788970378be339fc8e562"
PARENT_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "df08ff6b70c079c3bc36f9841ecb8c9cb3eaeed7fdf4064990f8354994126dc2"
)
PARENT_IDENTITY_SET_GRANT_WORKPAPER_BLOB = "346b524ff947004470d171ea54b8ec71d96152d8"
PARENT_IDENTITY_SET_GRANT_EVIDENCE_BLOB = "ed6bb06c72817bb21880c28ee8cc7961c5f03b0b"
PARENT_IDENTITY_SET_GRANT_EVIDENCE_JSON_SHA256 = (
    "c6562788955093db383036dbf2f784888969c5e593d195e68f21a68cee868f93"
)
PARENT_IDENTITY_SET_R1_WORKPAPER_BLOB = "9acd70071aaabdf9eda61eacb1ef2f826251570e"
PARENT_IDENTITY_SET_R1_EVIDENCE_BLOB = "3d3c0879be1b74a5db8ae203cef7f50a0e60a672"
PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256 = (
    "ac5fe6cd2ca3e108bf46d3c7bb7572f50407ae3f641c1936fc846314d6001df3"
)
PARENT_IDENTITY_SET_R1_PR = 503
PARENT_IDENTITY_SET_R1_COMMIT = "2a678dcaf02a766c8eb3158090d1e411d77d620b"
PARENT_IDENTITY_SET_R1_MERGE = "1a788e614e58989ed6b777c2c0a4392931dab4fa"
PARENT_IDENTITY_SET_GRANT_PR = 502
PARENT_IDENTITY_SET_GRANT_COMMIT = "71c2186b6cfeb1cf844c739ba7a24494521ffe42"
PARENT_IDENTITY_SET_GRANT_MERGE = "eb239e0dfd3cb123742ad163157815fe123ef099"
PARENT_IDENTITY_SET_CONTRACT_PR = 500
PARENT_IDENTITY_SET_CONTRACT_COMMIT = "7b0fad18d8daa52dc912883b2dc8e2bb50185d48"
PARENT_IDENTITY_SET_CONTRACT_MERGE = "7b32e0a97d2428c9621de312d24d6fc3be8a93fa"
BASE_MAIN_SHA = "1a788e614e58989ed6b777c2c0a4392931dab4fa"
BASE_MAIN_TREE_SHA = "a80be7c7a746f151808d998699d29b8d610e5c97"
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"

CONTRACT_PATH = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.json"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation.py"
)
LANDING_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
UNIQUE_FLIP = (
    "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_CONTRACT_AUTHORIZED"
)
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


def _git_blob(path: str | Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_live_origin_policy_grains_match_coordinator_review_pins() -> None:
    entries = replay_identity_origin_entries()
    assert len(entries) == 3
    cutoff = last_legal_cutoff_before_test()
    assert cutoff_business_date(cutoff) == date(2026, 2, 16)
    assert ORIGIN_MODEL_ID == V0_3_S3_FORECASTS_AUTHORITY
    assert ORIGIN_QUANTILES == ("P50", "P80", "P90")
    assert all(entry.forecast_cutoff_at == cutoff for entry in entries)
    assert all(entry.model_id == ORIGIN_MODEL_ID for entry in entries)
    assert tuple(entry.forecast_quantile for entry in entries) == ORIGIN_QUANTILES
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "REVIEW_MODEL_ID=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF" in text
    assert "REVIEW_QUANTILES=P50,P80,P90" in text
    assert "REVIEW_MEMBER_COUNT=3" in text
    assert f"REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256={REVIEWED_SET_IDENTITY_SHA256}" in text


def test_frozen_python_and_parent_blobs_unchanged() -> None:
    assert _git_blob("backend/tests/s3_daily_rowset/test_catalog_artifact.py") == (
        TEST_CATALOG_ARTIFACT_PY_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/catalog_artifact.py") == CATALOG_ARTIFACT_PY_BLOB
    assert (
        _git_blob(
            "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
        )
        == GRAIN_IDENTITY_SET_PY_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
        == CONTENT_PRODUCER_PY_BLOB
    )
    assert (
        _git_blob("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
        == ALEMBIC_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
        == OBTAIN_MODULE_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py")
        == CONSTRUCTION_MODULE_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/binding.py") == BINDING_PY_BLOB
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py")
        == BINDABLE_REPOSITORY_PY_BLOB
    )
    assert (
        _git_blob(
            "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
        )
        == AVAILABLE_CLOSEOUT_PY_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
        == REVIEWED_SET_CLOSEOUT_PY_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/completeness.py") == COMPLETENESS_PY_BLOB
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py")
        == COMPLETENESS_PASS_CLOSEOUT_PY_BLOB
    )
    assert_forecast_artifact_py_historical_blob_pinned(FORECAST_ARTIFACT_PY_BLOB)
    assert (
        _git_blob("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py")
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB
    assert (
        _git_blob("docs/v0-3/s3/s3-reviewed-grain-identity-set-closeout-contract.md")
        == PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-completeness-pass-closeout-contract.md")
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-contract.md")
        == PARENT_IDENTITY_SET_CONTRACT_DOC_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
        )
        == PARENT_IDENTITY_SET_CONTRACT_WORKPAPER_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.json"
        )
        == PARENT_IDENTITY_SET_CONTRACT_EVIDENCE_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-authorization.md"
        )
        == PARENT_IDENTITY_SET_GRANT_WORKPAPER_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-authorization.json"
        )
        == PARENT_IDENTITY_SET_GRANT_EVIDENCE_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.md"
        )
        == PARENT_IDENTITY_SET_R1_WORKPAPER_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.json"
        )
        == PARENT_IDENTITY_SET_R1_EVIDENCE_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md")
        == PARENT_PRESENCE_CONTRACT_BLOB
    )


def test_landed_artifact_exists_and_default_global_loader_remains_empty() -> None:
    artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
    assert artifact.artifact_available is True
    assert artifact.reason_code is None
    assert len(artifact.members) == REVIEW_MEMBER_COUNT
    assert artifact.artifact_id == REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    assert artifact.artifact_id == REVIEWED_SET_IDENTITY_SHA256
    assert artifact.review_cutoff_at == REVIEW_CUTOFF_AT
    assert artifact.review_cutoff_business_date == date.fromisoformat(REVIEW_CUTOFF_BUSINESS_DATE)
    assert artifact.review_model_id == REVIEW_MODEL_ID
    assert artifact.review_quantiles == REVIEW_QUANTILES
    assert tuple(member.forecast_quantile for member in artifact.members) == ORIGIN_QUANTILES
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_frozen_closeouts_still_report_no_reviewed_and_pass_unauthorized() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
        reviewed = ReviewedGrainIdentitySetCloseoutClassifier().classify()
        completeness = CompletenessPassCloseoutClassifier().classify()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )
    assert produced.no_bindable_catalog_in_repository is True
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.reason_code is ReviewedSetCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert reviewed.coordinator_reviewed_identity_set_exists is False
    assert reviewed.reviewed_identity_set_member_count == 0
    assert completeness.s3_a2_completeness_pass_authorized is False
    assert completeness.no_reviewed_grain_identity_set_in_repository is True
    assert completeness.live_origin_grains_are_reviewed_set is False
    assert completeness.coordinator_reviewed_identity_set_exists is False
    assert completeness.weather_and_plans_block_completeness_pass is True
    assert load_reviewed_grain_identity_set() == ()
    assert reviewed_grain_identity_set_artifact_available() is False


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
        in text
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in text
    )
    assert "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=true" in (
        text
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in text
    assert "FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED=true" in text
    assert "FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "USER_GATE=可以继续" in text
    assert "CONTRACT_GATE_ACCEPTED_AS=可以下一步" in text
    assert "USER_UTTERANCE=可以继续  天气和种植计划 放到下个版本" in text
    assert "CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_OBSERVATION=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWIRE_GLOBAL_REVIEWED_SET_LOADER=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_REVIEWED_SET_CLOSEOUT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_COMPLETENESS_PASS_CLOSEOUT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_COMPLETENESS_PASS_AUTHORIZED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_INVENT_WEATHER=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_INVENT_PLANS=true" in text
    assert "FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true" in text
    assert "FORBIDDEN_INVENT_ADDITIONAL_MEMBERS=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert "WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS=true" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert f"PARENT_IDENTITY_SET_R1_PR={PARENT_IDENTITY_SET_R1_PR}" in text
    assert f"PARENT_IDENTITY_SET_R1_COMMIT={PARENT_IDENTITY_SET_R1_COMMIT}" in text
    assert f"PARENT_IDENTITY_SET_R1_MERGE={PARENT_IDENTITY_SET_R1_MERGE}" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert f"BASE_MAIN_TREE_SHA={BASE_MAIN_TREE_SHA}" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_evidence_json_sha256_matches_payload_without_self_key() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    digest = payload["evidence_json_sha256"]
    assert len(digest) == 64
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == digest
    assert payload["authorization"][
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation_contract_authorized"
    ]
    assert not payload["authorization"][
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation_implementation_authorized"
    ]
    assert not payload["authorization"][
        "deterministic_coordinator_reviewed_live_origin_grain_identity_set_observation_implemented"
    ]
    assert payload["authorization"][
        "deterministic_coordinator_reviewed_live_origin_grain_identity_set_implemented"
    ]
    assert payload["authorization"]["no_reviewed_grain_identity_set_in_repository"] is False
    assert payload["authorization"]["default_global_reviewed_set_loader_remains_empty"] is True
    assert payload["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert payload["authorization"]["no_bindable_catalog_in_repository"] is True
    assert payload["authorization"]["evaluation_instance_registry_available"] is False
    assert payload["reviewed_artifact"]["review_member_count"] == 3
    assert payload["reviewed_artifact"]["review_cutoff_business_date"] == "2026-02-16"
    assert payload["reviewed_artifact"]["identity_sha256"] == REVIEWED_SET_IDENTITY_SHA256
    assert payload["weather_and_plans"]["weather_and_plans_deferred_to_next_version"] is True
    assert payload["weather_and_plans"]["weather_and_plans_do_not_block_non_curve_implementation"]
    assert payload["weather_and_plans"]["weather_and_plans_block_completeness_pass"] is True
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True
    assert payload["parent_identity_set_r1"]["parent_identity_set_r1_pr"] == (
        PARENT_IDENTITY_SET_R1_PR
    )
    assert payload["parent_identity_set_r1"]["parent_identity_set_r1_commit"] == (
        PARENT_IDENTITY_SET_R1_COMMIT
    )
    assert payload["parent_identity_set_r1"]["parent_identity_set_r1_merge"] == (
        PARENT_IDENTITY_SET_R1_MERGE
    )
    assert payload["parent_identity_set_r1"]["parent_identity_set_r1_evidence_json_sha256"] == (
        PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_identity_set_grant"]["parent_identity_set_grant_pr"] == (
        PARENT_IDENTITY_SET_GRANT_PR
    )
    assert payload["parent_identity_set_grant"]["parent_identity_set_grant_commit"] == (
        PARENT_IDENTITY_SET_GRANT_COMMIT
    )
    assert payload["parent_identity_set_grant"]["parent_identity_set_grant_merge"] == (
        PARENT_IDENTITY_SET_GRANT_MERGE
    )
    assert (
        payload["parent_identity_set_grant"]["parent_identity_set_grant_evidence_json_sha256"]
        == PARENT_IDENTITY_SET_GRANT_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_identity_set_contract"]["parent_identity_set_contract_pr"] == (
        PARENT_IDENTITY_SET_CONTRACT_PR
    )
    assert payload["parent_identity_set_contract"]["parent_identity_set_contract_commit"] == (
        PARENT_IDENTITY_SET_CONTRACT_COMMIT
    )
    assert payload["parent_identity_set_contract"]["parent_identity_set_contract_merge"] == (
        PARENT_IDENTITY_SET_CONTRACT_MERGE
    )
    assert (
        payload["parent_identity_set_contract"]["parent_identity_set_contract_evidence_json_sha256"]
        == PARENT_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256
    )
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以继续" in text
    assert "CONTRACT_ONLY=true" in text
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert f"{UNIQUE_FLIP}=true" in text
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
        in text
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in text
    )
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_development_plan_live_compact_flips_only_observation_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=true" in (
        live_intro
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
        in contract
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in contract
    )
    pointer = text.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md" in (
        pointer
    )
    r1_pointer = text.split(
        "#### Coordinator-reviewed live-origin grain identity-set R1 pointer", 1
    )[1]
    if "#### Coordinator-reviewed live-origin grain identity-set observation contract pointer" in (
        r1_pointer
    ):
        r1_pointer = r1_pointer.split(
            "#### Coordinator-reviewed live-origin grain identity-set observation contract pointer",
            1,
        )[0]
    assert UNIQUE_FLIP not in r1_pointer
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.md" in r1_pointer


def test_amendment_records_observation_contract_pointer_and_isolates_section_189() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "## 189. Coordinator-reviewed live-origin grain identity-set R1 pointer" in text
    assert (
        "## 190. Coordinator-reviewed live-origin grain identity-set observation contract pointer"
        in text
    )
    assert f"{UNIQUE_FLIP}=true" in text
    section_189 = text.split("## 189.", 1)[1]
    if "## 190." in section_189:
        section_189 = section_189.split("## 190.", 1)[0]
    assert "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=true" in (
        section_189
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in section_189
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_189
    assert UNIQUE_FLIP not in section_189
    section_190 = text.split("## 190.", 1)[1]
    if "## 191." in section_190:
        section_190 = section_190.split("## 191.", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in section_190
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
        in section_190
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in section_190
    )
    assert "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=true" in (
        section_190
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in section_190
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in section_190
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_190
    assert PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256 in section_190
    assert PARENT_IDENTITY_SET_R1_COMMIT in section_190
    lowered = section_190.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_this_contract_freeze_does_not_create_the_observation_production_module() -> None:
    assert LANDING_MODULE.is_file()
    assert PRODUCTION_MODULE.name == (
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation.py"
    )
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "THIS_PR_IS_NOT_R1=true" in contract
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_OBSERVATION=true" in contract
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in contract
    )
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert Path(
        "backend/app/s3_daily_rowset/incumbent_forecast_replay_identity_origin.py"
    ).is_file()
