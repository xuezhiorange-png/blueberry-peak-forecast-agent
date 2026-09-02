"""S3-A2 default catalog live-origin obtain contract freeze tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

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

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
CONTRACT_PATH = Path("docs/v0-3/s3/s3-default-catalog-live-origin-obtain-contract.md")
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-contract.md"
)
EVIDENCE_PATH = Path("docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-contract.json")


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


def test_default_catalog_still_no_versioned_after_contract_freeze() -> None:
    with patch_handoff_disabled(), patch("backend.app.db.session.AsyncSessionMaker", None):
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert S2IdentityAlignmentHarvestSource().obtain() == ()


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_CONTRACT_AUTHORIZED=true" in text
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED=false" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "FORBIDDEN_INVENT_WEATHER=true" in text
    assert "FORBIDDEN_INVENT_PLANS=true" in text
    assert "FORBIDDEN_INVENT_TONNES=true" in text
    assert "CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false" in text
    assert "DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert "postgresql://" not in text.lower()


def test_evidence_json_sha256_matches_payload_without_self_key() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    digest = payload["evidence_json_sha256"]
    assert len(digest) == 64
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == digest
    assert payload["authorization"]["s3_a2_default_catalog_live_origin_obtain_contract_authorized"]
    assert not payload["authorization"][
        "s3_a2_default_catalog_live_origin_obtain_implementation_authorized"
    ]
    assert payload["weather_and_plans"]["weather_unavailable"] is True
    assert payload["weather_and_plans"]["plans_unavailable"] is True


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以下一步" in text
    assert "CONTRACT_ONLY=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
