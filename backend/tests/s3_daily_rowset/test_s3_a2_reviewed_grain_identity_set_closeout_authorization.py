"""S3-A2 reviewed grain identity-set closeout authorization tests."""

from __future__ import annotations

import json
import subprocess
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
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
    DefaultCatalogBindableRepositoryClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
    EvaluationInstanceRegistryAvailableCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DOC = REPO_ROOT / "docs/v0-3/s3/s3-reviewed-grain-identity-set-closeout-contract.md"
CONTRACT_WORKPAPER = REPO_ROOT / (
    "docs/v0-3/s3/workpapers/s3-a2-reviewed-grain-identity-set-closeout-contract.md"
)
CONTRACT_EVIDENCE = REPO_ROOT / (
    "docs/v0-3/s3/evidence/s3-a2-reviewed-grain-identity-set-closeout-contract.json"
)
GRANT_WORKPAPER = REPO_ROOT / (
    "docs/v0-3/s3/workpapers/s3-a2-reviewed-grain-identity-set-closeout-authorization.md"
)
GRANT_EVIDENCE = REPO_ROOT / (
    "docs/v0-3/s3/evidence/s3-a2-reviewed-grain-identity-set-closeout-authorization.json"
)
AMENDMENT = REPO_ROOT / "docs/v0-3/s3/s3-daily-rowset-amendment.md"
DEVELOPMENT_PLAN = REPO_ROOT / "docs/v0-3/development-plan.md"
PRESENCE_CONTRACT = (
    REPO_ROOT / "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md"
)
AVAILABLE_CLOSEOUT_CONTRACT = (
    REPO_ROOT / "docs/v0-3/s3/s3-evaluation-instance-registry-available-closeout-contract.md"
)
PRODUCTION_MODULE = REPO_ROOT / (
    "backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py"
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
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_AVAILABLE_CLOSEOUT_CONTRACT_BLOB = "8e386c5bbe61239cc8645a09a46d8cc17cf0b8b0"
PARENT_CONTRACT_COMMIT = "aac0f7bef83d1dfa45b5f822175338abfa009328"
PARENT_CONTRACT_MERGE = "a66d30cc3d2d8940eef7737819e0729da3b8f17a"
PARENT_CONTRACT_PR = 495
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "0191067600e5419547d18e8c8b8768e46ccf955da1d968f9a355f953265f3cb2"
)
PARENT_CONTRACT_DOC_BLOB = "07335abbf900611c2c7f990bc7a0b92a485e111d"
PARENT_CONTRACT_WORKPAPER_BLOB = "53e8a95bea15d417c9c149adae96b2b5f35203a0"
PARENT_CONTRACT_EVIDENCE_BLOB = "84b108b3812399b86ac721320436a062c1087b6a"
PARENT_AVAILABLE_CLOSEOUT_R1_MERGE = "cf1c61fc31108211c06c8c8926cb81ef6962df51"
PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 = (
    "ebcc32b9443d9c23c9bb459472a9c275596bf76bb80d1e5caea8a04441a4ed1d"
)
UNIQUE_FLIP = "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED"
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


def test_grant_unique_flip_is_implementation_authorized() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[UNIQUE_FLIP] is True
    assert flags["S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_CONTRACT_AUTHORIZED"]
    assert flags["DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED"] is False
    assert flags["DETERMINISTIC_EVALUATION_INSTANCE_REGISTRY_AVAILABLE_CLOSEOUT_IMPLEMENTED"] is (
        True
    )
    assert flags["CONTRACT_AUTHORIZED"] is True
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False


def test_parent_contract_blobs_and_evidence_remain() -> None:
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    parent = json.loads(CONTRACT_EVIDENCE.read_text(encoding="utf-8"))
    assert parent["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert parent["authorization"]["s3_a2_reviewed_grain_identity_set_closeout_contract_authorized"]
    assert not parent["authorization"][
        "s3_a2_reviewed_grain_identity_set_closeout_implementation_authorized"
    ]
    assert not parent["authorization"][
        "deterministic_reviewed_grain_identity_set_closeout_implemented"
    ]


def test_parent_presence_and_contract_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_presence_contract_blob"] == PARENT_PRESENCE_CONTRACT_BLOB
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert payload["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert payload["base_main_sha"] == PARENT_CONTRACT_MERGE
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_BLOB
    assert _git_blob(AVAILABLE_CLOSEOUT_CONTRACT) == PARENT_AVAILABLE_CLOSEOUT_CONTRACT_BLOB


def test_frozen_catalog_grain_construction_and_binding_blobs_remain() -> None:
    assert (
        _git_blob(REPO_ROOT / "backend/app/s3_daily_rowset/catalog_artifact.py")
        == CATALOG_ARTIFACT_PY_BLOB
    )
    assert (
        _git_blob(REPO_ROOT / "backend/tests/s3_daily_rowset/test_catalog_artifact.py")
        == TEST_CATALOG_ARTIFACT_PY_BLOB
    )
    grain = (
        REPO_ROOT
        / "backend/app/s3_daily_rowset"
        / "incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
    )
    assert _git_blob(grain) == GRAIN_IDENTITY_SET_PY_BLOB
    content = REPO_ROOT / "backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py"
    assert _git_blob(content) == CONTENT_PRODUCER_PY_BLOB
    alembic = (
        REPO_ROOT / "backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py"
    )
    assert _git_blob(alembic) == ALEMBIC_BLOB
    obtain = REPO_ROOT / "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py"
    assert _git_blob(obtain) == OBTAIN_MODULE_BLOB
    construction = (
        REPO_ROOT / "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py"
    )
    assert _git_blob(construction) == CONSTRUCTION_MODULE_BLOB
    bindable = (
        REPO_ROOT / "backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py"
    )
    assert _git_blob(bindable) == BINDABLE_REPOSITORY_PY_BLOB
    available = (
        REPO_ROOT
        / "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
    )
    assert _git_blob(available) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(REPO_ROOT / "backend/app/s3_daily_rowset/binding.py") == BINDING_PY_BLOB
    assert (
        _git_blob(REPO_ROOT / "backend/app/s3_daily_rowset/forecast_artifact.py")
        == FORECAST_ARTIFACT_PY_BLOB
    )
    assert (
        _git_blob(
            REPO_ROOT / "backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"
        )
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )


def test_fail_closed_produce_still_records_no_reviewed_set_after_grant() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )
    assert produced.no_bindable_catalog_in_repository is True
    assert produced.evaluation_instance_registry_available is False
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert bindable.no_bindable_catalog_in_repository is True
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert available.evaluation_instance_registry_available is False
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_grant_does_not_flip_completeness_or_invent_weather_plans() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["WEATHER_UNAVAILABLE"] is True
    assert flags["PLANS_UNAVAILABLE"] is True
    assert flags["LLM_MUST_NOT_INVENT_TONNES"] is True
    assert flags["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert flags["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert flags["COMPLETENESS_VERIFICATION_STATUS"] == "CONTRACT_STILL_BOUND_BLOCKED"
    assert flags["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert flags["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is True
    assert flags["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert flags["AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP"] is True
    assert flags["DEFAULT_CATALOG_FIRST_BLOCKER"] == "ARTIFACT_PRODUCED"


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


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "s3-a2-reviewed-grain-identity-set-closeout-authorization.md" in plan
    assert "## 182." in amendment
    assert "## 181." in amendment
    assert f"{UNIQUE_FLIP}=true" in amendment
    grant_snapshot = amendment.split("## 182.", 1)[1]
    if "## 183." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 183.", 1)[0]
    assert "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED=false" in grant_snapshot
    assert UNIQUE_FLIP + "=true" in grant_snapshot
    contract_snapshot = amendment.split("## 181.", 1)[1].split("## 182.", 1)[0]
    assert "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=false" in (
        contract_snapshot
    )
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-reviewed-grain-identity-set-closeout-authorization.md" in contract_pointer
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"]["DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED"] is (
        False
    )


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_r1"] is True
    assert payload["flags"]["DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED"] is (
        False
    )
    assert not PRODUCTION_MODULE.exists()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_parent_contract_commit_is_named_for_traceability() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert PARENT_CONTRACT_COMMIT[:7] in json.dumps(payload)
    assert payload["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert payload["parent_available_closeout_r1_merge"] == PARENT_AVAILABLE_CLOSEOUT_R1_MERGE
    assert (
        payload["parent_available_closeout_r1_evidence_json_sha256"]
        == PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_JSON_SHA256
    )


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("NO_NEW_SQLALCHEMY_API_FAMILY", True),
        ("TEST_REMAINS_SEALED", True),
        ("CATALOG_ARTIFACT_PY_MUST_REMAIN_FROZEN", True),
        ("BINDING_PY_MUST_REMAIN_FROZEN", True),
        ("FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6", True),
        ("NO_BINDABLE_CATALOG_IN_REPOSITORY", True),
        ("NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY", True),
        ("DEFAULT_HARVEST_OBTAIN_EMPTY", True),
        ("WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION", True),
        ("S3_A2_COMPLETENESS_PASS_AUTHORIZED", False),
        ("AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP", True),
        ("EVALUATION_INSTANCE_REGISTRY_AVAILABLE", False),
        ("FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET", True),
        ("FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002", True),
    ],
)
def test_grant_keeps_safety_flags(flag: str, expected: bool) -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"][flag] is expected
