"""Lane D materialized dataset persistence, load, and storage-backed rebuild."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.s2_materialized_dataset.lane_d.manifest import (
    recompute_manifest_sha256_from_published,
)
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    BUILDER_VERSION,
    DATASET_SCHEMA_VERSION,
    PARTITION_DATE_FIELD,
    MaterializableRow,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
    UpstreamBundlePort,
)


class MaterializedDatasetConflictError(Exception):
    """Raised when a dataset version identity conflicts with stored facts."""


class MaterializedDatasetStorageRebuildError(Exception):
    """Raised when storage-backed rebuild does not match persisted hashes."""


def _builder_imports():
    from backend.app.s2_materialized_dataset.lane_d.builder import (
        BuildTimestamps,
        MaterializedDatasetBuildError,
        build_materialized_dataset,
        materialize_partition_bytes,
    )
    from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS

    return (
        BuildTimestamps,
        MaterializedDatasetBuildError,
        build_materialized_dataset,
        materialize_partition_bytes,
        FROZEN_PARTITIONS,
    )


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _sha_check(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"


class S2MaterializedDatasetModel(Base):
    __tablename__ = "s2_materialized_dataset"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    materialized_dataset_identity_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    raw_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaning_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    correction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_dataset_version_identity: Mapped[str] = mapped_column(Text, nullable=False)
    builder_version: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_gate_status: Mapped[str] = mapped_column(Text, nullable=False)
    build_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    build_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upstream_snapshot_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    materializable_rows: Mapped[list[S2MaterializedMaterializableRowModel]] = relationship(
        back_populates="dataset",
        order_by="S2MaterializedMaterializableRowModel.row_sort_key",
    )
    partitions: Mapped[list[S2MaterializedPartitionModel]] = relationship(
        back_populates="dataset",
        order_by="S2MaterializedPartitionModel.partition_name",
    )

    __table_args__ = (
        UniqueConstraint(
            "materialized_dataset_identity_sha256",
            name="uq_s2_materialized_dataset_identity",
        ),
        UniqueConstraint(
            "dataset_id", "dataset_version", name="uq_s2_materialized_dataset_version"
        ),
        CheckConstraint(
            _sha_check("materialized_dataset_identity_sha256"),
            name="ck_s2_materialized_dataset_identity",
        ),
    )


class S2MaterializedMaterializableRowModel(Base):
    __tablename__ = "s2_materialized_materializable_row"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    materialized_dataset_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_sort_key: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    farm: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm: Mapped[str] = mapped_column(Text, nullable=False)
    variety: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_harvest_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_row_identity: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_row_identity: Mapped[str] = mapped_column(Text, nullable=False)
    pit_visibility_identity: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_identity: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[S2MaterializedDatasetModel] = relationship(back_populates="materializable_rows")


class S2MaterializedPartitionModel(Base):
    __tablename__ = "s2_materialized_partition"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    materialized_dataset_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    partition_name: Mapped[str] = mapped_column(Text, nullable=False)
    partition_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    partition_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    partition_date_field: Mapped[str] = mapped_column(Text, nullable=False)
    target_decision: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_grain: Mapped[str] = mapped_column(Text, nullable=False)
    split_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    materialized_partition_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    partition_identity_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lineage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_gate_status: Mapped[str] = mapped_column(Text, nullable=False)
    rebuild_hash_replay_status: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[S2MaterializedDatasetModel] = relationship(back_populates="partitions")


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneA:
    source_cohort_id: str
    source_cohort_manifest_sha256: str
    raw_policy_version: str

    def lineage_identity_present(self) -> bool:
        return bool(
            self.source_cohort_id and self.source_cohort_manifest_sha256 and self.raw_policy_version
        )


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneB:
    cleaned_dataset_version_identity: str
    cleaning_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    rows: tuple[MaterializableRow, ...]

    def iter_materializable_rows(self) -> tuple[MaterializableRow, ...]:
        return self.rows

    def lineage_identity_present(self) -> bool:
        return bool(
            self.cleaned_dataset_version_identity
            and self.cleaning_policy_version
            and self.correction_policy_version
            and self.exclusion_policy_version
        )


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneC:
    visibility_policy_version: str
    revision_winner_policy_version: str

    def lineage_identity_present(self) -> bool:
        return bool(self.visibility_policy_version and self.revision_winner_policy_version)


@dataclass(frozen=True, slots=True)
class StoredUpstreamBundle:
    lane_a: StoredUpstreamLaneA
    lane_b: StoredUpstreamLaneB
    lane_c: StoredUpstreamLaneC


def _row_sort_key(row: MaterializableRow) -> tuple[str, str, str, str, str]:
    return (
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
        row.harvest_business_date.isoformat(),
    )


def _upstream_snapshot_payload(upstream: UpstreamBundlePort) -> dict[str, object]:
    rows = upstream.lane_b.iter_materializable_rows()
    ordered_rows = sorted(rows, key=_row_sort_key)
    return {
        "cleaned_dataset_version_identity": upstream.lane_b.cleaned_dataset_version_identity,
        "cleaning_policy_version": upstream.lane_b.cleaning_policy_version,
        "correction_policy_version": upstream.lane_b.correction_policy_version,
        "exclusion_policy_version": upstream.lane_b.exclusion_policy_version,
        "materializable_rows": [
            {
                "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
                "cleaned_row_identity": row.cleaned_row_identity,
                "farm": row.farm,
                "harvest_business_date": row.harvest_business_date,
                "pit_visibility_identity": row.pit_visibility_identity,
                "revision_winner_identity": row.revision_winner_identity,
                "season": row.season,
                "source_row_identity": row.source_row_identity,
                "subfarm": row.subfarm,
                "variety": row.variety,
            }
            for row in ordered_rows
        ],
        "raw_policy_version": upstream.lane_a.raw_policy_version,
        "revision_winner_policy_version": upstream.lane_c.revision_winner_policy_version,
        "source_cohort_id": upstream.lane_a.source_cohort_id,
        "source_cohort_manifest_sha256": upstream.lane_a.source_cohort_manifest_sha256,
        "visibility_policy_version": upstream.lane_c.visibility_policy_version,
    }


def compute_upstream_snapshot_sha256(upstream: UpstreamBundlePort) -> str:
    from backend.app.rolling_backtest.canonical import sha256_payload

    return sha256_payload(_upstream_snapshot_payload(upstream))


def _stored_upstream_from_bundle(upstream: UpstreamBundlePort) -> StoredUpstreamBundle:
    rows = tuple(sorted(upstream.lane_b.iter_materializable_rows(), key=_row_sort_key))
    return StoredUpstreamBundle(
        lane_a=StoredUpstreamLaneA(
            source_cohort_id=upstream.lane_a.source_cohort_id,
            source_cohort_manifest_sha256=upstream.lane_a.source_cohort_manifest_sha256,
            raw_policy_version=upstream.lane_a.raw_policy_version,
        ),
        lane_b=StoredUpstreamLaneB(
            cleaned_dataset_version_identity=upstream.lane_b.cleaned_dataset_version_identity,
            cleaning_policy_version=upstream.lane_b.cleaning_policy_version,
            correction_policy_version=upstream.lane_b.correction_policy_version,
            exclusion_policy_version=upstream.lane_b.exclusion_policy_version,
            rows=rows,
        ),
        lane_c=StoredUpstreamLaneC(
            visibility_policy_version=upstream.lane_c.visibility_policy_version,
            revision_winner_policy_version=upstream.lane_c.revision_winner_policy_version,
        ),
    )


def load_upstream_bundle_from_storage(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> tuple[S2MaterializedDatasetModel, StoredUpstreamBundle, Any]:
    _BuildTimestamps, MaterializedDatasetBuildError, *_rest = _builder_imports()
    dataset = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if dataset is None:
        raise MaterializedDatasetBuildError(
            f"materialized dataset not found: {dataset_id}/{dataset_version}"
        )
    rows = session.scalars(
        select(S2MaterializedMaterializableRowModel)
        .where(S2MaterializedMaterializableRowModel.materialized_dataset_id == dataset.id)
        .order_by(S2MaterializedMaterializableRowModel.row_sort_key)
    ).all()
    materializable_rows = tuple(
        MaterializableRow(
            season=row.season,
            farm=row.farm,
            subfarm=row.subfarm,
            variety=row.variety,
            harvest_business_date=row.harvest_business_date,
            actual_harvest_quantity_kg=row.actual_harvest_quantity_kg,
            source_row_identity=row.source_row_identity,
            cleaned_row_identity=row.cleaned_row_identity,
            pit_visibility_identity=row.pit_visibility_identity,
            revision_winner_identity=row.revision_winner_identity,
        )
        for row in rows
    )
    bundle = StoredUpstreamBundle(
        lane_a=StoredUpstreamLaneA(
            source_cohort_id=dataset.source_cohort_id,
            source_cohort_manifest_sha256=dataset.source_cohort_manifest_sha256,
            raw_policy_version=dataset.raw_policy_version,
        ),
        lane_b=StoredUpstreamLaneB(
            cleaned_dataset_version_identity=dataset.cleaned_dataset_version_identity,
            cleaning_policy_version=dataset.cleaning_policy_version,
            correction_policy_version=dataset.correction_policy_version,
            exclusion_policy_version=dataset.exclusion_policy_version,
            rows=materializable_rows,
        ),
        lane_c=StoredUpstreamLaneC(
            visibility_policy_version=dataset.visibility_policy_version,
            revision_winner_policy_version=dataset.revision_winner_policy_version,
        ),
    )
    timestamps = _BuildTimestamps(
        started_at=dataset.build_started_at,
        completed_at=dataset.build_completed_at,
    )
    return dataset, bundle, timestamps


def _partition_manifest_from_model(
    dataset_row: S2MaterializedDatasetModel,
    partition_row: S2MaterializedPartitionModel,
) -> PartitionManifest:
    return PartitionManifest(
        dataset_id=dataset_row.dataset_id,
        dataset_version=dataset_row.dataset_version,
        partition_name=PartitionName(partition_row.partition_name),
        source_cohort_id=dataset_row.source_cohort_id,
        source_cohort_manifest_sha256=dataset_row.source_cohort_manifest_sha256,
        target_decision=partition_row.target_decision,
        canonical_grain=partition_row.canonical_grain,
        partition_date_field=PARTITION_DATE_FIELD,
        partition_start_date=partition_row.partition_start_date,
        partition_end_date=partition_row.partition_end_date,
        raw_policy_version=dataset_row.raw_policy_version,
        cleaning_policy_version=dataset_row.cleaning_policy_version,
        correction_policy_version=dataset_row.correction_policy_version,
        exclusion_policy_version=dataset_row.exclusion_policy_version,
        visibility_policy_version=dataset_row.visibility_policy_version,
        revision_winner_policy_version=dataset_row.revision_winner_policy_version,
        split_policy_version=partition_row.split_policy_version,
        builder_version=dataset_row.builder_version,
        dataset_schema_version=dataset_row.dataset_schema_version,
        manifest_schema_version=partition_row.manifest_schema_version,
        materialized_partition_schema_version=partition_row.materialized_partition_schema_version,
        row_count=partition_row.row_count,
        byte_count=partition_row.byte_count,
        content_sha256=partition_row.content_sha256,
        partition_identity_sha256=partition_row.partition_identity_sha256,
        manifest_sha256=partition_row.manifest_sha256,
        build_started_at=dataset_row.build_started_at,
        build_completed_at=dataset_row.build_completed_at,
        lineage_complete=partition_row.lineage_complete,
        quality_gate_status=QualityGateStatus(partition_row.quality_gate_status),
        rebuild_hash_replay_status=RebuildHashReplayStatus(
            partition_row.rebuild_hash_replay_status
        ),
    )


def load_materialized_dataset_result(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> MaterializedDatasetResult:
    _BuildTimestamps, MaterializedDatasetBuildError, *_rest = _builder_imports()
    dataset_row = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if dataset_row is None:
        raise MaterializedDatasetBuildError(
            f"materialized dataset not found: {dataset_id}/{dataset_version}"
        )
    partition_rows = session.scalars(
        select(S2MaterializedPartitionModel)
        .where(S2MaterializedPartitionModel.materialized_dataset_id == dataset_row.id)
        .order_by(S2MaterializedPartitionModel.partition_name)
    ).all()
    manifests = tuple(
        _partition_manifest_from_model(dataset_row, partition_row)
        for partition_row in partition_rows
    )
    return MaterializedDatasetResult(
        dataset_id=dataset_row.dataset_id,
        dataset_version=dataset_row.dataset_version,
        materialized_dataset_identity_sha256=dataset_row.materialized_dataset_identity_sha256,
        lineage_complete=dataset_row.lineage_complete,
        quality_gate_status=QualityGateStatus(dataset_row.quality_gate_status),
        partitions=manifests,
    )


def rebuild_materialized_dataset_from_storage(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> MaterializedDatasetResult:
    """Reload versioned upstream inputs from storage and rerun the D1 builder."""
    _BuildTimestamps, _MaterializedDatasetBuildError, build_materialized_dataset, *_rest = (
        _builder_imports()
    )
    _dataset_row, upstream, timestamps = load_upstream_bundle_from_storage(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    return build_materialized_dataset(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        upstream=upstream,
        timestamps=timestamps,
    )


def verify_storage_rebuild_parity(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> None:
    persisted = load_materialized_dataset_result(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    rebuilt = rebuild_materialized_dataset_from_storage(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    if (
        rebuilt.materialized_dataset_identity_sha256
        != persisted.materialized_dataset_identity_sha256
    ):
        raise MaterializedDatasetStorageRebuildError(
            "dataset identity mismatch after storage rebuild"
        )
    persisted_by_name = {manifest.partition_name: manifest for manifest in persisted.partitions}
    for rebuilt_manifest in rebuilt.partitions:
        stored_manifest = persisted_by_name[rebuilt_manifest.partition_name]
        if rebuilt_manifest.content_sha256 != stored_manifest.content_sha256:
            raise MaterializedDatasetStorageRebuildError(
                f"content_sha256 mismatch for {rebuilt_manifest.partition_name.value}"
            )
        if rebuilt_manifest.manifest_sha256 != stored_manifest.manifest_sha256:
            raise MaterializedDatasetStorageRebuildError(
                f"manifest_sha256 mismatch for {rebuilt_manifest.partition_name.value}"
            )
        if (
            recompute_manifest_sha256_from_published(stored_manifest)
            != stored_manifest.manifest_sha256
        ):
            raise MaterializedDatasetStorageRebuildError(
                f"stored manifest hash mismatch for {rebuilt_manifest.partition_name.value}"
            )


def persist_materialized_dataset(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
    upstream: UpstreamBundlePort,
    timestamps: Any | None = None,
) -> MaterializedDatasetResult:
    (
        BuildTimestamps,
        MaterializedDatasetBuildError,
        build_materialized_dataset,
        materialize_partition_bytes,
        FROZEN_PARTITIONS,
    ) = _builder_imports()
    built = build_materialized_dataset(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        upstream=upstream,
        timestamps=timestamps,
    )
    snapshot_sha256 = compute_upstream_snapshot_sha256(upstream)
    existing = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if existing is not None:
        if (
            existing.materialized_dataset_identity_sha256
            == built.materialized_dataset_identity_sha256
        ):
            return load_materialized_dataset_result(
                session,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            )
        raise MaterializedDatasetConflictError(
            "dataset_id/version conflict: identity hash differs from persisted facts"
        )

    started = (
        timestamps.started_at if timestamps is not None else built.partitions[0].build_started_at
    )
    completed = (
        timestamps.completed_at
        if timestamps is not None
        else built.partitions[0].build_completed_at
    )
    stored_upstream = _stored_upstream_from_bundle(upstream)
    dataset_row = S2MaterializedDatasetModel(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=built.materialized_dataset_identity_sha256,
        source_cohort_id=stored_upstream.lane_a.source_cohort_id,
        source_cohort_manifest_sha256=stored_upstream.lane_a.source_cohort_manifest_sha256,
        raw_policy_version=stored_upstream.lane_a.raw_policy_version,
        cleaning_policy_version=stored_upstream.lane_b.cleaning_policy_version,
        correction_policy_version=stored_upstream.lane_b.correction_policy_version,
        exclusion_policy_version=stored_upstream.lane_b.exclusion_policy_version,
        visibility_policy_version=stored_upstream.lane_c.visibility_policy_version,
        revision_winner_policy_version=stored_upstream.lane_c.revision_winner_policy_version,
        cleaned_dataset_version_identity=stored_upstream.lane_b.cleaned_dataset_version_identity,
        builder_version=BUILDER_VERSION,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        lineage_complete=built.lineage_complete,
        quality_gate_status=built.quality_gate_status.value,
        build_started_at=started,
        build_completed_at=completed,
        upstream_snapshot_sha256=snapshot_sha256,
    )
    session.add(dataset_row)
    session.flush()

    for sort_key, row in enumerate(stored_upstream.lane_b.rows):
        session.add(
            S2MaterializedMaterializableRowModel(
                materialized_dataset_id=dataset_row.id,
                row_sort_key=sort_key,
                season=row.season,
                farm=row.farm,
                subfarm=row.subfarm,
                variety=row.variety,
                harvest_business_date=row.harvest_business_date,
                actual_harvest_quantity_kg=row.actual_harvest_quantity_kg,
                source_row_identity=row.source_row_identity,
                cleaned_row_identity=row.cleaned_row_identity,
                pit_visibility_identity=row.pit_visibility_identity,
                revision_winner_identity=row.revision_winner_identity,
            )
        )

    manifest_by_name = {manifest.partition_name: manifest for manifest in built.partitions}
    for partition_spec in FROZEN_PARTITIONS:
        manifest = manifest_by_name[partition_spec.name]
        partition_bytes = materialize_partition_bytes(
            partition=partition_spec,
            upstream_rows=stored_upstream.lane_b.rows,
        )
        if partition_bytes.content_sha256 != manifest.content_sha256:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "content_sha256 differs from built manifest"
            )
        if len(partition_bytes.content_bytes) != manifest.byte_count:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "byte_count differs from built manifest"
            )
        if partition_bytes.row_count != manifest.row_count:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "row_count differs from built manifest"
            )
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset_row.id,
                partition_name=manifest.partition_name.value,
                partition_start_date=manifest.partition_start_date,
                partition_end_date=manifest.partition_end_date,
                partition_date_field=manifest.partition_date_field,
                target_decision=manifest.target_decision,
                canonical_grain=manifest.canonical_grain,
                split_policy_version=manifest.split_policy_version,
                manifest_schema_version=manifest.manifest_schema_version,
                materialized_partition_schema_version=manifest.materialized_partition_schema_version,
                row_count=manifest.row_count,
                byte_count=manifest.byte_count,
                content_sha256=manifest.content_sha256,
                partition_identity_sha256=manifest.partition_identity_sha256,
                manifest_sha256=manifest.manifest_sha256,
                content_bytes=partition_bytes.content_bytes,
                lineage_complete=manifest.lineage_complete,
                quality_gate_status=manifest.quality_gate_status.value,
                rebuild_hash_replay_status=manifest.rebuild_hash_replay_status.value,
            )
        )

    session.flush()
    return built
