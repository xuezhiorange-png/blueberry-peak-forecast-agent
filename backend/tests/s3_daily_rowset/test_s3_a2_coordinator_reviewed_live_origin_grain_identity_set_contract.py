"""S3-A2 coordinator-reviewed live-origin grain identity-set contract freeze tests."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ORIGIN_MODEL_ID,
    ORIGIN_QUANTILES,
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
from backend.app.s3_daily_rowset.registry import V0_3_S3_FORECASTS_AUTHORITY
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
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
    ReviewedSetCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.window import cutoff_business_date
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
CONSTRUCTION_MODULE_BLOB = "39b3a06bc768b728e5b283c1720a8f38ed5ff71a"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
REVIEWED_SET_CLOSEOUT_PY_BLOB = "ab9e2edf2e157b80dca5e230129374f5ac97810c"
COMPLETENESS_PY_BLOB = "06b778b75710a0de30035569d15c8e3d87b095d4"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB = "07335abbf900611c2c7f990bc7a0b92a485e111d"
PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB = "f46e0d7330b022185b55dbea31d381d1a9757d04"
PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_EVIDENCE_BLOB = "c0bdb872e78cbee8736e1eedaff26fb2c6270427"
PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_EVIDENCE_JSON_SHA256 = (
    "2d668215a2b9a65605e901ba0b384d2b45d66967d9d38083a8d77860b6efed1b"
)
PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_COMMIT = "321e25ffbb0c49b940cb28b9e19fc3be9ff2fd11"
PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_MERGE = "6996a10013138bc9bef53d71b0df23c227e2aecd"
PARENT_REVIEWED_SET_CLOSEOUT_R1_MERGE = "492a45a00da45c2399521aad3d7630b21c078546"
PARENT_REVIEWED_SET_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 = (
    "ffab6ba99cffca6155365aa4f251636f0f54c0477d0ee0894cc9df2dd8bcce33"
)

CONTRACT_PATH = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
)
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.json"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
UNIQUE_FLIP = "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED"
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


def test_live_origin_policy_grains_match_coordinator_review_pins() -> None:
    entries = replay_identity_origin_entries()
    assert len(entries) == 3
    cutoff = last_legal_cutoff_before_test()
    assert cutoff_business_date(cutoff) == date(2026, 2, 16)
    assert ORIGIN_MODEL_ID == V0_3_S3_FORECASTS_AUTHORITY
    assert ORIGIN_QUANTILES == ("P50", "P80", "P90")
    assert all(entry.forecast_cutoff_at == cutoff for entry in entries)
    assert all(entry.model_id == ORIGIN_MODEL_ID for entry in entries)
    assert tuple(entry.forecast_quantile for entry in entries) == ORIGIN_QUANTILES
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "REVIEW_MODEL_ID=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF" in text
    assert "REVIEW_QUANTILES=P50,P80,P90" in text
    assert "REVIEW_MEMBER_COUNT=3" in text


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
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py")
        == CONSTRUCTION_MODULE_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/binding.py") == BINDING_PY_BLOB
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py")
        == BINDABLE_REPOSITORY_PY_BLOB
    )
    assert (
        _git_blob(
            "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
        )
        == AVAILABLE_CLOSEOUT_PY_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
        == REVIEWED_SET_CLOSEOUT_PY_BLOB
    )
    assert _git_blob("backend/app/s3_daily_rowset/completeness.py") == COMPLETENESS_PY_BLOB
    assert (
        _git_blob("backend/app/s3_daily_rowset/forecast_artifact.py") == FORECAST_ARTIFACT_PY_BLOB
    )
    assert (
        _git_blob("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py")
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-reviewed-grain-identity-set-closeout-contract.md")
        == PARENT_REVIEWED_SET_CLOSEOUT_CONTRACT_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-completeness-pass-closeout-contract.md")
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_CONTRACT_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/evidence/s3-a2-completeness-pass-closeout-authorization.json")
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_EVIDENCE_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md")
        == PARENT_PRESENCE_CONTRACT_BLOB
    )


def test_fail_closed_produce_still_records_no_reviewed_set() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
        reviewed = ReviewedGrainIdentitySetCloseoutClassifier().classify()
    assert (
        produced.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )
    assert produced.no_bindable_catalog_in_repository is True
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.reason_code is ReviewedSetCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert reviewed.no_reviewed_grain_identity_set_in_repository is True
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false"
        in text
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=false"
        in text
    )
    assert "S3_A2_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=true" in text
    assert "DETERMINISTIC_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTED=false" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_LAND_MEMBERS=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_COMPLETENESS_PASS_AUTHORIZED=true" in text
    assert "FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true" in text
    assert "FORBIDDEN_INVENT_ADDITIONAL_MEMBERS=true" in text
    assert "LATER_R1_MAY_LAND_THESE_THREE_POLICY_GRAINS_AS_REVIEWED_SET=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert "WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS=true" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
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
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_contract_authorized"
    ]
    assert not payload["authorization"][
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set_implementation_authorized"
    ]
    assert not payload["authorization"][
        "deterministic_coordinator_reviewed_live_origin_grain_identity_set_implemented"
    ]
    assert payload["authorization"]["s3_a2_completeness_pass_authorized"] is False
    assert payload["authorization"]["no_reviewed_grain_identity_set_in_repository"] is True
    assert payload["reviewed_candidate"]["review_member_count"] == 3
    assert payload["reviewed_candidate"]["review_cutoff_business_date"] == "2026-02-16"
    assert payload["reviewed_candidate"]["review_model_id"] == (
        "V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF"
    )
    assert payload["reviewed_candidate"]["review_quantiles"] == ["P50", "P80", "P90"]
    assert payload["weather_and_plans"]["weather_and_plans_do_not_block_non_curve_implementation"]
    assert payload["weather_and_plans"]["weather_and_plans_block_completeness_pass"] is True
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True
    assert (
        payload["parent_completeness_pass_closeout_grant"][
            "parent_completeness_pass_closeout_grant_commit"
        ]
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_COMMIT
    )
    assert (
        payload["parent_completeness_pass_closeout_grant"][
            "parent_completeness_pass_closeout_grant_evidence_json_sha256"
        ]
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_GRANT_EVIDENCE_JSON_SHA256
    )


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以继续" in text
    assert "CONTRACT_ONLY=true" in text
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_development_plan_live_compact_flips_coordinator_review_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=true" in live_intro
    assert "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false"
        in contract
    )
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=false"
        in contract
    )


def test_amendment_records_coordinator_review_contract_pointer() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "## 185. Completeness PASS closeout implementation authorization pointer" in text
    assert "## 186. Coordinator-reviewed live-origin grain identity-set contract pointer" in text
    assert f"{UNIQUE_FLIP}=true" in text
    section_186 = text.split("## 186.", 1)[1]
    if "## 187." in section_186:
        section_186 = section_186.split("## 187.", 1)[0]
    assert (
        "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED=false"
        in section_186
    )
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false"
        in section_186
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in section_186
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in section_186
    grant_snapshot = text.split("## 185.", 1)[1].split("## 186.", 1)[0]
    assert "S3_A2_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=true" in grant_snapshot
    assert "DETERMINISTIC_COMPLETENESS_PASS_CLOSEOUT_IMPLEMENTED=false" in grant_snapshot
    lowered = section_186.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_no_coordinator_review_production_module() -> None:
    assert PRODUCTION_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert Path(
        "backend/app/s3_daily_rowset/incumbent_forecast_replay_identity_origin.py"
    ).is_file()
