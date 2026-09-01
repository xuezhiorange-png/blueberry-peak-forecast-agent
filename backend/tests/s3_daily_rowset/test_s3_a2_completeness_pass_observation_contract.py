"""S3-A2 completeness PASS observation contract freeze tests."""

from __future__ import annotations

from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import assert_forecast_artifact_py_historical_blob_pinned
import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset import (
    s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation as observation,
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
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_closeout import (
    CompletenessPassCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_MEMBER_COUNT,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
)

ObservationClassifier = (
    observation.CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier
)
ObservationReasonCode = observation.ObservationReasonCode

CONTRACT_PATH = Path("docs/v0-3/s3/s3-completeness-pass-observation-contract.md")
WORKPAPER_PATH = Path("docs/v0-3/s3/workpapers/s3-a2-completeness-pass-observation-contract.md")
EVIDENCE_PATH = Path("docs/v0-3/s3/evidence/s3-a2-completeness-pass-observation-contract.json")
PRODUCTION_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_completeness_pass_observation.py")
OBSERVATION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation.py"
)
LANDING_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
COMPLETENESS_PASS_CLOSEOUT_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py"
)
REVIEWED_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
OBSERVATION_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.md"
)
OBSERVATION_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.json"
)
OBSERVATION_CONTRACT = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
OBSERVATION_CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
OBSERVATION_CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.json"
)
OBSERVATION_GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.md"
)
OBSERVATION_GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.json"
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
CONSTRUCTION_MODULE_BLOB = "39b3a06bc768b728e5b283c1720a8f38ed5ff71a"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
REVIEWED_SET_CLOSEOUT_PY_BLOB = "ab9e2edf2e157b80dca5e230129374f5ac97810c"
COMPLETENESS_PY_BLOB = "06b778b75710a0de30035569d15c8e3d87b095d4"
COMPLETENESS_PASS_CLOSEOUT_PY_BLOB = "d1a6654b7f584c6e944628ecc63265ab8f9a1e7e"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
IDENTITY_SET_LANDING_PY_BLOB = "2ce94233f153f8e5297e4b978243323ca917dcf8"
OBSERVATION_MODULE_BLOB = "b9e047b4946fbdf658ad4911f2a94bb67628accd"
PARENT_OBSERVATION_R1_PR = 506
PARENT_OBSERVATION_R1_COMMIT = "cce345530e402d93902ae8d17a9cefd2576c6206"
PARENT_OBSERVATION_R1_MERGE = "de0e54250bd34943537cbe1338a8d50069cef778"
PARENT_OBSERVATION_R1_EVIDENCE_JSON_SHA256 = (
    "6cdaeb69f319490c0f9925c81ff9bdc8ca4765dce5821f1b78070e7d6ced1efa"
)
PARENT_OBSERVATION_R1_WORKPAPER_BLOB = "7389a3d8a928f421f24688e94c6f2f6fbbdc84f5"
PARENT_OBSERVATION_R1_EVIDENCE_BLOB = "f6638db2746275bb5d2d339ae0fa0c6a5707fd7f"
PARENT_OBSERVATION_GRANT_PR = 505
PARENT_OBSERVATION_GRANT_COMMIT = "fc73cd5613d77c6e5b4f739c6af6b485481eddc1"
PARENT_OBSERVATION_GRANT_MERGE = "c801c2004222082d33064b2f23bf93861b586a42"
PARENT_OBSERVATION_GRANT_EVIDENCE_JSON_SHA256 = (
    "5f8600f11581d9290440b07a1660e2ee3dd2a9eda8c0da31135d20e567817ade"
)
PARENT_OBSERVATION_GRANT_WORKPAPER_BLOB = "c397d4e81157ddaa3676f82a1c63e4d26b011119"
PARENT_OBSERVATION_GRANT_EVIDENCE_BLOB = "430c7dfb14272de359040aa6bf1fb39c4a238d7d"
PARENT_OBSERVATION_CONTRACT_PR = 504
PARENT_OBSERVATION_CONTRACT_COMMIT = "9672221f3874bd9d4a2759fd3c232fa3542bcf01"
PARENT_OBSERVATION_CONTRACT_MERGE = "b4d9563de530356b2faa7e6b692f11fe3c1dc546"
PARENT_OBSERVATION_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "a063ff025af7dcc61ed8bcc9ec37e0273df6f2c3c3ed38285a02ef7916a5d777"
)
PARENT_OBSERVATION_CONTRACT_DOC_BLOB = "43ce74a76cfb8a7f96cff5121eb7ae9f72bfd2b8"
PARENT_OBSERVATION_CONTRACT_WORKPAPER_BLOB = "d88dfdca891a3a9925d0db7137a8d08ea0dadff1"
PARENT_OBSERVATION_CONTRACT_EVIDENCE_BLOB = "40166a8298fca091eae37e0eb7bd311ccd8b51e6"
BASE_MAIN_SHA = "de0e54250bd34943537cbe1338a8d50069cef778"
BASE_MAIN_TREE_SHA = "c131940859b664f5d0095d4a496698795fc14c15"
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
UNIQUE_FLIP = "S3_A2_COMPLETENESS_PASS_OBSERVATION_CONTRACT_AUTHORIZED"
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


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_frozen_blobs_and_parent_observation_packages_unchanged() -> None:
    assert _git_blob(Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")) == (
        TEST_CATALOG_ARTIFACT_PY_BLOB
    )
    assert _git_blob(Path("backend/app/s3_daily_rowset/catalog_artifact.py")) == (
        CATALOG_ARTIFACT_PY_BLOB
    )
    assert (
        _git_blob(
            Path(
                "backend/app/s3_daily_rowset/"
                "incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
            )
        )
        == GRAIN_IDENTITY_SET_PY_BLOB
    )
    assert _git_blob(
        Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
    ) == (CONTENT_PRODUCER_PY_BLOB)
    assert (
        _git_blob(
            Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
        )
        == ALEMBIC_BLOB
    )
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py"))
        == OBTAIN_MODULE_BLOB
    )
    assert (
        _git_blob(
            Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py")
        )
        == CONSTRUCTION_MODULE_BLOB
    )
    assert _git_blob(Path("backend/app/s3_daily_rowset/binding.py")) == BINDING_PY_BLOB
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py"))
        == BINDABLE_REPOSITORY_PY_BLOB
    )
    assert (
        _git_blob(
            Path(
                "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
            )
        )
        == AVAILABLE_CLOSEOUT_PY_BLOB
    )
    assert _git_blob(REVIEWED_MODULE) == REVIEWED_SET_CLOSEOUT_PY_BLOB
    assert _git_blob(Path("backend/app/s3_daily_rowset/completeness.py")) == COMPLETENESS_PY_BLOB
    assert _git_blob(COMPLETENESS_PASS_CLOSEOUT_MODULE) == COMPLETENESS_PASS_CLOSEOUT_PY_BLOB
    assert_forecast_artifact_py_historical_blob_pinned(FORECAST_ARTIFACT_PY_BLOB)
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"))
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB
    assert _git_blob(OBSERVATION_MODULE) == OBSERVATION_MODULE_BLOB
    assert _git_blob(OBSERVATION_R1_WORKPAPER) == PARENT_OBSERVATION_R1_WORKPAPER_BLOB
    assert _git_blob(OBSERVATION_R1_EVIDENCE) == PARENT_OBSERVATION_R1_EVIDENCE_BLOB
    assert _git_blob(OBSERVATION_CONTRACT) == PARENT_OBSERVATION_CONTRACT_DOC_BLOB
    assert _git_blob(OBSERVATION_CONTRACT_WORKPAPER) == PARENT_OBSERVATION_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(OBSERVATION_CONTRACT_EVIDENCE) == PARENT_OBSERVATION_CONTRACT_EVIDENCE_BLOB
    assert _git_blob(OBSERVATION_GRANT_WORKPAPER) == PARENT_OBSERVATION_GRANT_WORKPAPER_BLOB
    assert _git_blob(OBSERVATION_GRANT_EVIDENCE) == PARENT_OBSERVATION_GRANT_EVIDENCE_BLOB


def test_observation_exists_and_pass_observation_module_is_not_created() -> None:
    assert OBSERVATION_MODULE.is_file()
    assert LANDING_MODULE.is_file()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
    assert PRODUCTION_MODULE.name == "s3_a2_completeness_pass_observation.py"
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "THIS_PR_IS_NOT_R1=true" in contract
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_COMPLETENESS_PASS_OBSERVATION=true" in contract
    assert "DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED=false" in contract
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_observation_sees_three_grains_and_default_loader_stays_empty() -> None:
    result = ObservationClassifier().classify()
    assert result.reason_code is (
        ObservationReasonCode.COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVED
    )
    assert result.coordinator_reviewed_identity_set_exists is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    assert result.reviewed_grain_identity_set_identity_sha256 == REVIEWED_SET_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    )
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.default_global_reviewed_set_loader_remains_empty is True
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_frozen_closeouts_still_unauthorized_after_observation() -> None:
    ObservationClassifier().classify()
    assert load_reviewed_grain_identity_set() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        reviewed = ReviewedGrainIdentitySetCloseoutClassifier().classify()
        completeness = CompletenessPassCloseoutClassifier().classify()
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert reviewed.coordinator_reviewed_identity_set_exists is False
    assert completeness.s3_a2_completeness_pass_authorized is False
    assert completeness.no_reviewed_grain_identity_set_in_repository is True
    assert completeness.weather_and_plans_block_completeness_pass is True
    assert completeness.no_bindable_catalog_in_repository is True
    assert completeness.evaluation_instance_registry_available is False


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert "S3_A2_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED=false" in text
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=true"
        in (text)
    )
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in text
    assert "FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED=true" in text
    assert "FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED=true" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_GATE_ACCEPTED_AS=可以继续" in text
    assert "USER_UTTERANCE=可以下一步" in text
    assert "CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_COMPLETENESS_PASS_OBSERVATION=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_COMPLETENESS_PASS_CLOSEOUT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_OBSERVATION=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_COMPLETENESS_PASS_AUTHORIZED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_INVENT_WEATHER=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_INVENT_PLANS=true" in text
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert "WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS=true" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert f"PARENT_OBSERVATION_R1_PR={PARENT_OBSERVATION_R1_PR}" in text
    assert f"PARENT_OBSERVATION_R1_COMMIT={PARENT_OBSERVATION_R1_COMMIT}" in text
    assert f"PARENT_OBSERVATION_R1_MERGE={PARENT_OBSERVATION_R1_MERGE}" in text
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
    assert payload["authorization"]["s3_a2_completeness_pass_observation_contract_authorized"]
    assert not payload["authorization"][
        "s3_a2_completeness_pass_observation_implementation_authorized"
    ]
    assert not payload["authorization"]["deterministic_completeness_pass_observation_implemented"]
    assert payload["authorization"][
        "deterministic_coordinator_reviewed_live_origin_grain_identity_set_observation_implemented"
    ]
    assert payload["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert payload["authorization"]["no_reviewed_grain_identity_set_in_repository"] is False
    assert payload["authorization"]["default_global_reviewed_set_loader_remains_empty"] is True
    assert payload["reviewed_artifact"]["review_member_count"] == 3
    assert payload["reviewed_artifact"]["identity_sha256"] == REVIEWED_SET_IDENTITY_SHA256
    assert payload["weather_and_plans"]["weather_and_plans_deferred_to_next_version"] is True
    assert payload["weather_and_plans"]["weather_and_plans_block_completeness_pass"] is True
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True
    assert payload["parent_observation_r1"]["parent_observation_r1_pr"] == PARENT_OBSERVATION_R1_PR
    assert payload["parent_observation_r1"]["parent_observation_r1_commit"] == (
        PARENT_OBSERVATION_R1_COMMIT
    )
    assert payload["parent_observation_r1"]["parent_observation_r1_merge"] == (
        PARENT_OBSERVATION_R1_MERGE
    )
    assert payload["parent_observation_r1"]["parent_observation_r1_evidence_json_sha256"] == (
        PARENT_OBSERVATION_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_observation_grant"]["parent_observation_grant_pr"] == (
        PARENT_OBSERVATION_GRANT_PR
    )
    assert payload["parent_observation_grant"]["parent_observation_grant_commit"] == (
        PARENT_OBSERVATION_GRANT_COMMIT
    )
    assert payload["parent_observation_grant"]["parent_observation_grant_merge"] == (
        PARENT_OBSERVATION_GRANT_MERGE
    )
    assert payload["parent_observation_grant"]["parent_observation_grant_evidence_json_sha256"] == (
        PARENT_OBSERVATION_GRANT_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_observation_contract"]["parent_observation_contract_pr"] == (
        PARENT_OBSERVATION_CONTRACT_PR
    )
    assert payload["parent_observation_contract"]["parent_observation_contract_commit"] == (
        PARENT_OBSERVATION_CONTRACT_COMMIT
    )
    assert payload["parent_observation_contract"]["parent_observation_contract_merge"] == (
        PARENT_OBSERVATION_CONTRACT_MERGE
    )
    assert (
        payload["parent_observation_contract"]["parent_observation_contract_evidence_json_sha256"]
        == PARENT_OBSERVATION_CONTRACT_EVIDENCE_JSON_SHA256
    )
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_ONLY=true" in text
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in text
    assert f"{UNIQUE_FLIP}=true" in text
    assert "S3_A2_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED=false" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_development_plan_live_compact_flips_only_this_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=true"
        in (live_intro)
    )
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "S3_A2_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false" in contract
    pointer = text.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-completeness-pass-observation-contract.md" in pointer
    r1_pointer = text.split(
        "#### Coordinator-reviewed live-origin grain identity-set observation R1 pointer",
        1,
    )[1]
    if "#### Completeness PASS observation contract pointer" in r1_pointer:
        r1_pointer = r1_pointer.split("#### Completeness PASS observation contract pointer", 1)[0]
    assert UNIQUE_FLIP not in r1_pointer
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.md" in (
        r1_pointer
    )


def test_amendment_records_pointer_and_isolates_section_192() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert (
        "## 192. Coordinator-reviewed live-origin grain identity-set observation R1 pointer" in text
    )
    assert "## 193. Completeness PASS observation contract pointer" in text
    assert f"{UNIQUE_FLIP}=true" in text
    section_192 = text.split("## 192.", 1)[1]
    if "## 193." in section_192:
        section_192 = section_192.split("## 193.", 1)[0]
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=true"
        in (section_192)
    )
    assert UNIQUE_FLIP not in section_192
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_192
    section_193 = text.split("## 193.", 1)[1]
    if "## 194." in section_193:
        section_193 = section_193.split("## 194.", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in section_193
    assert "S3_A2_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false" in section_193
    assert "DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED=false" in section_193
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_193
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in section_193
    assert PARENT_OBSERVATION_R1_EVIDENCE_JSON_SHA256 in section_193
    assert PARENT_OBSERVATION_R1_COMMIT in section_193
    lowered = section_193.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered
