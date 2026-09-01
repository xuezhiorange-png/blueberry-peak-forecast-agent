"""S3-A2 incumbent forecast artifact presence-package independent-review R1 tests."""

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
    s3_a2_incumbent_forecast_artifact_presence_package_independent_review as independent_review,
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
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

IncumbentForecastArtifactPresencePackageIndependentReviewClassifier = (
    independent_review.IncumbentForecastArtifactPresencePackageIndependentReviewClassifier
)
IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode = (
    independent_review.IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode
)
IncumbentForecastArtifactContentForReviewedGrainsClassifier = (
    content_for_reviewed.IncumbentForecastArtifactContentForReviewedGrainsClassifier
)
IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)

PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "s3_a2_incumbent_forecast_artifact_presence_package_independent_review.py"
)
CONTENT_FOR_REVIEWED_GRAINS_MODULE = Path(
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
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-authorization.json"
)
GRANT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_presence_package_independent_review_authorization.py"
)
CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-presence-package-independent-review-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-contract.json"
)
CONTRACT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_presence_package_independent_review_contract.py"
)
PARENT_CONTENT_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.md"
)
PARENT_CONTENT_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.json"
)
PRESENCE_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-r1.md"
)
PRESENCE_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-r1.json"
)
PRESENCE_OBSERVATION_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
)
PRESENCE_OBSERVATION_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-r1.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB = "d206aa94afc558ba21a5e89221107b5507dcc1c2"
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
PARENT_GRANT_WORKPAPER_BLOB = "54832aaa1589eb11ef6331f484c777a8c12ef58c"
PARENT_GRANT_EVIDENCE_BLOB = "f53083a4d79f3cfddfee296bce4ca1233324f14e"
PARENT_GRANT_TEST_BLOB = "452b6b285ba5a00bdddc62f64b9ef1d311dc19ce"
PARENT_CONTRACT_DOC_BLOB = "1e519510b3b7f1d5deb1e3fd9415bcf0f411a280"
PARENT_CONTRACT_WORKPAPER_BLOB = "37a72dc7b6876f709aa5f8c5e1005dc18193b7bc"
PARENT_CONTRACT_EVIDENCE_BLOB = "348e13ea2c5914760d8c8af5a47d41f5c154f372"
PARENT_CONTRACT_TEST_BLOB = "9c143d0d2e9b05d70f13c7500498ae0b7beda71d"
PARENT_CONTENT_R1_WORKPAPER_BLOB = "3994a27c6ad0f7b523e4449eab8da78187b15991"
PARENT_CONTENT_R1_EVIDENCE_BLOB = "56f72e9dd9827a8c0d0d59d2bd5aec8dcd59191f"
PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB = "ad183d08bd11d08b7b36c519ca29297610dcf586"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB = "c40ee9e08ceffc0a1932f5b863b4ed2f22ea526a"
PARENT_PRESENCE_R1_WORKPAPER_BLOB = "316b117812c1461acc4eba1c42ad9dea5822c465"
PARENT_PRESENCE_R1_EVIDENCE_BLOB = "13628db068c3ed950925bc96ed5c1e152d1c35b1"
PARENT_GRANT_PR = 517
PARENT_GRANT_MERGE = "75c79ab6d21cb4902bd0eb9075bfa2a2885b8782"
PARENT_GRANT_COMMIT = "bf431bd7773c00b23385f2d234b467c53ef7eeb6"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "f1aad70faff7a7b352e62ab41733f9a7f7db9e5bb3cdd515409de4d921999a7f"
)
PARENT_CONTRACT_PR = 516
PARENT_CONTRACT_COMMIT = "ed0b5e53ee192cd1591525a30fda3c08206b4d5e"
PARENT_CONTRACT_MERGE = "34c7908c1e2706c665a1f0f3dadbc78d9c5f96b3"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "4ffea502d633e2981796a0e6efe217e62b0ba6883a9584861cb30c9476420b33"
)
PARENT_CONTENT_R1_PR = 515
PARENT_CONTENT_R1_COMMIT = "ec1b9014115319651d6d1cfb96daada032775bf1"
PARENT_CONTENT_R1_MERGE = "1f1c7e0dd0e2c5042222e31934ec56ffb41e8ec2"
PARENT_CONTENT_R1_EVIDENCE_JSON_SHA256 = (
    "ae96af5192ddf0a337e346c342edf494473d806d53fa1098a932d2ba2cab1d91"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
REVIEW_EVIDENCE_DIGEST_SHA256 = "40e03141b52188cafe9e9cb6842d14f2ebd6caa3abe1fd80142ad71162781f64"
UNIQUE_FLIP = (
    "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_PRESENCE_PACKAGE_INDEPENDENT_REVIEW_IMPLEMENTED"
)
IMPLEMENTATION_AUTHORIZED = (
    "S3_A2_INCUMBENT_FORECAST_ARTIFACT_PRESENCE_PACKAGE_"
    "INDEPENDENT_REVIEW_IMPLEMENTATION_AUTHORIZED"
)
GRANT_POINTER_HEADING = (
    "#### Incumbent forecast artifact presence-package independent-review "
    "implementation authorization pointer"
)
R1_POINTER_HEADING = (
    "#### Incumbent forecast artifact presence-package independent-review R1 pointer"
)
SECTION_203_HEADING = (
    "## 203. Incumbent forecast artifact presence-package independent-review "
    "implementation authorization pointer"
)
SECTION_204_HEADING = (
    "## 204. Incumbent forecast artifact presence-package independent-review R1 pointer"
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


def _independent_digest() -> str:
    return sha256_payload(
        {
            "reviewed_grain_identity_set_identity_sha256": REVIEWED_SET_IDENTITY_SHA256,
            "content_identity_sha256": CONTENT_IDENTITY_SHA256,
            "review_cutoff_at": REVIEW_CUTOFF_AT,
            "review_model_id": REVIEW_MODEL_ID,
            "review_quantiles": REVIEW_QUANTILES,
            "reviewed_identity_set_member_count": REVIEW_MEMBER_COUNT,
            "repository_presence_observation_recorded": True,
        }
    )


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
    assert _git_blob(CONTENT_FOR_REVIEWED_GRAINS_MODULE) == CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB
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
    assert _git_blob(PARENT_CONTENT_R1_WORKPAPER) == PARENT_CONTENT_R1_WORKPAPER_BLOB
    assert _git_blob(PARENT_CONTENT_R1_EVIDENCE) == PARENT_CONTENT_R1_EVIDENCE_BLOB
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_WORKPAPER)
        == PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB
    )
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_EVIDENCE) == PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB
    )
    assert _git_blob(PRESENCE_R1_WORKPAPER) == PARENT_PRESENCE_R1_WORKPAPER_BLOB
    assert _git_blob(PRESENCE_R1_EVIDENCE) == PARENT_PRESENCE_R1_EVIDENCE_BLOB


def test_production_module_exists() -> None:
    assert PRODUCTION_MODULE.is_file()
    assert CONTENT_FOR_REVIEWED_GRAINS_MODULE.is_file()
    assert PRESENCE_OBSERVATION_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_default_import_does_not_wire_reviewed_set_loader() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_classify_records_independent_review_digest_and_precondition_4() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    result = IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.PRESENCE_PACKAGE_INDEPENDENT_REVIEW_RECORDED
    )
    assert result.presence_package_independent_review_recorded is True
    assert result.review_evidence_digest_sha256 == REVIEW_EVIDENCE_DIGEST_SHA256
    assert result.review_evidence_digest_sha256 == _independent_digest()
    assert result.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    assert result.content_row_count == 3
    assert result.repository_presence_observation_recorded is True
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
    assert result.no_versioned_flip_precondition_4_holds is True
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.no_reviewed_grain_identity_set_in_repository is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.in_memory_catalog_is_not_presence_package is True
    assert result.default_session_provider_left_unset is True
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_digest_is_computed_from_existing_identities_not_invented() -> None:
    content = IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    result = IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    assert result.content_identity_sha256 == content.content_identity_sha256
    assert result.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        content.reviewed_grain_identity_set_identity_sha256
    )
    assert result.review_evidence_digest_sha256 == _independent_digest()


def test_default_empty_produce_still_none_after_classify() -> None:
    IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    clear_v0_2_live_postgres_session_provider()
    assert IncumbentForecastArtifactContentProducer().produce() is None
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_origin_entries_empty_or_extra() -> None:
    classifier = IncumbentForecastArtifactPresencePackageIndependentReviewClassifier()
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        empty = classifier.classify()
    assert empty.reason_code is (
        IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert empty.presence_package_independent_review_recorded is False
    assert empty.review_evidence_digest_sha256 == ""
    assert empty.content_identity_sha256 == ""
    assert empty.no_versioned_flip_precondition_4_holds is False
    assert empty.no_versioned_incumbent_forecast_artifact_in_repository is True

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
        IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert mismatched.presence_package_independent_review_recorded is False
    assert mismatched.review_evidence_digest_sha256 == ""
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_content_producer_returns_none() -> None:
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains."
        "IncumbentForecastArtifactContentProducer.produce",
        return_value=None,
    ):
        result = IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.CONTENT_PRODUCER_RETURNED_NONE
    )
    assert result.presence_package_independent_review_recorded is False
    assert result.review_evidence_digest_sha256 == ""
    assert result.no_versioned_flip_precondition_4_holds is False
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_closeouts_still_unauthorized_after_classify() -> None:
    IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
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
    IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
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


def test_r1_does_not_flip_no_versioned() -> None:
    result = IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    assert result.no_versioned_flip_precondition_4_holds is True
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )


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
    assert f"{IMPLEMENTATION_AUTHORIZED}=true" in live_intro
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
    assert "NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS=true" in r1_pointer
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in r1_pointer
    assert CONTENT_IDENTITY_SHA256 in r1_pointer
    assert amendment.count(SECTION_203_HEADING) == 1
    assert amendment.count(SECTION_204_HEADING) == 1
    assert amendment.count("## 202.") == 1
    assert plan.count(GRANT_POINTER_HEADING) == 1
    assert plan.count(R1_POINTER_HEADING) == 1
    grant_snapshot = amendment.split("## 203.", 1)[1]
    if "## 204." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 204.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    r1_snapshot = amendment.split("## 204.", 1)[1]
    if "\n## " in r1_snapshot:
        r1_snapshot = r1_snapshot.split("\n## ", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS=true" in r1_snapshot
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in r1_snapshot
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in r1_snapshot


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
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in workpaper
    assert "NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS=true" in workpaper
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in workpaper


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][UNIQUE_FLIP] is False
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS"] is True
    assert r1["flags"]["NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["review"]["content_identity_sha256"] == CONTENT_IDENTITY_SHA256
    assert r1["review"]["review_evidence_digest_sha256"] == REVIEW_EVIDENCE_DIGEST_SHA256


def test_default_catalog_remain_fail_closed_after_classify() -> None:
    IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )
