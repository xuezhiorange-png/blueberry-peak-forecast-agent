from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException
from typing import Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.repository import (
    CoreForecastRepository,
    SqlAlchemyCoreForecastRepository,
    Task8AuthoritySource,
    Task9AuthoritySource,
    Task9MemberSource,
)
from backend.app.core_forecast.schemas import (
    OUTPUT_QUANTUM,
    QUANTILE_RANK,
    QUANTILES,
    CompleteDailyMarketableCurveRequest,
    CompleteDailyMarketableCurveResult,
    CompleteDailyMarketableCurveRow,
    CoreForecastBlocker,
    CoreForecastBlockerCode,
    MarketableRetentionPolicyEntry,
    MarketableRetentionPolicySnapshot,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

_SCHEMA_VERSION = "v0.1-complete-daily-marketable-curve-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class _CompositionDataError(ValueError):
    def __init__(self, code: CoreForecastBlockerCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _PolicyResolution:
    status: Literal["OK", "MISSING", "CONFLICT", "INVALID"]
    index: dict[tuple[int, str, int, int, int], MarketableRetentionPolicyEntry] | None
    message: str


def _block(code: CoreForecastBlockerCode, message: str) -> CompleteDailyMarketableCurveResult:
    return CompleteDailyMarketableCurveResult(
        status="BLOCKED",
        rows=(),
        curve_hash=None,
        blockers=(CoreForecastBlocker(code=code, message=message),),
    )


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _decimal(value: object, code: CoreForecastBlockerCode) -> Decimal:
    if isinstance(value, float) or isinstance(value, bool):
        raise _CompositionDataError(code, "native float/bool is not a supported authority quantity")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, ValueError, TypeError, OverflowError) as exc:
        raise _CompositionDataError(code, "authority quantity is not Decimal-compatible") from exc
    if not parsed.is_finite() or parsed < 0 or (parsed.is_signed() and parsed == 0):
        raise _CompositionDataError(code, "authority quantity must be finite and non-negative")
    return parsed


def _fixed(value: object, code: CoreForecastBlockerCode) -> str:
    parsed = _decimal(value, code)
    try:
        quantized = parsed.quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_EVEN)
    except (DecimalException, OverflowError) as exc:
        raise _CompositionDataError(code, "authority quantity cannot be quantized") from exc
    return format(quantized, "f")


def _policy_decimal(value: object) -> Decimal:
    if not isinstance(value, str) or not value or value.startswith("-"):
        raise _CompositionDataError(
            "MARKETABLE_RETENTION_POLICY_INVALID",
            "retention policy rate is not a canonical non-negative decimal string",
        )
    try:
        parsed = Decimal(value)
    except (DecimalException, ValueError, TypeError, OverflowError) as exc:
        raise _CompositionDataError(
            "MARKETABLE_RETENTION_POLICY_INVALID",
            "retention policy rate is not Decimal-compatible",
        ) from exc
    if (
        not parsed.is_finite()
        or parsed < 0
        or parsed > 1
        or (parsed.is_signed() and parsed == 0)
        or format(parsed, "f") != value
    ):
        raise _CompositionDataError(
            "MARKETABLE_RETENTION_POLICY_INVALID",
            "retention policy rate is outside the frozen finite [0, 1] contract",
        )
    return parsed


def _dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def _scope_key(row: Task9MemberSource) -> tuple[int, int, int]:
    if row.subfarm_id is None:
        raise ValueError("subfarm_id is required for the V0.1 projection")
    return row.farm_id, row.subfarm_id, row.variety_id


def _business_key(row: Task9MemberSource) -> tuple[date, int, int, int, str]:
    farm_id, subfarm_id, variety_id = _scope_key(row)
    return row.state_date, farm_id, subfarm_id, variety_id, row.forecast_quantile


def _policy_key(
    season_id: int,
    season_code: str,
    scope: tuple[int, int, int],
) -> tuple[int, str, int, int, int]:
    farm_id, subfarm_id, variety_id = scope
    return season_id, season_code, farm_id, subfarm_id, variety_id


def _policy_index(
    request: CompleteDailyMarketableCurveRequest,
    snapshot: MarketableRetentionPolicySnapshot,
) -> _PolicyResolution:
    if not isinstance(snapshot.entries, tuple):
        return _PolicyResolution(
            status="INVALID",
            index=None,
            message="retention policy entries are not a typed tuple",
        )
    requested = {
        _policy_key(
            request.forecast_season_id,
            request.forecast_season_code,
            (scope.farm_id, scope.subfarm_id, scope.variety_id),
        )
        for scope in request.scopes
    }
    if not snapshot.entries:
        return _PolicyResolution(
            status="MISSING",
            index=None,
            message="retention policy is required for every requested scope",
        )
    index: dict[tuple[int, str, int, int, int], MarketableRetentionPolicyEntry] = {}
    for raw_entry in snapshot.entries:
        try:
            entry = MarketableRetentionPolicyEntry.model_validate(
                raw_entry.model_dump(mode="python")
                if isinstance(raw_entry, MarketableRetentionPolicyEntry)
                else raw_entry
            )
            _policy_decimal(entry.sorting_retention_rate)
            _policy_decimal(entry.postharvest_retention_rate)
        except (ValidationError, _CompositionDataError, TypeError, ValueError):
            return _PolicyResolution(
                status="INVALID",
                index=None,
                message="retention policy entry is malformed",
            )
        key = _policy_key(
            entry.forecast_season_id,
            entry.forecast_season_code,
            (entry.farm_id, entry.subfarm_id, entry.variety_id),
        )
        if key in index:
            return _PolicyResolution(
                status="CONFLICT",
                index=None,
                message="retention policy contains a duplicate scope",
            )
        index[key] = entry
    if set(index) - requested:
        return _PolicyResolution(
            status="CONFLICT",
            index=None,
            message="retention policy contains an unrequested scope",
        )
    if requested - set(index):
        return _PolicyResolution(
            status="MISSING",
            index=None,
            message="retention policy is missing a requested scope",
        )
    return _PolicyResolution(status="OK", index=index, message="")


def _task8_supply(
    source: Task8AuthoritySource,
    members: tuple[Task9MemberSource, ...],
    request: CompleteDailyMarketableCurveRequest,
) -> bool:
    member_supply: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for member in members:
        member_supply[(member.state_date, member.forecast_quantile)] += _decimal(
            member.natural_maturity_supply_kg,
            "DAILY_CURVE_STATE_INVARIANT_FAILED",
        )
    predictions = {row.prediction_date: row for row in source.daily_predictions}
    for current_date in _dates(request.forecast_start_date, request.forecast_end_date):
        prediction = predictions.get(current_date)
        if prediction is None:
            return False
        for quantile, field_name in (
            ("P50", "p50_kg"),
            ("P80", "p80_kg"),
            ("P90", "p90_kg"),
        ):
            if member_supply[(current_date, quantile)] != _decimal(
                getattr(prediction, field_name),
                "TASK8_TASK9_SUPPLY_RECONCILIATION_FAILED",
            ):
                return False
    return True


def _validate_member_quantities(source: Task9AuthoritySource) -> None:
    for row in source.member_rows:
        for value in (
            row.natural_maturity_supply_kg,
            row.opening_mature_inventory_kg,
            row.available_mature_quantity_kg,
            row.mature_inventory_loss_quantity_kg,
            row.harvestable_mature_quantity_kg,
            row.allocated_harvest_capacity_kg,
            row.harvested_quantity_kg,
            row.closing_mature_inventory_kg,
            row.unharvested_backlog_kg,
        ):
            _decimal(value, "DAILY_CURVE_STATE_INVARIANT_FAILED")


def _validate_task8(
    source: Task8AuthoritySource,
    request: CompleteDailyMarketableCurveRequest,
) -> CoreForecastBlocker | None:
    if source.run_id != request.task8_forecast_run_id or source.status != "completed":
        return CoreForecastBlocker(
            code="TASK8_AUTHORITY_NOT_FOUND",
            message="completed Task 8 forecast authority is unavailable",
        )
    if (
        source.prediction_start_date > request.forecast_start_date
        or source.prediction_end_date < request.forecast_end_date
        or source.artifact_id <= 0
        or source.artifact_run_id != source.model_run_id
    ):
        return CoreForecastBlocker(
            code="AUTHORITY_SCOPE_MISMATCH",
            message="Task 8 authority does not cover the requested date range",
        )
    if not _valid_hash(source.artifact_hash):
        return CoreForecastBlocker(
            code="AUTHORITY_HASH_MALFORMED",
            message="Task 8 artifact hash is not a lowercase SHA-256",
        )
    return None


def _validate_task9(
    source: Task9AuthoritySource,
    task8: Task8AuthoritySource,
    request: CompleteDailyMarketableCurveRequest,
) -> CoreForecastBlocker | None:
    if source.run_id != request.task9_harvest_state_run_id or source.status != "completed":
        return CoreForecastBlocker(
            code="TASK9_AUTHORITY_NOT_FOUND",
            message="completed Task 9 harvest-state authority is unavailable",
        )
    if not _valid_hash(source.result_hash) or not _valid_hash(source.maturity_model_artifact_hash):
        return CoreForecastBlocker(
            code="AUTHORITY_HASH_MALFORMED",
            message="Task 9 authority hash is not a lowercase SHA-256",
        )
    if (
        source.forecast_season_id != request.forecast_season_id
        or source.destination_factory_id != request.destination_factory_id
        or source.forecast_start_date != request.forecast_start_date
        or source.forecast_end_date != request.forecast_end_date
        or source.maturity_forecast_run_id != request.task8_forecast_run_id
        or source.maturity_model_artifact_hash != task8.artifact_hash
    ):
        return CoreForecastBlocker(
            code="AUTHORITY_LINEAGE_MISMATCH",
            message="Task 8 and Task 9 authority lineage does not match the request",
        )
    return None


def _validate_member_rows(
    source: Task9AuthoritySource,
    request: CompleteDailyMarketableCurveRequest,
) -> CoreForecastBlocker | None:
    requested_scopes = {
        (scope.farm_id, scope.subfarm_id, scope.variety_id) for scope in request.scopes
    }
    expected_dates = set(_dates(request.forecast_start_date, request.forecast_end_date))
    expected_keys = {
        (current_date, *scope, quantile)
        for current_date in expected_dates
        for scope in requested_scopes
        for quantile in QUANTILES
    }
    seen: set[tuple[date, int, int, int, str]] = set()
    for row in source.member_rows:
        try:
            key = _business_key(row)
            scope = _scope_key(row)
        except ValueError:
            return CoreForecastBlocker(
                code="AUTHORITY_SCOPE_MISMATCH",
                message="Task 9 member row has a null or malformed subfarm scope",
            )
        if (
            row.state_date not in expected_dates
            or row.destination_factory_id != request.destination_factory_id
            or row.forecast_quantile not in QUANTILES
            or scope not in requested_scopes
        ):
            return CoreForecastBlocker(
                code="AUTHORITY_SCOPE_MISMATCH",
                message="Task 9 member rows contain an unrequested scope or date",
            )
        if key in seen:
            return CoreForecastBlocker(
                code="DAILY_CURVE_DUPLICATE_KEY",
                message="Task 9 member rows contain a duplicate business key",
            )
        seen.add(key)
    if seen != expected_keys:
        return CoreForecastBlocker(
            code="DAILY_CURVE_INCOMPLETE_SERIES",
            message="Task 9 member rows do not form complete requested series",
        )
    return None


def _validate_state(
    row: Task9MemberSource,
    previous: Task9MemberSource | None,
) -> CoreForecastBlocker | None:
    opening = _decimal(row.opening_mature_inventory_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    natural = _decimal(row.natural_maturity_supply_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    available = _decimal(row.available_mature_quantity_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    loss = _decimal(row.mature_inventory_loss_quantity_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    harvestable = _decimal(
        row.harvestable_mature_quantity_kg,
        "DAILY_CURVE_STATE_INVARIANT_FAILED",
    )
    capacity = _decimal(row.allocated_harvest_capacity_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    harvested = _decimal(row.harvested_quantity_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    closing = _decimal(row.closing_mature_inventory_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    backlog = _decimal(row.unharvested_backlog_kg, "DAILY_CURVE_STATE_INVARIANT_FAILED")
    if (
        available != opening + natural
        or harvestable != available - loss
        or harvested > harvestable
        or harvested > capacity
        or closing != harvestable - harvested
        or backlog != closing
        or opening + natural != loss + harvested + closing
    ):
        return CoreForecastBlocker(
            code="DAILY_CURVE_STATE_INVARIANT_FAILED",
            message="Task 9 member state equations are inconsistent",
        )
    if previous is not None and opening != _decimal(
        previous.closing_mature_inventory_kg,
        "DAILY_CURVE_STATE_INVARIANT_FAILED",
    ):
        return CoreForecastBlocker(
            code="DAILY_CURVE_CONTINUITY_FAILED",
            message="Task 9 member inventory is not continuous across business dates",
        )
    return None


def _compose_validated_curve(
    *,
    task8: Task8AuthoritySource,
    task9: Task9AuthoritySource,
    request: CompleteDailyMarketableCurveRequest,
    policy_index: dict[tuple[int, str, int, int, int], MarketableRetentionPolicyEntry],
) -> CompleteDailyMarketableCurveResult:
    _validate_member_quantities(task9)
    if not _task8_supply(task8, task9.member_rows, request):
        return _block(
            "TASK8_TASK9_SUPPLY_RECONCILIATION_FAILED",
            "Task 8 daily quantities do not equal Task 9 member natural supply",
        )

    grouped = defaultdict(list)
    for member in task9.member_rows:
        grouped[(*_scope_key(member), member.forecast_quantile)].append(member)
    for members in grouped.values():
        members.sort(key=lambda item: item.state_date)

    output_rows: list[CompleteDailyMarketableCurveRow] = []
    for key in sorted(
        grouped,
        key=lambda item: (item[0], item[1], item[2], QUANTILE_RANK[item[3]]),
    ):
        previous: Task9MemberSource | None = None
        for member in grouped[key]:
            state_blocker = _validate_state(member, previous)
            if state_blocker is not None:
                return _block(state_blocker.code, state_blocker.message)
            previous = member
            policy = policy_index[
                _policy_key(
                    request.forecast_season_id,
                    request.forecast_season_code,
                    _scope_key(member),
                )
            ]
            harvested = _decimal(
                member.harvested_quantity_kg,
                "DAILY_CURVE_STATE_INVARIANT_FAILED",
            )
            sorting = _policy_decimal(policy.sorting_retention_rate)
            postharvest = _policy_decimal(policy.postharvest_retention_rate)
            try:
                effective = (harvested * sorting * postharvest).quantize(
                    OUTPUT_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                )
            except (DecimalException, OverflowError) as exc:
                raise _CompositionDataError(
                    "MARKETABLE_RETENTION_POLICY_INVALID",
                    "retention policy cannot be applied exactly",
                ) from exc
            payload = {
                "date": member.state_date,
                "forecast_quantile": member.forecast_quantile,
                "farm_id": member.farm_id,
                "subfarm_id": member.subfarm_id,
                "variety_id": member.variety_id,
                "destination_factory_id": member.destination_factory_id,
                "natural_maturity_supply_kg": _fixed(
                    member.natural_maturity_supply_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "opening_mature_inventory_kg": _fixed(
                    member.opening_mature_inventory_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "available_mature_quantity_kg": _fixed(
                    member.available_mature_quantity_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "mature_inventory_loss_quantity_kg": _fixed(
                    member.mature_inventory_loss_quantity_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "harvestable_mature_quantity_kg": _fixed(
                    member.harvestable_mature_quantity_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "effective_harvest_capacity_kg": _fixed(
                    member.allocated_harvest_capacity_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "model_harvested_marketable_quantity_kg": _fixed(
                    member.harvested_quantity_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "closing_mature_inventory_kg": _fixed(
                    member.closing_mature_inventory_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "unharvested_backlog_kg": _fixed(
                    member.unharvested_backlog_kg,
                    "DAILY_CURVE_STATE_INVARIANT_FAILED",
                ),
                "sorting_retention_rate": _fixed(
                    sorting,
                    "MARKETABLE_RETENTION_POLICY_INVALID",
                ),
                "postharvest_retention_rate": _fixed(
                    postharvest,
                    "MARKETABLE_RETENTION_POLICY_INVALID",
                ),
                "effective_marketable_quantity_kg": _fixed(
                    effective,
                    "MARKETABLE_RETENTION_POLICY_INVALID",
                ),
                "task8_forecast_run_id": request.task8_forecast_run_id,
                "task9_harvest_state_run_id": request.task9_harvest_state_run_id,
                "task8_artifact_hash": task8.artifact_hash,
                "task9_result_hash": task9.result_hash,
                "marketable_policy_version": policy.version,
                "marketable_policy_hash": policy.hash,
            }
            row_hash = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
            output_rows.append(CompleteDailyMarketableCurveRow(**payload, row_hash=row_hash))

    output_rows.sort(
        key=lambda row: (
            row.date,
            row.farm_id,
            row.subfarm_id,
            row.variety_id,
            QUANTILE_RANK[row.forecast_quantile],
        )
    )
    rows = tuple(output_rows)
    curve_hash = hashlib.sha256(
        canonical_json_dumps(
            {
                "schema_version": _SCHEMA_VERSION,
                "rows": [row.model_dump(mode="json") for row in rows],
            }
        ).encode("utf-8")
    ).hexdigest()
    return CompleteDailyMarketableCurveResult(
        status="COMPLETED",
        rows=rows,
        curve_hash=curve_hash,
        blockers=(),
    )


async def compose_complete_daily_marketable_curve(
    session: AsyncSession,
    *,
    request: CompleteDailyMarketableCurveRequest,
    retention_policy: MarketableRetentionPolicySnapshot,
    repository: CoreForecastRepository | None = None,
) -> CompleteDailyMarketableCurveResult:
    """Compose a complete read-only curve from persisted Task 8/9 authorities."""

    repo = repository or SqlAlchemyCoreForecastRepository(session)
    resolution = _policy_index(request, retention_policy)
    if resolution.status == "MISSING":
        return _block("MARKETABLE_RETENTION_POLICY_MISSING", resolution.message)
    if resolution.status == "CONFLICT":
        return _block("MARKETABLE_RETENTION_POLICY_CONFLICT", resolution.message)
    if resolution.status == "INVALID":
        return _block("MARKETABLE_RETENTION_POLICY_INVALID", resolution.message)
    assert resolution.index is not None

    try:
        task8 = await repo.load_task8_authority(request.task8_forecast_run_id)
        task9 = await repo.load_task9_authority(request.task9_harvest_state_run_id)
        season = await repo.load_season(request.forecast_season_id)
    except Exception:
        return _block("UPSTREAM_READ_FAILURE", "authority read failed")
    if task8 is None:
        return _block("TASK8_AUTHORITY_NOT_FOUND", "Task 8 forecast authority was not found")
    if task9 is None:
        return _block("TASK9_AUTHORITY_NOT_FOUND", "Task 9 harvest-state authority was not found")
    if season is None or season.code != request.forecast_season_code:
        return _block(
            "AUTHORITY_SCOPE_MISMATCH", "forecast season identity does not match dim_season"
        )

    blocker = _validate_task8(task8, request)
    if blocker is not None:
        return _block(blocker.code, blocker.message)
    blocker = _validate_task9(task9, task8, request)
    if blocker is not None:
        return _block(blocker.code, blocker.message)
    blocker = _validate_member_rows(task9, request)
    if blocker is not None:
        return _block(blocker.code, blocker.message)
    try:
        return _compose_validated_curve(
            task8=task8,
            task9=task9,
            request=request,
            policy_index=resolution.index,
        )
    except _CompositionDataError as exc:
        return _block(exc.code, exc.message)
    except (ValueError, TypeError, DecimalException, OverflowError, ValidationError):
        return _block(
            "DAILY_CURVE_STATE_INVARIANT_FAILED",
            "validated composition failed closed",
        )
