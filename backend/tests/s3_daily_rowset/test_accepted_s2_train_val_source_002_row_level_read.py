"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read tests."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

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
    OFFICIAL_TRAIN_BYTE_COUNT,
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_BYTE_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
    SEALED_TEST_BYTE_COUNT,
    SEALED_TEST_CONTENT_SHA256,
    SEALED_TEST_ROW_COUNT,
    Source002RowLevelReadReasonCode,
    attest_accepted_s2_train_val_source_002_row_level_read,
    clear_source_002_row_level_read_session_provider,
    set_source_002_row_level_read_session_provider,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
READER_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py"
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
    train_stored_hash: str | None = None,
    validation_stored_hash: str | None = None,
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
            stored_content_sha256=train_stored_hash,
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
            stored_content_sha256=validation_stored_hash,
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


def test_official_hash_constants_are_s2_acceptance_package_copy() -> None:
    assert OFFICIAL_DATASET_ID == EXPECTED_DATASET_ID == "source-002"
    assert OFFICIAL_DATASET_VERSION == EXPECTED_DATASET_VERSION == "e5-live-v1"
    assert (
        OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256
        == EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
        == "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
    )
    assert OFFICIAL_TRAIN_ROW_COUNT == 16224
    assert OFFICIAL_TRAIN_BYTE_COUNT == 9087071
    assert (
        OFFICIAL_TRAIN_CONTENT_SHA256
        == "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )
    assert OFFICIAL_VALIDATION_ROW_COUNT == 8006
    assert OFFICIAL_VALIDATION_BYTE_COUNT == 4484905
    assert (
        OFFICIAL_VALIDATION_CONTENT_SHA256
        == "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
    )
    assert SEALED_TEST_ROW_COUNT == 0
    assert SEALED_TEST_BYTE_COUNT == 240
    assert (
        SEALED_TEST_CONTENT_SHA256
        == "bd3d846a300c70a638bc169a095c3b02cb9e20c2c2aa6a96af0990d85a1fb1bd"
    )
    assert content_sha256(_sealed_test_bytes()) == SEALED_TEST_CONTENT_SHA256
    assert len(_sealed_test_bytes()) == SEALED_TEST_BYTE_COUNT


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_default_without_session_fail_closes() -> None:
    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.official_hashes_attested_from_a_live_read is False
    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION
    assert result.test_remains_sealed is True


def test_provider_returning_none_fail_closes() -> None:
    set_source_002_row_level_read_session_provider(lambda: None)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION
    assert result.attested is False
    assert result.source_002_row_level_read is False


def test_unreadable_session_provider_fail_closes() -> None:
    def _raise() -> Session:
        raise RuntimeError("session unavailable")

    set_source_002_row_level_read_session_provider(_raise)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE
    assert result.attested is False
    assert result.source_002_row_level_read is False


def test_empty_tables_fail_closed_no_accepted_dataset() -> None:
    session = _session()
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_rejected_quality_gate_is_not_accepted_dataset() -> None:
    session = _session()
    _persist_accepted_dataset(session, quality_gate_status="REJECTED")
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET
    assert result.attested is False


def test_identity_mismatch_fail_closes() -> None:
    session = _session()
    _persist_accepted_dataset(
        session,
        identity=_placeholder_sha("not-official-identity"),
    )
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert (
        result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH
    )
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.dataset_id == "source-002"
    assert result.dataset_version == "e5-live-v1"
    assert result.materialized_dataset_identity_sha256 == _placeholder_sha("not-official-identity")


def test_wrong_dataset_version_is_identity_mismatch() -> None:
    session = _session()
    _persist_accepted_dataset(session, dataset_version="not-e5-live-v1")
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert (
        result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH
    )
    assert result.attested is False


def test_missing_train_bytes_fail_closes() -> None:
    session = _session()
    _persist_accepted_dataset(session, include_train=False)
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES
    )
    assert result.attested is False
    assert result.source_002_row_level_read is False


def test_empty_validation_bytes_fail_closes() -> None:
    session = _session()
    _persist_accepted_dataset(session, validation_bytes=b"")
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is (
        Source002RowLevelReadReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES
    )
    assert result.attested is False


def test_stored_official_hash_with_different_bytes_is_hash_mismatch() -> None:
    session = _session()
    _persist_accepted_dataset(
        session,
        train_stored_hash=OFFICIAL_TRAIN_CONTENT_SHA256,
        validation_stored_hash=OFFICIAL_VALIDATION_CONTENT_SHA256,
    )
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_HASH_MISMATCH
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.official_hashes_attested_from_a_live_read is False
    assert result.train_content_sha256 == content_sha256(SYNTHETIC_TRAIN_BYTES)
    assert result.train_content_sha256 != OFFICIAL_TRAIN_CONTENT_SHA256
    assert result.validation_content_sha256 == content_sha256(SYNTHETIC_VAL_BYTES)
    assert result.validation_content_sha256 != OFFICIAL_VALIDATION_CONTENT_SHA256
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_synthetic_persist_against_official_hashes_is_hash_mismatch() -> None:
    session = _session()
    _persist_accepted_dataset(session)
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_HASH_MISMATCH
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.official_hashes_attested_from_a_live_read is False
    assert result.test_remains_sealed is True
    assert result.train_byte_count == len(SYNTHETIC_TRAIN_BYTES)
    assert result.validation_byte_count == len(SYNTHETIC_VAL_BYTES)


def test_test_row_count_nonzero_is_test_unsealed() -> None:
    session = _session()
    _persist_accepted_dataset(session, test_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_TEST_UNSEALED
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.test_remains_sealed is False
    assert result.test_row_count == 1


def test_test_bytes_not_sealed_hash_is_test_unsealed() -> None:
    session = _session()
    _persist_accepted_dataset(session, test_bytes=b"unsealed-test\n", test_row_count=0)
    set_source_002_row_level_read_session_provider(lambda: session)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_TEST_UNSEALED
    assert result.attested is False
    assert result.test_remains_sealed is False


def test_count_mismatch_after_hash_match_is_not_official_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _persist_accepted_dataset(session, train_row_count=1, validation_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session)
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_TRAIN_CONTENT_SHA256",
        content_sha256(SYNTHETIC_TRAIN_BYTES),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_VALIDATION_CONTENT_SHA256",
        content_sha256(SYNTHETIC_VAL_BYTES),
    )

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_COUNT_MISMATCH
    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.official_hashes_attested_from_a_live_read is False
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_monkeypatched_constants_attested_path_is_not_official_live_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _persist_accepted_dataset(session, train_row_count=1, validation_row_count=1)
    set_source_002_row_level_read_session_provider(lambda: session)
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_TRAIN_CONTENT_SHA256",
        content_sha256(SYNTHETIC_TRAIN_BYTES),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_VALIDATION_CONTENT_SHA256",
        content_sha256(SYNTHETIC_VAL_BYTES),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_TRAIN_ROW_COUNT",
        1,
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_VALIDATION_ROW_COUNT",
        1,
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_TRAIN_BYTE_COUNT",
        len(SYNTHETIC_TRAIN_BYTES),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read"
        ".OFFICIAL_VALIDATION_BYTE_COUNT",
        len(SYNTHETIC_VAL_BYTES),
    )

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.ATTESTED
    assert result.attested is True
    assert result.source_002_row_level_read is True
    assert result.official_hashes_attested_from_a_live_read is True
    assert result.test_remains_sealed is True
    assert SOURCE_002_ROW_LEVEL_READ is False
    assert OFFICIAL_TRAIN_CONTENT_SHA256 == (
        "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )


def test_attestation_model_does_not_expose_kg_or_content_bytes() -> None:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
        AcceptedS2TrainValSource002RowLevelReadAttestation,
    )

    field_names = set(AcceptedS2TrainValSource002RowLevelReadAttestation.model_fields)
    assert "actual_harvest_quantity_kg" not in field_names
    assert "content_bytes" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names


def test_reader_module_contains_no_dsn() -> None:
    source = READER_MODULE.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "dsn" not in source
    assert "create_engine(" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
