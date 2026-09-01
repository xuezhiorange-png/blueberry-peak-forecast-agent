"""S3-A2 incumbent forecast replay-identity bindable name tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    AUDIT_TABLE_COUNT,
    FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
    MATCH_TABLE_COUNT,
    MATCH_TABLE_NAMES,
    NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY,
    bindable_table_names,
    is_bindable,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
AUTHORITY_MODULE_PATH = Path(
    "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_sql_table_authority.py"
)
FORBIDDEN_SQL_TOKENS = ("SELECT", "FROM", "JOIN", "WHERE")


def test_frozen_bindable_replay_identity_table_name() -> None:
    assert FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME == "s3_incumbent_forecast_replay_identity"


def test_no_bindable_v0_2_flag_is_false_after_r1() -> None:
    assert NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY is False


def test_bindable_table_names_returns_frozen_name_only() -> None:
    assert bindable_table_names() == ("s3_incumbent_forecast_replay_identity",)


def test_match_table_audit_authority_unchanged() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert MATCH_TABLE_COUNT == 0
    assert AUDIT_TABLE_COUNT == 106


def test_is_bindable_accepts_frozen_name_only() -> None:
    assert is_bindable("s3_incumbent_forecast_replay_identity") is True
    assert is_bindable("core_forecast_daily_row") is False
    assert is_bindable("rolling_backtest_binding_row") is False


def test_default_replay_source_obtain_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_first_blocker_is_no_versioned_forecast() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_authority_module_contains_no_sql_io_tokens() -> None:
    source = AUTHORITY_MODULE_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "__future__" in stripped:
            continue
        upper = line.upper()
        for token in FORBIDDEN_SQL_TOKENS:
            assert token not in upper
