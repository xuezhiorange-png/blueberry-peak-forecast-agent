from __future__ import annotations

import hashlib
import json
from datetime import date, time
from decimal import Decimal
from typing import Any


def canonical_hash_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def make_stable_cohort_key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def make_task8_source_ref(
    *,
    prediction_date: date,
    forecast_quantile: str,
    source_quantity_kg: Decimal,
    forecast_run_id: int = 401,
    forecast_source_signature: str = "forecast-sig-1",
    model_source_signature: str = "model-sig-1",
    artifact_hash: str = "artifact-hash-1",
    weather_mapping_id: int | None = 801,
    base_temperature_search_run_id: int | None = 901,
    forecast_run_status: str = "completed",
) -> dict[str, Any]:
    return {
        "source_ref_type": "TASK8_DAILY_PREDICTION",
        "source_ref_schema_version": "task9a-source-ref-v1",
        "maturity_model_run_id": 101,
        "maturity_model_version": "task8-v1",
        "maturity_model_config_hash": "task8-model-config-hash",
        "maturity_model_source_signature": model_source_signature,
        "maturity_model_artifact_id": 201,
        "maturity_model_artifact_hash": artifact_hash,
        "maturity_forecast_run_id": forecast_run_id,
        "forecast_run_status": forecast_run_status,
        "artifact_run_id": 101,
        "forecast_model_run_id": 101,
        "forecast_artifact_id": 201,
        "maturity_forecast_source_signature": forecast_source_signature,
        "maturity_forecast_as_of_date": date(2026, 2, 28),
        "maturity_forecast_prediction_start_date": date(2026, 3, 1),
        "maturity_forecast_prediction_end_date": date(2026, 3, 3),
        "maturity_daily_prediction_id": 301 + prediction_date.day,
        "daily_prediction_forecast_run_id": forecast_run_id,
        "prediction_date": prediction_date,
        "forecast_quantile": forecast_quantile,
        "source_quantity_kg": source_quantity_kg,
        "p50_kg": Decimal("20") if forecast_quantile != "P50" else source_quantity_kg,
        "p80_kg": Decimal("24") if forecast_quantile != "P80" else source_quantity_kg,
        "p90_kg": Decimal("28") if forecast_quantile != "P90" else source_quantity_kg,
        "plan_id": 501,
        "location_reference_id": 601,
        "weather_mapping_id": weather_mapping_id,
        "base_temperature_search_run_id": base_temperature_search_run_id,
    }


def make_initial_source_ref(
    *,
    as_of_date: date,
    available_at: date | None = None,
    source_record_key: str = "init-row-1",
    source_row_hash: str = "init-row-hash-1",
) -> dict[str, Any]:
    return {
        "source_ref_type": "INITIAL_INVENTORY_SNAPSHOT",
        "source_ref_schema_version": "task9a-source-ref-v1",
        "source_system": "ops_snapshot",
        "source_record_key": source_record_key,
        "source_version": "v1",
        "source_row_hash": source_row_hash,
        "available_at": available_at or as_of_date,
        "as_of_date": as_of_date,
    }


def make_parameter_source_ref(
    *,
    parameter_code: str,
    as_of_date: date,
    source_record_key: str | None = None,
    source_row_hash: str | None = None,
    available_at: date | None = None,
) -> dict[str, Any]:
    key = source_record_key or parameter_code.lower()
    row_hash = source_row_hash or f"{parameter_code.lower()}-hash"
    return {
        "source_ref_type": "PARAMETER_SOURCE",
        "source_ref_schema_version": "task9a-source-ref-v1",
        "parameter_code": parameter_code,
        "source_system": "task9a-config",
        "source_record_key": key,
        "source_version": "v1",
        "source_row_hash": row_hash,
        "available_at": available_at or as_of_date,
        "as_of_date": as_of_date,
    }


def make_pool(
    *,
    pool_id: str = "pool-a",
    grain: str = "SUBFARM",
    members: list[dict[str, int | None]] | None = None,
) -> dict[str, Any]:
    return {
        "capacity_pool_id": pool_id,
        "capacity_pool_grain": grain,
        "members": members
        or [
            {"farm_id": 1, "subfarm_id": 11, "variety_id": 101},
            {"farm_id": 1, "subfarm_id": 11, "variety_id": 102},
        ],
    }


def make_capacity_input(
    *,
    capacity_date: date,
    pool_id: str = "pool-a",
    mode: str = "LABOR_DERIVED",
    labor_ratio: Decimal = Decimal("1"),
    operational_ratio: Decimal = Decimal("1"),
    planned_picker_count: Decimal | None = Decimal("10"),
    productivity: Decimal | None = Decimal("20"),
    direct_capacity: Decimal | None = None,
) -> dict[str, Any]:
    parameter_refs = [
        make_parameter_source_ref(
            parameter_code="LABOR_AVAILABILITY_RATIO",
            as_of_date=date(2026, 2, 28),
            source_record_key=f"{pool_id}-{capacity_date}-labor",
            source_row_hash=f"{pool_id}-{capacity_date}-labor-hash",
        ),
        make_parameter_source_ref(
            parameter_code="OPERATIONAL_EFFICIENCY_RATIO",
            as_of_date=date(2026, 2, 28),
            source_record_key=f"{pool_id}-{capacity_date}-ops",
            source_row_hash=f"{pool_id}-{capacity_date}-ops-hash",
        ),
    ]
    if mode == "LABOR_DERIVED":
        parameter_refs.extend(
            [
                make_parameter_source_ref(
                    parameter_code="PLANNED_PICKER_COUNT",
                    as_of_date=date(2026, 2, 28),
                    source_record_key=f"{pool_id}-{capacity_date}-pickers",
                    source_row_hash=f"{pool_id}-{capacity_date}-pickers-hash",
                ),
                make_parameter_source_ref(
                    parameter_code="PICKER_PRODUCTIVITY",
                    as_of_date=date(2026, 2, 28),
                    source_record_key=f"{pool_id}-{capacity_date}-productivity",
                    source_row_hash=f"{pool_id}-{capacity_date}-productivity-hash",
                ),
            ]
        )
    else:
        parameter_refs.append(
            make_parameter_source_ref(
                parameter_code="DIRECT_NOMINAL_CAPACITY",
                as_of_date=date(2026, 2, 28),
                source_record_key=f"{pool_id}-{capacity_date}-direct",
                source_row_hash=f"{pool_id}-{capacity_date}-direct-hash",
            )
        )
    return {
        "capacity_date": capacity_date,
        "capacity_pool_id": pool_id,
        "capacity_input_mode": mode,
        "planned_picker_count": planned_picker_count,
        "kg_per_person_per_day": productivity,
        "direct_nominal_capacity_kg_per_day": direct_capacity,
        "labor_availability_ratio": labor_ratio,
        "operational_efficiency_ratio": operational_ratio,
        "capacity_parameter_source_refs": parameter_refs,
    }


def make_weather_feature(
    *,
    capacity_date: date,
    pool_id: str,
    feature_id: str,
    value: Decimal,
) -> dict[str, Any]:
    return {
        "capacity_date": capacity_date,
        "capacity_pool_id": pool_id,
        "feature_id": feature_id,
        "value": value,
        "source_ref": make_parameter_source_ref(
            parameter_code="WEATHER_FEATURE_OBSERVATION",
            as_of_date=date(2026, 2, 28),
            source_record_key=f"{pool_id}-{capacity_date}-{feature_id}",
            source_row_hash=f"{pool_id}-{capacity_date}-{feature_id}-hash",
        ),
    }


def make_loss_input(
    *,
    state_date: date,
    pool_id: str,
    quantile: str,
    quantity: Decimal,
) -> dict[str, Any]:
    return {
        "state_date": state_date,
        "capacity_pool_id": pool_id,
        "forecast_quantile": quantile,
        "mature_inventory_loss_quantity_kg": quantity,
        "source_ref": make_parameter_source_ref(
            parameter_code="MATURE_INVENTORY_LOSS",
            as_of_date=date(2026, 2, 28),
            source_record_key=f"{pool_id}-{state_date}-{quantile}-loss",
            source_row_hash=f"{pool_id}-{state_date}-{quantile}-loss-hash",
        ),
    }


def make_initial_cohort(
    *,
    quantile: str,
    quantity: Decimal,
    cohort_date: date = date(2026, 2, 28),
    variety_id: int = 101,
    capacity_pool_id: str = "pool-a",
    capacity_pool_membership_hash: str = "membership-hash-placeholder",
    destination_factory_id: int = 701,
) -> dict[str, Any]:
    source_ref = make_initial_source_ref(as_of_date=date(2026, 2, 28))
    stable_key = make_stable_cohort_key(
        {
            "schema_version": "task9a-cohort-key-v1",
            "source_ref_type": "INITIAL_INVENTORY_SNAPSHOT",
            "source_system": source_ref["source_system"],
            "source_record_key": source_ref["source_record_key"],
            "source_version": source_ref["source_version"],
            "source_row_hash": source_ref["source_row_hash"],
            "cohort_date": cohort_date.isoformat(),
            "forecast_quantile": quantile,
            "farm_id": 1,
            "subfarm_id": 11,
            "variety_id": variety_id,
            "capacity_pool_id": capacity_pool_id,
            "capacity_pool_membership_hash": capacity_pool_membership_hash,
            "destination_factory_id": destination_factory_id,
        }
    )
    return {
        "cohort_date": cohort_date,
        "farm_id": 1,
        "subfarm_id": 11,
        "variety_id": variety_id,
        "remaining_quantity_kg": quantity,
        "source_ref": source_ref,
        "forecast_quantile": quantile,
        "stable_cohort_key": stable_key,
        "stable_cohort_key_schema_version": "task9a-cohort-key-v1",
    }


def make_task8_supply(
    *,
    prediction_date: date,
    quantile: str,
    quantity: Decimal,
    variety_id: int = 101,
) -> dict[str, Any]:
    return {
        "prediction_date": prediction_date,
        "farm_id": 1,
        "subfarm_id": 11,
        "variety_id": variety_id,
        "source_ref": make_task8_source_ref(
            prediction_date=prediction_date,
            forecast_quantile=quantile,
            source_quantity_kg=quantity,
        ),
    }


def make_request() -> dict[str, Any]:
    forecast_dates = [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]
    quantiles = ("P50", "P80", "P90")
    pool = make_pool()
    capacity_pool_membership_hash = make_stable_cohort_key(
        {
            "capacity_pool_grain": pool["capacity_pool_grain"],
            "members": sorted(
                pool["members"],
                key=lambda item: (item["farm_id"], item["subfarm_id"], item["variety_id"]),
            ),
        }
    )
    task8_predictions = []
    for prediction_date in forecast_dates:
        for quantile, amount in (
            ("P50", Decimal("20")),
            ("P80", Decimal("24")),
            ("P90", Decimal("28")),
        ):
            task8_predictions.extend(
                [
                    make_task8_supply(
                        prediction_date=prediction_date,
                        quantile=quantile,
                        quantity=amount,
                        variety_id=101,
                    ),
                    make_task8_supply(
                        prediction_date=prediction_date,
                        quantile=quantile,
                        quantity=amount,
                        variety_id=102,
                    ),
                ]
            )
    losses = [
        make_loss_input(
            state_date=prediction_date,
            pool_id="pool-a",
            quantile=quantile,
            quantity=Decimal("0"),
        )
        for prediction_date in forecast_dates
        for quantile in quantiles
    ]
    weather_features = []
    for prediction_date in forecast_dates:
        weather_features.extend(
            [
                make_weather_feature(
                    capacity_date=prediction_date,
                    pool_id="pool-a",
                    feature_id="daily_precipitation_mm",
                    value=Decimal("0"),
                ),
                make_weather_feature(
                    capacity_date=prediction_date,
                    pool_id="pool-a",
                    feature_id="consecutive_rainy_days",
                    value=Decimal("0"),
                ),
                make_weather_feature(
                    capacity_date=prediction_date,
                    pool_id="pool-a",
                    feature_id="minimum_temperature_c",
                    value=Decimal("12"),
                ),
            ]
        )
    global_parameter_source_refs = [
        make_parameter_source_ref(
            parameter_code="HOLIDAY_CALENDAR",
            as_of_date=date(2026, 2, 28),
            source_record_key="holiday-calendar-v1",
            source_row_hash="holiday-calendar-v1-hash",
        ),
        make_parameter_source_ref(
            parameter_code="WEATHER_RULE_CONFIG",
            as_of_date=date(2026, 2, 28),
            source_record_key="weather-rule-v1",
            source_row_hash="weather-rule-v1-hash",
        ),
        make_parameter_source_ref(
            parameter_code="HARVEST_TO_ARRIVAL_LAG",
            as_of_date=date(2026, 2, 28),
            source_record_key="arrival-lag-v1",
            source_row_hash="arrival-lag-v1-hash",
        ),
        make_parameter_source_ref(
            parameter_code="TIMEZONE_CONFIG",
            as_of_date=date(2026, 2, 28),
            source_record_key="timezone-v1",
            source_row_hash="timezone-v1-hash",
        ),
        make_parameter_source_ref(
            parameter_code="HARVEST_BUCKET_ANCHOR_TIME",
            as_of_date=date(2026, 2, 28),
            source_record_key="anchor-time-v1",
            source_row_hash="anchor-time-v1-hash",
        ),
    ]
    return {
        "as_of_date": date(2026, 2, 28),
        "forecast_start_date": forecast_dates[0],
        "forecast_end_date": forecast_dates[-1],
        "forecast_quantiles": list(quantiles),
        "destination_factory_id": 701,
        "farm_timezone": "Asia/Shanghai",
        "destination_factory_timezone": "Asia/Tokyo",
        "harvest_bucket_anchor_local_time": time(18, 0, 0),
        "harvest_to_arrival_lag_days": 1,
        "holiday_calendar_version": "holiday-v1",
        "holiday_calendar_hash": "holiday-hash-v1",
        "holiday_dates": [],
        "weather_rule_config": {
            "version": "weather-rule-v1",
            "required_feature_ids": [
                "daily_precipitation_mm",
                "consecutive_rainy_days",
                "minimum_temperature_c",
            ],
            "feature_rules": [
                {
                    "feature_id": "daily_precipitation_mm",
                    "bands": [
                        {
                            "lower_bound": "0",
                            "lower_inclusive": True,
                            "upper_bound": "0",
                            "upper_inclusive": True,
                            "multiplier": "1",
                        },
                        {
                            "lower_bound": "0",
                            "lower_inclusive": False,
                            "upper_bound": "1000",
                            "upper_inclusive": True,
                            "multiplier": "0.5",
                        },
                    ],
                },
                {
                    "feature_id": "consecutive_rainy_days",
                    "bands": [
                        {
                            "lower_bound": "0",
                            "lower_inclusive": True,
                            "upper_bound": "2",
                            "upper_inclusive": True,
                            "multiplier": "1",
                        },
                        {
                            "lower_bound": "2",
                            "lower_inclusive": False,
                            "upper_bound": "1000",
                            "upper_inclusive": True,
                            "multiplier": "0.7",
                        },
                    ],
                },
                {
                    "feature_id": "minimum_temperature_c",
                    "bands": [
                        {
                            "lower_bound": "-100",
                            "lower_inclusive": True,
                            "upper_bound": "10",
                            "upper_inclusive": False,
                            "multiplier": "0.8",
                        },
                        {
                            "lower_bound": "10",
                            "lower_inclusive": True,
                            "upper_bound": "100",
                            "upper_inclusive": True,
                            "multiplier": "1",
                        },
                    ],
                },
            ],
            "combination_method": "MULTIPLY",
            "minimum_ratio": "0",
            "maximum_ratio": "1",
            "missing_feature_policy": "BLOCK",
        },
        "run_parameter_source_refs": global_parameter_source_refs,
        "capacity_pools": [pool],
        "daily_capacity_inputs": [
            make_capacity_input(capacity_date=prediction_date) for prediction_date in forecast_dates
        ],
        "daily_weather_features": weather_features,
        "task8_daily_predictions": task8_predictions,
        "initial_inventory_cohorts": [
            make_initial_cohort(
                quantile="P50",
                quantity=Decimal("5"),
                variety_id=101,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
            make_initial_cohort(
                quantile="P50",
                quantity=Decimal("3"),
                variety_id=102,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
            make_initial_cohort(
                quantile="P80",
                quantity=Decimal("6"),
                variety_id=101,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
            make_initial_cohort(
                quantile="P80",
                quantity=Decimal("4"),
                variety_id=102,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
            make_initial_cohort(
                quantile="P90",
                quantity=Decimal("7"),
                variety_id=101,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
            make_initial_cohort(
                quantile="P90",
                quantity=Decimal("5"),
                variety_id=102,
                capacity_pool_membership_hash=capacity_pool_membership_hash,
            ),
        ],
        "initial_opening_mature_inventory_kg": Decimal("30"),
        "mature_inventory_loss_inputs": losses,
    }
