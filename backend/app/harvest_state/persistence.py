from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    is_sha256_hex,
    make_result_hash,
    sha256_hex,
)
from backend.app.harvest_state.enums import (
    RESOLVED_PARAMETER_SNAPSHOT_SCHEMA_VERSION,
    RESULT_HASH_SCHEMA_VERSION,
    SOURCE_REF_SCHEMA_VERSION,
    STABLE_COHORT_KEY_SCHEMA_VERSION,
)
from backend.app.harvest_state.schemas import (
    CohortTransitionRow,
    DailyMemberStateRow,
    DailyPoolStateRow,
    FutureArrivalScheduleRow,
    SourceRefCatalogEntry,
    Task9ABlockedOutput,
    Task9ACompletedOutput,
)
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.repositories.harvest_state import (
    get_harvest_state_run,
    get_harvest_state_run_by_result_hash,
    list_harvest_state_cohort_transition_rows,
    list_harvest_state_daily_member_rows,
    list_harvest_state_daily_pool_rows,
    list_harvest_state_future_arrival_rows,
)


class HarvestStatePersistenceError(RuntimeError):
    pass


class HarvestStateHashConflictError(HarvestStatePersistenceError):
    pass


class HarvestStateResultHashMismatchError(HarvestStatePersistenceError):
    pass


class HarvestStatePersistenceIntegrityError(HarvestStatePersistenceError):
    pass


@dataclass(slots=True)
class _Task8Identity:
    maturity_model_run_id: int | None
    maturity_model_version: str | None
    maturity_model_config_hash: str | None
    maturity_model_source_signature: str | None
    maturity_model_artifact_id: int | None
    maturity_model_artifact_hash: str | None
    maturity_forecast_run_id: int | None
    maturity_forecast_source_signature: str | None
    maturity_forecast_as_of_date: date | None


def _canonical_output_payload(
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> dict[str, Any]:
    return cast(dict[str, Any], canonical_json_value(output.model_dump(mode="python")))


def _canonical_output_storage_payload(
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> dict[str, Any]:
    return cast(dict[str, Any], canonical_json_value(output.model_dump(mode="json")))


def _canonical_output_json(output: Task9ACompletedOutput | Task9ABlockedOutput) -> str:
    return canonical_json_dumps(_canonical_output_payload(output))


def _canonical_output_storage_json(output: Task9ACompletedOutput | Task9ABlockedOutput) -> str:
    return canonical_json_dumps(_canonical_output_storage_payload(output))


def _subfarm_identity_key(subfarm_id: int | None) -> str:
    return "NONE" if subfarm_id is None else str(subfarm_id)


def _extract_task8_identity(
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> _Task8Identity:
    task8_inputs = cast(
        list[dict[str, Any]],
        output.input_snapshot.get("task8_daily_predictions", []),
    )
    if not task8_inputs:
        return _Task8Identity(None, None, None, None, None, None, None, None, None)

    catalog_by_hash = {
        entry.source_ref_hash: entry.source_ref_payload for entry in output.source_ref_catalog
    }
    first = task8_inputs[0]
    source_ref_hash = cast(str | None, first.get("source_ref_hash"))
    source_ref = catalog_by_hash.get(source_ref_hash or "")
    verification = cast(dict[str, Any], first.get("verification_snapshot", {}))
    return _Task8Identity(
        maturity_model_run_id=cast(int | None, verification.get("maturity_model_run_id")),
        maturity_model_version=cast(
            str | None,
            verification.get("maturity_model_version")
            or (source_ref or {}).get("maturity_model_version"),
        ),
        maturity_model_config_hash=cast(
            str | None,
            verification.get("maturity_model_config_hash")
            or (source_ref or {}).get("maturity_model_config_hash"),
        ),
        maturity_model_source_signature=cast(
            str | None,
            verification.get("maturity_model_source_signature")
            or (source_ref or {}).get("maturity_model_source_signature"),
        ),
        maturity_model_artifact_id=cast(
            int | None,
            verification.get("maturity_model_artifact_id")
            or (source_ref or {}).get("maturity_model_artifact_id"),
        ),
        maturity_model_artifact_hash=cast(
            str | None,
            verification.get("maturity_model_artifact_hash")
            or (source_ref or {}).get("maturity_model_artifact_hash"),
        ),
        maturity_forecast_run_id=cast(
            int | None,
            verification.get("maturity_forecast_run_id")
            or (source_ref or {}).get("maturity_forecast_run_id"),
        ),
        maturity_forecast_source_signature=cast(
            str | None,
            verification.get("maturity_forecast_source_signature")
            or (source_ref or {}).get("maturity_forecast_source_signature"),
        ),
        maturity_forecast_as_of_date=cast(
            date | None,
            verification.get("maturity_forecast_as_of_date")
            or (source_ref or {}).get("maturity_forecast_as_of_date"),
        ),
    )


def _validate_output_contract(output: Task9ACompletedOutput | Task9ABlockedOutput) -> None:
    if not is_sha256_hex(output.config_hash):
        raise HarvestStatePersistenceError("Task 9A output config_hash is not canonical SHA-256")
    if not is_sha256_hex(output.result_hash):
        raise HarvestStatePersistenceError("Task 9A output result_hash is not canonical SHA-256")

    if output.status == "completed":
        if output.blockers:
            raise HarvestStatePersistenceError("completed Task 9A output cannot contain blockers")
        if output.resolved_parameter_snapshot is None:
            raise HarvestStatePersistenceError(
                "completed Task 9A output requires resolved_parameter_snapshot"
            )
        if output.mass_balance_result is None or output.continuity_result is None:
            raise HarvestStatePersistenceError(
                "completed Task 9A output requires mass_balance_result and continuity_result"
            )
        if not output.daily_pool_state_rows:
            raise HarvestStatePersistenceError("completed Task 9A output requires pool rows")
        if not output.daily_member_state_rows:
            raise HarvestStatePersistenceError("completed Task 9A output requires member rows")
        if not output.cohort_transition_rows:
            raise HarvestStatePersistenceError(
                "completed Task 9A output requires cohort transition rows"
            )
        return

    if output.daily_pool_state_rows:
        raise HarvestStatePersistenceError("blocked Task 9A output must not contain pool rows")
    if output.daily_member_state_rows:
        raise HarvestStatePersistenceError("blocked Task 9A output must not contain member rows")
    if output.cohort_transition_rows:
        raise HarvestStatePersistenceError("blocked Task 9A output must not contain cohort rows")
    if output.future_arrival_schedule:
        raise HarvestStatePersistenceError(
            "blocked Task 9A output must not contain future arrival rows"
        )
    if not output.blockers:
        raise HarvestStatePersistenceError("blocked Task 9A output requires blockers")


def _validate_output_result_hash(output: Task9ACompletedOutput | Task9ABlockedOutput) -> None:
    computed = make_result_hash(output.model_dump(mode="python"))
    if computed != output.result_hash:
        raise HarvestStateResultHashMismatchError(
            "Task 9A output result_hash does not match the canonical Task 9A payload"
        )


def _run_versions(
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> tuple[str, str, str, str]:
    resolved = output.resolved_parameter_snapshot
    if resolved is None:
        return (
            RESULT_HASH_SCHEMA_VERSION,
            RESOLVED_PARAMETER_SNAPSHOT_SCHEMA_VERSION,
            SOURCE_REF_SCHEMA_VERSION,
            STABLE_COHORT_KEY_SCHEMA_VERSION,
        )
    return (
        resolved.run_parameters.result_hash_schema_version,
        resolved.schema_version,
        resolved.run_parameters.source_ref_schema_version,
        resolved.run_parameters.stable_cohort_key_schema_version,
    )


def _catalog_payload_by_hash(
    catalog: Iterable[SourceRefCatalogEntry],
) -> dict[str, dict[str, Any]]:
    return {entry.source_ref_hash: entry.source_ref_payload for entry in catalog}


def _snapshot_date(snapshot: dict[str, Any], key: str) -> date:
    raw = snapshot[key]
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return date.fromisoformat(raw)
    raise HarvestStatePersistenceError(f"input_snapshot[{key!r}] is not a valid date")


def _expected_row_counts(
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> tuple[int, int, int, int]:
    return (
        len(output.daily_pool_state_rows),
        len(output.daily_member_state_rows),
        len(output.cohort_transition_rows),
        len(output.future_arrival_schedule),
    )


async def save_harvest_state_output(
    session: AsyncSession,
    *,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> HarvestStateRun:
    _validate_output_contract(output)
    _validate_output_result_hash(output)
    canonical_json = _canonical_output_json(output)
    canonical_output = _canonical_output_storage_payload(output)
    canonical_payload_hash = sha256_hex(canonical_output)
    pool_row_count, member_row_count, cohort_row_count, future_arrival_row_count = (
        _expected_row_counts(output)
    )

    existing = await get_harvest_state_run_by_result_hash(session, result_hash=output.result_hash)
    if existing is not None:
        if (
            existing.canonical_payload_hash != canonical_payload_hash
            or existing.canonical_output != canonical_output
        ):
            raise HarvestStateHashConflictError(
                "result_hash already exists for a different canonical Task 9A output"
            )
        return existing

    (
        result_hash_schema_version,
        resolved_schema_version,
        source_ref_schema_version,
        stable_key_version,
    ) = _run_versions(output)
    identity = _extract_task8_identity(output)
    source_ref_catalog = cast(
        list[dict[str, Any]],
        canonical_json_value(
            [entry.model_dump(mode="python") for entry in output.source_ref_catalog]
        ),
    )
    catalog_payloads = _catalog_payload_by_hash(output.source_ref_catalog)
    pool_membership_by_key = {
        (
            row.state_date,
            row.capacity_pool_id,
            row.forecast_quantile.value,
        ): row.capacity_pool_membership_hash
        for row in output.daily_pool_state_rows
    }

    run = HarvestStateRun(
        status=output.status,
        output_schema_version=output.output_schema_version,
        result_hash_schema_version=result_hash_schema_version,
        resolved_parameter_snapshot_schema_version=resolved_schema_version,
        source_ref_schema_version=source_ref_schema_version,
        stable_cohort_key_schema_version=stable_key_version,
        input_snapshot=cast(dict[str, Any], canonical_json_value(output.input_snapshot)),
        resolved_parameter_snapshot=cast(
            dict[str, Any] | None,
            canonical_json_value(
                output.resolved_parameter_snapshot.model_dump(mode="python")
                if output.resolved_parameter_snapshot is not None
                else None
            ),
        ),
        source_ref_catalog=source_ref_catalog,
        warnings=cast(list[str], canonical_json_value(output.warnings)),
        blockers=cast(list[str], canonical_json_value(output.blockers)),
        mass_balance_result=cast(
            dict[str, Any] | None,
            canonical_json_value(getattr(output, "mass_balance_result", None)),
        ),
        continuity_result=cast(
            dict[str, Any] | None,
            canonical_json_value(getattr(output, "continuity_result", None)),
        ),
        canonical_output=canonical_output,
        config_hash=output.config_hash,
        result_hash=output.result_hash,
        canonical_payload_hash=canonical_payload_hash,
        forecast_start_date=_snapshot_date(output.input_snapshot, "forecast_start_date"),
        forecast_end_date=_snapshot_date(output.input_snapshot, "forecast_end_date"),
        as_of_date=_snapshot_date(output.input_snapshot, "as_of_date"),
        destination_factory_id=cast(int, output.input_snapshot["destination_factory_id"]),
        pool_row_count=pool_row_count,
        member_row_count=member_row_count,
        cohort_row_count=cohort_row_count,
        future_arrival_row_count=future_arrival_row_count,
        maturity_model_run_id=identity.maturity_model_run_id,
        maturity_model_version=identity.maturity_model_version,
        maturity_model_config_hash=identity.maturity_model_config_hash,
        maturity_model_source_signature=identity.maturity_model_source_signature,
        maturity_model_artifact_id=identity.maturity_model_artifact_id,
        maturity_model_artifact_hash=identity.maturity_model_artifact_hash,
        maturity_forecast_run_id=identity.maturity_forecast_run_id,
        maturity_forecast_source_signature=identity.maturity_forecast_source_signature,
    )

    try:
        session.add(run)
        await session.flush()

        if output.status == "completed":
            for pool_row in output.daily_pool_state_rows:
                session.add(
                    HarvestStateDailyPoolRowModel(
                        harvest_state_run_id=run.id,
                        **pool_row.model_dump(mode="python"),
                    )
                )
            for member_row in output.daily_member_state_rows:
                session.add(
                    HarvestStateDailyMemberRowModel(
                        harvest_state_run_id=run.id,
                        subfarm_identity_key=_subfarm_identity_key(member_row.subfarm_id),
                        **member_row.model_dump(mode="python"),
                    )
                )
            for cohort_row in output.cohort_transition_rows:
                source_ref_payload = catalog_payloads.get(cohort_row.source_ref_hash)
                if source_ref_payload is None:
                    raise HarvestStatePersistenceError(
                        "source_ref_hash "
                        f"{cohort_row.source_ref_hash} is missing from source_ref_catalog"
                    )
                session.add(
                    HarvestStateCohortTransitionRowModel(
                        harvest_state_run_id=run.id,
                        source_ref=cast(dict[str, Any], canonical_json_value(source_ref_payload)),
                        capacity_pool_membership_hash=pool_membership_by_key[
                            (
                                cohort_row.state_date,
                                cohort_row.capacity_pool_id,
                                cohort_row.forecast_quantile.value,
                            )
                        ],
                        **cohort_row.model_dump(mode="python"),
                    )
                )
            lag_days = (
                output.resolved_parameter_snapshot.run_parameters.harvest_to_arrival_lag_days
                if output.resolved_parameter_snapshot is not None
                else 0
            )
            farm_timezone = (
                output.resolved_parameter_snapshot.run_parameters.farm_timezone
                if output.resolved_parameter_snapshot is not None
                else cast(str, output.input_snapshot["farm_timezone"])
            )
            destination_timezone = (
                output.resolved_parameter_snapshot.run_parameters.destination_factory_timezone
                if output.resolved_parameter_snapshot is not None
                else cast(str, output.input_snapshot["destination_factory_timezone"])
            )
            for future_row in output.future_arrival_schedule:
                session.add(
                    HarvestStateFutureArrivalRowModel(
                        harvest_state_run_id=run.id,
                        subfarm_identity_key=_subfarm_identity_key(future_row.subfarm_id),
                        harvest_to_arrival_lag_days=lag_days,
                        farm_timezone=farm_timezone,
                        destination_factory_timezone=destination_timezone,
                        **future_row.model_dump(mode="python"),
                    )
                )
        await session.commit()
        await session.refresh(run)
        return run
    except IntegrityError:
        await session.rollback()
        existing = await get_harvest_state_run_by_result_hash(
            session,
            result_hash=output.result_hash,
        )
        if existing is None:
            raise
        loaded = await load_harvest_state_output_by_id(session, run_id=existing.id)
        if loaded is None:
            raise HarvestStatePersistenceError(
                "conflicting run exists but could not be loaded"
            ) from None
        if (
            existing.canonical_payload_hash != canonical_payload_hash
            or existing.canonical_output != canonical_output
            or _canonical_output_json(loaded) != canonical_json
        ):
            raise HarvestStateHashConflictError(
                "database contains the same result_hash for a different canonical payload"
            ) from None
        return existing
    except Exception:
        await session.rollback()
        raise


def _pool_row_sort_key(row: DailyPoolStateRow) -> tuple[date, str, int]:
    order = {"P50": 0, "P80": 1, "P90": 2}
    return (row.state_date, row.capacity_pool_id, order[row.forecast_quantile.value])


def _member_row_sort_key(row: DailyMemberStateRow) -> tuple[date, str, int, int, int, int]:
    order = {"P50": 0, "P80": 1, "P90": 2}
    subfarm = -1 if row.subfarm_id is None else row.subfarm_id
    return (
        row.state_date,
        row.capacity_pool_id,
        row.farm_id,
        subfarm,
        row.variety_id,
        order[row.forecast_quantile.value],
    )


def _cohort_row_sort_key(row: CohortTransitionRow) -> tuple[date, str, date, int, int, str]:
    subfarm = -1 if row.subfarm_id is None else row.subfarm_id
    return (
        row.state_date,
        row.capacity_pool_id,
        row.cohort_date,
        row.variety_id,
        subfarm,
        row.stable_cohort_key,
    )


def _future_arrival_sort_key(row: FutureArrivalScheduleRow) -> tuple[int, date, int, int, str, int]:
    order = {"P50": 0, "P80": 1, "P90": 2}
    subfarm = -1 if row.subfarm_id is None else row.subfarm_id
    return (
        row.destination_factory_id,
        row.arrival_local_date,
        row.variety_id,
        order[row.forecast_quantile.value],
        row.capacity_pool_id,
        subfarm,
    )


def _row_payload(instance: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(instance, field) for field in fields}


async def _actual_row_counts(
    session: AsyncSession,
    *,
    run_id: int,
) -> tuple[int, int, int, int]:
    pool_count = int(
        await session.scalar(
            select(func.count())
            .select_from(HarvestStateDailyPoolRowModel)
            .where(HarvestStateDailyPoolRowModel.harvest_state_run_id == run_id)
        )
        or 0
    )
    member_count = int(
        await session.scalar(
            select(func.count())
            .select_from(HarvestStateDailyMemberRowModel)
            .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == run_id)
        )
        or 0
    )
    cohort_count = int(
        await session.scalar(
            select(func.count())
            .select_from(HarvestStateCohortTransitionRowModel)
            .where(HarvestStateCohortTransitionRowModel.harvest_state_run_id == run_id)
        )
        or 0
    )
    future_count = int(
        await session.scalar(
            select(func.count())
            .select_from(HarvestStateFutureArrivalRowModel)
            .where(HarvestStateFutureArrivalRowModel.harvest_state_run_id == run_id)
        )
        or 0
    )
    return (pool_count, member_count, cohort_count, future_count)


def _validate_canonical_payload_hash(run: HarvestStateRun) -> None:
    if not is_sha256_hex(run.canonical_payload_hash):
        raise HarvestStatePersistenceIntegrityError(
            "harvest-state canonical_payload_hash is not canonical SHA-256"
        )
    computed_hash = sha256_hex(run.canonical_output)
    if computed_hash != run.canonical_payload_hash:
        raise HarvestStatePersistenceIntegrityError(
            "harvest-state canonical_payload_hash does not match canonical_output"
        )


def _expected_counts_from_run(run: HarvestStateRun) -> tuple[int, int, int, int]:
    return (
        run.pool_row_count,
        run.member_row_count,
        run.cohort_row_count,
        run.future_arrival_row_count,
    )


async def load_harvest_state_output_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> Task9ACompletedOutput | Task9ABlockedOutput | None:
    run = await get_harvest_state_run(session, run_id=run_id)
    if run is None:
        return None

    _validate_canonical_payload_hash(run)
    expected_counts = _expected_counts_from_run(run)
    actual_counts = await _actual_row_counts(session, run_id=run.id)
    if expected_counts != actual_counts:
        raise HarvestStatePersistenceIntegrityError(
            "harvest-state child row counts do not match expected persisted counts"
        )

    if run.status == "completed":
        try:
            payload = Task9ACompletedOutput.model_validate(run.canonical_output)
        except ValidationError as exc:
            raise HarvestStatePersistenceIntegrityError(
                "harvest-state canonical_output is not a valid completed payload"
            ) from exc
        canonical_counts = _expected_row_counts(payload)
        if canonical_counts != expected_counts:
            raise HarvestStatePersistenceIntegrityError(
                "harvest-state canonical_output row counts do not match persisted counts"
            )
        if payload.config_hash != run.config_hash or payload.result_hash != run.result_hash:
            raise HarvestStatePersistenceIntegrityError(
                "harvest-state canonical_output does not match persisted run hashes"
            )
        if payload.blockers:
            raise HarvestStatePersistenceIntegrityError(
                "completed harvest-state canonical_output cannot contain blockers"
            )
        if payload.resolved_parameter_snapshot is None:
            raise HarvestStatePersistenceIntegrityError(
                "completed harvest-state canonical_output requires resolved parameters"
            )
        if run.pool_row_count <= 0 or run.member_row_count <= 0 or run.cohort_row_count <= 0:
            raise HarvestStatePersistenceIntegrityError(
                "completed harvest-state run must persist non-zero pool/member/cohort counts"
            )

        pool_fields = tuple(DailyPoolStateRow.model_fields.keys())
        member_fields = tuple(DailyMemberStateRow.model_fields.keys())
        cohort_fields = tuple(CohortTransitionRow.model_fields.keys())
        future_fields = tuple(FutureArrivalScheduleRow.model_fields.keys())
        pool_rows = [
            DailyPoolStateRow.model_validate(_row_payload(row, pool_fields))
            for row in await list_harvest_state_daily_pool_rows(session, run_id=run.id)
        ]
        member_rows = [
            DailyMemberStateRow.model_validate(_row_payload(row, member_fields))
            for row in await list_harvest_state_daily_member_rows(session, run_id=run.id)
        ]
        cohort_rows = [
            CohortTransitionRow.model_validate(_row_payload(row, cohort_fields))
            for row in await list_harvest_state_cohort_transition_rows(session, run_id=run.id)
        ]
        future_arrivals = [
            FutureArrivalScheduleRow.model_validate(_row_payload(row, future_fields))
            for row in await list_harvest_state_future_arrival_rows(session, run_id=run.id)
        ]

        actual_pool = [
            item.model_dump(mode="python") for item in sorted(pool_rows, key=_pool_row_sort_key)
        ]
        actual_member = [
            item.model_dump(mode="python") for item in sorted(member_rows, key=_member_row_sort_key)
        ]
        actual_cohort = [
            item.model_dump(mode="python") for item in sorted(cohort_rows, key=_cohort_row_sort_key)
        ]
        actual_future = [
            item.model_dump(mode="python")
            for item in sorted(future_arrivals, key=_future_arrival_sort_key)
        ]

        expected_pool = [
            item.model_dump(mode="python")
            for item in sorted(payload.daily_pool_state_rows, key=_pool_row_sort_key)
        ]
        expected_member = [
            item.model_dump(mode="python")
            for item in sorted(payload.daily_member_state_rows, key=_member_row_sort_key)
        ]
        expected_cohort = [
            item.model_dump(mode="python")
            for item in sorted(payload.cohort_transition_rows, key=_cohort_row_sort_key)
        ]
        expected_future = [
            item.model_dump(mode="python")
            for item in sorted(payload.future_arrival_schedule, key=_future_arrival_sort_key)
        ]

        if actual_pool != expected_pool:
            raise HarvestStatePersistenceIntegrityError(
                "normalized daily pool rows do not match canonical_output"
            )
        if actual_member != expected_member:
            raise HarvestStatePersistenceIntegrityError(
                "normalized daily member rows do not match canonical_output"
            )
        if actual_cohort != expected_cohort:
            raise HarvestStatePersistenceIntegrityError(
                "normalized cohort transition rows do not match canonical_output"
            )
        if actual_future != expected_future:
            raise HarvestStatePersistenceIntegrityError(
                "normalized future arrival rows do not match canonical_output"
            )
        return payload

    if actual_counts != (0, 0, 0, 0):
        raise HarvestStatePersistenceIntegrityError(
            "blocked harvest-state run must not persist state child rows"
        )

    try:
        blocked_payload = Task9ABlockedOutput.model_validate(run.canonical_output)
    except ValidationError as exc:
        raise HarvestStatePersistenceIntegrityError(
            "harvest-state canonical_output is not a valid blocked payload"
        ) from exc
    canonical_counts = _expected_row_counts(blocked_payload)
    if canonical_counts != (0, 0, 0, 0):
        raise HarvestStatePersistenceIntegrityError(
            "blocked harvest-state canonical_output must not contain state rows"
        )
    if (
        blocked_payload.config_hash != run.config_hash
        or blocked_payload.result_hash != run.result_hash
    ):
        raise HarvestStatePersistenceIntegrityError(
            "blocked harvest-state canonical_output does not match persisted run hashes"
        )
    if not blocked_payload.blockers:
        raise HarvestStatePersistenceIntegrityError(
            "blocked harvest-state canonical_output requires blockers"
        )
    return blocked_payload


async def load_harvest_state_output_by_result_hash(
    session: AsyncSession,
    *,
    result_hash: str,
) -> Task9ACompletedOutput | Task9ABlockedOutput | None:
    run = await get_harvest_state_run_by_result_hash(session, result_hash=result_hash)
    if run is None:
        return None
    return await load_harvest_state_output_by_id(session, run_id=run.id)
