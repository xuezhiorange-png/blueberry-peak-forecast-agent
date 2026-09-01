"""S3-A2 default catalog live-origin obtain R1 tests."""

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
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
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
from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_obtain import (
    DefaultCatalogLiveOriginObtainReasonCode,
    obtain_default_catalog_from_landed_origin,
    obtain_default_catalog_from_live_origin,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled
from backend.tests.s3_daily_rowset.test_s3_a2_live_catalog_execution import (
    TEST_CATALOG_ARTIFACT_PY_BLOB,
    _in_season_rows,
    _patch_official_counts,
    _session_maker_with_rows,
    _sync_replay_session,
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
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-authorization.json"
)
R1_WORKPAPER = Path("docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-r1.md")
R1_EVIDENCE = Path("docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-r1.json")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "2e7c66ad27f5d1d0d95857913a0ce76101a9e5dc09da94c2fc2d6b98122dfd53"
)
PARENT_GRANT_MERGE = "632d0692375d6f15d7892990a1733cfaf9e08a49"
UNIQUE_FLIP = "DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED"


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _assert_defaults_remain_empty() -> None:
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        default_catalog = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        default_catalog.reason_code
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )


def test_envelope_does_not_expose_content_bytes_kg_or_farms() -> None:
    from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_obtain import (
        DefaultCatalogLiveOriginObtainEnvelope,
    )

    field_names = set(DefaultCatalogLiveOriginObtainEnvelope.model_fields)
    assert "content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names
    assert "harvest_business_date" not in field_names


def test_obtain_reads_landed_origin_and_injects_ports_without_default_wiring() -> None:
    train_rows, validation_rows = _in_season_rows()
    actuals = InMemoryS2ActualsSource(train_rows + validation_rows)
    session = _sync_replay_session()
    landing = land_replay_identity_origin_into_sync_session(session)
    assert landing.landed is True
    assert landing.table_row_count == 3

    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = obtain_default_catalog_from_landed_origin(
            actuals_source=actuals,
            sync_session=session,
            dataset_identity=DATASET_IDENTITY,
        )

    assert envelope.obtain_reason_code is DefaultCatalogLiveOriginObtainReasonCode.ARTIFACT_PRODUCED
    assert envelope.catalog_reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED.value
    assert envelope.origin_entry_count == 3
    assert envelope.table_row_count == 3
    assert envelope.aligned_identity_count == 2
    assert envelope.catalog_entry_count == 6
    assert envelope.uses_harvest_date_as_forecast_cutoff is False
    assert envelope.test_remains_sealed is True
    assert envelope.current_s3_daily_rowset_completeness_verified is False
    assert envelope.no_bindable_catalog_in_repository is True
    assert envelope.default_harvest_obtain_empty is True
    assert (
        envelope.default_catalog_first_blocker
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT.value
    )
    assert envelope.default_session_provider_left_unset is True
    _assert_defaults_remain_empty()


def test_obtain_fail_closed_when_origin_table_empty() -> None:
    train_rows, validation_rows = _in_season_rows()
    actuals = InMemoryS2ActualsSource(train_rows + validation_rows)
    session = _sync_replay_session()

    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = obtain_default_catalog_from_landed_origin(
            actuals_source=actuals,
            sync_session=session,
            dataset_identity=DATASET_IDENTITY,
        )

    assert envelope.obtain_reason_code is (
        DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_NO_ORIGIN_ENTRIES
    )
    assert envelope.origin_entry_count == 0
    assert envelope.catalog_entry_count == 0
    assert envelope.current_s3_daily_rowset_completeness_verified is False
    _assert_defaults_remain_empty()


def test_patched_session_maker_obtains_catalog_from_landed_origin(
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
        envelope = obtain_default_catalog_from_live_origin()

    assert envelope.obtain_reason_code is DefaultCatalogLiveOriginObtainReasonCode.ARTIFACT_PRODUCED
    assert envelope.catalog_reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED.value
    assert envelope.origin_entry_count == 3
    assert envelope.aligned_identity_count == 2
    assert envelope.catalog_entry_count == 6
    assert envelope.actuals_bound is True
    assert envelope.parsed_total_row_count == 2
    assert envelope.test_row_count == 0
    assert SOURCE_002_ROW_LEVEL_READ is True
    assert (
        envelope.default_catalog_first_blocker == CatalogArtifactReasonCode.ARTIFACT_PRODUCED.value
    )
    _assert_defaults_remain_empty()


def test_obtain_module_does_not_land_or_embed_connection_strings() -> None:
    source = OBTAIN_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "land_replay_identity_origin" not in source
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "dsn" not in lowered


def test_frozen_blobs_unchanged() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(GRAIN_PY) == GRAIN_IDENTITY_SET_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(ALEMBIC_PY) == ALEMBIC_BLOB


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"]["S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED"]
    assert payload["flags"][UNIQUE_FLIP] is False
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED"] is True
    assert r1["flags"]["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert r1["flags"]["WEATHER_UNAVAILABLE"] is True
    assert r1["flags"]["PLANS_UNAVAILABLE"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_WEATHER"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_PLANS"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
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
    assert UNIQUE_FLIP + "=true" in plan
    assert "s3-a2-default-catalog-live-origin-obtain-r1.md" in plan
    assert "## 171." in amendment
    assert "## 170." in amendment
    assert "## 169." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in plan
    assert "WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION=true" in amendment


def test_official_live_default_catalog_obtain_fail_closed_or_produced() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_obtain import (
    obtain_default_catalog_from_live_origin,
)
envelope = obtain_default_catalog_from_live_origin()
print(json.dumps({
    "obtain_reason_code": envelope.obtain_reason_code.value,
    "catalog_reason_code": envelope.catalog_reason_code,
    "origin_entry_count": envelope.origin_entry_count,
    "aligned_identity_count": envelope.aligned_identity_count,
    "catalog_entry_count": envelope.catalog_entry_count,
    "completeness_verified": envelope.current_s3_daily_rowset_completeness_verified,
    "test_remains_sealed": envelope.test_remains_sealed,
    "uses_harvest_date_as_forecast_cutoff": envelope.uses_harvest_date_as_forecast_cutoff,
    "default_harvest_obtain_empty": envelope.default_harvest_obtain_empty,
    "default_catalog_first_blocker": envelope.default_catalog_first_blocker,
    "parsed_train_row_count": envelope.parsed_train_row_count,
    "parsed_validation_row_count": envelope.parsed_validation_row_count,
    "table_row_count": envelope.table_row_count,
    "default_session_provider_left_unset": envelope.default_session_provider_left_unset,
    "default_harvest_after": S2IdentityAlignmentHarvestSource().obtain() == (),
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
    if payload["obtain_reason_code"] == "ARTIFACT_PRODUCED":
        assert payload["catalog_reason_code"] == "ARTIFACT_PRODUCED"
        assert payload["origin_entry_count"] == 3
        assert payload["aligned_identity_count"] > 0
        assert payload["catalog_entry_count"] == payload["aligned_identity_count"] * 3
        assert payload["completeness_verified"] is False
        assert payload["test_remains_sealed"] is True
        assert payload["uses_harvest_date_as_forecast_cutoff"] is False
        assert payload["default_harvest_obtain_empty"] is True
        assert payload["default_harvest_after"] is True
        assert payload["default_session_provider_left_unset"] is True
        assert payload["default_catalog_first_blocker"] in {
            "ARTIFACT_PRODUCED",
            "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT",
        }
        assert payload["parsed_train_row_count"] == OFFICIAL_TRAIN_ROW_COUNT
        assert payload["parsed_validation_row_count"] == OFFICIAL_VALIDATION_ROW_COUNT
        assert payload["table_row_count"] == 3
    else:
        assert payload["obtain_reason_code"] != "ARTIFACT_PRODUCED"
        assert payload["completeness_verified"] is False


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
