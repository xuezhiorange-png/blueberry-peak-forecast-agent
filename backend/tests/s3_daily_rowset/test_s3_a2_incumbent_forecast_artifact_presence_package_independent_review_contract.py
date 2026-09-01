"""S3-A2 incumbent forecast artifact presence-package independent-review contract tests."""

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
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
    assert_forecast_artifact_py_historical_blob_pinned,
)

IncumbentForecastArtifactContentForReviewedGrainsClassifier = (
    content_for_reviewed.IncumbentForecastArtifactContentForReviewedGrainsClassifier
)
IncumbentForecastArtifactContentForReviewedGrainsReasonCode = (
    content_for_reviewed.IncumbentForecastArtifactContentForReviewedGrainsReasonCode
)
IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)

CONTRACT_PATH = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-presence-package-independent-review-contract.md"
)
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-presence-package-independent-review-contract.json"
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
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PARENT_CONTENT_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.md"
)
PARENT_CONTENT_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.json"
)
PARENT_CONTENT_R1_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_r1.py"
)
PARENT_CONTENT_GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.md"
)
PARENT_CONTENT_GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-authorization.json"
)
PARENT_CONTENT_GRANT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_authorization.py"
)
PARENT_CONTENT_CONTRACT = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-content-for-reviewed-grains-contract.md"
)
PARENT_CONTENT_CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-contract.md"
)
PARENT_CONTENT_CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-contract.json"
)
PARENT_CONTENT_CONTRACT_TEST = Path(
    "backend/tests/s3_daily_rowset/"
    "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_contract.py"
)
PRESENCE_OBSERVATION_R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.md"
)
PRESENCE_OBSERVATION_R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json"
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
BASE_MAIN_SHA = "1f1c7e0dd0e2c5042222e31934ec56ffb41e8ec2"
BASE_MAIN_TREE_SHA = "8889d0d95165ef6cb1e0a9b6d7fb02f1ad7608ea"
PARENT_CONTENT_R1_PR = 515
PARENT_CONTENT_R1_COMMIT = "ec1b9014115319651d6d1cfb96daada032775bf1"
PARENT_CONTENT_R1_MERGE = "1f1c7e0dd0e2c5042222e31934ec56ffb41e8ec2"
PARENT_CONTENT_R1_EVIDENCE_JSON_SHA256 = (
    "ae96af5192ddf0a337e346c342edf494473d806d53fa1098a932d2ba2cab1d91"
)
PARENT_CONTENT_R1_WORKPAPER_BLOB = "3994a27c6ad0f7b523e4449eab8da78187b15991"
PARENT_CONTENT_R1_EVIDENCE_BLOB = "56f72e9dd9827a8c0d0d59d2bd5aec8dcd59191f"
PARENT_CONTENT_R1_TEST_BLOB = "8c00fba1402d75a8a39dade816eaba263ebcc8ef"
PARENT_CONTENT_GRANT_PR = 514
PARENT_CONTENT_GRANT_COMMIT = "9d3b2b7a08f5f658b69059a982268793cc2de7f3"
PARENT_CONTENT_GRANT_MERGE = "60e83b82632bdf73649634abb62e40d4854d5e82"
PARENT_CONTENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "f906e76c51ef238479fb24c682cc5180e070eca00efd7556e188add0623a98fc"
)
PARENT_CONTENT_GRANT_WORKPAPER_BLOB = "234af626036d56c078ed98f27e8609cd384c57f5"
PARENT_CONTENT_GRANT_EVIDENCE_BLOB = "49e8f93814904f0bd37d1fb4972e4207206536ce"
PARENT_CONTENT_GRANT_TEST_BLOB = "1d9ca027b67066d66e51874894aeab1a1d26bcda"
PARENT_CONTENT_CONTRACT_PR = 513
PARENT_CONTENT_CONTRACT_COMMIT = "b6d262bca7654566523f88030281a038c261f5b5"
PARENT_CONTENT_CONTRACT_MERGE = "41c09ab148390cfd8ee97eff7b051a7e241f19af"
PARENT_CONTENT_CONTRACT_DOC_BLOB = "c3d6ec6120222703f079fcafc77a0c9da2ecb374"
PARENT_CONTENT_CONTRACT_WORKPAPER_BLOB = "b8247226794a5f8504984ad3e71468ceae8a0d7d"
PARENT_CONTENT_CONTRACT_EVIDENCE_BLOB = "d335bdcad0c6ca7239b6e0ab6460f147c11c99e5"
PARENT_CONTENT_CONTRACT_TEST_BLOB = "12d9a22e64737ea66c99747bb5c6c764d751299f"
PARENT_CONTENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "911514b072a0f938e9c3aa382cd117220f8e18acf77d1c2b3ee516807390856b"
)
PARENT_PRESENCE_OBSERVATION_R1_PR = 512
PARENT_PRESENCE_OBSERVATION_R1_COMMIT = "3321cf83e518585027c07b770b1339c24ef5eb0b"
PARENT_PRESENCE_OBSERVATION_R1_MERGE = "3a15492d2233dfc32c4b6f3199b0d945c04689ad"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_JSON_SHA256 = (
    "ed3ecc806a1ede8f6b85f0c601bd518936cd6b78edef1024b06d65fb787b091b"
)
PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB = "ad183d08bd11d08b7b36c519ca29297610dcf586"
PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB = "c40ee9e08ceffc0a1932f5b863b4ed2f22ea526a"
PARENT_PRESENCE_R1_PR = 481
PARENT_PRESENCE_R1_COMMIT = "bffd2bfc9c0d9f8cbbbd6db7c37898b16b5808a1"
PARENT_PRESENCE_R1_MERGE = "fde7acec586e83eafd99b755f3049d9e3e4a074c"
PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256 = (
    "4422928e91f49807bf9fa4d6678bde06efcf2cc38a134611424aad9888243782"
)
PARENT_PRESENCE_R1_WORKPAPER_BLOB = "316b117812c1461acc4eba1c42ad9dea5822c465"
PARENT_PRESENCE_R1_EVIDENCE_BLOB = "13628db068c3ed950925bc96ed5c1e152d1c35b1"
PARENT_PRESENCE_CONTRACT_GIT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
UNIQUE_FLIP = (
    "S3_A2_INCUMBENT_FORECAST_ARTIFACT_PRESENCE_PACKAGE_INDEPENDENT_REVIEW_CONTRACT_AUTHORIZED"
)
THIS_FAMILY_IMPLEMENTATION_AUTHORIZED = (
    "S3_A2_INCUMBENT_FORECAST_ARTIFACT_PRESENCE_PACKAGE_"
    "INDEPENDENT_REVIEW_IMPLEMENTATION_AUTHORIZED"
)
THIS_FAMILY_IMPLEMENTED = (
    "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_PRESENCE_PACKAGE_INDEPENDENT_REVIEW_IMPLEMENTED"
)
PARENT_R1_POINTER_HEADING = (
    "#### Incumbent forecast artifact content for reviewed grains R1 pointer"
)
NEW_POINTER_HEADING = (
    "#### Incumbent forecast artifact presence-package independent-review contract pointer"
)
SECTION_202_HEADING = (
    "## 202. Incumbent forecast artifact presence-package independent-review contract pointer"
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


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_frozen_blobs_and_parent_packages_unchanged() -> None:
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
    assert _git_blob(CONTENT_FOR_REVIEWED_GRAINS_MODULE) == CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB
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
    assert _git_blob(PASS_OBSERVATION_MODULE) == COMPLETENESS_PASS_OBSERVATION_PY_BLOB
    assert _git_blob(PRESENCE_OBSERVATION_MODULE) == PRESENCE_OBSERVATION_PY_BLOB
    assert _git_blob(PARENT_CONTENT_R1_WORKPAPER) == PARENT_CONTENT_R1_WORKPAPER_BLOB
    assert _git_blob(PARENT_CONTENT_R1_EVIDENCE) == PARENT_CONTENT_R1_EVIDENCE_BLOB
    assert _git_blob(PARENT_CONTENT_R1_TEST) == PARENT_CONTENT_R1_TEST_BLOB
    assert _git_blob(PARENT_CONTENT_GRANT_WORKPAPER) == PARENT_CONTENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(PARENT_CONTENT_GRANT_EVIDENCE) == PARENT_CONTENT_GRANT_EVIDENCE_BLOB
    assert _git_blob(PARENT_CONTENT_GRANT_TEST) == PARENT_CONTENT_GRANT_TEST_BLOB
    assert _git_blob(PARENT_CONTENT_CONTRACT) == PARENT_CONTENT_CONTRACT_DOC_BLOB
    assert _git_blob(PARENT_CONTENT_CONTRACT_WORKPAPER) == PARENT_CONTENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(PARENT_CONTENT_CONTRACT_EVIDENCE) == PARENT_CONTENT_CONTRACT_EVIDENCE_BLOB
    assert _git_blob(PARENT_CONTENT_CONTRACT_TEST) == PARENT_CONTENT_CONTRACT_TEST_BLOB
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_WORKPAPER)
        == PARENT_PRESENCE_OBSERVATION_R1_WORKPAPER_BLOB
    )
    assert (
        _git_blob(PRESENCE_OBSERVATION_R1_EVIDENCE) == PARENT_PRESENCE_OBSERVATION_R1_EVIDENCE_BLOB
    )
    assert _git_blob(PRESENCE_R1_WORKPAPER) == PARENT_PRESENCE_R1_WORKPAPER_BLOB
    assert _git_blob(PRESENCE_R1_EVIDENCE) == PARENT_PRESENCE_R1_EVIDENCE_BLOB
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_GIT_BLOB


def test_production_module_is_filename_only_and_pep420_holds() -> None:
    assert CONTENT_FOR_REVIEWED_GRAINS_MODULE.is_file()
    assert PRESENCE_OBSERVATION_MODULE.is_file()
    assert PASS_OBSERVATION_MODULE.is_file()
    assert OBSERVATION_MODULE.is_file()
    assert LANDING_MODULE.is_file()
    assert PRODUCTION_MODULE.name == (
        "s3_a2_incumbent_forecast_artifact_presence_package_independent_review.py"
    )
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "THIS_PR_IS_NOT_R1=true" in contract
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_PRESENCE_PACKAGE_INDEPENDENT_REVIEW=true" in contract
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in contract
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_classify_content_for_reviewed_grains_records_content_and_precondition_3() -> None:
    result = IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    assert result.reason_code is (
        IncumbentForecastArtifactContentForReviewedGrainsReasonCode.CONTENT_FOR_REVIEWED_GRAINS_RECORDED
    )
    assert result.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    assert result.content_row_count == 3
    assert result.coordinator_reviewed_identity_set_exists is True
    assert result.reviewed_identity_set_member_count == REVIEW_MEMBER_COUNT
    assert result.reviewed_grain_identity_set_identity_sha256 == REVIEWED_SET_IDENTITY_SHA256
    assert result.reviewed_grain_identity_set_identity_sha256 == (
        REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    )
    assert result.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert result.no_versioned_flip_precondition_3_holds is True
    assert result.no_versioned_flip_precondition_4_holds is False
    assert result.default_global_reviewed_set_loader_remains_empty is True
    assert result.s3_a2_completeness_pass_authorized is False
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_frozen_presence_observation_still_reports_precondition_3_false() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    presence = IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
    assert presence.no_versioned_incumbent_forecast_artifact_in_repository is True
    assert presence.no_versioned_flip_precondition_3_holds is False
    assert presence.no_versioned_flip_precondition_4_holds is False


def test_default_content_producer_on_empty_obtain_returns_none() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    assert IncumbentForecastArtifactContentProducer().produce() is None


def test_frozen_closeouts_still_unauthorized_after_content_classify() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
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


def test_default_catalog_remain_fail_closed_after_classify() -> None:
    IncumbentForecastArtifactContentForReviewedGrainsClassifier().classify()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert f"{THIS_FAMILY_IMPLEMENTATION_AUTHORIZED}=false" in text
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in text
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=true"
        in text
    )
    assert "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in text
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in text
    assert "FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED=true" in text
    assert "FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "DEFAULT_CATALOG_FIRST_BLOCKER=ARTIFACT_PRODUCED" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_GATE_ACCEPTED_AS=可以继续" in text
    assert "USER_UTTERANCE=可以继续" in text
    assert "CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_PRESENCE_PACKAGE_INDEPENDENT_REVIEW=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true" in text
    assert "NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS=true" in text
    assert "NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS=true" in text
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=true" in text
    assert "NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS=false" in text
    assert "LATER_R1_MAY_SATISFY_PRECONDITION_4_WITHOUT_FLIPPING_NO_VERSIONED=true" in text
    assert "LATER_R1_MUST_NOT_FLIP_NO_VERSIONED=true" in text
    assert "IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT=true" in text
    assert "CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE=true" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert f"PARENT_CONTENT_R1_PR={PARENT_CONTENT_R1_PR}" in text
    assert f"PARENT_CONTENT_R1_COMMIT={PARENT_CONTENT_R1_COMMIT}" in text
    assert f"PARENT_CONTENT_R1_MERGE={PARENT_CONTENT_R1_MERGE}" in text
    assert f"PARENT_PRESENCE_OBSERVATION_R1_PR={PARENT_PRESENCE_OBSERVATION_R1_PR}" in text
    assert f"PARENT_PRESENCE_R1_PR={PARENT_PRESENCE_R1_PR}" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert f"BASE_MAIN_TREE_SHA={BASE_MAIN_TREE_SHA}" in text
    assert f"REVIEWED_SET_IDENTITY_SHA256={REVIEWED_SET_IDENTITY_SHA256}" in text
    assert f"CONTENT_IDENTITY_SHA256={CONTENT_IDENTITY_SHA256}" in text
    assert f"IN_MEMORY_CATALOG_IDENTITY_SHA256={IN_MEMORY_CATALOG_IDENTITY_SHA256}" in text
    assert f"CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB={CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB}" in text
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
        "s3_a2_incumbent_forecast_artifact_presence_package_independent_review_contract_authorized"
    ]
    assert not payload["authorization"][
        "s3_a2_incumbent_forecast_artifact_presence_package_independent_review_implementation_authorized"
    ]
    assert not payload["authorization"][
        "deterministic_incumbent_forecast_artifact_presence_package_independent_review_implemented"
    ]
    assert payload["authorization"][
        "deterministic_incumbent_forecast_artifact_content_for_reviewed_grains_implemented"
    ]
    assert payload["authorization"][
        "deterministic_incumbent_forecast_artifact_content_producer_implemented"
    ]
    assert (
        payload["authorization"]["no_versioned_incumbent_forecast_artifact_in_repository"] is True
    )
    assert payload["authorization"]["no_reviewed_grain_identity_set_in_repository"] is False
    assert payload["authorization"]["default_global_reviewed_set_loader_remains_empty"] is True
    assert payload["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert payload["reviewed_artifact"]["review_member_count"] == 3
    assert payload["reviewed_artifact"]["identity_sha256"] == REVIEWED_SET_IDENTITY_SHA256
    assert payload["reviewed_artifact"]["content_identity_sha256"] == CONTENT_IDENTITY_SHA256
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True
    assert payload["parent_content_r1"]["parent_content_r1_pr"] == PARENT_CONTENT_R1_PR
    assert payload["parent_content_r1"]["parent_content_r1_commit"] == PARENT_CONTENT_R1_COMMIT
    assert payload["parent_content_r1"]["parent_content_r1_merge"] == PARENT_CONTENT_R1_MERGE
    assert payload["parent_content_r1"]["parent_content_r1_evidence_json_sha256"] == (
        PARENT_CONTENT_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_content_grant"]["parent_content_grant_pr"] == PARENT_CONTENT_GRANT_PR
    assert payload["parent_content_contract"]["parent_content_contract_pr"] == (
        PARENT_CONTENT_CONTRACT_PR
    )
    assert payload["parent_presence_observation_r1"]["parent_presence_observation_r1_pr"] == (
        PARENT_PRESENCE_OBSERVATION_R1_PR
    )
    assert payload["parent_presence_r1"]["parent_presence_r1_pr"] == PARENT_PRESENCE_R1_PR
    assert payload["base_main_sha"] == BASE_MAIN_SHA
    assert payload["base_main_tree_sha"] == BASE_MAIN_TREE_SHA
    assert payload["user_gate"] == "可以下一步"
    assert payload["contract_gate_accepted_as"] == "可以继续"
    assert payload["user_utterance"] == "可以继续"
    assert payload["no_versioned_flip_preconditions"]["no_versioned_flip_precondition_3_holds"]
    assert not payload["no_versioned_flip_preconditions"]["no_versioned_flip_precondition_4_holds"]


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_ONLY=true" in text
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in text
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert f"{UNIQUE_FLIP}=true" in text
    assert f"{THIS_FAMILY_IMPLEMENTATION_AUTHORIZED}=false" in text
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert f"PARENT_CONTENT_R1_PR={PARENT_CONTENT_R1_PR}" in text
    assert f"CONTENT_IDENTITY_SHA256={CONTENT_IDENTITY_SHA256}" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_development_plan_live_compact_flips_only_this_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=true"
        in live_intro
    )
    assert f"{THIS_FAMILY_IMPLEMENTATION_AUTHORIZED}=false" not in live_intro
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" not in live_intro
    assert (
        "S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTATION_AUTHORIZED=false"
        not in live_intro
    )
    assert (
        "DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_FOR_REVIEWED_GRAINS_IMPLEMENTED=false"
        not in live_intro
    )
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{THIS_FAMILY_IMPLEMENTATION_AUTHORIZED}=false" in contract
    r1_pointer = text.split(PARENT_R1_POINTER_HEADING, 1)[1]
    if NEW_POINTER_HEADING in r1_pointer:
        r1_pointer = r1_pointer.split(NEW_POINTER_HEADING, 1)[0]
    if "### 4.5" in r1_pointer:
        r1_pointer = r1_pointer.split("### 4.5", 1)[0]
    assert UNIQUE_FLIP not in r1_pointer
    assert "s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.md" in r1_pointer
    assert (
        "s3-incumbent-forecast-artifact-presence-package-independent-review-contract.md"
        in text.split("### 4.5", maxsplit=1)[0]
    )
    assert text.count(NEW_POINTER_HEADING) == 1


def test_amendment_records_pointer_and_isolates_section_201() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert text.count("## 201.") == 1
    assert text.count(SECTION_202_HEADING) == 1
    assert f"{UNIQUE_FLIP}=true" in text
    section_201 = text.split("## 201.", 1)[1]
    if "## 202." in section_201:
        section_201 = section_201.split("## 202.", 1)[0]
    assert UNIQUE_FLIP not in section_201
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=true" in section_201
    assert CONTENT_IDENTITY_SHA256 in section_201
    section_202 = text.split("## 202.", 1)[1]
    assert f"{UNIQUE_FLIP}=true" in section_202
    assert f"{THIS_FAMILY_IMPLEMENTATION_AUTHORIZED}=false" in section_202
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in section_202
    assert "NO_VERSIONED_FLIP_PRECONDITION_3_HOLDS=true" in section_202
    assert "NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS=false" in section_202
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in section_202
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_202
    assert CONTENT_IDENTITY_SHA256 in section_202
    assert REVIEWED_SET_IDENTITY_SHA256 in section_202
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in section_202
    lowered = section_202.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered
