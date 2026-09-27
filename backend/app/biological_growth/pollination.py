"""Pollination opportunity is not equated with pollinator presence or fruit set."""

from __future__ import annotations

from datetime import datetime

from .schemas import EventType, ManagementEvent


def pollination_sufficiency(
    events: tuple[ManagementEvent, ...],
    *,
    at: datetime,
    baseline: float,
    introduction_increment: float,
    temperature_suitability: float,
) -> float:
    active = any(
        event.event_type is EventType.POLLINATOR_INTRODUCTION and event.event_datetime <= at
        for event in events
    )
    window_events = sorted(
        (
            event
            for event in events
            if event.event_type
            in {
                EventType.POLLINATION_WINDOW_START,
                EventType.POLLINATION_WINDOW_END,
                EventType.POLLINATION_START,
                EventType.POLLINATION_END,
            }
            and event.event_datetime <= at
        ),
        key=lambda event: (event.event_datetime, event.event_id),
    )
    window_open = not window_events or window_events[-1].event_type in {
        EventType.POLLINATION_WINDOW_START,
        EventType.POLLINATION_START,
    }
    opportunity = (baseline if window_open else 0.0) + (
        introduction_increment if active and window_open else 0.0
    )
    return min(max(opportunity * temperature_suitability, 0.0), 1.0)
