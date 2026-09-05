"""Single-event-loop live DB acquisition for TRAIN/VALIDATION pairing materialization.

All production SOURCE-002 attestation, partition-byte obtain, replay-identity
read, and PIT-visible provider acquisition execute inside one held AsyncSession
and one outer asyncio.run bridge.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.app.forecast_quality.train_val_pairing_materialization import (
    TrainValidationPairingMaterializationBlocker,
    TrainValidationPairingMaterializationDeps,
    TrainValidationPairingMaterializationResult,
    _reviewed_forecast_entries,
    derive_materialization_grain_union,
    load_official_partition_rows_from_content_bytes,
    materialize_train_validation_pairing_inputs,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    _attest_from_session,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
    _obtain_from_session,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync import (  # noqa: E501
    resolve_live_async_session_maker,
)
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    compute_content_identity_sha256,
    project_incumbent_forecast_artifact_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    _obtain_from_async_session,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    reviewed_grain_identity_set_identity_sha256,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_obtain import (
    _read_origin_from_held_session,
)


def _read_replay_identity_from_held_session(
    sync_session: Session,
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    return _read_origin_from_held_session(sync_session)


async def _materialize_train_validation_pairing_inputs_live_async() -> (
    TrainValidationPairingMaterializationResult
):
    live_async_session_maker = resolve_live_async_session_maker()
    if live_async_session_maker is None:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=(
                TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
            ),
        )

    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=(
                TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
            ),
        )
    try:
        if session is None:
            return TrainValidationPairingMaterializationResult(
                completed=False,
                blocker=(
                    TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
                ),
            )
        return await _materialize_with_held_async_session(session)
    finally:
        await session_cm.__aexit__(None, None, None)


async def _materialize_with_held_async_session(
    session: AsyncSession,
) -> TrainValidationPairingMaterializationResult:
    attestation = await session.run_sync(_attest_from_session)
    if not attestation.attested:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=(
                TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
            ),
        )

    obtain = await session.run_sync(_obtain_from_session)
    if (
        not obtain.obtained
        or obtain.train_content_bytes is None
        or obtain.validation_content_bytes is None
    ):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.OFFICIAL_PARTITION_BYTES_NOT_OBTAINED,
        )

    official = load_official_partition_rows_from_content_bytes(
        train_content_bytes=obtain.train_content_bytes,
        validation_content_bytes=obtain.validation_content_bytes,
    )
    if isinstance(official, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(completed=False, blocker=official)

    origin_entries = await session.run_sync(_read_replay_identity_from_held_session)
    if not origin_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS,
            official_partitions=official,
            forecast_row_count=0,
        )

    replay_entries = project_incumbent_forecast_artifact_entries(origin_entries)
    reviewed_entries = _reviewed_forecast_entries(replay_entries)
    if not reviewed_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.REVIEWED_FORECAST_GRAIN_MISMATCH,
            official_partitions=official,
            forecast_row_count=len(replay_entries),
        )

    forecast_content_identity = compute_content_identity_sha256(rows=reviewed_entries)
    forecast_cutoff_authority = reviewed_grain_identity_set_identity_sha256()

    materialization_grains = derive_materialization_grain_union(official)
    if isinstance(materialization_grains, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=materialization_grains,
            official_partitions=official,
            forecast_row_count=len(reviewed_entries),
        )

    curve_obtain = await _obtain_from_async_session(
        session,
        materialization_grains=materialization_grains,
    )
    if not curve_obtain.obtained or curve_obtain.provider is None:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER,
            official_partitions=official,
            forecast_row_count=len(reviewed_entries),
        )

    deps = TrainValidationPairingMaterializationDeps(
        official_partitions=official,
        forecast_replay_entries=replay_entries,
        forecast_provider=curve_obtain.provider,
        forecast_cutoff_authority_identity=forecast_cutoff_authority,
        forecast_content_identity_sha256=forecast_content_identity,
    )
    return materialize_train_validation_pairing_inputs(deps)
