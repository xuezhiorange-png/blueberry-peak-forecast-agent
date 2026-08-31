"""S3-A2 default catalog live-origin construction implementation authorization tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DOC = REPO_ROOT / "docs/v0-3/s3/s3-default-catalog-live-origin-construction-contract.md"
CONTRACT_WORKPAPER = (
    REPO_ROOT / "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-construction-contract.md"
)
CONTRACT_EVIDENCE = (
    REPO_ROOT / "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-construction-contract.json"
)
GRANT_WORKPAPER = (
    REPO_ROOT
    / "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-construction-authorization.md"
)
GRANT_EVIDENCE = (
    REPO_ROOT
    / "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-construction-authorization.json"
)
AMENDMENT = REPO_ROOT / "docs/v0-3/s3/s3-daily-rowset-amendment.md"
DEVELOPMENT_PLAN = REPO_ROOT / "docs/v0-3/development-plan.md"
PRESENCE_CONTRACT = (
    REPO_ROOT / "docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md"
)
PRODUCTION_DIR = REPO_ROOT / "backend/app/s3_daily_rowset"

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_CONTRACT_COMMIT = "b5fce9f5ad8d4e3e6d01d65c90ba6960eded61e7"
PARENT_CONTRACT_MERGE = "edace90a66e9d5f11c398a4a762949ec6d5435cc"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "250a77441070da1243c722b22af60aa4efaac17760e01a4133f1de0abe69af3d"
)
PARENT_CONTRACT_DOC_BLOB = "cc6f93a5bd48606684d40a26f4689d797f848e10"
PARENT_CONTRACT_WORKPAPER_BLOB = "aa0b5031c2d11d02b374d5ea9431b7d47f64db5b"
PARENT_CONTRACT_EVIDENCE_BLOB = "e6432776f840e7c6e5ba33eb3247e4d071e81167"
UNIQUE_FLIP = "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED"
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
    assert flags["S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_CONTRACT_AUTHORIZED"] is True
    assert flags["DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED"] is False
    assert flags["DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED"] is True
    assert flags["CONTRACT_AUTHORIZED"] is True
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False


def test_parent_contract_blobs_and_evidence_remain() -> None:
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB
    parent = json.loads(CONTRACT_EVIDENCE.read_text(encoding="utf-8"))
    assert parent["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert parent["authorization"][
        "s3_a2_default_catalog_live_origin_construction_contract_authorized"
    ]
    assert not parent["authorization"][
        "s3_a2_default_catalog_live_origin_construction_implementation_authorized"
    ]
    assert not parent["authorization"][
        "deterministic_default_catalog_live_origin_construction_implemented"
    ]


def test_parent_presence_and_contract_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["parent_presence_contract_blob"] == PARENT_PRESENCE_CONTRACT_BLOB
    assert payload["parent_contract_evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert payload["parent_contract_doc_blob"] == PARENT_CONTRACT_DOC_BLOB
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert payload["parent_contract_pr"] == 486
    assert payload["base_main_sha"] == PARENT_CONTRACT_MERGE
    assert _git_blob(PRESENCE_CONTRACT) == PARENT_PRESENCE_CONTRACT_BLOB


def test_frozen_catalog_grain_and_obtain_blobs_remain() -> None:
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


def test_bare_default_catalog_still_no_versioned_after_grant() -> None:
    clear_v0_2_live_postgres_session_provider()
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
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
    assert "b5fce9f" in workpaper


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED=false" in live_intro
    assert "s3-a2-default-catalog-live-origin-construction-authorization.md" in plan
    assert "## 173." in amendment
    assert f"{UNIQUE_FLIP}=true" in amendment
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED=false" in amendment
    assert "## 172." in amendment
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-default-catalog-live-origin-construction-authorization.md" in contract_pointer


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    matches = list(PRODUCTION_DIR.glob("*default_catalog_live_origin_construction*"))
    assert matches == []
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["grant_only"] is True
    assert payload["this_pr_is_not_r1"] is True
    assert payload["flags"][
        "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED"
    ] is (False)


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
        ("WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION", True),
        ("S3_A2_COMPLETENESS_PASS_AUTHORIZED", False),
    ],
)
def test_grant_keeps_safety_flags(flag: str, expected: bool) -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["flags"][flag] is expected
