"""Single-loop live materialization DB acquisition tests (R1)."""

from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls

from backend.app.forecast_quality.train_val_pairing_materialization import (
    OfficialPartitionRows,
    TrainValidationPairingMaterializationBlocker,
    TrainValidationPairingMaterializationResult,
    materialize_train_validation_pairing_inputs_live,
)
from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    Source002RowLevelReadReasonCode,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
    LiveObtainReasonCode,
)
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    LiveIncumbentForecastDailyCurveObtainResult,
    reset_live_incumbent_forecast_daily_curve_provider_cache,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
)
from backend.tests.forecast_quality.test_s3_b_train_val_pairing_materialization_r1 import (
    _reviewed_forecast_entries,
    _small_official_partitions,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_ROOT = _REPO_ROOT / "backend" / "app"
_MATERIALIZATION_MODULE = _APP_ROOT / "forecast_quality" / "train_val_pairing_materialization.py"
_LIVE_ASYNC_MODULE = (
    _APP_ROOT / "forecast_quality" / "train_val_pairing_materialization_live_async.py"
)
_REVIEWED_CUTOFF = __import__("datetime").datetime.fromisoformat(REVIEW_CUTOFF_AT)
_LOAD_OFFICIAL_PATCH = (
    "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
    "load_official_partition_rows_from_content_bytes"
)


def _patch_official_partitions(official: OfficialPartitionRows):
    return patch(_LOAD_OFFICIAL_PATCH, return_value=official)


def _mock_async_session_maker(
    *,
    run_sync_side_effect: object,
    session: MagicMock | None = None,
) -> MagicMock:
    async_session = session or MagicMock(spec=AsyncSession)
    if isinstance(run_sync_side_effect, Exception):
        async_session.run_sync = AsyncMock(side_effect=run_sync_side_effect)
    else:
        async_session.run_sync = AsyncMock(side_effect=run_sync_side_effect)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=async_session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    maker = MagicMock(spec=_AsyncSessionMakerCls)
    maker.return_value = session_cm
    return maker


def _official_obtain_envelope(official: OfficialPartitionRows) -> MagicMock:
    return MagicMock(
        obtained=True,
        reason_code=LiveObtainReasonCode.OBTAINED,
        train_content_bytes=build_partition_bytes(official.train_rows),
        validation_content_bytes=build_partition_bytes(official.validation_rows),
    )


def _attested_envelope() -> MagicMock:
    return MagicMock(attested=True, reason_code=Source002RowLevelReadReasonCode.ATTESTED)


def _union_grains(official: OfficialPartitionRows) -> frozenset[tuple[str, str, str, str]]:
    from backend.app.forecast_quality.train_val_pairing_materialization import (
        derive_materialization_grain_union,
    )

    grains = derive_materialization_grain_union(official)
    assert not isinstance(grains, TrainValidationPairingMaterializationBlocker)
    return grains


@pytest.fixture(autouse=True)
def _reset_provider_cache() -> None:
    reset_live_incumbent_forecast_daily_curve_provider_cache()
    clear_v0_2_live_postgres_session_provider()
    yield
    reset_live_incumbent_forecast_daily_curve_provider_cache()
    clear_v0_2_live_postgres_session_provider()


def test_materialization_has_exactly_one_asyncio_run() -> None:
    """A: MATERIALIZATION_HAS_EXACTLY_ONE_ASYNCIO_RUN."""
    run_count = 0
    original_run = asyncio.run

    def counting_run(coro: object) -> object:
        nonlocal run_count
        run_count += 1
        return original_run(coro)

    with patch("asyncio.run", side_effect=counting_run):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_materialize_with_held_async_session",
            new_callable=AsyncMock,
            return_value=MagicMock(
                completed=False,
                blocker=TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED,
            ),
        ):
            with patch(
                "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
                "resolve_live_async_session_maker",
                return_value=_mock_async_session_maker(run_sync_side_effect=RuntimeError("unused")),
            ):
                materialize_train_validation_pairing_inputs_live()

    assert run_count == 1


def test_same_async_session_attest_and_obtain() -> None:
    """B: SAME_ASYNC_SESSION_ATTEST_AND_OBTAIN."""
    official = _small_official_partitions()
    held_session = MagicMock(spec=AsyncSession)
    run_sync_names: list[str] = []

    async def _run_sync_side_effect(fn: object) -> object:
        assert callable(fn)
        run_sync_names.append(fn.__name__)
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    held_session.run_sync = AsyncMock(side_effect=_run_sync_side_effect)
    maker = _mock_async_session_maker(
        run_sync_side_effect=_run_sync_side_effect,
        session=held_session,
    )

    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False),
        ) as obtain_async:
            with _patch_official_partitions(official):
                materialize_train_validation_pairing_inputs_live()

    assert held_session.run_sync.await_count >= 2
    assert run_sync_names[:2] == ["_attest_from_session", "_obtain_from_session"]
    obtain_async.assert_awaited_once()
    assert obtain_async.await_args.args[0] is held_session


def test_sequential_event_loop_regression() -> None:
    """C: SEQUENTIAL_EVENT_LOOP_REGRESSION."""
    official = _small_official_partitions()
    sequential_failures = 0

    async def _run_sync_side_effect(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)

    def sequential_obtain_failure() -> MagicMock:
        nonlocal sequential_failures
        sequential_failures += 1
        return MagicMock(
            obtained=False,
            reason_code=LiveObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
            train_content_bytes=None,
            validation_content_bytes=None,
        )

    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
            ".run_live_source_002_sync_reader",
            side_effect=[
                _attested_envelope(),
                sequential_obtain_failure(),
            ],
        ):
            from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
                obtain_accepted_s2_train_val_content_bytes_from_bound_live_session,
            )

            attest = __import__(
                "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read",
                fromlist=["attest_accepted_s2_train_val_source_002_row_level_read"],
            ).attest_accepted_s2_train_val_source_002_row_level_read()
            obtain = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()
            assert attest.attested is True
            assert obtain.obtained is False
            assert sequential_failures == 1

        with _patch_official_partitions(official):
            with patch(
                "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
                "_obtain_from_async_session",
                new_callable=AsyncMock,
                return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False),
            ):
                result = materialize_train_validation_pairing_inputs_live()

    assert result.blocker != (
        TrainValidationPairingMaterializationBlocker.OFFICIAL_PARTITION_BYTES_NOT_OBTAINED
    )


def test_replay_identity_from_held_session() -> None:
    """D: REPLAY_IDENTITY_FROM_HELD_SESSION."""
    official = _small_official_partitions()
    replay_fn_names: list[str] = []

    async def _run_sync_side_effect(fn: object) -> object:
        replay_fn_names.append(fn.__name__)
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False),
        ):
            with _patch_official_partitions(official):
                materialize_train_validation_pairing_inputs_live()

    assert "_read_replay_identity_from_held_session" in replay_fn_names


def test_replay_provider_cleanup() -> None:
    """E: REPLAY_PROVIDER_CLEANUP."""
    official = _small_official_partitions()

    async def _run_sync_side_effect(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return fn(MagicMock())
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read."
            "read_bindable_replay_identity_rows",
            side_effect=RuntimeError("replay-read-failure"),
        ):
            with _patch_official_partitions(official):
                result = materialize_train_validation_pairing_inputs_live()

    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS
    )
    from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
        _session_provider,
    )

    assert _session_provider is None


def test_pit_provider_same_event_loop() -> None:
    """F: PIT_PROVIDER_SAME_EVENT_LOOP."""
    official = _small_official_partitions()
    asyncio_run_calls = 0
    original_run = asyncio.run

    def counting_run(coro: object) -> object:
        nonlocal asyncio_run_calls
        asyncio_run_calls += 1
        return original_run(coro)

    async def _run_sync_side_effect(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch("asyncio.run", side_effect=counting_run):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "resolve_live_async_session_maker",
            return_value=maker,
        ):
            with patch(
                "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
                "_obtain_from_async_session",
                new_callable=AsyncMock,
                return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False),
            ) as obtain_async:
                with _patch_official_partitions(official):
                    with patch(
                        "backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain."
                        "obtain_live_incumbent_forecast_daily_curve_provider",
                    ) as sync_obtain:
                        materialize_train_validation_pairing_inputs_live()

    obtain_async.assert_awaited_once()
    sync_obtain.assert_not_called()
    assert asyncio_run_calls == 1


def test_pit_provider_same_async_session() -> None:
    """G: PIT_PROVIDER_SAME_ASYNC_SESSION."""
    official = _small_official_partitions()
    held_session = MagicMock(spec=AsyncSession)

    async def _run_sync_side_effect(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    held_session.run_sync = AsyncMock(side_effect=_run_sync_side_effect)
    maker = _mock_async_session_maker(
        run_sync_side_effect=_run_sync_side_effect,
        session=held_session,
    )

    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False),
        ) as obtain_async:
            with _patch_official_partitions(official):
                materialize_train_validation_pairing_inputs_live()

    assert obtain_async.await_args.args[0] is held_session
    assert obtain_async.await_args.kwargs["materialization_grains"] == _union_grains(official)


def test_source_002_identity_regression() -> None:
    """H: SOURCE_002_IDENTITY_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_run_sync_correction_r1.py",
            "-k",
            "official_identity or train_hash or validation_hash",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_test_seal_regression() -> None:
    """I: TEST_SEAL_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_run_sync_correction_r1.py",
            "-k",
            "test_remains_sealed",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_exact_grain_union_regression() -> None:
    """J: EXACT_GRAIN_UNION_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/test_s3_b_live_pairing_authority_handoff_r1.py",
            "-k",
            "live_materialization_passes_exact_union_grains",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_per_cell_per_horizon_authority_regression() -> None:
    """K: PER_CELL_PER_HORIZON_AUTHORITY_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/test_s3_b_live_pairing_authority_handoff_r1.py",
            "-k",
            "per_cell_authority",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr550_regression() -> None:
    """L: PR550_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/"
            "test_s3_b_persisted_task10_authority_reference_relation_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr551_regression() -> None:
    """M: PR551_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/rolling_backtest/"
            "test_s3_b_persisted_task10_authority_production_writer_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr552_regression() -> None:
    """PR552 authority handoff regression."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/test_s3_b_live_pairing_authority_handoff_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr553_standalone_reader_regression() -> None:
    """N: PR553_STANDALONE_READER_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_run_sync_correction_r1.py",
            "-k",
            "not materialization_entrypoint",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _collect_asyncio_run_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "run":
            if isinstance(func.value, ast.Name) and func.value.id == "asyncio":
                calls.append(node)
        elif isinstance(func, ast.Name) and func.id == "asyncio_run":
            calls.append(node)
    return calls


def test_no_second_asyncio_run_in_live_materialization_db_path() -> None:
    """O: NO_SECOND_ASYNCIO_RUN_IN_LIVE_MATERIALIZATION_DB_PATH."""
    materialization_source = _MATERIALIZATION_MODULE.read_text(encoding="utf-8")
    live_start = materialization_source.index(
        "def materialize_train_validation_pairing_inputs_live"
    )
    live_end = materialization_source.index(
        "def build_materialization_evidence_payload",
        live_start,
    )
    live_entry_source = materialization_source[live_start:live_end]
    entry_runs = _collect_asyncio_run_calls(live_entry_source)
    assert len(entry_runs) == 1

    live_async_source = _LIVE_ASYNC_MODULE.read_text(encoding="utf-8")
    live_async_runs = _collect_asyncio_run_calls(live_async_source)
    assert len(live_async_runs) == 0
    forbidden_calls = (
        "attest_accepted_s2_train_val_source_002_row_level_read",
        "obtain_accepted_s2_train_val_content_bytes_from_bound_live_session",
        "obtain_live_incumbent_forecast_daily_curve_provider",
        "run_live_source_002_sync_reader",
    )
    for name in forbidden_calls:
        assert name not in live_async_source


def test_failure_boundaries() -> None:
    """P: FAILURE_BOUNDARIES."""
    official = _small_official_partitions()

    async def _run_sync_attest_fail(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return MagicMock(attested=False)
        raise AssertionError("attest failure should short-circuit")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_attest_fail)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        result = materialize_train_validation_pairing_inputs_live()
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
    )

    async def _run_sync_obtain_fail(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return MagicMock(
                obtained=False,
                train_content_bytes=None,
                validation_content_bytes=None,
            )
        raise AssertionError("obtain failure should short-circuit")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_obtain_fail)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        result = materialize_train_validation_pairing_inputs_live()
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.OFFICIAL_PARTITION_BYTES_NOT_OBTAINED
    )

    async def _run_sync_empty_replay(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return ()
        raise AssertionError("empty replay should short-circuit")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_empty_replay)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with _patch_official_partitions(official):
            result = materialize_train_validation_pairing_inputs_live()
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS
    )

    async def _run_sync_replay_mismatch(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return (
                __import__(
                    "backend.app.s3_daily_rowset.catalog_artifact",
                    fromlist=["IncumbentForecastArtifactEntry"],
                ).IncumbentForecastArtifactEntry(
                    model_id="wrong-model",
                    forecast_cutoff_at=_REVIEWED_CUTOFF,
                    forecast_quantile="P50",
                ),
            )
        raise AssertionError("replay mismatch should short-circuit")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_replay_mismatch)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with _patch_official_partitions(official):
            result = materialize_train_validation_pairing_inputs_live()
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.REVIEWED_FORECAST_GRAIN_MISMATCH
    )

    async def _run_sync_pit_unavailable(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError("pit unavailable should reach async obtain")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_pit_unavailable)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            return_value=LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None),
        ):
            with _patch_official_partitions(official):
                result = materialize_train_validation_pairing_inputs_live()
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER
    )


def _run_sync_raises_for(fn_name: str, *, official: OfficialPartitionRows | None = None) -> object:
    async def _side_effect(fn: object) -> object:
        if not callable(fn):
            raise AssertionError("run_sync expected callable")
        if fn.__name__ == fn_name:
            raise RuntimeError(f"{fn_name}-db-failure")
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            assert official is not None
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    return _side_effect


def test_attestation_run_sync_exception_fails_closed() -> None:
    """A: ATTESTATION_RUN_SYNC_EXCEPTION_FAILS_CLOSED."""
    maker = _mock_async_session_maker(
        run_sync_side_effect=_run_sync_raises_for("_attest_from_session"),
    )
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        result = materialize_train_validation_pairing_inputs_live()
    assert isinstance(result, TrainValidationPairingMaterializationResult)
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
    )


def test_content_obtain_run_sync_exception_fails_closed() -> None:
    """B: CONTENT_OBTAIN_RUN_SYNC_EXCEPTION_FAILS_CLOSED."""
    official = _small_official_partitions()
    maker = _mock_async_session_maker(
        run_sync_side_effect=_run_sync_raises_for("_obtain_from_session", official=official),
    )
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        result = materialize_train_validation_pairing_inputs_live()
    assert isinstance(result, TrainValidationPairingMaterializationResult)
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.OFFICIAL_PARTITION_BYTES_NOT_OBTAINED
    )


def test_replay_run_sync_exception_fails_closed() -> None:
    """C: REPLAY_RUN_SYNC_EXCEPTION_FAILS_CLOSED."""
    official = _small_official_partitions()
    maker = _mock_async_session_maker(
        run_sync_side_effect=_run_sync_raises_for(
            "_read_replay_identity_from_held_session",
            official=official,
        ),
    )
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with _patch_official_partitions(official):
            result = materialize_train_validation_pairing_inputs_live()
    assert isinstance(result, TrainValidationPairingMaterializationResult)
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS
    )


def test_pit_async_db_exception_fails_closed() -> None:
    """D: PIT_ASYNC_DB_EXCEPTION_FAILS_CLOSED."""
    official = _small_official_partitions()

    async def _run_sync_side_effect(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pit-db-execution-failure"),
        ):
            with _patch_official_partitions(official):
                result = materialize_train_validation_pairing_inputs_live()
    assert isinstance(result, TrainValidationPairingMaterializationResult)
    assert result.blocker is (
        TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER
    )


def test_no_exception_escapes_acquisition_phase() -> None:
    """E: NO_EXCEPTION_ESCAPES_ACQUISITION_PHASE."""
    official = _small_official_partitions()
    cases = [
        ("_attest_from_session", None),
        ("_obtain_from_session", official),
        ("_read_replay_identity_from_held_session", official),
    ]
    for fn_name, case_official in cases:
        maker = _mock_async_session_maker(
            run_sync_side_effect=_run_sync_raises_for(fn_name, official=case_official),
        )
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "resolve_live_async_session_maker",
            return_value=maker,
        ):
            patches = (
                [_patch_official_partitions(official)]
                if case_official is not None and fn_name != "_obtain_from_session"
                else []
            )
            if patches:
                with patches[0]:
                    result = materialize_train_validation_pairing_inputs_live()
            else:
                result = materialize_train_validation_pairing_inputs_live()
        assert isinstance(result, TrainValidationPairingMaterializationResult)

    async def _run_sync_success(fn: object) -> object:
        if fn.__name__ == "_attest_from_session":
            return _attested_envelope()
        if fn.__name__ == "_obtain_from_session":
            return _official_obtain_envelope(official)
        if fn.__name__ == "_read_replay_identity_from_held_session":
            return _reviewed_forecast_entries()
        raise AssertionError(f"unexpected run_sync fn: {fn.__name__}")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_success)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "resolve_live_async_session_maker",
        return_value=maker,
    ):
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "_obtain_from_async_session",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pit-db-execution-failure"),
        ):
            with _patch_official_partitions(official):
                result = materialize_train_validation_pairing_inputs_live()
    assert isinstance(result, TrainValidationPairingMaterializationResult)
