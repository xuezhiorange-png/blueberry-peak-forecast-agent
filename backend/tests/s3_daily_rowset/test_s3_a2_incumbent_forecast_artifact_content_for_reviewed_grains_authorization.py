"""S3-A2 incumbent forecast artifact content for reviewed grains authorization tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset import (
    s3_a2_incumbent_forecast_artifact_repository_presence_observation as repo_presence_obs,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
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

IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)
IncumbentForecastArtifactRepositoryPresenceObservationReasonCode = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationReasonCode
)

CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-content-for-reviewed-grains-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-contract.json"
)
CONTRACT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_contract.py"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PRESENCE_OBSERVATION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "s3_a2_incumbent_forecast_artifact_repository_presence_observation.py"
)
PASS_OBSERVATION_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_completeness_pass_observation.py")
OBSERVATION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation.py"
)
LANDING_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains.py"
)
COMPLETENESS_PASS_CLOSEOUT_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py"
)
REVIEWED_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
PRESENCE_OBSERVATION_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
)
PRESENCE_OBSERVATION_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json"
)
PRESENCE_OBSERVATION_GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.md"
)
PRESENCE_OBSERVATION_GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.json"
)
PRESENCE_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-r1.md"
)
PRESENCE_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-r1.json"
)
PRESENCE_CONTRACT = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md"
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
COMPLETENESS_PASS_OBSERVATION_PY_BLOB = "93badaacdd19f5a80a8306b7beeffa3c391711fc"
PRESENCE_OBSERVATION_PY_BLOB = "58e8f18d8d903572ad77c3b2abcf32b4bbb9147d"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_PRESENCE_R1_WORKPAPER_BLOB = "316b117812c1461acc4eba1c42ad9dea5822c465"
PARENT_PRESENCE_R1_EVIDENCE_BLOB = "13628db068c3ed950925bc96ed5c1e152d1c35b1"
PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB = "ad183d08bd11d08b7b36c519ca29297610dcf586"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB = "c40ee9e08ceffc0a1932f5b863b4ed2f22ea526a"
PARENT_PRESENCE_OBSERVATION_GRANT_WORKPAPER_BLOB = "4eca4b6749756a93f543b9e406fda0446c760d53"
PARENT_PRESENCE_OBSERVATION_GRANT_EVIDENCE_BLOB = "5d765e317fa1f9389272404b6a200b51db5b9df7"
BASE_MAIN_SHA = "41c09ab148390cfd8ee97eff7b051a7e241f19af"
BASE_MAIN_TREE_SHA = "f3ddd0298c7093109ae9525069dd6d73813dd33e"
PARENT_CONTRACT_PR = 513
PARENT_CONTRACT_COMMIT = "b6d262bca7654566523f88030281a038c261f5b5"
PARENT_CONTRACT_MERGE = "41c09ab148390cfd8ee97eff7b051a7e241f19af"
PARENT_CONTRACT_TREE_SHA = "f3ddd0298c7093109ae9525069dd6d73813dd33e"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "911514b072a0f938e9c3aa382cd117220f8e18acf77d1c2b3ee516807390856b"
)
PARENT_CONTRACT_DOC_BLOB = "c3d6ec6120222703f079fcafc77a0c9da2ecb374"
PARENT_CONTRACT_WORKPAPER_BLOB = "b8247226794a5f8504984ad3e71468ceae8a0d7d"
PARENT_CONTRACT_EVIDENCE_BLOB = "d335bdcad0c6ca7239b6e0ab6460f147c11c99e5"
PARENT_CONTRACT_TEST_BLOB = "3b285542160751f994c09d31a0faafbd1a7ee290"
PARENT_PRESENCE_OBSERVATION_R1_PR = 512
PARENT_PRESENCE_OBSERVATION_R1_COMMIT = "3321cf83e518585027c07b770b1339c24ef5eb0b"
PARENT_PRESENCE_OBSERVATION_R1_MERGE = "3a15492d2233dfc32c4b6f3199b0d945c04689ad"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_JSON_SHA256 = (
    "ed3ecc806a1ede8f6b85f0c601bd518936cd6b78edef1024b06d65fb787b091b"
)
PARENT_PRESENCE_OBSERVATION_GRANT_PR = 511
PARENT_PRESENCE_OBSERVATION_GRANT_COMMIT = "28755c0cd94428411db7c5f27d784585dbeb7cfc"
PARENT_PRESENCE_OBSERVATION_GRANT_MERGE = "432d682f6bdd259b7fee9294a89c509e0aaf2f47"
PARENT_PRESENCE_OBSERVATION_GRANT_EVIDENCE_JSON_SHA256 = (
    "7ea8bf5682a1051a0ec5bbc98d6751c23d19606b714275fbc059e7186b9135d3"
)
PARENT_PRESENCE_OBSERVATION_CONTRACT_PR = 510
PARENT_PRESENCE_OBSERVATION_CONTRACT_COMMIT = "576488a3888b357e8480640ad307f77beb598989"
PARENT_PRESENCE_OBSERVATION_CONTRACT_MERGE = "1f7faeab104e71d34b111de474c8ce3c8b59bf79"
PARENT_PRESENCE_OBSERVATION_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "ffe62428872d7c82055d3dc24b59d9d780d07ebf0e70ae7867600529532ce4f6"
)
PARENT_PRESENCE_R1_PR = 481
PARENT_PRESENCE_R1_COMMIT = "bffd2bfc9c0d9f8cbbbd6db7c37898b16b5808a1"
PARENT_PRESENCE_R1_MERGE = "fde7acec586e83eafd99b755f3049d9e3e4a074c"
PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256 = (
    "4422928e91f49807bf9fa4d6678bde06efcf2cc38a134611424aad9888243782"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
UNIQUE_FLIP = (
    "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTATION_AUTHORIZED"
)
GRANT_POINTER_HEADING = (
    "#### Incumbent forecast artifact content for reviewed grains "
    "implementation authorization pointer"
)
FORBIDDEN_THIS_GRANT_TOKENS = (
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


def test_grant_unique_flip_is_content_for_reviewed_grains_implementation_authorized() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[UNIQUE_FLIP] is True
    assert flags[
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_CONTRACT_AUTHORIZED"
    ]
    assert (
        flags["DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED"]
        is False
    )
    assert flags[
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTED"
    ]
    assert flags["DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED"]
    assert flags["DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED"]
    assert flags["DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED"]
    assert flags["CONTRACT_AUTHORIZED"] is True
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
    assert flags["DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY"] is True


def test_parent_contract_blobs_and_evidence_remain() -> None:
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    assert _git_blob(CONTRACT_TEST) == PARENT_CONTRACT_TEST_BLOB
    parent = json.loads(CONTRACT_EVIDENCE.read_text(encoding="utf-8"))
    assert parent["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert parent["authorization"][
        "s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_contract_authorized"
    ]
    assert not parent["authorization"][
        "s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_implementation_authorized"
    ]
    assert not parent["authorization"][
        "deterministic_incumbent_forecast_artifact_content_for_reviewed_grains_implemented"
    ]
    assert parent["authorization"][
        "deterministic_incumbent_forecast_artifact_repository_presence_observation_implemented"
    ]
    assert parent["authorization"][
        "deterministic_incumbent_forecast_artifact_content_producer_implemented"
    ]
    assert parent["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert parent["authorization"]["no_reviewed_grain_identity_set_in_repository"] is False


def test_parent_presence_observation_and_contract_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_presence_contract_blob"] == PARENT_PRESENCE_CONTRACT_BLOB
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["base_main_sha"] == PARENT_CONTRACT_MERGE
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_BLOB
    assert _git_blob(PRESENCE_R1_WORKPAPER) == PARENT_PRESENCE_R1_WORKPAPER_BLOB
    assert _git_blob(PRESENCE_R1_EVIDENCE) == PARENT_PRESENCE_R1_EVIDENCE_BLOB
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_WORKPAPER)
        == PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB
    )
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_EVIDENCE) == PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB
    )
    assert (
        _git_blob(PRESENCE_OBSERVATION_GRANT_WORKPAPER)
        == PARENT_PRESENCE_OBSERVATION_GRANT_WORKPAPER_BLOB
    )
    assert (
        _git_blob(PRESENCE_OBSERVATION_GRANT_EVIDENCE)
        == PARENT_PRESENCE_OBSERVATION_GRANT_EVIDENCE_BLOB
    )
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB
    assert _git_blob(OBSERVATION_MODULE) == OBSERVATION_MODULE_BLOB
    assert _git_blob(PASS_OBSERVATION_MODULE) == COMPLETENESS_PASS_OBSERVATION_PY_BLOB
    assert _git_blob(PRESENCE_OBSERVATION_MODULE) == PRESENCE_OBSERVATION_PY_BLOB


def test_frozen_catalog_grain_construction_and_binding_blobs_remain() -> None:
    assert _git_blob(Path("backend/app/s3_daily_rowset/catalog_artifact.py")) == (
        CATALOG_ARTIFACT_PY_BLOB
    )
    assert _git_blob(Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")) == (
        TEST_CATALOG_ARTIFACT_PY_BLOB
    )
    grain = Path(
        "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
    )
    assert _git_blob(grain) == GRAIN_IDENTITY_SET_PY_BLOB
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py"))
        == CONTENT_PRODUCER_PY_BLOB
    )
    alembic = Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
    assert _git_blob(alembic) == ALEMBIC_BLOB
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
    assert _git_blob(Path("backend/app/s3_daily_rowset/binding.py")) == BINDING_PY_BLOB
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/forecast_artifact.py"))
        == FORECAST_ARTIFACT_PY_BLOB
    )
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"))
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )


def test_presence_observation_exists_and_content_module_is_not_created() -> None:
    assert PRESENCE_OBSERVATION_MODULE.is_file()
    assert PASS_OBSERVATION_MODULE.is_file()
    assert OBSERVATION_MODULE.is_file()
    assert LANDING_MODULE.is_file()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
    assert _git_blob(PRESENCE_OBSERVATION_MODULE) == PRESENCE_OBSERVATION_PY_BLOB
    assert (
        PRODUCTION_MODULE.name == "s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains.py"
    )
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_presence_observation_sees_three_grains_and_default_loader_stays_empty_after_grant() -> (
    None
):
    result = IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactRepositoryPresenceObservationReasonCode.REPOSITORY_PRESENCE_OBSERVATION_RECORDED
    )
    assert result.coordinator_reviewed_identity_set_exists is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    assert result.reviewed_grain_identity_set_identity_sha256 == REVIEWED_SET_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    )
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.default_global_reviewed_set_loader_remains_empty is True
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_default_content_producer_on_empty_obtain_returns_none_after_grant() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert IncumbentForecastArtifactContentProducer().produce() is None


def test_frozen_closeouts_still_unauthorized_after_grant() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
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


def test_grant_does_not_flip_completeness_or_invent_weather_plans() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["WEATHER_UNAVAILABLE"] is True
    assert flags["PLANS_UNAVAILABLE"] is True
    assert flags["LLM_MUST_NOT_INVENT_TONNES"] is True
    assert flags["WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION"] is True
    assert flags["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert flags["WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS"] is True
    assert flags["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert flags["COMPLETENESS_VERIFICATION_STATUS"] == "CONTRACT_STILL_BOUND_BLOCKED"
    assert flags["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert flags["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
    assert flags["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert flags["AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP"] is True
    assert flags["DEFAULT_CATALOG_FIRST_BLOCKER"] == "ARTIFACT_PRODUCED"
    assert flags["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert flags["CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE"] is True
    assert flags["IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT"] is True
    assert flags["NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS"] is True
    assert flags["NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS"] is True
    assert flags["NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS"] is False
    assert flags["NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS"] is False
    assert flags["LATER_R1_MAY_SATISFY_PRECONDITION_3_WITHOUT_FLIPPING_NO_VERSIONED"] is True
    assert flags["LATER_R1_MUST_NOT_INVENT_CONTENT_IDENTITY_SHA256"] is True
    assert flags["LATER_R1_MUST_NOT_AUTO_WIRE_AT_IMPORT"] is True
    assert flags["LATER_R1_MUST_NOT_FLIP_NO_VERSIONED"] is True


def test_grant_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_grant_files_exist_and_avoid_forbidden_tokens() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    text = GRANT_WORKPAPER.read_text(encoding="utf-8") + GRANT_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_THIS_GRANT_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=授权" in workpaper
    assert "GRANT_ONLY=true" in workpaper
    assert "THIS_PR_IS_NOT_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_NEW_CONTRACT=true" in workpaper
    assert PARENT_CONTRACT_COMMIT[:7] in workpaper
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in workpaper
    assert "REVIEW_MEMBER_COUNT=3" in workpaper
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in workpaper
    assert f"{UNIQUE_FLIP}=true" in workpaper
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=false"
        in workpaper
    )


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_CONTRACT_AUTHORIZED=true"
        in live_intro
    )
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=false"
        not in live_intro
    )
    grant_pointer = plan.split(
        GRANT_POINTER_HEADING,
        1,
    )[1]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=false"
        in grant_pointer
    )
    assert "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.md" in plan
    assert "## 199." in amendment
    assert "## 200." in amendment
    assert (
        amendment.count(
            "## 199. Incumbent forecast artifact content for reviewed grains contract pointer"
        )
        == 1
    )
    assert (
        amendment.count(
            "## 200. Incumbent forecast artifact content for reviewed grains "
            "implementation authorization pointer"
        )
        == 1
    )
    assert plan.count(GRANT_POINTER_HEADING) == 1
    assert f"{UNIQUE_FLIP}=true" in amendment
    grant_snapshot = amendment.split("## 200.", 1)[1]
    assert UNIQUE_FLIP + "=true" in grant_snapshot
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=false"
        in grant_snapshot
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in grant_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in grant_snapshot
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in grant_snapshot
    contract_snapshot = amendment.split("## 199.", 1)[1]
    if "## 200." in contract_snapshot:
        contract_snapshot = contract_snapshot.split("## 200.", 1)[0]
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTATION_AUTHORIZED=false"
        in contract_snapshot
    )
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_CONTRACT_AUTHORIZED=true"
        in contract_snapshot
    )
    contract_pointer = plan.split(
        "#### Incumbent forecast artifact content for reviewed grains contract pointer",
        1,
    )[1]
    if GRANT_POINTER_HEADING in contract_pointer:
        contract_pointer = contract_pointer.split(
            GRANT_POINTER_HEADING,
            1,
        )[0]
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTATION_AUTHORIZED=false"
        in contract_pointer
    )
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert (
        payload["flags"][
            "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED"
        ]
        is False
    )


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_r1"] is True
    assert payload["this_pr_is_not_a_new_contract"] is True
    assert (
        payload["flags"][
            "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED"
        ]
        is False
    )
    assert PRESENCE_OBSERVATION_MODULE.is_file()
    assert LANDING_MODULE.is_file()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
    assert (
        PRODUCTION_MODULE.name == "s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains.py"
    )
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_parent_contract_commit_is_named_for_traceability() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert PARENT_CONTRACT_COMMIT[:7] in json.dumps(payload)
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert payload["parent_presence_observation_r1_commit"] == PARENT_PRESENCE_OBSERVATION_R1_COMMIT
    assert payload["parent_presence_observation_r1_merge"] == PARENT_PRESENCE_OBSERVATION_R1_MERGE
    assert (
        payload["parent_presence_observation_r1_evidence_json_sha256"]
        == PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_presence_observation_r1_pr"] == PARENT_PRESENCE_OBSERVATION_R1_PR
    assert payload["parent_presence_observation_grant_pr"] == PARENT_PRESENCE_OBSERVATION_GRANT_PR
    assert payload["parent_presence_r1_commit"] == PARENT_PRESENCE_R1_COMMIT
    assert payload["parent_presence_r1_merge"] == PARENT_PRESENCE_R1_MERGE
    assert (
        payload["parent_presence_r1_evidence_json_sha256"]
        == PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_presence_r1_pr"] == PARENT_PRESENCE_R1_PR


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("NO_NEW_SQLALCHEMY_API_FAMILY", True),
        ("TEST_REMAINS_SEALED", True),
        ("CATALOG_ARTIFACT_PY_MUST_REMAIN_FROZEN", True),
        ("BINDING_PY_MUST_REMAIN_FROZEN", True),
        ("FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6", True),
        ("NO_BINDABLE_CATALOG_IN_REPOSITORY", True),
        ("NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY", False),
        ("DEFAULT_HARVEST_OBTAIN_EMPTY", True),
        ("DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY", True),
        ("WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION", True),
        ("WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION", True),
        ("WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS", True),
        ("S3_A2_COMPLETENESS_PASS_AUTHORIZED", False),
        ("AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP", True),
        ("EVALUATION_INSTANCE_REGISTRY_AVAILABLE", False),
        ("FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002", True),
        ("FORBIDDEN_INVENT_ADDITIONAL_MEMBERS", True),
        ("LATER_R1_MAY_SATISFY_PRECONDITION_3_WITHOUT_FLIPPING_NO_VERSIONED", True),
        ("LATER_R1_MUST_NOT_INVENT_CONTENT_IDENTITY_SHA256", True),
        ("LATER_R1_MUST_NOT_AUTO_WIRE_AT_IMPORT", True),
        ("LATER_R1_MUST_NOT_FLIP_NO_VERSIONED", True),
        (
            "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTED",
            True,
        ),
        ("DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED", True),
        ("DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED", True),
        ("DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED", True),
        ("DETERMINISTIC_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTED", True),
        ("FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED", True),
        ("FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED", True),
        ("FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET", True),
        ("CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE", True),
        ("IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT", True),
        ("NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS", True),
        ("NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS", True),
        ("NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS", False),
        ("NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS", False),
    ],
)
def test_grant_keeps_safety_flags(flag: str, expected: bool) -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"][flag] is expected
