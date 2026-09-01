"""S3-A2 incumbent forecast artifact content for reviewed grains R1 tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset import (
    s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains as content_for_reviewed,
)
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
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_closeout import (
    CompletenessPassCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MEMBER_COUNT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    load_coordinator_reviewed_live_origin_grain_identity_set,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

IncumbentForecastArtifactContentForReviewedGrainsClassifier = (
    content_for_reviewed.IncumbentForecastArtifactContentForReviewedGrainsClassifier
)
IncumbentForecastArtifactContentForReviewedGrainsReasonCode = (
    content_for_reviewed.IncumbentForecastArtifactContentForReviewedGrainsReasonCode
)
IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains.py"
)
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
COMPLETENESS_PASS_CLOSEOUT_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py"
)
REVIEWED_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
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
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.json"
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
GRANT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_authorization.py"
)
PRESENCE_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-r1.md"
)
PRESENCE_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-r1.json"
)
PRESENCE_OBSERVATION_GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.md"
)
PRESENCE_OBSERVATION_GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-authorization.json"
)
PRESENCE_OBSERVATION_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
)
PRESENCE_OBSERVATION_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.json"
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
PRESENCE_OBSERVATION_PY_BLOB = "58e8f18d8d903572ad77c3b2abcf32b4bbb9147d"
PARENT_GRANT_WORKPAPER_BLOB = "234af626036d56c078ed98f27e8609cd384c57f5"
PARENT_GRANT_EVIDENCE_BLOB = "49e8f93814904f0bd37d1fb4972e4207206536ce"
PARENT_GRANT_TEST_BLOB = "357ae09fcc359638349cc5dec65cdcd470b8dfc1"
PARENT_CONTRACT_DOC_BLOB = "c3d6ec6120222703f079fcafc77a0c9da2ecb374"
PARENT_CONTRACT_WORKPAPER_BLOB = "b8247226794a5f8504984ad3e71468ceae8a0d7d"
PARENT_CONTRACT_EVIDENCE_BLOB = "d335bdcad0c6ca7239b6e0ab6460f147c11c99e5"
PARENT_CONTRACT_TEST_BLOB = "3b285542160751f994c09d31a0faafbd1a7ee290"
PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB = "ad183d08bd11d08b7b36c519ca29297610dcf586"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB = "c40ee9e08ceffc0a1932f5b863b4ed2f22ea526a"
PARENT_PRESENCE_OBSERVATION_GRANT_WORKPAPER_BLOB = "4eca4b6749756a93f543b9e406fda0446c760d53"
PARENT_PRESENCE_OBSERVATION_GRANT_EVIDENCE_BLOB = "5d765e317fa1f9389272404b6a200b51db5b9df7"
PARENT_PRESENCE_R1_WORKPAPER_BLOB = "316b117812c1461acc4eba1c42ad9dea5822c465"
PARENT_PRESENCE_R1_EVIDENCE_BLOB = "13628db068c3ed950925bc96ed5c1e152d1c35b1"
PARENT_GRANT_PR = 514
PARENT_GRANT_MERGE = "60e83b82632bdf73649634abb62e40d4854d5e82"
PARENT_GRANT_COMMIT = "9d3b2b7a08f5f658b69059a982268793cc2de7f3"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "f906e76c51ef238479fb24c682cc5180e070eca00efd7556e188add0623a98fc"
)
PARENT_CONTRACT_PR = 513
PARENT_CONTRACT_COMMIT = "b6d262bca7654566523f88030281a038c261f5b5"
PARENT_CONTRACT_MERGE = "41c09ab148390cfd8ee97eff7b051a7e241f19af"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "911514b072a0f938e9c3aa382cd117220f8e18acf77d1c2b3ee516807390856b"
)
PARENT_PRESENCE_OBSERVATION_R1_PR = 512
PARENT_PRESENCE_OBSERVATION_R1_COMMIT = "3321cf83e518585027c07b770b1339c24ef5eb0b"
PARENT_PRESENCE_OBSERVATION_R1_MERGE = "3a15492d2233dfc32c4b6f3199b0d945c04689ad"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_JSON_SHA256 = (
    "ed3ecc806a1ede8f6b85f0c601bd518936cd6b78edef1024b06d65fb787b091b"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
UNIQUE_FLIP = "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED"
GRANT_POINTER_HEADING = (
    "#### Incumbent forecast artifact content for reviewed grains "
    "implementation authorization pointer"
)
R1_POINTER_HEADING = "#### Incumbent forecast artifact content for reviewed grains R1 pointer"
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


def _landed_replay_rows() -> tuple[IncumbentForecastArtifactEntry, ...]:
    artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
    return tuple(
        IncumbentForecastArtifactEntry(
            model_id=member.model_id,
            forecast_cutoff_at=member.forecast_cutoff_at,
            forecast_quantile=member.forecast_quantile,
        )
        for member in artifact.members
    )


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
    assert "EvaluationInstanceCatalogArtifactProductionService" not in source
    assert "install_into_reviewed_set_loader" not in source


def test_frozen_blobs_unchanged() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(GRAIN_PY) == GRAIN_IDENTITY_SET_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(ALEMBIC_PY) == ALEMBIC_BLOB
    obtain = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
    construction = Path(
        "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py"
    )
    bindable = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py")
    available = Path(
        "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
    )
    assert _git_blob(obtain) == OBTAIN_MODULE_BLOB
    assert _git_blob(construction) == CONSTRUCTION_MODULE_BLOB
    assert _git_blob(bindable) == BINDABLE_REPOSITORY_PY_BLOB
    assert _git_blob(available) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(REVIEWED_MODULE) == REVIEWED_SET_CLOSEOUT_PY_BLOB
    assert _git_blob(COMPLETENESS_PY) == COMPLETENESS_PY_BLOB
    assert _git_blob(COMPLETENESS_PASS_CLOSEOUT_MODULE) == COMPLETENESS_PASS_CLOSEOUT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert _git_blob(FORECAST_PY) == FORECAST_ARTIFACT_PY_BLOB
    assert _git_blob(ALIGNMENT_EVIDENCE_PY) == ALIGNMENT_EVIDENCE_PY_BLOB
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB
    assert _git_blob(OBSERVATION_MODULE) == OBSERVATION_MODULE_BLOB
    assert _git_blob(PASS_OBSERVATION_MODULE) == COMPLETENESS_PASS_OBSERVATION_PY_BLOB
    assert _git_blob(PRESENCE_OBSERVATION_MODULE) == PRESENCE_OBSERVATION_PY_BLOB
    assert _git_blob(GRANT_WORKPAPER) == PARENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(GRANT_EVIDENCE) == PARENT_GRANT_EVIDENCE_BLOB
    assert _git_blob(GRANT_TEST) == PARENT_GRANT_TEST_BLOB
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    assert _git_blob(CONTRACT_TEST) == PARENT_CONTRACT_TEST_BLOB
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
    assert _git_blob(PRESENCE_R1_WORKPAPER) == PARENT_PRESENCE_R1_WORKPAPER_BLOB
    assert _git_blob(PRESENCE_R1_EVIDENCE) == PARENT_PRESENCE_R1_EVIDENCE_BLOB


def test_production_module_exists() -> None:
    assert PRODUCTION_MODULE.is_file()
    assert PRESENCE_OBSERVATION_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_default_import_does_not_wire_reviewed_set_loader() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_classify_records_three_grains_content_hash_and_precondition_3() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    result = IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactContentForReviewedGrainsReasonCode.CONTENT_FOR_REVIEWED_GRAINS_RECORDED
    )
    assert result.content_for_reviewed_grains_recorded is True
    assert result.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    assert result.content_row_count == 3
    assert result.coordinator_reviewed_identity_set_exists is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    assert result.reviewed_grain_identity_set_identity_sha256 == REVIEWED_SET_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    )
    assert result.review_cutoff_at == REVIEW_CUTOFF_AT
    assert result.review_cutoff_business_date == "2026-02-16"
    assert result.review_model_id == REVIEW_MODEL_ID
    assert result.review_quantiles == REVIEW_QUANTILES
    assert result.default_global_reviewed_set_loader_remains_empty is True
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert result.no_versioned_flip_precondition_1_holds is True
    assert result.no_versioned_flip_precondition_2_holds is True
    assert result.no_versioned_flip_precondition_3_holds is True
    assert result.no_versioned_flip_precondition_4_holds is False
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.no_reviewed_grain_identity_set_in_repository is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.frozen_reviewed_set_closeout_still_reports_no_reviewed is True
    assert result.frozen_completeness_pass_closeout_still_unauthorized is True
    assert result.frozen_presence_r1_still_reports_fail_closed_no_reviewed_set is True
    assert result.content_producer_on_empty_obtain_returns_none is True
    assert result.in_memory_catalog_artifact_produced_is_not_versioned_repository_artifact is True
    assert result.forbidden_derive_members_from_source_002 is True
    assert result.forbidden_invent_additional_members is True
    assert result.default_session_provider_left_unset is True
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_independent_producer_hash_matches_classify() -> None:
    replay_rows = _landed_replay_rows()
    produced = IncumbentForecastArtifactContentProducer(
        replay_rows=replay_rows,
        declared_catalog_source_kind=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF,
        uses_harvest_date_as_forecast_cutoff=False,
    ).produce()
    assert produced is not None
    assert produced.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    result = IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    assert result.content_identity_sha256 == produced.content_identity_sha256
    assert result.content_identity_sha256 == CONTENT_IDENTITY_SHA256


def test_default_empty_produce_still_none_after_classify() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    clear_v0_2_live_postgres_session_provider()
    assert IncumbentForecastArtifactContentProducer().produce() is None
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_origin_entries_empty_or_extra() -> None:
    classifier = IncumbentForecastArtifactContentForReviewedGrainsClassifier()
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        empty = classifier.classify()
    assert empty.reason_code is (
        IncumbentForecastArtifactContentForReviewedGrainsReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert empty.content_for_reviewed_grains_recorded is False
    assert empty.content_identity_sha256 == ""
    assert empty.content_row_count == 0
    assert empty.coordinator_reviewed_identity_set_exists is False
    assert empty.reviewed_identity_set_member_count == 0
    assert empty.no_versioned_flip_precondition_3_holds is False
    assert empty.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert empty.default_global_reviewed_set_loader_remains_empty is True

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
        IncumbentForecastArtifactContentForReviewedGrainsReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert mismatched.content_for_reviewed_grains_recorded is False
    assert mismatched.content_identity_sha256 == ""
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_closeouts_still_unauthorized_after_classify() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    assert load_reviewed_grain_identity_set() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        reviewed = ReviewedGrainIdentitySetCloseoutClassifier().classify()
        completeness = CompletenessPassCloseoutClassifier().classify()
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert reviewed.coordinator_reviewed_identity_set_exists is False
    assert completeness.s3_a2_completeness_pass_authorized is False
    assert completeness.no_reviewed_grain_identity_set_in_repository is True
    assert completeness.no_bindable_catalog_in_repository is True
    assert completeness.evaluation_instance_registry_available is False
    assert completeness.current_s3_daily_rowset_completeness_verified is False
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_presence_observation_still_reports_precondition_3_false() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    presence = IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert presence.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert presence.no_versioned_flip_precondition_3_holds is False
    assert presence.no_versioned_flip_precondition_4_holds is False
    presence_obs_r1_workpaper = PRESENCE_OBSERVATION_R1_WORKPAPER.read_text(encoding="utf-8")
    presence_obs_r1_payload = json.loads(
        PRESENCE_OBSERVATION_R1_EVIDENCE.read_text(encoding="utf-8")
    )
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=false" in presence_obs_r1_workpaper
    assert presence_obs_r1_payload["flags"]["NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS"] is False
    presence_r1_workpaper = PRESENCE_R1_WORKPAPER.read_text(encoding="utf-8")
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in presence_r1_workpaper


def test_r1_evidence_sha256_payload_without_self_key() -> None:
    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_r1_pointer_isolation_grant_snapshot_still_implemented_false() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert UNIQUE_FLIP + "=true" in live_intro
    assert UNIQUE_FLIP + "=false" not in live_intro
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTATION_AUTHORIZED=true"
        in live_intro
    )
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    grant_pointer = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if R1_POINTER_HEADING in grant_pointer:
        grant_pointer = grant_pointer.split(R1_POINTER_HEADING, 1)[0]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_pointer
    r1_pointer = plan.split(R1_POINTER_HEADING, 1)[1]
    if "### 4.5" in r1_pointer:
        r1_pointer = r1_pointer.split("### 4.5", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_pointer
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=true" in r1_pointer
    assert CONTENT_IDENTITY_SHA256 in r1_pointer
    assert amendment.count("## 200.") == 1
    assert amendment.count("## 201.") == 1
    grant_snapshot = amendment.split("## 200.", 1)[1]
    if "## 201." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 201.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    r1_snapshot = amendment.split("## 201.", 1)[1]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=true" in r1_snapshot
    assert CONTENT_IDENTITY_SHA256 in r1_snapshot


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper
    assert UNIQUE_FLIP + "=true" in workpaper
    assert CONTENT_IDENTITY_SHA256 in workpaper


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert (
        payload["flags"][
            "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED"
        ]
        is False
    )
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS"] is True
    assert r1["flags"]["NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS"] is False
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["content"]["content_identity_sha256"] == CONTENT_IDENTITY_SHA256


def test_default_catalog_remain_fail_closed_after_classify() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )
    _assert_harvest_replay_and_provider_remain_empty()
