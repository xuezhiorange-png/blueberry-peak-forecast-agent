"""TASK-013 Slice A — pytest configuration and shared fixtures.

* ``sqlite_session`` — per-test SQLite in-memory async session bound to the
  existing TASK-009/010 tables (subset compatible with SQLite — the
  Postgres-only ``HarvestStateReplaySourceVisibilityAuditModel`` and the
  Postgres ``JSONB`` columns are intentionally excluded, matching the
  pattern in ``backend/tests/test_residual_model_execution_api.py``).
* ``sample_normalized_request`` — a deterministic NormalizedAgentRequest.
* ``sample_uncertainty_widening_policy`` — frozen policy with monotonic factors.
* ``sample_peak_metric_policy`` — frozen peak policy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agent.canonical import sha256_payload
from backend.app.agent.schemas import (
    AdvancedOverrides,
    LocationInput,
    MinimalInputRequest,
    MinimalVarietyInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    UncertaintyWideningPolicy,
)


# --- Tables included in the SQLite fixture --------------------------------

def _harvest_state_tables() -> list:
    from backend.app.models.harvest_state import (
        HarvestStateCohortTransitionRowModel,
        HarvestStateDailyMemberRowModel,
        HarvestStateDailyPoolRowModel,
        HarvestStateFutureArrivalRowModel,
        HarvestStateRun,
    )

    return [
        HarvestStateRun.__table__,
        HarvestStateDailyPoolRowModel.__table__,
        HarvestStateDailyMemberRowModel.__table__,
        HarvestStateCohortTransitionRowModel.__table__,
        HarvestStateFutureArrivalRowModel.__table__,
    ]


def _residual_tables() -> list:
    from backend.app.models.residual_model import (
        ResidualModelArtifact,
        ResidualModelExecutionAttempt,
        ResidualModelManifestRow,
        ResidualModelPredictionRow,
        ResidualModelPredictionRun,
        ResidualModelTrainingRun,
    )

    return [
        ResidualModelTrainingRun.__table__,
        ResidualModelManifestRow.__table__,
        ResidualModelArtifact.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
        ResidualModelExecutionAttempt.__table__,
    ]


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    """SQLite-backed AsyncSession with the TASK-009/010 tables created.

    Slice A does not introduce any new tables or migrations; we only create
    the existing ORM tables that the upstream services already query.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    from backend.app.models.harvest_state import HarvestStateRun
    from backend.app.models.residual_model import ResidualModelTrainingRun

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: HarvestStateRun.metadata.create_all(
                sync_conn, tables=_harvest_state_tables()
            )
        )
        await conn.run_sync(
            lambda sync_conn: ResidualModelTrainingRun.metadata.create_all(
                sync_conn, tables=_residual_tables()
            )
        )

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session

    await engine.dispose()


# --- Deterministic fixtures ---------------------------------------------

@pytest.fixture
def sample_normalized_request() -> NormalizedAgentRequest:
    """A canonical NormalizedAgentRequest used across tests."""

    provenance = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=date(2026, 3, 1),
        effective_as_of_date=date(2026, 3, 1),
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    nr = NormalizedAgentRequest(
        request_id="req-test-1",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=provenance,
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        varieties=[NormalizedVarietyInput(variety_id="101", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    real_hash = sha256_payload(nr.model_dump(mode="python"))
    return nr.model_copy(update={"canonical_request_hash": real_hash})


@pytest.fixture
def sample_uncertainty_widening_policy() -> UncertaintyWideningPolicy:
    factors = {
        "step_1_same_farm_same_variety_high_evidence": "1.000",
        "step_2_same_township_similar_altitude": "1.250",
        "step_3_same_county_same_climate_zone": "1.500",
        "step_4_province_level_same_variety": "1.750",
        "step_5_variety_document_prior_only": "2.000",
    }
    return UncertaintyWideningPolicy(
        policy_version="uncertainty-widening/v1",
        config_hash="b" * 64,
        factors_by_source_level=factors,
        monotonicity_invariant=True,
    )


@pytest.fixture
def sample_peak_metric_policy() -> PeakMetricPolicy:
    return PeakMetricPolicy(
        policy_version="peak-metric/v1",
        policy_config_hash="c" * 64,
        sustained_window_days=3,
        sustained_metric="ROLLING_DAILY_AVERAGE",
        tie_break="EARLIEST_START_DATE",
        peak_window_days_before=7,
        peak_window_days_after=7,
        high_load_reference="SINGLE_DAY_PEAK",
        high_load_threshold_ratio="0.900",
    )


@pytest.fixture
def sample_minimal_input_request() -> MinimalInputRequest:
    return MinimalInputRequest(
        request_id="req-test-1",
        location=LocationInput(
            raw_text="Yunnan, China",
            location_reference_id=1,
        ),
        varieties=[MinimalVarietyInput(variety_id="101", planting_area_mu="100.0")],
        requested_as_of_date=date(2026, 3, 1),
        requested_forecast_season=2026,
    )