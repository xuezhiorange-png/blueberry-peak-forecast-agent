"""SOURCE-002 live reader run_sync correction tests (R1)."""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import Table

from backend.app.s2_materialized_dataset.lane_d.canonical import build_test_synthetic_bytes
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_END, TEST_START
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_ROW_LEVEL_READ,
    SPLIT_POLICY_VERSION,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    Source002RowLevelReadReasonCode,
    attest_accepted_s2_train_val_source_002_row_level_read,
    clear_source_002_row_level_read_session_provider,
    set_source_002_row_level_read_session_provider,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
    LiveObtainReasonCode,
    obtain_accepted_s2_train_val_content_bytes_from_bound_live_session,
)

_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
READER_MODULE = _APP_ROOT / "s3_daily_rowset" / "accepted_s2_train_val_source_002_row_level_read.py"
LIVE_SESSION_MODULE = (
    _APP_ROOT
    / "s3_daily_rowset"
    / "accepted_s2_train_val_source_002_row_level_read_live_session.py"
)
LIVE_OBTAIN_MODULE = (
    _APP_ROOT / "s3_daily_rowset" / "accepted_s2_train_val_source_002_row_level_read_live_obtain.py"
)
RUN_SYNC_MODULE = (
    _APP_ROOT
    / "s3_daily_rowset"
    / "accepted_s2_train_val_source_002_row_level_read_live_run_sync.py"
)
SYNTHETIC_TRAIN_BYTES = b"synthetic-train-partition\n"
SYNTHETIC_VAL_BYTES = b"synthetic-validation-partition\n"


def _sealed_test_bytes() -> bytes:
    return build_test_synthetic_bytes(
        partition_name="TEST",
        partition_start_date=TEST_START.isoformat(),
        partition_end_date=TEST_END.isoformat(),
        split_policy_version=SPLIT_POLICY_VERSION,
    )


def _placeholder_sha(label: str) -> str:
    return content_sha256(label.encode("utf-8"))


def _create_tables(engine: sa.Engine) -> None:
    cast(Table, S2MaterializedDatasetModel.__table__).create(engine)
    cast(Table, S2MaterializedPartitionModel.__table__).create(engine)


def _session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    _create_tables(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _add_partition(
    session: Session,
    *,
    dataset_id: int,
    name: str,
    start: date,
    end: date,
    content_bytes: bytes,
    row_count: int,
    stored_content_sha256: str | None = None,
) -> None:
    session.add(
        S2MaterializedPartitionModel(
            materialized_dataset_id=dataset_id,
            partition_name=name,
            partition_start_date=start,
            partition_end_date=end,
            partition_date_field="HARVEST_BUSINESS_DATE",
            target_decision="OBSERVED_FARM_PICK_QUANTITY",
            canonical_grain="SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE",
            split_policy_version=SPLIT_POLICY_VERSION,
            manifest_schema_version="v0-3-s2-materialized-dataset-manifest-v1",
            materialized_partition_schema_version="v0-3-s2-materialized-partition-v1",
            row_count=row_count,
            byte_count=len(content_bytes),
            content_sha256=stored_content_sha256 or content_sha256(content_bytes),
            partition_identity_sha256=_placeholder_sha(f"identity-{name}"),
            manifest_sha256=_placeholder_sha(f"manifest-{name}"),
            content_bytes=content_bytes,
            lineage_complete=True,
            quality_gate_status="ACCEPTED",
            rebuild_hash_replay_status="PASS",
        )
    )


def _persist_accepted_dataset(
    session: Session,
    *,
    dataset_id: str = OFFICIAL_DATASET_ID,
    dataset_version: str = OFFICIAL_DATASET_VERSION,
    identity: str = OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    quality_gate_status: str = "ACCEPTED",
    include_train: bool = True,
    include_validation: bool = True,
    include_test: bool = True,
    train_bytes: bytes = SYNTHETIC_TRAIN_BYTES,
    validation_bytes: bytes = SYNTHETIC_VAL_BYTES,
    train_row_count: int = 1,
    validation_row_count: int = 1,
    test_bytes: bytes | None = None,
    test_row_count: int = 0,
) -> None:
    now = datetime(2026, 4, 1, tzinfo=UTC)
    dataset = S2MaterializedDatasetModel(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=identity,
        source_cohort_id="source-002-s1-cohort-v1",
        source_cohort_manifest_sha256=(
            "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
        ),
        raw_policy_version="v0-3-s2-raw-policy-v1",
        cleaning_policy_version="v0-3-s2-cleaning-policy-v1",
        correction_policy_version="v0-3-s2-correction-policy-v1",
        exclusion_policy_version="v0-3-s2-exclusion-policy-v1",
        visibility_policy_version="v0-3-s2-visibility-policy-v1",
        revision_winner_policy_version="v0-3-s2-revision-winner-policy-v1",
        cleaned_dataset_version_identity="cleaned-dataset-v1",
        builder_version="v0-3-s2-lane-d-builder-r1",
        dataset_schema_version="v0-3-s2-materialized-dataset-v1",
        lineage_complete=True,
        quality_gate_status=quality_gate_status,
        build_started_at=now,
        build_completed_at=now,
        upstream_snapshot_sha256=_placeholder_sha("upstream"),
    )
    session.add(dataset)
    session.flush()
    if include_train:
        _add_partition(
            session,
            dataset_id=dataset.id,
            name="TRAIN",
            start=date(2025, 8, 5),
            end=date(2026, 1, 30),
            content_bytes=train_bytes,
            row_count=train_row_count,
        )
    if include_validation:
        _add_partition(
            session,
            dataset_id=dataset.id,
            name="VALIDATION",
            start=date(2026, 1, 31),
            end=date(2026, 3, 9),
            content_bytes=validation_bytes,
            row_count=validation_row_count,
        )
    if include_test:
        sealed = test_bytes if test_bytes is not None else _sealed_test_bytes()
        _add_partition(
            session,
            dataset_id=dataset.id,
            name="TEST",
            start=TEST_START,
            end=TEST_END,
            content_bytes=sealed,
            row_count=test_row_count,
        )
    session.commit()


@pytest.fixture(autouse=True)
def _clear_session_provider() -> Iterator[None]:
    clear_source_002_row_level_read_session_provider()
    yield
    clear_source_002_row_level_read_session_provider()


def _mock_async_session_maker(*, run_sync_side_effect: object) -> MagicMock:
    async_session = MagicMock(spec=AsyncSession)
    if isinstance(run_sync_side_effect, Exception):
        async_session.run_sync = AsyncMock(side_effect=run_sync_side_effect)
    else:
        async_session.run_sync = AsyncMock(side_effect=run_sync_side_effect)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=async_session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    maker = MagicMock()
    maker.return_value = session_cm
    return maker


def test_production_attestation_uses_async_session_run_sync() -> None:
    """A: PRODUCTION_ATTESTATION_USES_ASYNC_SESSION_RUN_SYNC."""
    captured: dict[str, object] = {}

    async def _run_sync_side_effect(fn: object) -> object:
        assert callable(fn)
        captured["sync_fn_name"] = fn.__name__
        return MagicMock(attested=False, reason_code=Source002RowLevelReadReasonCode.ATTESTED)

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
        ".resolve_live_async_session_maker",
        return_value=maker,
    ):
        attest_accepted_s2_train_val_source_002_row_level_read()

    maker.assert_called_once()
    async_session = maker.return_value.__aenter__.return_value
    async_session.run_sync.assert_awaited_once()
    assert captured["sync_fn_name"] == "_attest_from_session"


def test_production_content_obtain_uses_async_session_run_sync() -> None:
    """B: PRODUCTION_CONTENT_OBTAIN_USES_ASYNC_SESSION_RUN_SYNC."""
    captured: dict[str, object] = {}

    async def _run_sync_side_effect(fn: object) -> object:
        assert callable(fn)
        assert fn.__name__ == "_obtain_from_session"
        captured["called"] = True
        return MagicMock(obtained=False, reason_code=LiveObtainReasonCode.OBTAINED)

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
        ".resolve_live_async_session_maker",
        return_value=maker,
    ):
        obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert captured.get("called") is True


def test_sync_engine_session_bridge_removed() -> None:
    """C: SYNC_ENGINE_SESSION_BRIDGE_REMOVED."""
    for module in (LIVE_SESSION_MODULE, READER_MODULE, LIVE_OBTAIN_MODULE, RUN_SYNC_MODULE):
        source = module.read_text(encoding="utf-8")
        assert ".sync_engine" not in source
        assert "Session(bind" not in source


def test_no_new_engine_in_corrected_live_reader_path() -> None:
    """D: NO_NEW_ENGINE."""
    for module in (READER_MODULE, LIVE_OBTAIN_MODULE, RUN_SYNC_MODULE, LIVE_SESSION_MODULE):
        source = module.read_text(encoding="utf-8").lower()
        assert "create_engine(" not in source
        assert "create_async_engine(" not in source


def test_official_identity_regression() -> None:
    """E: OFFICIAL_IDENTITY_REGRESSION."""
    session = _session()
    _persist_accepted_dataset(session, dataset_version="not-e5-live-v1")
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert (
        result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH
    )
    assert result.attested is False


def test_train_hash_count_regression() -> None:
    """F: TRAIN_HASH_COUNT_REGRESSION."""
    session = _session()
    _persist_accepted_dataset(session)
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_HASH_MISMATCH
    assert result.train_byte_count == len(SYNTHETIC_TRAIN_BYTES)
    assert result.train_content_sha256 == content_sha256(SYNTHETIC_TRAIN_BYTES)


def test_validation_hash_count_regression() -> None:
    """G: VALIDATION_HASH_COUNT_REGRESSION."""
    session = _session()
    _persist_accepted_dataset(session, validation_bytes=b"")
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES
    )


def test_test_remains_sealed() -> None:
    """H: TEST_REMAINS_SEALED."""
    session = _session()
    _persist_accepted_dataset(session, test_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session)

    attestation = attest_accepted_s2_train_val_source_002_row_level_read()
    assert attestation.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_TEST_UNSEALED

    session2 = _session()
    _persist_accepted_dataset(session2, train_row_count=1, validation_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session2)
    with (
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_CONTENT_SHA256",
            content_sha256(SYNTHETIC_TRAIN_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_CONTENT_SHA256",
            content_sha256(SYNTHETIC_VAL_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_ROW_COUNT",
            1,
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_ROW_COUNT",
            1,
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_BYTE_COUNT",
            len(SYNTHETIC_TRAIN_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_BYTE_COUNT",
            len(SYNTHETIC_VAL_BYTES),
        ),
    ):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.obtained is True
    assert envelope.train_content_bytes == SYNTHETIC_TRAIN_BYTES
    assert envelope.validation_content_bytes == SYNTHETIC_VAL_BYTES
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
        AcceptedS2TrainValLiveObtainEnvelope,
    )

    assert "test_content_bytes" not in AcceptedS2TrainValLiveObtainEnvelope.model_fields


def test_explicit_test_provider_compatibility() -> None:
    """I: EXPLICIT_TEST_PROVIDER_COMPATIBILITY."""
    session = _session()
    _persist_accepted_dataset(session, train_row_count=1, validation_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session)
    with (
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_CONTENT_SHA256",
            content_sha256(SYNTHETIC_TRAIN_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_CONTENT_SHA256",
            content_sha256(SYNTHETIC_VAL_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_ROW_COUNT",
            1,
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_ROW_COUNT",
            1,
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_TRAIN_BYTE_COUNT",
            len(SYNTHETIC_TRAIN_BYTES),
        ),
        patch(
            "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
            ".OFFICIAL_VALIDATION_BYTE_COUNT",
            len(SYNTHETIC_VAL_BYTES),
        ),
    ):
        result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.ATTESTED
    assert result.attested is True
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_missing_async_session_maker_fails_closed() -> None:
    """J: MISSING_ASYNC_SESSION_MAKER_FAILS_CLOSED."""
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
        ".resolve_live_async_session_maker",
        return_value=None,
    ):
        attestation = attest_accepted_s2_train_val_source_002_row_level_read()
        obtain = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert attestation.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    )
    assert attestation.attested is False
    assert obtain.reason_code is LiveObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    assert obtain.obtained is False


def test_run_sync_failure_fails_closed() -> None:
    """K: RUN_SYNC_FAILURE_FAILS_CLOSED."""

    async def _run_sync_side_effect(_fn: object) -> object:
        raise RuntimeError("run_sync failed")

    maker = _mock_async_session_maker(run_sync_side_effect=_run_sync_side_effect)
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
        ".resolve_live_async_session_maker",
        return_value=maker,
    ):
        attestation = attest_accepted_s2_train_val_source_002_row_level_read()
        obtain = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert attestation.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE
    )
    assert obtain.reason_code is LiveObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE


def test_async_session_not_obtained_fails_closed() -> None:
    maker = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("cannot enter"))
    session_cm.__aexit__ = AsyncMock(return_value=None)
    maker.return_value = session_cm
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync"
        ".resolve_live_async_session_maker",
        return_value=maker,
    ):
        attestation = attest_accepted_s2_train_val_source_002_row_level_read()

    assert attestation.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED
    )


def test_materialization_entrypoint_regression() -> None:
    """L: MATERIALIZATION_ENTRYPOINT_REGRESSION."""
    from backend.app.forecast_quality.train_val_pairing_materialization import (
        materialize_train_validation_pairing_inputs_live,
    )

    materialization_source = (
        _APP_ROOT / "forecast_quality" / "train_val_pairing_materialization.py"
    ).read_text(encoding="utf-8")
    live_start = materialization_source.index("def materialize_train_validation_pairing_inputs_live")
    live_end = materialization_source.index("def build_materialization_evidence_payload", live_start)
    live_source = materialization_source[live_start:live_end]
    tree = ast.parse(live_source)
    call_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.append(func.id)
            elif isinstance(func, ast.Attribute):
                call_names.append(func.attr)
    assert "asyncio" in live_source
    assert "_materialize_train_validation_pairing_inputs_live_async" in live_source
    assert "attest_accepted_s2_train_val_source_002_row_level_read" not in live_source
    assert "obtain_accepted_s2_train_val_content_bytes_from_bound_live_session" not in live_source
    assert "obtain_live_incumbent_forecast_daily_curve_provider" not in live_source

    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
        "_materialize_with_held_async_session",
        new_callable=AsyncMock,
        return_value=MagicMock(
            completed=False,
            blocker=__import__(
                "backend.app.forecast_quality.train_val_pairing_materialization",
                fromlist=["TrainValidationPairingMaterializationBlocker"],
            ).TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED,
        ),
    ) as materialize_async:
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization_live_async."
            "resolve_live_async_session_maker",
            return_value=MagicMock(),
        ):
            materialize_train_validation_pairing_inputs_live()

    materialize_async.assert_awaited_once()


def test_pr550_pr551_pr552_regression() -> None:
    """M: PR550_PR551_PR552_REGRESSION."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/test_s3_b_persisted_task10_authority_reference_relation_r1.py",
            "backend/tests/rolling_backtest/test_s3_b_persisted_task10_authority_production_writer_r1.py",
            "backend/tests/forecast_quality/test_s3_b_live_pairing_authority_handoff_r1.py",
            "-q",
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
