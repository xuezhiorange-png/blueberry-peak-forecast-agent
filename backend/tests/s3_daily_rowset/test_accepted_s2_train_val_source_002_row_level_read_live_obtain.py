"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-obtain tests."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
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
    SEALED_TEST_BYTE_COUNT,
    SEALED_TEST_CONTENT_SHA256,
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
    set_source_002_row_level_read_session_provider,
)

_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain"
)
_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
AcceptedS2TrainValLiveObtainEnvelope = _obtain.AcceptedS2TrainValLiveObtainEnvelope
LiveObtainReasonCode = _obtain.LiveObtainReasonCode
obtain_accepted_s2_train_val_content_bytes_from_bound_live_session = (
    _obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
)
bind_default_source_002_row_level_read_live_session_provider = (
    _live_session.bind_default_source_002_row_level_read_live_session_provider
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "bca600a15ebf3daa292050ab52ebcebfd953540a"
LIVE_SESSION_TEST_PY_BLOB = "c1ba24a1b87269d998b243002c231d654b08eb5a"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
READER_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py"
)
LIVE_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_session.py"
)
LIVE_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_obtain.py"
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
            content_sha256=content_sha256(content_bytes),
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
def _restore_session_provider() -> Iterator[None]:
    clear_source_002_row_level_read_session_provider()
    yield
    clear_source_002_row_level_read_session_provider()


def _assert_not_source_002(envelope: Any) -> None:
    assert envelope.source_002_row_level_read is False
    assert envelope.official_hashes_attested_from_a_live_read is False
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_no_session_fail_closes_without_bytes() -> None:
    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.obtained is False
    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION
    assert envelope.train_content_bytes is None
    assert envelope.validation_content_bytes is None
    assert envelope.test_remains_sealed is True
    _assert_not_source_002(envelope)


def test_provider_returning_none_fail_closes() -> None:
    set_source_002_row_level_read_session_provider(lambda: None)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION
    assert envelope.obtained is False
    assert envelope.train_content_bytes is None
    _assert_not_source_002(envelope)


def test_unreadable_session_provider_fail_closes() -> None:
    def _raise() -> Session:
        raise RuntimeError("session unavailable")

    set_source_002_row_level_read_session_provider(_raise)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE
    assert envelope.obtained is False
    assert envelope.train_content_bytes is None
    _assert_not_source_002(envelope)


def test_no_accepted_dataset_fail_closes() -> None:
    session = _session()
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET
    assert envelope.obtained is False
    assert envelope.train_content_bytes is None
    _assert_not_source_002(envelope)


def test_dataset_identity_mismatch_fail_closes() -> None:
    session = _session()
    _persist_accepted_dataset(session, dataset_version="not-e5-live-v1")
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH
    assert envelope.obtained is False
    assert envelope.train_content_bytes is None
    _assert_not_source_002(envelope)


def test_missing_train_or_validation_bytes_fail_closes() -> None:
    session = _session()
    _persist_accepted_dataset(session, include_train=False)
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert (
        envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES
    )
    assert envelope.obtained is False
    assert envelope.train_content_bytes is None
    assert envelope.validation_content_bytes is None
    _assert_not_source_002(envelope)


def test_unsealed_test_fail_closes_without_returning_test_bytes() -> None:
    session = _session()
    _persist_accepted_dataset(
        session,
        test_bytes=b"unsealed-test-payload-must-not-be-returned\n",
        test_row_count=1,
    )
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.reason_code is LiveObtainReasonCode.FAIL_CLOSED_TEST_UNSEALED
    assert envelope.obtained is False
    assert envelope.test_remains_sealed is False
    assert envelope.train_content_bytes is None
    assert envelope.validation_content_bytes is None
    assert "test_content_bytes" not in AcceptedS2TrainValLiveObtainEnvelope.model_fields
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_obtain_is_not_official_live_obtain() -> None:
    session = _session()
    _persist_accepted_dataset(session)
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.obtained is True
    assert envelope.reason_code is LiveObtainReasonCode.OBTAINED
    assert envelope.train_content_bytes == SYNTHETIC_TRAIN_BYTES
    assert envelope.validation_content_bytes == SYNTHETIC_VAL_BYTES
    assert envelope.train_byte_count == len(SYNTHETIC_TRAIN_BYTES)
    assert envelope.validation_byte_count == len(SYNTHETIC_VAL_BYTES)
    assert envelope.test_remains_sealed is True
    assert envelope.dataset_id == OFFICIAL_DATASET_ID
    assert envelope.dataset_version == OFFICIAL_DATASET_VERSION
    assert envelope.materialized_dataset_identity_sha256 == (
        OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256
    )
    _assert_not_source_002(envelope)
    assert content_sha256(envelope.train_content_bytes) != (
        "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )
    assert len(_sealed_test_bytes()) == SEALED_TEST_BYTE_COUNT
    assert content_sha256(_sealed_test_bytes()) == SEALED_TEST_CONTENT_SHA256


def test_obtained_bytes_that_fail_official_hash_match_are_not_source_002_row_level_read() -> None:
    session = _session()
    _persist_accepted_dataset(session)
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.obtained is True
    assert envelope.train_content_bytes == SYNTHETIC_TRAIN_BYTES
    assert envelope.validation_content_bytes == SYNTHETIC_VAL_BYTES
    _assert_not_source_002(envelope)


def test_obtain_envelope_does_not_expose_test_bytes_or_kg() -> None:
    field_names = set(AcceptedS2TrainValLiveObtainEnvelope.model_fields)
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


def test_bound_live_session_obtain_fail_closed_is_not_source_002_row_level_read() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    if envelope.obtained:
        assert envelope.reason_code is LiveObtainReasonCode.OBTAINED
        assert envelope.train_content_bytes
        assert envelope.validation_content_bytes
    else:
        assert envelope.train_content_bytes is None
        assert envelope.validation_content_bytes is None
        assert envelope.reason_code is not LiveObtainReasonCode.OBTAINED
    _assert_not_source_002(envelope)


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_obtain_and_parent_modules_contain_no_connection_string() -> None:
    for module in (READER_MODULE, LIVE_SESSION_MODULE, LIVE_OBTAIN_MODULE):
        source = module.read_text(encoding="utf-8").lower()
        assert "postgresql://" not in source
        assert "create_engine(" not in source


def test_parent_reader_and_live_session_blobs_unchanged() -> None:
    reader_blob = subprocess.check_output(
        ["git", "hash-object", str(READER_MODULE)],
        text=True,
    ).strip()
    live_session_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_SESSION_MODULE)],
        text=True,
    ).strip()
    reader_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/test_accepted_s2_train_val_source_002_row_level_read.py",
        ],
        text=True,
    ).strip()
    live_session_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_session.py",
        ],
        text=True,
    ).strip()
    assert reader_blob == PARENT_READER_PY_BLOB
    assert live_session_blob == LIVE_SESSION_PY_BLOB
    assert reader_tests == PARENT_READER_TEST_PY_BLOB
    assert live_session_tests == LIVE_SESSION_TEST_PY_BLOB


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
