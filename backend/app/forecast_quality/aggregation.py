from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from .canonical import build_actual_physical_registry
from .exceptions import S3StructuralDuplicateError
from .schemas import (
    FarmDailyActualAggregate,
    FarmDailyForecastAggregate,
    S3BindingRow,
)


def aggregate_daily_forecasts(
    rows: Iterable[S3BindingRow],
) -> list[FarmDailyForecastAggregate]:
    seen_keys: set[str] = set()
    grouped: dict[tuple[Any, ...], list[S3BindingRow]] = defaultdict(list)
    for row in rows:
        if row.forecast_business_key in seen_keys:
            raise S3StructuralDuplicateError("duplicate forecast business key")
        seen_keys.add(row.forecast_business_key)
        if row.forecast_value_kg is None:
            continue
        key = (
            row.season_business_key,
            row.farm_business_key,
            row.variety_business_key,
            row.forecast_target_date,
            row.forecast_cutoff_at,
            row.model_identity,
            row.forecast_quantile,
            row.forecast_horizon_days,
        )
        grouped[key].append(row)
    result = []
    for key, grouped_rows in sorted(grouped.items(), key=lambda item: repr(item[0])):
        values = [
            row.forecast_value_kg for row in grouped_rows if row.forecast_value_kg is not None
        ]
        result.append(
            FarmDailyForecastAggregate(
                season_business_key=key[0],
                farm_business_key=key[1],
                variety_business_key=key[2],
                target_date=key[3],
                forecast_cutoff_at=key[4],
                model_identity=key[5],
                forecast_quantile=key[6],
                forecast_horizon_days=key[7],
                forecast_value_kg=sum(values, Decimal("0")),
                source_forecast_business_keys=tuple(
                    row.forecast_business_key for row in grouped_rows
                ),
            )
        )
    return result


def aggregate_daily_actuals(rows: Iterable[S3BindingRow]) -> list[FarmDailyActualAggregate]:
    row_list = list(rows)
    registry = build_actual_physical_registry(row_list)
    actual_by_key: dict[str, tuple[str, Decimal]] = {
        key: (value["stable_actual_identity"], value["actual_value_kg"])
        for key, value in registry["records"].items()
    }
    grouped: dict[tuple[str, str, str, Any], list[str]] = defaultdict(list)
    for row in row_list:
        if row.actual_physical_key is None or row.actual_value_kg is None:
            continue
        key = (
            row.season_business_key,
            row.farm_business_key,
            row.variety_business_key,
            row.forecast_target_date,
        )
        if row.actual_physical_key not in grouped[key]:
            grouped[key].append(row.actual_physical_key)
    result = []
    for key, physical_keys in sorted(grouped.items(), key=lambda item: repr(item[0])):
        result.append(
            FarmDailyActualAggregate(
                season_business_key=key[0],
                farm_business_key=key[1],
                variety_business_key=key[2],
                target_date=key[3],
                actual_value_kg=sum(
                    (actual_by_key[physical_key][1] for physical_key in physical_keys),
                    Decimal("0"),
                ),
                unique_actual_physical_rows=len(physical_keys),
            )
        )
    return result
