"""S3-A2 incumbent forecast artifact repository-presence observation R1 tests."""

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
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
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
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_closeout import (
    CompletenessPassCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_observation import (
    CompletenessPassObservationClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MEMBER_COUNT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
    assert_forecast_artifact_py_historical_blob_pinned,
)

IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)
IncumbentForecastArtifactRepositoryPresenceObservationReasonCode = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationReasonCode
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "s3_a2_incumbent_forecast_artifact_repository_presence_observation.py"
)
PASS_OBSERVATION_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_completeness_pass_observation.py")
PASS_OBSERVATION_TEST = Path(
    "backend/tests/s3_daily_rowset/test_s3_a2_completeness_pass_observation_r1.py"
)
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
COMPLETENESS_PY = Path("backend/app/s3_daily_rowset/completeness.py")
TEST_CATALOG_PY = Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")
GRAIN_PY = Path(
    "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
)
CONTENT_PY = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
ALEMBIC_PY = Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
ALIGNMENT_EVIDENCE_PY = Path(
    "backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.json"
)
CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-observation-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-contract.json"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json"
)
PRESENCE_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-r1.md"
)
PRESENCE_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-r1.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

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
COMPLETENESS_PASS_OBSERVATION_TEST_BLOB = "7b108973384f6a5dcff5bfc17126107f0c9f88b2"
PARENT_GRANT_PR = 511
PARENT_GRANT_MERGE = "432d682f6bdd259b7fee9294a89c509e0aaf2f47"
PARENT_GRANT_COMMIT = "28755c0cd94428411db7c5f27d784585dbeb7cfc"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "7ea8bf5682a1051a0ec5bbc98d6751c23d19606b714275fbc059e7186b9135d3"
)
PARENT_GRANT_WORKPAPER_BLOB = "4eca4b6749756a93f543b9e406fda0446c760d53"
PARENT_GRANT_EVIDENCE_BLOB = "5d765e317fa1f9389272404b6a200b51db5b9df7"
PARENT_CONTRACT_PR = 510
PARENT_CONTRACT_COMMIT = "576488a3888b357e8480640ad307f77beb598989"
PARENT_CONTRACT_MERGE = "1f7faeab104e71d34b111de474c8ce3c8b59bf79"
PARENT_CONTRACT_DOC_BLOB = "9f2115fbea1d88e094c93aa5ca025453fbcafcca"
PARENT_CONTRACT_WORKPAPER_BLOB = "0327b1e21c9b057986665c0841ee4e2e6c05406c"
PARENT_CONTRACT_EVIDENCE_BLOB = "d80711386c153ee5342132bfcc7eb0f23cfdfae1"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "ffe62428872d7c82055d3dc24b59d9d780d07ebf0e70ae7867600529532ce4f6"
)
PARENT_PASS_OBSERVATION_R1_PR = 509
PARENT_PASS_OBSERVATION_R1_COMMIT = "7e7b322c00cdce9637c7aa1990fb900ea0edd303"
PARENT_PASS_OBSERVATION_R1_MERGE = "2c36b67fc32ef06ace4efcaf3ed5d7b96ae2cd20"
PARENT_PASS_OBSERVATION_R1_EVIDENCE_JSON_SHA256 = (
    "50b7dc42e55d020e077887fdeb9b87a06c31db266e85968e8887c57dd71e5fbd"
)
PARENT_PRESENCE_R1_PR = 481
PARENT_PRESENCE_R1_COMMIT = "bffd2bfc9c0d9f8cbbbd6db7c37898b16b5808a1"
PARENT_PRESENCE_R1_MERGE = "fde7acec586e83eafd99b755f3049d9e3e4a074c"
PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256 = (
    "4422928e91f49807bf9fa4d6678bde06efcf2cc38a134611424aad9888243782"
)
PARENT_PRESENCE_R1_WORKPAPER_BLOB = "316b117812c1461acc4eba1c42ad9dea5822c465"
PARENT_PRESENCE_R1_EVIDENCE_BLOB = "13628db068c3ed950925bc96ed5c1e152d1c35b1"
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
UNIQUE_FLIP = (
    "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTED"
)
GRANT_POINTER_HEADING = (
    "#### Incumbent forecast artifact repository-presence observation "
    "implementation authorization pointer"
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


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _assert_harvest_replay_and_provider_remain_empty() -> None:
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_production_module_does_not_land_or_embed_connection_strings() -> None:
    source = PRODUCTION_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "land_replay_identity_origin" not in source
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "content_bytes" not in source
    assert "sqlalchemy" not in lowered
    assert "dsn" not in lowered
    assert "CompletenessPassCloseoutClassifier" not in source
    assert "ReviewedGrainIdentitySetCloseoutClassifier" not in source
    assert "s3_a2_completeness_pass_closeout" not in source
    assert "repository_presence_r1" not in lowered
    assert "IncumbentForecastArtifactContentProducer" not in source
    assert "EvaluationInstanceCatalogArtifactProductionService" not in source


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
    assert _git_blob(REVIEWED_MODULE) == REVIEWED_SET_CLOSEOUT_PY_BLOB
    assert _git_blob(COMPLETENESS_PY) == COMPLETENESS_PY_BLOB
    assert _git_blob(COMPLETENESS_PASS_CLOSEOUT_MODULE) == COMPLETENESS_PASS_CLOSEOUT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert_forecast_artifact_py_historical_blob_pinned(FORECAST_ARTIFACT_PY_BLOB)
    assert _git_blob(ALIGNMENT_EVIDENCE_PY) == ALIGNMENT_EVIDENCE_PY_BLOB
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB
    assert _git_blob(OBSERVATION_MODULE) == OBSERVATION_MODULE_BLOB
    assert _git_blob(PASS_OBSERVATION_MODULE) == COMPLETENESS_PASS_OBSERVATION_PY_BLOB
    assert _git_blob(PASS_OBSERVATION_TEST) == COMPLETENESS_PASS_OBSERVATION_TEST_BLOB
    assert _git_blob(GRANT_WORKPAPER) == PARENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(GRANT_EVIDENCE) == PARENT_GRANT_EVIDENCE_BLOB
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    assert _git_blob(PRESENCE_R1_WORKPAPER) == PARENT_PRESENCE_R1_WORKPAPER_BLOB
    assert _git_blob(PRESENCE_R1_EVIDENCE) == PARENT_PRESENCE_R1_EVIDENCE_BLOB


def test_default_import_does_not_wire_reviewed_set_loader() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_classify_observes_three_grains_then_loader_empty() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    result = IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactRepositoryPresenceObservationReasonCode.REPOSITORY_PRESENCE_OBSERVATION_RECORDED
    )
    assert result.repository_presence_observation_recorded is True
    assert result.completeness_pass_observation_recorded is True
    assert result.coordinator_reviewed_identity_set_exists is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    assert result.reviewed_grain_identity_set_identity_sha256 == REVIEWED_SET_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    )
    assert result.artifact_available is True
    assert result.review_cutoff_at == REVIEW_CUTOFF_AT
    assert result.review_cutoff_business_date == "2026-02-16"
    assert result.review_model_id == REVIEW_MODEL_ID
    assert result.review_quantiles == REVIEW_QUANTILES
    assert result.default_global_reviewed_set_loader_remains_empty is True
    assert result.frozen_reviewed_set_closeout_still_reports_no_reviewed is True
    assert result.frozen_completeness_pass_closeout_still_unauthorized is True
    assert result.no_reviewed_grain_identity_set_in_repository is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.weather_unavailable is True
    assert result.plans_unavailable is True
    assert result.weather_and_plans_deferred_to_next_version is True
    assert result.weather_and_plans_do_not_block_non_curve_implementation is True
    assert result.weather_and_plans_block_completeness_pass is True
    assert result.forbidden_derive_members_from_source_002 is True
    assert result.forbidden_invent_additional_members is True
    assert result.default_session_provider_left_unset is True
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert result.frozen_presence_r1_still_reports_fail_closed_no_reviewed_set is True
    assert result.content_producer_on_empty_obtain_returns_none is True
    assert result.in_memory_catalog_artifact_produced_is_not_versioned_repository_artifact is True
    assert result.no_versioned_flip_precondition_1_holds is True
    assert result.no_versioned_flip_precondition_2_holds is True
    assert result.no_versioned_flip_precondition_3_holds is False
    assert result.no_versioned_flip_precondition_4_holds is False
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_pass_observation_fail_closes() -> None:
    classifier = IncumbentForecastArtifactRepositoryPresenceObservationClassifier()
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        empty = classifier.classify()
    assert empty.reason_code is (
        IncumbentForecastArtifactRepositoryPresenceObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert empty.repository_presence_observation_recorded is False
    assert empty.completeness_pass_observation_recorded is False
    assert empty.coordinator_reviewed_identity_set_exists is False
    assert empty.reviewed_identity_set_member_count == 0
    assert empty.reviewed_grain_identity_set_identity_sha256 == ""
    assert empty.artifact_available is False
    assert empty.default_global_reviewed_set_loader_remains_empty is True
    assert empty.s3_a2_completeness_pass_authorized is False
    assert empty.no_reviewed_grain_identity_set_in_repository is False
    assert empty.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert load_reviewed_grain_identity_set() == ()
    assert reviewed_grain_identity_set_artifact_available() is False

    extra = (
        *replay_identity_origin_entries(),
        IncumbentForecastArtifactEntry(
            model_id=REVIEW_MODEL_ID,
            forecast_cutoff_at=last_legal_cutoff_before_test(),
            forecast_quantile="P50",
        ),
    )
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=extra,
    ):
        mismatched = classifier.classify()
    assert mismatched.reason_code is (
        IncumbentForecastArtifactRepositoryPresenceObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert mismatched.artifact_available is False
    assert mismatched.reviewed_identity_set_member_count == 0
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_closeouts_still_report_unauthorized_after_observation() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert load_reviewed_grain_identity_set() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        reviewed = ReviewedGrainIdentitySetCloseoutClassifier().classify()
        completeness = CompletenessPassCloseoutClassifier().classify()
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert reviewed.coordinator_reviewed_identity_set_exists is False
    assert reviewed.reviewed_identity_set_member_count == 0
    assert completeness.s3_a2_completeness_pass_authorized is False
    assert completeness.no_reviewed_grain_identity_set_in_repository is True
    assert completeness.live_origin_grains_are_reviewed_set is False
    assert completeness.no_bindable_catalog_in_repository is True
    assert completeness.evaluation_instance_registry_available is False
    assert completeness.current_s3_daily_rowset_completeness_verified is False
    assert completeness.weather_and_plans_block_completeness_pass is True
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_presence_r1_still_reports_fail_closed_no_reviewed_set() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    presence_r1_workpaper = PRESENCE_R1_WORKPAPER.read_text(encoding="utf-8")
    presence_r1_payload = json.loads(PRESENCE_R1_EVIDENCE.read_text(encoding="utf-8"))
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in presence_r1_workpaper
    implementation = presence_r1_payload["implementation"]
    authorization = presence_r1_payload["authorization"]
    assert implementation["no_reviewed_grain_identity_set_in_repository"] is True
    assert authorization["no_reviewed_grain_identity_set_in_repository"] is True
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" not in presence_r1_workpaper


def test_default_content_producer_and_catalog_remain_fail_closed() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    clear_v0_2_live_postgres_session_provider()
    assert IncumbentForecastArtifactContentProducer().produce() is None
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert produced.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    _assert_harvest_replay_and_provider_remain_empty()


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTATION_AUTHORIZED"
    ]
    assert payload["flags"][UNIQUE_FLIP] is False
    assert payload["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert r1["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert r1["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert r1["parent_pass_observation_r1_pr"] == PARENT_PASS_OBSERVATION_R1_PR
    assert r1["parent_pass_observation_r1_commit"] == PARENT_PASS_OBSERVATION_R1_COMMIT
    assert r1["parent_pass_observation_r1_merge"] == PARENT_PASS_OBSERVATION_R1_MERGE
    assert (
        r1["parent_pass_observation_r1_evidence_json_sha256"]
        == PARENT_PASS_OBSERVATION_R1_EVIDENCE_JSON_SHA256
    )
    assert r1["parent_presence_r1_pr"] == PARENT_PRESENCE_R1_PR
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"][
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_CONTRACT_AUTHORIZED"
    ]
    assert r1["flags"][
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTATION_AUTHORIZED"
    ]
    assert r1["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert r1["flags"]["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert r1["flags"]["WEATHER_UNAVAILABLE"] is True
    assert r1["flags"]["PLANS_UNAVAILABLE"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_WEATHER"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_PLANS"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS"] is True
    assert r1["flags"]["FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_ADDITIONAL_MEMBERS"] is True
    assert r1["flags"]["DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY"] is True
    assert r1["flags"]["FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET"] is True
    assert r1["flags"]["CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE"] is True
    assert r1["flags"]["IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT"]
    assert r1["reviewed_set"]["review_member_count"] == 3
    assert r1["reviewed_set"]["identity_sha256"] == REVIEWED_SET_IDENTITY_SHA256
    assert GRANT_WORKPAPER.is_file()
    assert R1_WORKPAPER.is_file()


def test_r1_evidence_sha256_payload_matches_embedded_digest() -> None:
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
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_CONTRACT_AUTHORIZED=true"
        in live_intro
    )
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTATION_AUTHORIZED=true"
        in live_intro
    )
    assert "DETERMINISTIC_COMPLETENESS_PASS_OBSERVATION_IMPLEMENTED=true" in live_intro
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert UNIQUE_FLIP + "=false" not in live_intro
    assert (
        "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
        in plan.split("### 4.5", maxsplit=1)[0]
    )
    assert "## 196." in amendment
    assert "## 197." in amendment
    assert "## 198." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    grant_snapshot = amendment.split("## 197.", 1)[1]
    if "## 198." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 198.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTATION_AUTHORIZED=true"
        in grant_snapshot
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in grant_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in grant_snapshot
    r1_snapshot = amendment.split("## 198.", 1)[1]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in r1_snapshot
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in r1_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in r1_snapshot
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in r1_snapshot
    contract_snapshot = amendment.split("## 196.", 1)[1]
    if "## 197." in contract_snapshot:
        contract_snapshot = contract_snapshot.split("## 197.", 1)[0]
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
        in contract_snapshot
    )
    assert UNIQUE_FLIP + "=false" in contract_snapshot
    grant_pointer = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    if (
        "#### Incumbent forecast artifact repository-presence observation R1 pointer"
        in grant_pointer
    ):
        grant_pointer = grant_pointer.split(
            "#### Incumbent forecast artifact repository-presence observation R1 pointer",
            1,
        )[0]
    assert UNIQUE_FLIP + "=false" in grant_pointer


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper
    assert "REVIEW_MEMBER_COUNT=3" in workpaper
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in workpaper
    assert UNIQUE_FLIP + "=true" in workpaper


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert PRODUCTION_MODULE.is_file()
    assert PASS_OBSERVATION_MODULE.is_file()
    assert OBSERVATION_MODULE.is_file()
    assert LANDING_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()


def test_pass_observation_still_works_after_repository_presence_observation() -> None:
    IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    result = CompletenessPassObservationClassifier().classify()
    assert result.completeness_pass_observation_recorded is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    _assert_harvest_replay_and_provider_remain_empty()
