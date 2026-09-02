"""S3-A2 default catalog live-origin obtain implementation authorization tests."""

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
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DOC = REPO_ROOT / "docs/v0-3/s3/s3-default-catalog-live-origin-obtain-contract.md"
CONTRACT_WORKPAPER = (
    REPO_ROOT / "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-contract.md"
)
CONTRACT_EVIDENCE = (
    REPO_ROOT / "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-contract.json"
)
GRANT_WORKPAPER = (
    REPO_ROOT / "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-authorization.md"
)
GRANT_EVIDENCE = (
    REPO_ROOT / "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-authorization.json"
)
AMENDMENT = REPO_ROOT / "docs/v0-3/s3/s3-daily-rowset-amendment.md"
DEVELOPMENT_PLAN = REPO_ROOT / "docs/v0-3/development-plan.md"
PRESENCE_CONTRACT = (
    REPO_ROOT / "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md"
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256 = (
    "4422928e91f49807bf9fa4d6678bde06efcf2cc38a134611424aad9888243782"
)
PARENT_LIVE_ORIGIN_MERGE_SHA = "3fd69ccc292848e13f091bf731fc9241eb6bd4ec"
PARENT_LIVE_ORIGIN_EVIDENCE_JSON_SHA256 = (
    "36a64657db1e437e90999d0d9446368942faf9c07e68da52f2890ba297e1fcea"
)
PARENT_CONTRACT_COMMIT = "acf4486088688b8acafef4707cf8e18184b860d2"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "f3f13966dafe41cf13f840eb36aa22ad1910f1b0270508a06d105143ba61b6ae"
)
PARENT_CONTRACT_DOC_BLOB = "c42b4a550915e6a1ccd4f6feaf1a19cfb1cede10"
PARENT_CONTRACT_WORKPAPER_BLOB = "c649ce2f084d8cf29b2814a0a9700557fefca5c7"
PARENT_CONTRACT_EVIDENCE_BLOB = "ca5eadbba930f8a1b0b8ae873cf0699ac247d582"
UNIQUE_FLIP = "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED"
FORBIDDEN_THIS_GRANT_TOKENS = (
    "localhost",
    "5432",
    "psycopg",
    "content_bytes",
    "postgresql://",
)


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def test_grant_unique_flip_is_implementation_authorized() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[UNIQUE_FLIP] is True
    assert flags["S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_CONTRACT_AUTHORIZED"] is True
    assert flags["DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED"] is False
    assert flags["CONTRACT_AUTHORIZED"] is True
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False


def test_parent_contract_blobs_and_evidence_remain() -> None:
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    parent = json.loads(CONTRACT_EVIDENCE.read_text(encoding="utf-8"))
    assert parent["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert (
        parent["authorization"]["s3_a2_default_catalog_live_origin_obtain_contract_authorized"]
        is True
    )
    assert (
        parent["authorization"][
            "s3_a2_default_catalog_live_origin_obtain_implementation_authorized"
        ]
        is False
    )
    assert (
        parent["authorization"]["deterministic_default_catalog_live_origin_obtain_implemented"]
        is False
    )


def test_parent_presence_and_live_origin_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_presence_contract_blob"] == PARENT_PRESENCE_CONTRACT_BLOB
    assert (
        payload["parent_presence_r1_evidence_json_sha256"]
        == PARENT_PRESENCE_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_live_origin_execution_merge_sha"] == PARENT_LIVE_ORIGIN_MERGE_SHA
    assert (
        payload["parent_live_origin_execution_evidence_json_sha256"]
        == PARENT_LIVE_ORIGIN_EVIDENCE_JSON_SHA256
    )
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_BLOB


def test_frozen_catalog_and_grain_blobs_remain() -> None:
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


def test_default_catalog_still_no_versioned_after_grant() -> None:
    with patch_handoff_disabled(), patch("backend.app.db.session.AsyncSessionMaker", None):
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert S2IdentityAlignmentHarvestSource().obtain() == ()


def test_grant_does_not_flip_completeness_or_invent_weather_plans() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["WEATHER_UNAVAILABLE"] is True
    assert flags["PLANS_UNAVAILABLE"] is True
    assert flags["LLM_MUST_NOT_INVENT_TONNES"] is True
    assert flags["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert flags["COMPLETENESS_VERIFICATION_STATUS"] == "CONTRACT_STILL_BOUND_BLOCKED"


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
    assert "USER_GATE=授权" in GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "GRANT_ONLY=true" in GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "THIS_PR_IS_NOT_R1=true" in GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "acf4486" in GRANT_WORKPAPER.read_text(encoding="utf-8")


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    assert UNIQUE_FLIP in plan
    assert "s3-a2-default-catalog-live-origin-obtain-authorization.md" in plan
    assert "## 170." in amendment
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED=true" in amendment
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED=false" in amendment
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED=true" in plan
    assert "## 167." in amendment
    assert "## 168." in amendment
    assert "## 169." in amendment
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-default-catalog-live-origin-obtain-authorization.md" in contract_pointer


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    assert "USER_GATE=授权" in GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "THIS_PR_IS_NOT_R1=true" in GRANT_WORKPAPER.read_text(encoding="utf-8")
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_r1"] is True
    assert payload["flags"]["DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED"] is False


def test_parent_contract_commit_is_named_for_traceability() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert PARENT_CONTRACT_COMMIT[:7] in json.dumps(payload)


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("NO_NEW_SQLALCHEMY_API_FAMILY", True),
        ("TEST_REMAINS_SEALED", True),
        ("NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REMAINS_DEFAULT_BLOCKER", True),
        ("CATALOG_ARTIFACT_PY_MUST_REMAIN_FROZEN", True),
        ("FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6", True),
        ("NO_BINDABLE_CATALOG_IN_REPOSITORY", True),
        ("DEFAULT_HARVEST_OBTAIN_EMPTY", True),
    ],
)
def test_grant_keeps_safety_flags(flag: str, expected: bool) -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"][flag] is expected
