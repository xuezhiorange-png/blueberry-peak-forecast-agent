"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-async-obtain tests."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
)

_async_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_obtain"
)
_async_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_session"
)
_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain"
)
_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
AcceptedS2TrainValLiveAsyncObtainEnvelope = _async_obtain.AcceptedS2TrainValLiveAsyncObtainEnvelope
LiveAsyncObtainReasonCode = _async_obtain.LiveAsyncObtainReasonCode
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session = _async_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session  # noqa: E501
obtain_accepted_s2_train_val_async_session_from_the_already_configured_live_async_sessionmaker = _async_session.obtain_accepted_s2_train_val_async_session_from_the_already_configured_live_async_sessionmaker  # noqa: E501
LiveAsyncSessionReasonCode = _async_session.LiveAsyncSessionReasonCode
obtain_accepted_s2_train_val_content_bytes_from_bound_live_session = (
    _obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
)
bind_default_source_002_row_level_read_live_session_provider = (
    _live_session.bind_default_source_002_row_level_read_live_session_provider
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "0e21ccc316eb828e52353f9b01adc7cc7743141d"
LIVE_SESSION_TEST_PY_BLOB = "94c54c117ad92a191e2aac00e8314f398e971125"
LIVE_OBTAIN_TEST_PY_BLOB = "d45f8d8d644b02d8bc4ca5fe091610e956fc1c91"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "775b45df7c5c1ccbf97bde417da2637cbf1972c3"
LIVE_CONNECTION_TEST_PY_BLOB = "b7692f1af6bf4ce04a3e9f9a05ce2a82630e908e"
LIVE_ASYNC_CONNECTION_TEST_PY_BLOB = "d3e68be59c3511ad3592ef5b0cffdaea572023e6"
LIVE_ASYNC_SESSION_TEST_PY_BLOB = "b5f55aaecf584f144d5e45e851c45344c893d512"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
LIVE_OBTAIN_PY_BLOB = "bf6e50cccf172f00c9be224d3d42bd2b1ef1bf8c"
LIVE_SESSION_QUERY_PY_BLOB = "d6a082dcabd7fbd1db324fd8ba6153ea2240fe39"
LIVE_CONNECTION_PY_BLOB = "f87bdf8b8add435298056f61614ee1d91c9dbbf0"
LIVE_ASYNC_CONNECTION_PY_BLOB = "51672d5a159d0889a159d9c03e8191e7f8a6b344"
LIVE_ASYNC_SESSION_PY_BLOB = "40afc94dacb2208accd4903b12ae46152a750b41"
SESSION_PY_BLOB = "49845a077d252af2a7a246fa25616d7595535037"
READER_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py"
)
LIVE_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_session.py"
)
LIVE_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_obtain.py"
)
LIVE_SESSION_QUERY_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_session_query.py"
)
LIVE_CONNECTION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_connection.py"
)
LIVE_ASYNC_CONNECTION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_connection.py"
)
LIVE_ASYNC_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session.py"
)
SESSION_MODULE = Path("backend/app/db/session.py")
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


def _create_tables(sync_conn: sa.Connection) -> None:
    cast(Table, S2MaterializedDatasetModel.__table__).create(sync_conn)
    cast(Table, S2MaterializedPartitionModel.__table__).create(sync_conn)


async def _persist_accepted_dataset_async(
    session: AsyncSession,
    *,
    dataset_id: str = OFFICIAL_DATASET_ID,
    dataset_version: str = OFFICIAL_DATASET_VERSION,
    identity: str = OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    train_bytes: bytes = SYNTHETIC_TRAIN_BYTES,
    validation_bytes: bytes = SYNTHETIC_VAL_BYTES,
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
        quality_gate_status="ACCEPTED",
        build_started_at=now,
        build_completed_at=now,
        upstream_snapshot_sha256=_placeholder_sha("upstream"),
    )
    session.add(dataset)
    await session.flush()
    for name, start, end, content_bytes, row_count in (
        ("TRAIN", date(2025, 8, 5), date(2026, 1, 30), train_bytes, 1),
        ("VALIDATION", date(2026, 1, 31), date(2026, 3, 9), validation_bytes, 1),
        ("TEST", TEST_START, TEST_END, _sealed_test_bytes(), 0),
    ):
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset.id,
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
                content_sha256=content_sha256(content_bytes),
                partition_identity_sha256=_placeholder_sha(f"identity-{name}"),
                manifest_sha256=_placeholder_sha(f"manifest-{name}"),
                content_bytes=content_bytes,
                lineage_complete=True,
                quality_gate_status="ACCEPTED",
                rebuild_hash_replay_status="PASS",
            )
        )
    await session.commit()


async def _async_session_maker_with_dataset() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_tables)
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        await _persist_accepted_dataset_async(session)
    return session_maker


def _session_maker_with_dataset() -> async_sessionmaker[AsyncSession]:
    return asyncio.run(_async_session_maker_with_dataset())


@pytest.fixture(autouse=True)
def _restore_session_provider() -> Iterator[None]:
    clear_source_002_row_level_read_session_provider()
    yield
    clear_source_002_row_level_read_session_provider()


def _assert_not_source_002(envelope: Any) -> None:
    assert envelope.source_002_row_level_read is False
    assert envelope.official_hashes_attested_from_a_live_read is False
    if hasattr(envelope, "accepted_s2_train_val_content_bytes_obtained_from_bound_live_session"):
        assert (
            envelope.accepted_s2_train_val_content_bytes_obtained_from_bound_live_session is False
        )
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_official_live_async_obtain_path_fail_closed_or_obtained() -> None:
    envelope = (
        obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()
    )

    if envelope.obtained:
        assert envelope.reason_code is LiveAsyncObtainReasonCode.OBTAINED
        assert envelope.train_content_bytes is not None
        assert envelope.validation_content_bytes is not None
    else:
        assert envelope.reason_code is not LiveAsyncObtainReasonCode.OBTAINED
        assert envelope.train_content_bytes is None
        assert envelope.validation_content_bytes is None
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_aiosqlite_obtained_is_not_official_live_async_obtain() -> None:
    session_maker = _session_maker_with_dataset()

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()  # noqa: E501

    assert envelope.obtained is True
    assert envelope.reason_code is LiveAsyncObtainReasonCode.OBTAINED
    assert envelope.train_content_bytes == SYNTHETIC_TRAIN_BYTES
    assert envelope.validation_content_bytes == SYNTHETIC_VAL_BYTES
    assert envelope.test_remains_sealed is True
    _assert_not_source_002(envelope)
    assert content_sha256(envelope.train_content_bytes) != (
        "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )


def test_missing_async_session_maker_fail_closes_no_async_session_maker() -> None:
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is LiveAsyncObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    _assert_not_source_002(envelope)


def test_session_maker_that_raises_on_enter_fail_closes_not_obtained() -> None:
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("session refused"))
    failing_ctx.__aexit__ = AsyncMock(return_value=None)
    failing_maker = MagicMock(return_value=failing_ctx)
    failing_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", failing_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()  # noqa: E501

    assert envelope.obtained is False
    assert (
        envelope.reason_code
        is LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_unreadable_async_session_fail_closes_async_session_unreadable() -> None:
    unreadable_session = AsyncMock(spec=AsyncSession)
    unreadable_session.scalar = AsyncMock(side_effect=RuntimeError("unreadable"))
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=unreadable_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE
    assert envelope.train_content_bytes is None
    assert envelope.validation_content_bytes is None
    _assert_not_source_002(envelope)


def test_async_obtain_envelope_does_not_expose_test_bytes_or_kg() -> None:
    field_names = set(AcceptedS2TrainValLiveAsyncObtainEnvelope.model_fields)
    assert "obtained" in field_names
    assert "train_content_bytes" in field_names
    assert "validation_content_bytes" in field_names
    assert "test_content_bytes" not in field_names
    assert "content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names


def test_parent_attestation_model_still_does_not_expose_content_bytes() -> None:
    field_names = set(AcceptedS2TrainValSource002RowLevelReadAttestation.model_fields)
    assert "content_bytes" not in field_names
    assert "train_content_bytes" not in field_names
    assert "validation_content_bytes" not in field_names


def test_sibling_async_session_and_live_obtain_still_not_source_002() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    async_session_envelope = (
        obtain_accepted_s2_train_val_async_session_from_the_already_configured_live_async_sessionmaker()  # noqa: E501
    )
    obtain_envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    if async_session_envelope.obtained:
        assert async_session_envelope.reason_code is LiveAsyncSessionReasonCode.OBTAINED
    else:
        assert async_session_envelope.reason_code is not LiveAsyncSessionReasonCode.OBTAINED
    assert obtain_envelope.source_002_row_level_read is False
    assert obtain_envelope.official_hashes_attested_from_a_live_read is False
    _assert_not_source_002(async_session_envelope)
    _assert_not_source_002(obtain_envelope)


def test_s2_source_002_row_level_read_constant_is_true_parent_family_live_attestation() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_async_obtain_module_contains_no_forbidden_patterns() -> None:
    module = Path(
        "backend/app/s3_daily_rowset/"
        "accepted_s2_train_val_source_002_row_level_read_live_async_obtain.py"
    )
    source = module.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "create_engine(" not in source
    assert "create_async_engine(" not in source
    assert "async_sessionmaker(" not in source
    assert "session.connection(" not in source
    assert "bind.connect(" not in source
    assert "get_bind(" not in source
    assert "engine.connect(" not in source
    assert "run_sync(" not in source
    assert "bound_source_002_row_level_read_session_provider(" not in source


def test_production_modules_contain_no_sync_engine_session_bridge() -> None:
    modules = [
        READER_MODULE,
        LIVE_SESSION_MODULE,
        LIVE_OBTAIN_MODULE,
        LIVE_SESSION_QUERY_MODULE,
        LIVE_CONNECTION_MODULE,
        LIVE_ASYNC_SESSION_MODULE,
        LIVE_ASYNC_CONNECTION_MODULE,
    ]
    for module in modules:
        source = module.read_text(encoding="utf-8").lower()
        assert ".sync_engine" not in source
        assert "session(bind" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
