"""S3-A2 reviewed grain identity-set closeout contract freeze tests."""

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
from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
    assert_forecast_artifact_py_historical_blob_pinned,
)

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
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
PARENT_PRESENCE_CONTRACT_BLOB = "899aeafbbe9737703aaade44e07953df22e642c1"
PARENT_AVAILABLE_CLOSEOUT_CONTRACT_BLOB = "8e386c5bbe61239cc8645a09a46d8cc17cf0b8b0"
PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_BLOB = "6b6e3aa21a6b0bcb0063a20c161198a2c2f796a7"
PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 = (
    "ebcc32b9443d9c23c9bb459472a9c275596bf76bb80d1e5caea8a04441a4ed1d"
)
PARENT_AVAILABLE_CLOSEOUT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "1bc4360a1c96ae17676296d708633b326c0cea9d3b9b510d3cff347da5c91282"
)
PARENT_AVAILABLE_CLOSEOUT_R1_MERGE = "cf1c61fc31108211c06c8c8926cb81ef6962df51"
PARENT_AVAILABLE_CLOSEOUT_CONTRACT_MERGE = "dba273ab47e26308b186525bd6b99a642e1a556d"
PARENT_AVAILABLE_CLOSEOUT_CONTRACT_COMMIT = "64b0fd51c9d2e9318b4fdc4a1ec6091ed2131664"

CONTRACT_PATH = Path("docs/v0-3/s3/s3-reviewed-grain-identity-set-closeout-contract.md")
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-reviewed-grain-identity-set-closeout-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-reviewed-grain-identity-set-closeout-contract.json"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
UNIQUE_FLIP = "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_CONTRACT_AUTHORIZED"
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
    assert_forecast_artifact_py_historical_blob_pinned(FORECAST_ARTIFACT_PY_BLOB)
    assert (
        _git_blob("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py")
        == ALIGNMENT_EVIDENCE_PY_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-evaluation-instance-registry-available-closeout-contract.md")
        == PARENT_AVAILABLE_CLOSEOUT_CONTRACT_BLOB
    )
    assert (
        _git_blob(
            "docs/v0-3/s3/evidence/s3-a2-evaluation-instance-registry-available-closeout-r1.json"
        )
        == PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_BLOB
    )
    assert (
        _git_blob("docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md")
        == PARENT_PRESENCE_CONTRACT_BLOB
    )


def test_fail_closed_produce_and_classify_still_record_no_reviewed_set() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
    assert produced.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    assert produced.no_bindable_catalog_in_repository is True
    assert produced.evaluation_instance_registry_available is False
    assert produced.current_s3_daily_rowset_completeness_verified is False
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert bindable.no_bindable_catalog_in_repository is True
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert available.evaluation_instance_registry_available is False
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_contract_is_authorized_and_not_an_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED=false" in text
    assert "DETERMINISTIC_EVALUATION_INSTANCE_REGISTRY_AVAILABLE_CLOSEOUT_IMPLEMENTED=true" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_BINDING=true" in text
    assert "CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REVIEWED_SET_CLOSEOUT=true" in text
    assert "FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET=true" in text
    assert "FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "FORBIDDEN_INVENT_WEATHER=true" in text
    assert "FORBIDDEN_INVENT_PLANS=true" in text
    assert "FORBIDDEN_INVENT_TONNES=true" in text
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false" in text
    assert "DEFAULT_CATALOG_FIRST_BLOCKER=ARTIFACT_PRODUCED" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    assert "NO_NEW_SQLALCHEMY_API_FAMILY=true" in text
    assert f"PARENT_AVAILABLE_CLOSEOUT_R1_MERGE={PARENT_AVAILABLE_CLOSEOUT_R1_MERGE}" in text
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
        "s3_a2_reviewed_grain_identity_set_closeout_contract_authorized"
    ]
    assert not payload["authorization"][
        "s3_a2_reviewed_grain_identity_set_closeout_implementation_authorized"
    ]
    assert not payload["authorization"][
        "deterministic_reviewed_grain_identity_set_closeout_implemented"
    ]
    assert payload["parent_available_closeout"][
        "deterministic_evaluation_instance_registry_available_closeout_implemented"
    ]
    assert payload["parent_available_closeout"]["parent_available_closeout_r1_merge"] == (
        PARENT_AVAILABLE_CLOSEOUT_R1_MERGE
    )
    assert (
        payload["parent_available_closeout"]["parent_available_closeout_r1_evidence_json_sha256"]
        == PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_JSON_SHA256
    )
    assert (
        payload["parent_available_closeout"]["parent_available_closeout_contract_merge"]
        == PARENT_AVAILABLE_CLOSEOUT_CONTRACT_MERGE
    )
    assert (
        payload["parent_available_closeout"]["parent_available_closeout_contract_commit"]
        == PARENT_AVAILABLE_CLOSEOUT_CONTRACT_COMMIT
    )
    assert (
        payload["parent_available_closeout"][
            "parent_available_closeout_contract_evidence_json_sha256"
        ]
        == PARENT_AVAILABLE_CLOSEOUT_CONTRACT_EVIDENCE_JSON_SHA256
    )
    assert payload["weather_and_plans"]["weather_unavailable"] is True
    assert payload["weather_and_plans"]["plans_unavailable"] is True
    assert payload["weather_and_plans"]["weather_and_plans_do_not_block_non_curve_implementation"]
    assert payload["authorization"]["no_reviewed_grain_identity_set_in_repository"] is True
    assert payload["authorization"]["no_bindable_catalog_in_repository"] is True
    assert payload["authorization"]["evaluation_instance_registry_available"] is False
    assert payload["unique_flip"]["field"] == UNIQUE_FLIP
    assert payload["unique_flip"]["before"] is False
    assert payload["unique_flip"]["after"] is True


def test_workpaper_exists_and_is_contract_only() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert "USER_GATE=可以继续" in text
    assert "CONTRACT_ONLY=true" in text
    assert "WEATHER_UNAVAILABLE=true" in text
    assert "PLANS_UNAVAILABLE=true" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_development_plan_live_compact_flips_only_reviewed_set_closeout_contract() -> None:
    text = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    live_intro = text.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "DETERMINISTIC_EVALUATION_INSTANCE_REGISTRY_AVAILABLE_CLOSEOUT_IMPLEMENTED=true" in (
        live_intro
    )
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "DEFAULT_CATALOG_FIRST_BLOCKER=ARTIFACT_PRODUCED" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=false" in contract
    assert "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED=false" in contract


def test_amendment_records_reviewed_set_closeout_contract_pointer() -> None:
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "## 180. Evaluation instance registry AVAILABLE closeout R1 pointer" in text
    assert "## 181. Reviewed grain identity-set closeout contract pointer" in text
    assert f"{UNIQUE_FLIP}=true" in text
    assert PARENT_AVAILABLE_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 in text
    section_181 = text.split("## 181.", 1)[1]
    if "## 182." in section_181:
        section_181 = section_181.split("## 182.", 1)[0]
    assert "DETERMINISTIC_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTED=false" in section_181
    assert "S3_A2_REVIEWED_GRAIN_IDENTITY_SET_CLOSEOUT_IMPLEMENTATION_AUTHORIZED=false" in (
        section_181
    )
    assert "DETERMINISTIC_EVALUATION_INSTANCE_REGISTRY_AVAILABLE_CLOSEOUT_IMPLEMENTED=true" in (
        section_181
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in section_181
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in section_181
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in section_181
    lowered = section_181.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_no_reviewed_set_closeout_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert Path(
        "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
    ).is_file()
    assert PRODUCTION_MODULE.is_file()
