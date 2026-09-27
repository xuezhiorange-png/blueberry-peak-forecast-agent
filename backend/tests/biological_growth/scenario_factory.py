"""Reproducible synthetic environment fixture. It contains no farm observations."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.biological_growth.parameters import reference_parameter_set
from backend.app.biological_growth.schemas import (
    CaneCohort,
    Cultivar,
    EnvironmentHour,
    EventType,
    InitialPlantState,
    ManagementEvent,
    PlantStructure,
    ProductionSystem,
    SimulationInput,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def scenario_config(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def build_scenario(name: str, *, chill_requirement: float = 260.0) -> SimulationInput:
    config = scenario_config(name)
    start = datetime(2030, 10, 1)
    days = 330
    environment: list[EnvironmentHour] = []
    for day_offset in range(days):
        mean_temp = _synthetic_daily_mean(day_offset)
        current_day = start.date() + timedelta(days=day_offset)
        day_of_year = current_day.timetuple().tm_yday
        photoperiod = 12.0 + 3.0 * math.cos(2.0 * math.pi * (day_of_year - 172) / 365.0)
        for hour in range(24):
            temperature = mean_temp + 5.0 * math.sin(2.0 * math.pi * (hour - 8) / 24.0)
            environment.append(
                EnvironmentHour(
                    timestamp=start + timedelta(days=day_offset, hours=hour),
                    air_temperature_c=temperature,
                    source_id="SYNTHETIC_REFERENCE_TEMPERATURE",
                    source_priority=1,
                    relative_humidity_pct=70.0,
                    root_zone_temperature_c=mean_temp - 1.0,
                    radiation_index=0.65 if 7 <= hour <= 17 else 0.05,
                    photoperiod_hours=photoperiod,
                )
            )
    events = tuple(
        ManagementEvent(
            event_id=f"{name}-event-{index + 1}",
            event_type=EventType(item["event_type"]),
            event_datetime=start + timedelta(days=item["day_offset"]),
            intensity=item.get("intensity"),
            intensity_unit="fraction_0_1" if item.get("intensity") is not None else None,
            observed_or_planned="PLANNED",
            source_reference=f"GOLDEN_SCENARIO:{name}",
            target="SYNTHETIC_COUNTERFACTUAL",
        )
        for index, item in enumerate(config.get("events", []))
    )
    overrides = dict(config.get("parameter_overrides", {}))
    overrides["chill_requirement"] = chill_requirement
    if config["production_system"] == "EVERGREEN":
        overrides["day_neutral_genotype"] = 1.0
    return SimulationInput(
        simulation_id=f"S3-{name}",
        cultivar=Cultivar(
            "REFERENCE-SHB",
            "SOUTHERN_HIGHBUSH",
            "EVERBEARING" if name == "evergreen" else "SEASONAL",
            True if name == "evergreen" else None,
        ),
        production_system=ProductionSystem(config["production_system"]),
        plant_structure=PlantStructure(
            plant_density_per_mu=500.0,
            canes=(CaneCohort(1, 4.0, 0.8), CaneCohort(2, 5.0, 0.7), CaneCohort(3, 2.0, 0.4)),
            leaf_area_index=0.8,
            productive_shoots_per_plant=12.0,
            fruiting_wood_index=1.0,
        ),
        initial_state=InitialPlantState(
            reserve_index=0.55,
            vigor_index=0.65,
            canopy_health_index=0.9,
            flower_bud_potential_per_plant=config.get("initial_flower_buds", 75.0),
            prior_crop_load_index=0.35,
            leaf_retention_ratio=0.85,
        ),
        environment=tuple(environment),
        management_events=events,
        parameter_set=reference_parameter_set(overrides, chill_model="CHILL_HOURS"),
        productive_area_mu=1.0,
        environment_mode="THEORETICAL_SCENARIO_MICROCLIMATE",
    )


def _synthetic_daily_mean(day_offset: int) -> float:
    if day_offset < 60:
        return 15.0 - 0.12 * day_offset
    if day_offset < 140:
        return 5.0
    if day_offset < 230:
        return 5.0 + 0.20 * (day_offset - 140)
    return 23.0
