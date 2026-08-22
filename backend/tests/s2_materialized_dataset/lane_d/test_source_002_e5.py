"""SOURCE_002 E5 controlled SQL materialization tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.app.s2_materialized_dataset.lane_d.source_002_sql import (
    Source002E5MaterializationError,
    compute_grain_revision_winner_identity,
    compute_idfl_pit_visibility_not_applicable_identity,
    verify_source_002_sql_boundaries,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED,
    SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    SOURCE_002_ROW_LEVEL_READ,
)


def test_source_002_row_level_read_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_source_002_controlled_sql_materialization_enabled() -> None:
    assert SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED is True


def test_expected_boundary_oracle_constants() -> None:
    assert SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT == 233171
    assert SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT == 33894


def test_pit_visibility_not_applicable_identity_is_stable() -> None:
    first = compute_idfl_pit_visibility_not_applicable_identity()
    second = compute_idfl_pit_visibility_not_applicable_identity()
    assert first == second
    assert len(first) == 64


def test_grain_revision_winner_identity_singleton_uses_content_hash() -> None:
    content_hash = "a" * 64
    assert compute_grain_revision_winner_identity((content_hash,)) == content_hash


def test_grain_revision_winner_identity_multi_contributor_is_deterministic() -> None:
    hashes = ("b" * 64, "a" * 64)
    assert compute_grain_revision_winner_identity(hashes) == compute_grain_revision_winner_identity(
        tuple(reversed(hashes))
    )
    assert compute_grain_revision_winner_identity(hashes) != hashes[0]


def test_verify_sql_boundaries_fail_closed_on_idfl_count(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_idfl_label_side_winner_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="IDFL SQL count mismatch"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_pit_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_pit_visibility_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="PIT SQL must be 0"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_kg_equal(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: False,
    )
    with pytest.raises(Source002E5MaterializationError, match="kg_equal is not true"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_controlled_materialize_reports_object_missing_without_frozen_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.s2_materialized_dataset.lane_d.source_002_sql import (
        controlled_materialize_source_002_from_environment,
    )

    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.source_002_sql._source_002_frozen_object_available",
        lambda _roots: False,
    )
    report = controlled_materialize_source_002_from_environment(
        MagicMock(),
        dataset_id="source-002",
        dataset_version="e5-v1",
        persist=False,
    )
    assert report.rebuild_parity == "OBJECT_MISSING"
    assert report.dataset_identity is None
