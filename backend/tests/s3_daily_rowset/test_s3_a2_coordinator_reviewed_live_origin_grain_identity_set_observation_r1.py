"""S3-A2 coordinator-reviewed live-origin grain identity-set observation R1 tests."""

from __future__ import annotations

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
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
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
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
    assert_forecast_artifact_py_historical_blob_pinned,
)

CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier = (
    observation.CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier
)
ObservationReasonCode = observation.ObservationReasonCode
PRODUCTION_MODULE = Path(
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
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.json"
)
CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.json"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/"
    "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.json"
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
PARENT_GRANT_PR = 505
PARENT_GRANT_MERGE = "c801c2004222082d33064b2f23bf93861b586a42"
PARENT_GRANT_COMMIT = "fc73cd5613d77c6e5b4f739c6af6b485481eddc1"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "5f8600f11581d9290440b07a1660e2ee3dd2a9eda8c0da31135d20e567817ade"
)
PARENT_GRANT_WORKPAPER_BLOB = "c397d4e81157ddaa3676f82a1c63e4d26b011119"
PARENT_GRANT_EVIDENCE_BLOB = "430c7dfb14272de359040aa6bf1fb39c4a238d7d"
PARENT_CONTRACT_PR = 504
PARENT_CONTRACT_COMMIT = "9672221f3874bd9d4a2759fd3c232fa3542bcf01"
PARENT_CONTRACT_MERGE = "b4d9563de530356b2faa7e6b692f11fe3c1dc546"
PARENT_CONTRACT_DOC_BLOB = "43ce74a76cfb8a7f96cff5121eb7ae9f72bfd2b8"
PARENT_CONTRACT_WORKPAPER_BLOB = "d88dfdca891a3a9925d0db7137a8d08ea0dadff1"
PARENT_CONTRACT_EVIDENCE_BLOB = "40166a8298fca091eae37e0eb7bd311ccd8b51e6"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "a063ff025af7dcc61ed8bcc9ec37e0273df6f2c3c3ed38285a02ef7916a5d777"
)
PARENT_IDENTITY_SET_R1_PR = 503
PARENT_IDENTITY_SET_R1_COMMIT = "2a678dcaf02a766c8eb3158090d1e411d77d620b"
PARENT_IDENTITY_SET_R1_MERGE = "1a788e614e58989ed6b777c2c0a4392931dab4fa"
PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256 = (
    "ac5fe6cd2ca3e108bf46d3c7bb7572f50407ae3f641c1936fc846314d6001df3"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
UNIQUE_FLIP = (
    "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED"
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
    assert _git_blob(GRANT_WORKPAPER) == PARENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(GRANT_EVIDENCE) == PARENT_GRANT_EVIDENCE_BLOB
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB


def test_default_import_does_not_wire_reviewed_set_loader() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_classify_observes_landed_three_grain_artifact_then_uninstalls() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    result = CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier().classify()
    assert result.reason_code is (
        ObservationReasonCode.COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVED
    )
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
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_origin_is_not_exact_policy_set() -> None:
    classifier = CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier()
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        empty = classifier.classify()
    assert empty.reason_code is (
        ObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert empty.coordinator_reviewed_identity_set_exists is False
    assert empty.reviewed_identity_set_member_count == 0
    assert empty.reviewed_grain_identity_set_identity_sha256 == ""
    assert empty.artifact_available is False
    assert empty.default_global_reviewed_set_loader_remains_empty is True
    assert empty.s3_a2_completeness_pass_authorized is False
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
        ObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
    )
    assert mismatched.artifact_available is False
    assert mismatched.reviewed_identity_set_member_count == 0
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_frozen_closeouts_still_report_no_reviewed_after_observation() -> None:
    CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier().classify()
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


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_IMPLEMENTATION_AUTHORIZED"
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
    assert r1["parent_identity_set_r1_pr"] == PARENT_IDENTITY_SET_R1_PR
    assert r1["parent_identity_set_r1_commit"] == PARENT_IDENTITY_SET_R1_COMMIT
    assert r1["parent_identity_set_r1_merge"] == PARENT_IDENTITY_SET_R1_MERGE
    assert (
        r1["parent_identity_set_r1_evidence_json_sha256"]
        == PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256
    )
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"][
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_IMPLEMENTATION_AUTHORIZED"
    ]
    assert r1["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
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
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_IMPLEMENTATION_AUTHORIZED=true"
    ) in live_intro
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_CONTRACT_AUTHORIZED=true"
    ) in live_intro
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.md" in plan
    assert "## 191." in amendment
    assert "## 192." in amendment
    assert "## 190." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    grant_snapshot = amendment.split("## 191.", 1)[1]
    if "## 192." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 192.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_IMPLEMENTATION_AUTHORIZED=true"
    ) in grant_snapshot
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in grant_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in grant_snapshot
    r1_snapshot = amendment.split("## 192.", 1)[1]
    if "## 193." in r1_snapshot:
        r1_snapshot = r1_snapshot.split("## 193.", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in r1_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in r1_snapshot
    assert "DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true" in r1_snapshot
    contract_snapshot = amendment.split("## 190.", 1)[1].split("## 191.", 1)[0]
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
        "OBSERVATION_IMPLEMENTATION_AUTHORIZED=false"
    ) in contract_snapshot
    assert UNIQUE_FLIP + "=false" in contract_snapshot
    grant_pointer = plan.split(
        "#### Coordinator-reviewed live-origin grain identity-set observation "
        "implementation authorization pointer",
        1,
    )[1]
    if "#### Coordinator-reviewed live-origin grain identity-set observation R1 pointer" in (
        grant_pointer
    ):
        grant_pointer = grant_pointer.split(
            "#### Coordinator-reviewed live-origin grain identity-set observation R1 pointer",
            1,
        )[0]
    assert UNIQUE_FLIP + "=false" in grant_pointer
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-r1.md" in (
        contract_pointer
    )


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
    assert LANDING_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
