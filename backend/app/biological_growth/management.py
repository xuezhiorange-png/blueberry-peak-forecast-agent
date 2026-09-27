"""Time-scoped management and scenario microclimate effects."""

from __future__ import annotations

from datetime import datetime

from .schemas import EnvironmentHour, EventType, ManagementEvent


def event_is_active(event: ManagementEvent, timestamp: datetime) -> bool:
    return event.event_datetime <= timestamp


def effective_temperature_c(
    observation: EnvironmentHour,
    events: tuple[ManagementEvent, ...],
    *,
    scenario_mode: bool,
    closure_delta_c: float,
    heating_delta_c: float,
) -> float:
    temperature = observation.air_temperature_c
    if not scenario_mode:
        return temperature
    closure = _latest_toggle(
        events, observation.timestamp, EventType.GREENHOUSE_CLOSE, EventType.GREENHOUSE_OPEN
    )
    heating = _latest_toggle(
        events, observation.timestamp, EventType.HEATING_START, EventType.HEATING_STOP
    )
    if closure:
        temperature += closure_delta_c
    if heating:
        temperature += heating_delta_c
    return temperature


def effective_radiation_index(
    observation: EnvironmentHour,
    events: tuple[ManagementEvent, ...],
    *,
    scenario_mode: bool,
    shade_fraction: float,
) -> float:
    """Apply scenario shade to supplied light; measured microclimate passes through."""
    radiation = observation.radiation_index
    if radiation is None:
        return 0.0
    if not scenario_mode:
        return radiation

    shade_events = [
        event
        for event in events
        if event.event_type
        in {EventType.SHADE_START, EventType.SHADE_STOP, EventType.SHADE_APPLICATION}
        and event.event_datetime <= observation.timestamp
    ]
    active_intensity = 0.0
    for event in sorted(shade_events, key=lambda item: (item.event_datetime, item.event_id)):
        if event.event_type in {EventType.SHADE_START, EventType.SHADE_APPLICATION}:
            active_intensity = event.intensity or 0.0
        elif event.event_type is EventType.SHADE_STOP:
            active_intensity = 0.0
    attenuation = min(max(shade_fraction, 0.0), 1.0) * min(max(active_intensity, 0.0), 1.0)
    return max(0.0, radiation * (1.0 - attenuation))


def _latest_toggle(
    events: tuple[ManagementEvent, ...], at: datetime, on_type: EventType, off_type: EventType
) -> bool:
    toggles = [
        event
        for event in events
        if event.event_type in {on_type, off_type} and event.event_datetime <= at
    ]
    if not toggles:
        return False
    latest = max(toggles, key=lambda event: (event.event_datetime, event.event_id))
    return latest.event_type is on_type


def active_event_ids(events: tuple[ManagementEvent, ...], at: datetime) -> tuple[str, ...]:
    return tuple(event.event_id for event in events if event.event_datetime == at)
