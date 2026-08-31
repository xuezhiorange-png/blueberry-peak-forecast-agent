"""Default catalog construction from already-landed live-origin obtain.

Reuses the obtain `#476` bind-and-read path so bare catalog production with
dataset identity alone can resolve live forecast and alignment ports. Does not
rewrite frozen catalog production bytes, land grains, invent tonnes, or leave a
session provider set.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls

from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.forecast_artifact import VersionedIncumbentForecastArtifact
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.s3_a2_live_catalog_execution import LIVE_FORECAST_ENVELOPE_KIND

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True

_CACHE_MISS: object = object()
_nested_load = False
_nested_bundle: _LiveOriginConstructionBundle | None = None
_cached_maker_id: object = _CACHE_MISS
_cached_bundle: _LiveOriginConstructionBundle | None = None


@dataclass(frozen=True, slots=True)
class _LiveOriginConstructionBundle:
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...]
    harvest_rows: tuple[MaterializableRow, ...]


def _current_session_maker() -> object:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return None
    return live_async_session_maker


def _load_fresh_bundle() -> _LiveOriginConstructionBundle | None:
    live_async_session_maker = _current_session_maker()
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return None
    try:
        from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_obtain import (
            _bind_and_read_with_session_maker,
        )

        outcome = asyncio.run(_bind_and_read_with_session_maker(live_async_session_maker))
    except Exception:
        return None
    if outcome.bind.envelope.bound is not True or outcome.bind.actuals_source is None:
        return None
    if not outcome.origin_entries:
        return None
    if not isinstance(outcome.bind.actuals_source, InMemoryS2ActualsSource):
        return None
    harvest_rows = outcome.bind.actuals_source.rows
    if not harvest_rows:
        return None
    return _LiveOriginConstructionBundle(
        origin_entries=outcome.origin_entries,
        harvest_rows=harvest_rows,
    )


def _load_bundle() -> _LiveOriginConstructionBundle | None:
    global _nested_load, _nested_bundle, _cached_maker_id, _cached_bundle
    if _nested_load:
        return _nested_bundle
    maker_id = id(_current_session_maker())
    if maker_id == _cached_maker_id and _cached_bundle is not None:
        return _cached_bundle
    _nested_load = True
    _nested_bundle = None
    try:
        _nested_bundle = _load_fresh_bundle()
        if _nested_bundle is not None:
            _cached_bundle = _nested_bundle
            _cached_maker_id = maker_id
        return _nested_bundle
    finally:
        clear_v0_2_live_postgres_session_provider()
        _nested_load = False
        _nested_bundle = None


def live_origin_forecast_artifact_for_default_construction() -> (
    VersionedIncumbentForecastArtifact | None
):
    bundle = _load_bundle()
    if bundle is None:
        return None
    return IncumbentForecastArtifactContentProducer(
        replay_rows=bundle.origin_entries,
        declared_catalog_source_kind=LIVE_FORECAST_ENVELOPE_KIND,
        uses_harvest_date_as_forecast_cutoff=False,
    ).produce()


def live_origin_harvest_rows_for_default_construction() -> tuple[MaterializableRow, ...]:
    bundle = _load_bundle()
    if bundle is None:
        return ()
    return bundle.harvest_rows
