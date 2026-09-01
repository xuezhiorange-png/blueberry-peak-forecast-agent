"""S3-A2 default catalog live-origin construction R1 tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    land_replay_identity_origin_into_sync_session,
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
from backend.tests.s3_daily_rowset.test_s3_a2_live_catalog_execution import (
    TEST_CATALOG_ARTIFACT_PY_BLOB,
    _in_season_rows,
    _patch_official_counts,
    _session_maker_with_rows,
)

CONSTRUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py"
)
OBTAIN_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
TEST_CATALOG_PY = Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")
GRAIN_PY = Path(
    "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
)
CONTENT_PY = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
ALEMBIC_PY = Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-construction-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-construction-authorization.json"
)
R1_WORKPAPER = Path("docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-construction-r1.md")
R1_EVIDENCE = Path("docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-construction-r1.json")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "e2ec60dfc5750f10963abd79e19c64aa3f26409d4e9096e3ea876228660d6f24"
)
PARENT_GRANT_MERGE = "bc1c578021808c32bc5deee56237595f69598966"
PARENT_GRANT_COMMIT = "8bb343c29835a55a18b9f72273444d93585998c0"
PARENT_CONTRACT_COMMIT = "b5fce9f5ad8d4e3e6d01d65c90ba6960eded61e7"
PARENT_CONTRACT_MERGE = "edace90a66e9d5f11c398a4a762949ec6d5435cc"
UNIQUE_FLIP = "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTED"
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


def _assert_fail_closed_when_session_maker_unavailable() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        default_catalog = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        default_catalog.reason_code
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )
    assert default_catalog.no_bindable_catalog_in_repository is True
    assert default_catalog.evaluation_instance_registry_available is False
    assert default_catalog.current_s3_daily_rowset_completeness_verified is False


def test_construction_module_does_not_land_or_embed_connection_strings() -> None:
    source = CONSTRUCTION_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "land_replay_identity_origin" not in source
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "content_bytes" not in source
    assert "dsn" not in lowered


def test_frozen_blobs_unchanged() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(GRAIN_PY) == GRAIN_IDENTITY_SET_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(ALEMBIC_PY) == ALEMBIC_BLOB
    assert _git_blob(OBTAIN_MODULE) == OBTAIN_MODULE_BLOB


def test_patched_session_maker_constructs_bare_default_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    train_rows, validation_rows = _in_season_rows()
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    async def _land() -> None:
        async with session_maker() as session:
            await session.run_sync(land_replay_identity_origin_into_sync_session)

    asyncio.run(_land())

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert result.catalog_identity_sha256 is not None
    assert len(result.catalog.entries()) == 6
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert SOURCE_002_ROW_LEVEL_READ is True
    _assert_fail_closed_when_session_maker_unavailable()


def test_construction_fail_closed_when_origin_table_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_rows, validation_rows = _in_season_rows()
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code is CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    assert result.catalog_identity_sha256 is None
    assert result.no_bindable_catalog_in_repository is True
    _assert_fail_closed_when_session_maker_unavailable()


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][
        "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED"
    ]
    assert payload["flags"][UNIQUE_FLIP] is False
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED"]
    assert r1["flags"]["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert r1["flags"]["WEATHER_UNAVAILABLE"] is True
    assert r1["flags"]["PLANS_UNAVAILABLE"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_WEATHER"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_PLANS"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert r1["flags"]["DEFAULT_HARVEST_OBTAIN_EMPTY"] is True
    assert GRANT_WORKPAPER.is_file()
    assert R1_WORKPAPER.is_file()


def test_r1_evidence_sha256_payload_matches_embedded_digest() -> None:
    from backend.app.rolling_backtest.canonical import sha256_payload

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
    assert "S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_CONSTRUCTION_IMPLEMENTATION_AUTHORIZED=true" in (
        live_intro
    )
    assert "s3-a2-default-catalog-live-origin-construction-r1.md" in plan
    assert "## 174." in amendment
    assert "## 173." in amendment
    assert "## 172." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in plan
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in amendment
    grant_snapshot = amendment.split("## 173.", 1)[1].split("## 174.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-default-catalog-live-origin-construction-r1.md" in contract_pointer


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper


def test_official_live_default_catalog_construction_fail_closed_or_produced() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.catalog_artifact import (
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
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled
result = EvaluationInstanceCatalogArtifactProductionService(
    dataset_identity=DATASET_IDENTITY,
).produce()
clear_v0_2_live_postgres_session_provider()
print(json.dumps({
    "reason_code": result.reason_code.value,
    "catalog_identity_sha256": result.catalog_identity_sha256,
    "catalog_entry_count": len(result.catalog.entries()),
    "completeness_verified": result.current_s3_daily_rowset_completeness_verified,
    "no_bindable": result.no_bindable_catalog_in_repository,
    "registry_available": result.evaluation_instance_registry_available,
    "default_harvest_after": S2IdentityAlignmentHarvestSource().obtain() == (),
    "default_replay_after": IncumbentForecastReplaySource().obtain() == (),
    "bindable_after": read_bindable_replay_identity_rows() == (),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    if payload["reason_code"] == "ARTIFACT_PRODUCED":
        assert payload["catalog_identity_sha256"]
        assert payload["catalog_entry_count"] > 0
        assert payload["catalog_entry_count"] % 3 == 0
        assert payload["completeness_verified"] is False
        assert payload["no_bindable"] is True
        assert payload["registry_available"] is False
        assert payload["default_harvest_after"] is True
        assert payload["default_replay_after"] is True
        assert payload["bindable_after"] is True
        assert OFFICIAL_TRAIN_ROW_COUNT == 16224
        assert OFFICIAL_VALIDATION_ROW_COUNT == 8006
    else:
        assert payload["reason_code"] == "NO_S2_IDENTITY_ALIGNMENT"
        assert payload["completeness_verified"] is False
        assert payload["catalog_identity_sha256"] is None


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert CONSTRUCTION_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
