"""Append-only ORM models and persistence for Lane A lineage tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.db.base import Base
from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    RawImportBatchIdentity,
    RawSourceArtifactIdentity,
    SourceRowIdentity,
)


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _sha256_hex_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


def _encode_identity_hashes(hashes: tuple[str, ...]) -> str:
    return canonical_json_dumps(list(hashes))


def _decode_identity_hashes(payload: str) -> tuple[str, ...]:
    decoded = json.loads(payload)
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise ValueError("stored source row identity hashes must be a JSON string list")
    return tuple(decoded)


class S2RawSourceArtifactModel(Base):
    __tablename__ = "s2_raw_source_artifact"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    source_artifact_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_dataset: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_reference: Mapped[str] = mapped_column(Text, nullable=False)
    source_object_identity: Mapped[str] = mapped_column(Text, nullable=False)
    source_artifact_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_artifact_identity_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_owner_attestation: Mapped[str] = mapped_column(Text, nullable=False)
    cohort_manifest_reference: Mapped[str] = mapped_column(Text, nullable=False)
    custody_record_reference: Mapped[str] = mapped_column(Text, nullable=False)
    storage_locator_hash: Mapped[str] = mapped_column(Text, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "source_artifact_identity_hash",
            name="uq_s2_raw_source_artifact_identity_hash",
        ),
        CheckConstraint(
            "source_artifact_sequence >= 1",
            name="ck_s2_raw_source_artifact_sequence_positive",
        ),
        CheckConstraint(
            _sha256_hex_check("source_artifact_identity_hash"),
            name="ck_s2_raw_source_artifact_identity_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("source_artifact_sha256"),
            name="ck_s2_raw_source_artifact_sha256",
        ),
        CheckConstraint(
            _sha256_hex_check("storage_locator_hash"),
            name="ck_s2_raw_source_artifact_storage_locator_hash",
        ),
    )


class S2RawImportBatchModel(Base):
    __tablename__ = "s2_raw_import_batch"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    raw_import_batch_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    raw_source_artifact_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    external_batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_dataset: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    import_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    validation_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_id: Mapped[str] = mapped_column(Text, nullable=False)
    import_request_identity: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_hashes_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "raw_import_batch_identity_hash",
            name="uq_s2_raw_import_batch_identity_hash",
        ),
        UniqueConstraint(
            "raw_source_artifact_identity_hash",
            "source_system",
            "external_batch_id",
            name="uq_s2_raw_import_batch_external_identity",
        ),
        ForeignKeyConstraint(
            ["raw_source_artifact_identity_hash"],
            ["s2_raw_source_artifact.source_artifact_identity_hash"],
            name="fk_s2_raw_import_batch_source_artifact",
            ondelete="RESTRICT",
        ),
        CheckConstraint("source_row_count >= 0", name="ck_s2_raw_import_batch_row_count"),
        CheckConstraint(
            _sha256_hex_check("raw_import_batch_identity_hash"),
            name="ck_s2_raw_import_batch_identity_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_raw_import_batch_content_sha256",
        ),
        CheckConstraint(
            _sha256_hex_check("raw_source_artifact_identity_hash"),
            name="ck_s2_raw_import_batch_source_artifact_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("raw_payload_hash"),
            name="ck_s2_raw_import_batch_raw_payload_hash",
        ),
    )


class S2SourceRowLineageModel(Base):
    __tablename__ = "s2_source_row_lineage"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    raw_source_artifact_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_import_batch_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_sheet_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_column_mapping_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "source_row_identity_hash",
            "content_sha256",
            name="uq_s2_source_row_lineage_identity_content",
        ),
        ForeignKeyConstraint(
            ["raw_source_artifact_identity_hash"],
            ["s2_raw_source_artifact.source_artifact_identity_hash"],
            name="fk_s2_source_row_lineage_source_artifact",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["raw_import_batch_identity_hash"],
            ["s2_raw_import_batch.raw_import_batch_identity_hash"],
            name="fk_s2_source_row_lineage_import_batch",
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number >= 1", name="ck_s2_source_row_lineage_revision_positive"),
        CheckConstraint(
            "source_row_number IS NULL OR source_row_number >= 1",
            name="ck_s2_source_row_lineage_row_number_positive",
        ),
        CheckConstraint(
            _sha256_hex_check("source_row_identity_hash"),
            name="ck_s2_source_row_lineage_identity_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_source_row_lineage_content_sha256",
        ),
        CheckConstraint(
            _sha256_hex_check("source_column_mapping_snapshot_hash"),
            name="ck_s2_source_row_lineage_mapping_snapshot_hash",
        ),
    )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _artifact_model_from_identity(identity: RawSourceArtifactIdentity) -> S2RawSourceArtifactModel:
    return S2RawSourceArtifactModel(
        source_artifact_identity_hash=identity.source_artifact_identity_hash,
        source_artifact_sha256=identity.source_artifact_sha256,
        source_system=identity.source_system,
        source_dataset=identity.source_dataset,
        source_version=identity.source_version,
        source_snapshot_reference=identity.source_snapshot_reference,
        source_object_identity=identity.source_object_identity,
        source_artifact_sequence=identity.source_artifact_sequence,
        schema_version=identity.schema_version,
        mapping_policy_version=identity.mapping_policy_version,
        source_artifact_identity_version=identity.source_artifact_identity_version,
        source_owner_attestation=identity.source_owner_attestation,
        cohort_manifest_reference=identity.cohort_manifest_reference,
        custody_record_reference=identity.custody_record_reference,
        storage_locator_hash=identity.storage_locator_hash,
        registered_at=_utc_now(),
    )


def _batch_model_from_identity(identity: RawImportBatchIdentity) -> S2RawImportBatchModel:
    return S2RawImportBatchModel(
        raw_import_batch_identity_hash=identity.raw_import_batch_identity_hash,
        content_sha256=identity.content_sha256,
        raw_source_artifact_identity_hash=identity.raw_source_artifact_identity_hash,
        external_batch_id=identity.external_batch_id,
        source_system=identity.source_system,
        source_dataset=identity.source_dataset,
        raw_payload_hash=identity.raw_payload_hash,
        import_policy_version=identity.import_policy_version,
        schema_version=identity.schema_version,
        mapping_policy_version=identity.mapping_policy_version,
        validation_policy_version=identity.validation_policy_version,
        source_cohort_id=identity.source_cohort_id,
        import_request_identity=identity.import_request_identity,
        source_row_identity_hashes_json=_encode_identity_hashes(
            identity.source_row_identity_hashes
        ),
        source_row_count=len(identity.source_row_identity_hashes),
        registered_at=_utc_now(),
    )


def _row_model_from_identity(identity: SourceRowIdentity) -> S2SourceRowLineageModel:
    return S2SourceRowLineageModel(
        source_row_identity_hash=identity.source_row_identity_hash,
        content_sha256=identity.content_sha256,
        raw_source_artifact_identity_hash=identity.raw_source_artifact_identity_hash,
        raw_import_batch_identity_hash=identity.raw_import_batch_identity_hash,
        external_logical_record_id=identity.external_logical_record_id,
        external_revision_id=identity.external_revision_id,
        revision_number=identity.revision_number,
        source_system=identity.source_system,
        source_version=identity.source_version,
        schema_version=identity.schema_version,
        source_row_identity_version=identity.source_row_identity_version,
        source_sheet_name=identity.source_sheet_name,
        source_row_number=identity.source_row_number,
        source_column_mapping_snapshot_hash=identity.source_column_mapping_snapshot_hash,
        registered_at=_utc_now(),
    )


def _artifact_from_model(model: S2RawSourceArtifactModel) -> RawSourceArtifactIdentity:
    return RawSourceArtifactIdentity.model_validate(
        {
            "source_artifact_identity_hash": model.source_artifact_identity_hash,
            "source_artifact_sha256": model.source_artifact_sha256,
            "source_system": model.source_system,
            "source_dataset": model.source_dataset,
            "source_version": model.source_version,
            "source_snapshot_reference": model.source_snapshot_reference,
            "source_object_identity": model.source_object_identity,
            "source_artifact_sequence": model.source_artifact_sequence,
            "schema_version": model.schema_version,
            "mapping_policy_version": model.mapping_policy_version,
            "source_artifact_identity_version": model.source_artifact_identity_version,
            "source_owner_attestation": model.source_owner_attestation,
            "cohort_manifest_reference": model.cohort_manifest_reference,
            "custody_record_reference": model.custody_record_reference,
            "storage_locator_hash": model.storage_locator_hash,
        }
    )


def _batch_from_model(model: S2RawImportBatchModel) -> RawImportBatchIdentity:
    return RawImportBatchIdentity.model_validate(
        {
            "raw_import_batch_identity_hash": model.raw_import_batch_identity_hash,
            "content_sha256": model.content_sha256,
            "raw_source_artifact_identity_hash": model.raw_source_artifact_identity_hash,
            "external_batch_id": model.external_batch_id,
            "source_system": model.source_system,
            "source_dataset": model.source_dataset,
            "raw_payload_hash": model.raw_payload_hash,
            "import_policy_version": model.import_policy_version,
            "schema_version": model.schema_version,
            "mapping_policy_version": model.mapping_policy_version,
            "validation_policy_version": model.validation_policy_version,
            "source_cohort_id": model.source_cohort_id,
            "import_request_identity": model.import_request_identity,
            "source_row_identity_hashes": _decode_identity_hashes(
                model.source_row_identity_hashes_json
            ),
        }
    )


def _row_from_model(
    model: S2SourceRowLineageModel,
    *,
    winner_selection_blocked: bool,
) -> SourceRowIdentity:
    return SourceRowIdentity.model_validate(
        {
            "source_row_identity_hash": model.source_row_identity_hash,
            "content_sha256": model.content_sha256,
            "raw_source_artifact_identity_hash": model.raw_source_artifact_identity_hash,
            "raw_import_batch_identity_hash": model.raw_import_batch_identity_hash,
            "external_logical_record_id": model.external_logical_record_id,
            "external_revision_id": model.external_revision_id,
            "revision_number": model.revision_number,
            "source_system": model.source_system,
            "source_version": model.source_version,
            "schema_version": model.schema_version,
            "source_row_identity_version": model.source_row_identity_version,
            "source_sheet_name": model.source_sheet_name,
            "source_row_number": model.source_row_number,
            "source_column_mapping_snapshot_hash": model.source_column_mapping_snapshot_hash,
            "winner_selection_blocked": winner_selection_blocked,
        }
    )


def derive_winner_selection_blocked(
    session: Session,
    *,
    raw_source_artifact_identity_hash: str,
    source_system: str,
    external_logical_record_id: str,
    source_row_identity_hash: str,
) -> bool:
    identity_models = session.scalars(
        select(S2SourceRowLineageModel).where(
            S2SourceRowLineageModel.source_row_identity_hash == source_row_identity_hash
        )
    ).all()
    if len({model.content_sha256 for model in identity_models}) > 1:
        return True

    logical_models = session.scalars(
        select(S2SourceRowLineageModel).where(
            S2SourceRowLineageModel.raw_source_artifact_identity_hash
            == raw_source_artifact_identity_hash,
            S2SourceRowLineageModel.source_system == source_system,
            S2SourceRowLineageModel.external_logical_record_id == external_logical_record_id,
        )
    ).all()
    revision_ids_by_number: dict[int, set[str]] = {}
    for model in logical_models:
        revision_ids_by_number.setdefault(model.revision_number, set()).add(
            model.external_revision_id
        )
    return any(len(revision_ids) > 1 for revision_ids in revision_ids_by_number.values())


def fetch_source_artifact_by_identity_hash(
    session: Session,
    *,
    source_artifact_identity_hash: str,
) -> RawSourceArtifactIdentity | None:
    model = session.scalar(
        select(S2RawSourceArtifactModel).where(
            S2RawSourceArtifactModel.source_artifact_identity_hash == source_artifact_identity_hash
        )
    )
    if model is None:
        return None
    return _artifact_from_model(model)


def fetch_import_batch_by_identity_hash(
    session: Session,
    *,
    raw_import_batch_identity_hash: str,
) -> RawImportBatchIdentity | None:
    model = session.scalar(
        select(S2RawImportBatchModel).where(
            S2RawImportBatchModel.raw_import_batch_identity_hash == raw_import_batch_identity_hash
        )
    )
    if model is None:
        return None
    return _batch_from_model(model)


def fetch_import_batch_by_external_identity(
    session: Session,
    *,
    raw_source_artifact_identity_hash: str,
    source_system: str,
    external_batch_id: str,
) -> RawImportBatchIdentity | None:
    model = session.scalar(
        select(S2RawImportBatchModel).where(
            S2RawImportBatchModel.raw_source_artifact_identity_hash
            == raw_source_artifact_identity_hash,
            S2RawImportBatchModel.source_system == source_system,
            S2RawImportBatchModel.external_batch_id == external_batch_id,
        )
    )
    if model is None:
        return None
    return _batch_from_model(model)


def fetch_source_rows_by_identity_hash(
    session: Session,
    *,
    source_row_identity_hash: str,
) -> tuple[SourceRowIdentity, ...]:
    models = session.scalars(
        select(S2SourceRowLineageModel)
        .where(S2SourceRowLineageModel.source_row_identity_hash == source_row_identity_hash)
        .order_by(S2SourceRowLineageModel.content_sha256)
    ).all()
    return tuple(
        _row_from_model(
            model,
            winner_selection_blocked=derive_winner_selection_blocked(
                session,
                raw_source_artifact_identity_hash=model.raw_source_artifact_identity_hash,
                source_system=model.source_system,
                external_logical_record_id=model.external_logical_record_id,
                source_row_identity_hash=model.source_row_identity_hash,
            ),
        )
        for model in models
    )


def fetch_source_row_by_identity_and_content(
    session: Session,
    *,
    source_row_identity_hash: str,
    content_sha256: str,
) -> SourceRowIdentity | None:
    model = session.scalar(
        select(S2SourceRowLineageModel).where(
            S2SourceRowLineageModel.source_row_identity_hash == source_row_identity_hash,
            S2SourceRowLineageModel.content_sha256 == content_sha256,
        )
    )
    if model is None:
        return None
    return _row_from_model(
        model,
        winner_selection_blocked=derive_winner_selection_blocked(
            session,
            raw_source_artifact_identity_hash=model.raw_source_artifact_identity_hash,
            source_system=model.source_system,
            external_logical_record_id=model.external_logical_record_id,
            source_row_identity_hash=model.source_row_identity_hash,
        ),
    )


def fetch_source_rows_by_logical_key(
    session: Session,
    *,
    raw_source_artifact_identity_hash: str,
    source_system: str,
    external_logical_record_id: str,
) -> tuple[SourceRowIdentity, ...]:
    models = session.scalars(
        select(S2SourceRowLineageModel)
        .where(
            S2SourceRowLineageModel.raw_source_artifact_identity_hash
            == raw_source_artifact_identity_hash,
            S2SourceRowLineageModel.source_system == source_system,
            S2SourceRowLineageModel.external_logical_record_id == external_logical_record_id,
        )
        .order_by(
            S2SourceRowLineageModel.revision_number,
            S2SourceRowLineageModel.external_revision_id,
            S2SourceRowLineageModel.content_sha256,
        )
    ).all()
    return tuple(
        _row_from_model(
            model,
            winner_selection_blocked=derive_winner_selection_blocked(
                session,
                raw_source_artifact_identity_hash=model.raw_source_artifact_identity_hash,
                source_system=model.source_system,
                external_logical_record_id=model.external_logical_record_id,
                source_row_identity_hash=model.source_row_identity_hash,
            ),
        )
        for model in models
    )


def insert_source_artifact(
    session: Session,
    *,
    identity: RawSourceArtifactIdentity,
) -> RawSourceArtifactIdentity:
    session.add(_artifact_model_from_identity(identity))
    session.flush()
    return identity


def insert_import_batch(
    session: Session,
    *,
    identity: RawImportBatchIdentity,
) -> RawImportBatchIdentity:
    session.add(_batch_model_from_identity(identity))
    session.flush()
    return identity


def insert_source_row_lineage(
    session: Session,
    *,
    identity: SourceRowIdentity,
) -> SourceRowIdentity:
    session.add(_row_model_from_identity(identity))
    session.flush()
    return identity
