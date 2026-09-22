from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.area_yield.base_product import (
    AreaForecastProductResult,
    BaseDailyForecast,
    BaseRolling7DayPeak,
    BaseSingleDayPeak,
)
from backend.app.area_yield.base_product_authority import BaseProductAuthority
from backend.app.pit.models import ForecastRunSnapshot
from backend.app.pit.schemas import WeatherForecastSnapshotInput
from backend.app.pit.shadow_forecast import (
    ShadowForecastBlocked,
    ShadowForecastRequest,
    WeatherForecastCaptureResult,
    run_shadow_forecast,
    run_shadow_forecast_batch,
)

NOW = datetime.now(UTC).replace(microsecond=0)
BASE_A = "base_" + "a" * 24
BASE_B = "base_" + "b" * 24


def _upgrade_pit_schema(connection: object) -> None:
    context = MigrationContext.configure(connection)  # type: ignore[arg-type]
    operations = Operations(context)
    for revision in ("0036_v06_pit_data_foundation", "0037_v06_pit_scope_time_integrity"):
        migration = importlib.import_module(f"backend.alembic.versions.{revision}")
        migration.op = operations
        migration.upgrade()


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade_pit_schema)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _authority() -> BaseProductAuthority:
    bases = [
        {
            "base_id": BASE_A,
            "canonical_base_name": "Alpha Base",
            "covered_farms": ["Alpha Farm"],
            "productive_area_mu": "100",
        },
        {
            "base_id": BASE_B,
            "canonical_base_name": "Beta Base",
            "covered_farms": ["Beta Farm"],
            "productive_area_mu": "200",
        },
    ]
    history = [
        {
            "base_id": base["base_id"],
            "season": "2025-2026",
            "mapped_harvest_quantity_kg": "1000",
            "yield_kg_per_mu": "10",
            "source_sha256": "c" * 64,
            "identity_mapping_sha256": "d" * 64,
            "coverage_status": "INCOMPLETE",
        }
        for base in bases
    ]
    return BaseProductAuthority(
        registry={"bases": bases},
        model={
            "base_yield_history": [],
            "research_artifacts": {"temporal_model_artifact_sha256": "e" * 64},
        },
        registry_file_sha256="a" * 64,
        model_file_sha256="b" * 64,
        authority_hash="f" * 64,
        experimental_prior_history={"bases": history},
        experimental_prior_history_file_sha256="1" * 64,
    )


def _product_result() -> AreaForecastProductResult:
    quantities = [
        Decimal("10"),
        Decimal("20"),
        Decimal("30"),
        Decimal("15"),
        Decimal("10"),
        Decimal("8"),
        Decimal("7"),
    ]
    shares = [
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.15"),
        Decimal("0.1"),
        Decimal("0.08"),
        Decimal("0.07"),
    ]
    start = datetime(2026, 7, 1, tzinfo=UTC).date()
    return AreaForecastProductResult(
        canonical_base_id=BASE_A,
        canonical_base_name="Alpha Base",
        reference_area_mu="100",
        target_area_mu="100",
        target_season="2026-2027",
        forecast_start_date=start,
        forecast_end_date=start + timedelta(days=6),
        predicted_yield_kg_per_mu="10",
        predicted_season_total_kg="100",
        daily_curve=[
            BaseDailyForecast(
                date=start + timedelta(days=index),
                predicted_quantity_kg=format(quantity, "f"),
                normalized_share=format(share, "f"),
            )
            for index, (quantity, share) in enumerate(zip(quantities, shares, strict=True))
        ],
        single_day_peak=BaseSingleDayPeak(date=start + timedelta(days=2), quantity_kg="30"),
        rolling_7day_peak=BaseRolling7DayPeak(
            start_date=start,
            end_date=start + timedelta(days=6),
            cumulative_quantity_kg="100",
        ),
        mass_balance={"pass": True},
        metadata={"forecast_mode": "EXPERIMENTAL"},
        source_hashes=["a" * 64],
        limitations=["MODEL_STATUS_EXPERIMENTAL"],
        result_hash="1" * 64,
    )


@pytest.fixture
def fake_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.pit.shadow_forecast.forecast_base_area",
        lambda request, authority: _product_result().model_copy(
            update={
                "canonical_base_id": request.base_id,
                "canonical_base_name": authority.bases_by_id[request.base_id][
                    "canonical_base_name"
                ],
                "target_area_mu": request.target_area_mu,
            }
        ),
    )


@pytest.mark.unit
def test_unavailable_provider_is_explicit_and_does_not_masquerade_as_realized() -> None:
    from backend.app.pit.shadow_forecast import UnavailableWeatherForecastProvider

    result = UnavailableWeatherForecastProvider().capture(
        base={"base_id": BASE_A},
        forecast_created_at=NOW,
        target_season="2026-2027",
    )
    assert result.status == "UNAVAILABLE"
    assert result.snapshots == ()
    assert result.reason == "AS_ISSUED_FORECAST_PROVIDER_NOT_CONFIGURED"


@pytest.mark.unit
async def test_single_shadow_run_persists_pit_inputs_and_optional_weather(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    authority = _authority()
    created = datetime.now(UTC).replace(microsecond=0)
    async with sqlite_session.begin():
        execution = await run_shadow_forecast(
            sqlite_session,
            ShadowForecastRequest(
                base_id=BASE_A,
                target_season="2026-2027",
                target_area_mu=Decimal("100"),
                forecast_created_at=created,
                forecast_run_id="shadow-no-weather",
            ),
            authority=authority,
        )
    assert execution.snapshot.forecast_mode == "SHADOW"
    assert execution.snapshot.model_status == "EXPERIMENTAL"
    assert execution.weather_capture_status == "UNAVAILABLE"
    assert execution.snapshot.weather_snapshot_ids == []
    assert "WEATHER_FORECAST_NOT_AVAILABLE" in execution.snapshot.warnings
    assert execution.snapshot.area_revision_id.startswith("v06-reference-area-")
    assert execution.snapshot.prior_history_season == "2025-2026"
    assert execution.snapshot.prior_history_coverage_status == "INCOMPLETE"
    assert execution.snapshot.input_snapshot_hash
    assert execution.snapshot.result_hash


@pytest.mark.unit
async def test_weather_evidence_changes_pit_hash_not_frozen_model_output(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    class Provider:
        provider_name = "test-as-issued"

        def capture(self, *, base, forecast_created_at, target_season):
            del target_season
            return WeatherForecastCaptureResult(
                status="CAPTURED",
                provider=self.provider_name,
                snapshots=(
                    WeatherForecastSnapshotInput(
                        weather_snapshot_id="weather-as-issued-1",
                        provider=self.provider_name,
                        base_id=base["base_id"],
                        issued_at=forecast_created_at - timedelta(hours=2),
                        fetched_at=forecast_created_at - timedelta(hours=1),
                        known_at=forecast_created_at - timedelta(minutes=1),
                        valid_at=forecast_created_at + timedelta(days=1),
                        forecast_horizon_hours=24,
                        temperature_mean=Decimal("18"),
                        precipitation=Decimal("0"),
                        raw_payload_hash="1" * 64,
                        normalized_payload_hash="2" * 64,
                    ),
                ),
            )

    authority = _authority()
    created = datetime.now(UTC).replace(microsecond=0)
    async with sqlite_session.begin():
        without_weather = await run_shadow_forecast(
            sqlite_session,
            ShadowForecastRequest(
                base_id=BASE_A,
                target_season="2026-2027",
                target_area_mu=Decimal("100"),
                forecast_created_at=created,
                forecast_run_id="shadow-without-weather",
            ),
            authority=authority,
        )
        with_weather = await run_shadow_forecast(
            sqlite_session,
            ShadowForecastRequest(
                base_id=BASE_A,
                target_season="2026-2027",
                target_area_mu=Decimal("100"),
                forecast_created_at=created,
                forecast_run_id="shadow-with-weather",
            ),
            authority=authority,
            weather_provider=Provider(),
        )
    assert with_weather.weather_capture_status == "CAPTURED"
    assert len(with_weather.snapshot.weather_snapshot_ids) == 1
    assert without_weather.model_output_result_hash == with_weather.model_output_result_hash
    assert without_weather.snapshot.input_snapshot_hash != with_weather.snapshot.input_snapshot_hash
    assert without_weather.snapshot.result_hash != with_weather.snapshot.result_hash


@pytest.mark.unit
async def test_ecmwf_fixture_capture_reaches_shadow_persistence_path(
    sqlite_session: AsyncSession,
    fake_product: None,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.tests.v06_s2.test_ecmwf_open_data_provider import (
        _fixture_provider,
        _freeze_fixture_fetch_time,
    )

    provider, _, _ = _fixture_provider(
        tmp_path,
        monkeypatch,
        supported_runs={"20260919000000"},
        base_ids=[BASE_A],
        base_names=["Alpha Base"],
    )
    # Keep the offline fixture aligned with its fixed 2026-09-19 ECMWF run.
    # The production provider retains its dynamic three-day lookback; this
    # test must not depend on the wall clock moving through that window.
    created = datetime(2026, 9, 19, 11, tzinfo=UTC)
    monkeypatch.setattr("backend.app.pit.shadow_forecast._utc_now", lambda: created)
    _freeze_fixture_fetch_time(provider, "20260919000000", created)
    async with sqlite_session.begin():
        execution = await run_shadow_forecast(
            sqlite_session,
            ShadowForecastRequest(
                base_id=BASE_A,
                target_season="2026-2027",
                target_area_mu=Decimal("100"),
                forecast_created_at=created,
                forecast_run_id="shadow-ecmwf-fixture",
            ),
            authority=_authority(),
            weather_provider=provider,
        )
    assert execution.weather_capture_status == "CAPTURED"
    assert len(execution.snapshot.weather_snapshot_ids) == 4
    stored = await sqlite_session.get(
        ForecastRunSnapshot,
        "shadow-ecmwf-fixture",
    )
    assert stored is not None
    assert stored.weather_snapshot_ids == execution.snapshot.weather_snapshot_ids


@pytest.mark.unit
async def test_weather_scope_mismatch_fails_closed(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    class WrongProvider:
        provider_name = "wrong"

        def capture(self, *, base, forecast_created_at, target_season):
            del base, target_season
            from backend.app.pit.schemas import WeatherForecastSnapshotInput

            return WeatherForecastCaptureResult(
                status="CAPTURED",
                provider=self.provider_name,
                snapshots=(
                    WeatherForecastSnapshotInput(
                        weather_snapshot_id="weather-wrong-base",
                        provider=self.provider_name,
                        base_id=BASE_B,
                        issued_at=forecast_created_at - timedelta(hours=2),
                        fetched_at=forecast_created_at - timedelta(hours=1),
                        known_at=forecast_created_at,
                        valid_at=forecast_created_at + timedelta(days=1),
                        forecast_horizon_hours=24,
                        raw_payload_hash="3" * 64,
                        normalized_payload_hash="4" * 64,
                    ),
                ),
            )

    with pytest.raises(ShadowForecastBlocked, match="WEATHER_SCOPE_UNBOUND"):
        async with sqlite_session.begin():
            await run_shadow_forecast(
                sqlite_session,
                ShadowForecastRequest(base_id=BASE_A, target_season="2026-2027"),
                authority=_authority(),
                weather_provider=WrongProvider(),
            )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "provider", "snapshots"),
    (
        ("CAPTURED", "test-as-issued", ()),
        (
            "FAILED",
            "test-as-issued",
            (
                WeatherForecastSnapshotInput(
                    weather_snapshot_id="invalid-failed-weather",
                    provider="test-as-issued",
                    base_id=BASE_A,
                    issued_at=NOW - timedelta(hours=2),
                    fetched_at=NOW - timedelta(hours=1),
                    known_at=NOW,
                    valid_at=NOW + timedelta(days=1),
                    forecast_horizon_hours=24,
                    temperature_mean=Decimal("18"),
                    raw_payload_hash="5" * 64,
                    normalized_payload_hash="6" * 64,
                ),
            ),
        ),
        (
            "UNAVAILABLE",
            "test-as-issued",
            (
                WeatherForecastSnapshotInput(
                    weather_snapshot_id="invalid-unavailable-weather",
                    provider="test-as-issued",
                    base_id=BASE_A,
                    issued_at=NOW - timedelta(hours=2),
                    fetched_at=NOW - timedelta(hours=1),
                    known_at=NOW,
                    valid_at=NOW + timedelta(days=1),
                    forecast_horizon_hours=24,
                    temperature_mean=Decimal("18"),
                    raw_payload_hash="7" * 64,
                    normalized_payload_hash="8" * 64,
                ),
            ),
        ),
    ),
)
async def test_invalid_capture_result_contract_fails_closed(
    sqlite_session: AsyncSession,
    fake_product: None,
    status: str,
    provider: str,
    snapshots: tuple[WeatherForecastSnapshotInput, ...],
) -> None:
    class InvalidProvider:
        provider_name = provider

        def capture(self, *, base, forecast_created_at, target_season):
            del base, forecast_created_at, target_season
            return WeatherForecastCaptureResult(
                status=status,
                provider=provider,
                snapshots=snapshots,
            )

    with pytest.raises(ShadowForecastBlocked, match="WEATHER_CAPTURE_RESULT_INVALID"):
        async with sqlite_session.begin():
            await run_shadow_forecast(
                sqlite_session,
                ShadowForecastRequest(base_id=BASE_A, target_season="2026-2027"),
                authority=_authority(),
                weather_provider=InvalidProvider(),
            )


@pytest.mark.unit
async def test_capture_result_rejects_snapshot_provider_mismatch(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    class MismatchedProvider:
        provider_name = "test-as-issued"

        def capture(self, *, base, forecast_created_at, target_season):
            del target_season
            return WeatherForecastCaptureResult(
                status="CAPTURED",
                provider=self.provider_name,
                snapshots=(
                    WeatherForecastSnapshotInput(
                        weather_snapshot_id="provider-mismatch-weather",
                        provider="different-provider",
                        base_id=base["base_id"],
                        issued_at=forecast_created_at - timedelta(hours=2),
                        fetched_at=forecast_created_at - timedelta(hours=1),
                        known_at=forecast_created_at,
                        valid_at=forecast_created_at + timedelta(days=1),
                        forecast_horizon_hours=24,
                        temperature_mean=Decimal("18"),
                        raw_payload_hash="9" * 64,
                        normalized_payload_hash="a" * 64,
                    ),
                ),
            )

    with pytest.raises(ShadowForecastBlocked, match="WEATHER_CAPTURE_RESULT_INVALID"):
        async with sqlite_session.begin():
            await run_shadow_forecast(
                sqlite_session,
                ShadowForecastRequest(base_id=BASE_A, target_season="2026-2027"),
                authority=_authority(),
                weather_provider=MismatchedProvider(),
            )


@pytest.mark.unit
async def test_same_pit_input_is_idempotent_and_no_older_history_fallback(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    authority = _authority()
    created = datetime.now(UTC).replace(microsecond=0)
    request = ShadowForecastRequest(
        base_id=BASE_A,
        target_season="2026-2027",
        target_area_mu=Decimal("100"),
        forecast_created_at=created,
        forecast_run_id="shadow-idempotent",
    )
    async with sqlite_session.begin():
        first = await run_shadow_forecast(sqlite_session, request, authority=authority)
        second = await run_shadow_forecast(sqlite_session, request, authority=authority)
    assert second.snapshot.forecast_run_id == first.snapshot.forecast_run_id
    assert second.snapshot.input_snapshot_hash == first.snapshot.input_snapshot_hash
    assert second.snapshot.result_hash == first.snapshot.result_hash

    with pytest.raises(ShadowForecastBlocked, match="PRIOR_HISTORY_NOT_AVAILABLE"):
        async with sqlite_session.begin():
            await run_shadow_forecast(
                sqlite_session,
                ShadowForecastRequest(
                    base_id=BASE_A,
                    target_season="2027-2028",
                ),
                authority=authority,
            )


@pytest.mark.unit
async def test_batch_is_registry_ordered_and_isolates_blocked_base(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    result = None
    async with sqlite_session.begin():
        result = await run_shadow_forecast_batch(
            sqlite_session,
            target_season="2026-2027",
            authority=_authority(),
        )
    assert result is not None
    assert [item.base_id for item in result.items] == sorted([BASE_A, BASE_B])
    assert result.total_base_count == 2
    assert result.success_count == 2
    assert result.blocked_count == 0
    assert result.failed_count == 0


@pytest.mark.unit
async def test_batch_reports_one_blocked_base_without_dropping_success(
    sqlite_session: AsyncSession,
    fake_product: None,
) -> None:
    source_authority = _authority()
    authority = replace(
        source_authority,
        experimental_prior_history={
            "bases": [source_authority.experimental_prior_history["bases"][0]]
        },
    )
    async with sqlite_session.begin():
        result = await run_shadow_forecast_batch(
            sqlite_session,
            target_season="2026-2027",
            authority=authority,
        )
        saved_ids = list(await sqlite_session.scalars(select(ForecastRunSnapshot.forecast_run_id)))
    assert result.total_base_count == 2
    assert result.success_count == 1
    assert result.blocked_count == 1
    assert result.failed_count == 0
    assert [item.base_id for item in result.items] == sorted([BASE_A, BASE_B])
    assert saved_ids == ["shadow-" + result.items[0].execution.snapshot.input_snapshot_hash[:40]]


@pytest.mark.unit
async def test_frozen_registry_batch_supports_all_39_bases(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.area_yield.base_product_authority import load_base_product_authority

    authority = load_base_product_authority()
    async with sqlite_session.begin():
        result = await run_shadow_forecast_batch(
            sqlite_session,
            target_season="2026-2027",
            authority=authority,
        )
    assert result.total_base_count == 39
    assert result.success_count == 39
    assert result.blocked_count == 0
    assert result.failed_count == 0
    assert [item.base_id for item in result.items] == sorted(authority.bases_by_id)


@pytest.mark.unit
def test_shadow_request_requires_one_base_identity() -> None:
    with pytest.raises(ValueError):
        ShadowForecastRequest(target_season="2026-2027")
    with pytest.raises(ValueError):
        ShadowForecastRequest(
            base_id=BASE_A,
            base_name="Alpha Base",
            target_season="2026-2027",
        )
