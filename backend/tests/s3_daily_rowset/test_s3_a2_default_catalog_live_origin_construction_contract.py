"""S3-A2 default catalog live-origin construction contract freeze tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
PARENT_OBTAIN_CONTRACT_BLOB = "c42b4a550915e6a1ccd4f6feaf1a19cfb1cede10"
PARENT_OBTAIN_R1_EVIDENCE_BLOB = "4555f2618eb4cb85298470ac82573a2c11cd7475"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_OBTAIN_R1_EVIDENCE_JSON_SHA256 = (
    "46875227cc687708602dea79fc6c5a85db1a09d115acc80e4f48efc1655b3e8f"
)
PARENT_OBTAIN_R1_MERGE = "fd98db8d3ef9d8087fe96f27ae3469b273e62ac2"

CONTRACT_PATH = Path("docs/v0-3/s3/s3-default-catalog-live-origin-construction-contract.md")
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-construction-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-construction-contract.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PRODUCTION_DIR = Path("backend/app/s3_daily_rowset")
UNIQUE_FLIP = "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_CONTRACT_AUTHORIZED"
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


def _git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], text=True).strip()


def test_frozen_python_blobs_unchanged() -> None:
    assert _git_blob("backend/tests/s3_daily_rowset/test_catalog_artifact.py") == (
        TEST_CATALOG_ARTIFACT_PY_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/catalog_artifact.py") == CATALOG_ARTIFACT_PY_BLOB
    assert (
        _git_blob(
            "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
        )
        == GRAIN_IDENTITY_SET_PY_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
        == CONTENT_PRODUCER_PY_BLOB
    )
    assert (
        _git_blob("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
        == ALEMBIC_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
        == OBTAIN_MODULE_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-default-catalog-live-origin-obtain-contract.md")
        == PARENT_OBTAIN_CONTRACT_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-r1.json")
        == PARENT_OBTAIN_R1_EVIDENCE_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md")
        == PARENT_PRESENCE_CONTRACT_BLOB
    )


def test_bare_default_catalog_still_no_versioned_after_contract_freeze() -> None:
    clear_v0_2_live_postgres_session_provider()
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED=false" in text
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED=true" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "FORBIDDEN_INVENT_WEATHER=true" in text
    assert "FORBIDDEN_INVENT_PLANS=true" in text
    assert "FORBIDDEN_INVENT_TONNES=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false" in text
    assert "DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert "PARENT_OBTAIN_R1_MERGE=fd98db8d3ef9d8087fe96f27ae3469b273e62ac2" in text
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
        "s3_a2_default_catalog_live_origin_construction_contract_authorized"
    ]
    assert not payload["authorization"][
        "s3_a2_default_catalog_live_origin_construction_implementation_authorized"
    ]
    assert not payload["authorization"][
        "deterministic_default_catalog_live_origin_construction_implemented"
    ]
    assert payload["parent_obtain"]["deterministic_default_catalog_live_origin_obtain_implemented"]
    assert payload["parent_obtain"]["parent_obtain_r1_merge"] == PARENT_OBTAIN_R1_MERGE
    assert (
        payload["parent_obtain"]["parent_obtain_r1_evidence_json_sha256"]
        == PARENT_OBTAIN_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["weather_and_plans"]["weather_unavailable"] is True
    assert payload["weather_and_plans"]["plans_unavailable"] is True
    assert payload["weather_and_plans"]["weather_and_plans_do_not_block_non_curve_implementation"]
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_ONLY=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text


def test_development_plan_live_compact_flips_only_construction_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED=false" in live_intro
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert (
        "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED=false" in contract
    )


def test_amendment_records_construction_contract_pointer() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "## 172. Default catalog live-origin construction contract pointer" in text
    assert f"{UNIQUE_FLIP}=true" in text
    assert PARENT_OBTAIN_R1_EVIDENCE_JSON_SHA256 in text


def test_no_construction_production_module() -> None:
    matches = list(PRODUCTION_DIR.glob("*default_catalog_live_origin_construction*"))
    assert matches == []
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
