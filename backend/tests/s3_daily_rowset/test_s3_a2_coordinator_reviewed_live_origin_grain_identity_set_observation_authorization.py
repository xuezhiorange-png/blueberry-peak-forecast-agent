"""S3-A2 coordinator-reviewed live-origin grain identity-set observation authorization tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
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
    CompletenessPassCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_MEMBER_COUNT,
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
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-contract.json"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PRESENCE_CONTRACT = Path(
    "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md"
)
REVIEWED_SET_CLOSEOUT_CONTRACT = Path(
    "docs/v0-3/s3/s3-reviewed-grain-identity-set-closeout-contract.md"
)
COMPLETENESS_PASS_CLOSEOUT_CONTRACT = Path("docs/v0-3/s3/s3-completeness-pass-closeout-contract.md")
IDENTITY_SET_CONTRACT = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
)
LANDING_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation.py"
)
COMPLETENESS_PASS_CLOSEOUT_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py"
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
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB = "07335abbf900611c2c7f990bc7a0b92a485e111d"
PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB = "f46e0d7330b022185b55dbea31d381d1a9757d04"
PARENT_IDENTITY_SET_CONTRACT_DOC_BLOB = "ea729fc2e31d305a5f40baf2cbf028e9645d5745"
PARENT_CONTRACT_PR = 504
PARENT_CONTRACT_COMMIT = "9672221f3874bd9d4a2759fd3c232fa3542bcf01"
PARENT_CONTRACT_MERGE = "b4d9563de530356b2faa7e6b692f11fe3c1dc546"
PARENT_CONTRACT_TREE_SHA = "a3d9274f909ae72fdb42c27845400dfeaa57cd39"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "a063ff025af7dcc61ed8bcc9ec37e0273df6f2c3c3ed38285a02ef7916a5d777"
)
PARENT_CONTRACT_DOC_BLOB = "43ce74a76cfb8a7f96cff5121eb7ae9f72bfd2b8"
PARENT_CONTRACT_WORKPAPER_BLOB = "d88dfdca891a3a9925d0db7137a8d08ea0dadff1"
PARENT_CONTRACT_EVIDENCE_BLOB = "40166a8298fca091eae37e0eb7bd311ccd8b51e6"
PARENT_IDENTITY_SET_R1_PR = 503
PARENT_IDENTITY_SET_R1_COMMIT = "2a678dcaf02a766c8eb3158090d1e411d77d620b"
PARENT_IDENTITY_SET_R1_MERGE = "1a788e614e58989ed6b777c2c0a4392931dab4fa"
PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256 = (
    "ac5fe6cd2ca3e108bf46d3c7bb7572f50407ae3f641c1936fc846314d6001df3"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
UNIQUE_FLIP = (
    "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_"
    "OBSERVATION_IMPLEMENTATION_AUTHORIZED"
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


def test_grant_unique_flip_is_observation_implementation_authorized() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[UNIQUE_FLIP] is True
    assert flags[
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_CONTRACT_AUTHORIZED"
    ]
    assert flags[
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED"
    ] is (False)
    assert flags["DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED"]
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
    parent = json.loads(CONTRACT_EVIDENCE.read_text(encoding="utf-8"))
    assert parent["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert parent["authorization"][
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation_contract_authorized"
    ]
    assert not parent["authorization"][
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_observation_implementation_authorized"
    ]
    assert not parent["authorization"][
        "deterministic_coordinator_reviewed_live_origin_grain_identity_set_observation_implemented"
    ]
    assert parent["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert parent["authorization"]["no_reviewed_grain_identity_set_in_repository"] is False


def test_parent_presence_and_contract_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_presence_contract_blob"] == PARENT_PRESENCE_CONTRACT_BLOB
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["base_main_sha"] == PARENT_CONTRACT_MERGE
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_BLOB
    assert _git_blob(REVIEWED_SET_CLOSEOUT_CONTRACT) == PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB
    assert (
        _git_blob(COMPLETENESS_PASS_CLOSEOUT_CONTRACT)
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB
    )
    assert _git_blob(IDENTITY_SET_CONTRACT) == PARENT_IDENTITY_SET_CONTRACT_DOC_BLOB
    assert _git_blob(LANDING_MODULE) == IDENTITY_SET_LANDING_PY_BLOB


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
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py"))
        == REVIEWED_SET_CLOSEOUT_PY_BLOB
    )
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


def test_landed_artifact_exists_and_default_loader_remains_empty_after_grant() -> None:
    artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
    assert artifact.artifact_available is True
    assert len(artifact.members) == REVIEW_MEMBER_COUNT
    assert artifact.artifact_id == REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    assert artifact.artifact_id == REVIEWED_SET_IDENTITY_SHA256
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_fail_closed_produce_still_records_pass_unauthorized_after_grant() -> None:
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
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )
    assert produced.no_bindable_catalog_in_repository is True
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.reason_code is ReviewedSetCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert completeness.reason_code is CompletenessPassCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert completeness.s3_a2_completeness_pass_authorized is False
    assert completeness.weather_and_plans_block_completeness_pass is True


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
    assert flags["LATER_R1_MAY_OBSERVE_THE_ALREADY_LANDED_THREE_GRAIN_ARTIFACT"] is True
    assert flags["LATER_R1_MUST_NOT_AUTO_WIRE_AT_IMPORT"] is True
    assert flags["LATER_R1_MUST_NOT_REWRITE_FROZEN_CLOSEOUT_BYTES"] is True


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
    assert PARENT_CONTRACT_COMMIT[:7] in workpaper
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in workpaper
    assert "REVIEW_MEMBER_COUNT=3" in workpaper
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in workpaper


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_CONTRACT_AUTHORIZED=true"
        in (live_intro)
    )
    assert "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=true" in (
        live_intro
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=true"
        not in live_intro
    )
    assert (
        "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.md"
        in (plan)
    )
    assert "## 190." in amendment
    assert "## 191." in amendment
    assert f"{UNIQUE_FLIP}=true" in amendment
    grant_snapshot = amendment.split("## 191.", 1)[1]
    if "## 192." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 192.", 1)[0]
    assert UNIQUE_FLIP + "=true" in grant_snapshot
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED=false"
        in grant_snapshot
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in grant_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in grant_snapshot
    assert "WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true" in grant_snapshot
    contract_snapshot = amendment.split("## 190.", 1)[1]
    if "## 191." in contract_snapshot:
        contract_snapshot = contract_snapshot.split("## 191.", 1)[0]
    assert UNIQUE_FLIP + "=false" in contract_snapshot
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_CONTRACT_AUTHORIZED=true"
        in (contract_snapshot)
    )
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert (
        "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-observation-authorization.md"
        in (contract_pointer)
    )
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert (
        payload["flags"][
            "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVATION_IMPLEMENTED"
        ]
        is False
    )


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_r1"] is True
    assert not PRODUCTION_MODULE.exists()
    assert LANDING_MODULE.is_file()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_parent_contract_commit_is_named_for_traceability() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert PARENT_CONTRACT_COMMIT[:7] in json.dumps(payload)
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert payload["parent_identity_set_r1_commit"] == PARENT_IDENTITY_SET_R1_COMMIT
    assert payload["parent_identity_set_r1_merge"] == PARENT_IDENTITY_SET_R1_MERGE
    assert (
        payload["parent_identity_set_r1_evidence_json_sha256"]
        == PARENT_IDENTITY_SET_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_identity_set_r1_pr"] == PARENT_IDENTITY_SET_R1_PR


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
        ("LATER_R1_MAY_OBSERVE_THE_ALREADY_LANDED_THREE_GRAIN_ARTIFACT", True),
        ("LATER_R1_MUST_NOT_AUTO_WIRE_AT_IMPORT", True),
        ("LATER_R1_MUST_NOT_REWRITE_FROZEN_CLOSEOUT_BYTES", True),
        ("DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED", True),
        ("DETERMINISTIC_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTED", True),
    ],
)
def test_grant_keeps_safety_flags(flag: str, expected: bool) -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"][flag] is expected
