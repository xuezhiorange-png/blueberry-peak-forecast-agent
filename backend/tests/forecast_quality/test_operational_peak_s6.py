"""S6 authority, application and persistence contract tests."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.area_yield.data import digest
from backend.app.forecast_quality import operational_peak_authority as authority_module
from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    forecast_operational_peak,
)
from backend.app.forecast_quality.operational_peak_application import (
    execute_operational_peak_forecast_run,
)
from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
    load_operational_peak_authority,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceIntegrityError,
    OperationalPeakRunRepository,
)
from backend.app.models.operational_peak import (
    OperationalPeakForecastDaily,
    OperationalPeakForecastRun,
)


def _authority_payload() -> dict[str, object]:
    registry: dict[str, object] = {
        "bases": [
            {
                "base_id": "base-yangliu",
                "canonical_base_name": "保山杨柳基地",
                "productive_area_mu": "394.000000",
                "active": True,
            }
        ],
        "enrichment_hashes": {},
        "source_hash": "source-s6",
        "version": "BASE_REGISTRY_V1",
    }
    registry["hash"] = digest({key: value for key, value in registry.items()})
    profile: dict[str, object] = {
        "available_bins": list(range(42)),
        "fold_id": "B",
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {str(index): "1.000000000000" for index in range(42)},
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "train_row_set_hash": "train-s6",
        "validation_labels_used": False,
    }
    payload: dict[str, object] = {
        "authority_version": "OPERATIONAL_PEAK_AUTHORITY_V1",
        "policy_version": "OPERATIONAL_PEAK_POLICY_V1",
        "baseline_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "base_registry_payload_hash": registry["hash"],
        "base_registry_file_sha256": "0" * 64,
        "base_registry_payload": registry,
        "bases": registry["bases"],
        "reference_profile_fold": "B",
        "reference_profile_file_sha256": "1" * 64,
        "reference_profile_payload": profile,
        "weather_used": False,
    }
    payload["authority_hash"] = digest(payload)
    return payload


@pytest.fixture
def authority(tmp_path, monkeypatch):
    payload = _authority_payload()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    path = tmp_path / "operational-peak-authority.json"
    path.write_bytes(raw)
    monkeypatch.setattr(
        authority_module, "REGISTRY_FILE_SHA256", payload["base_registry_file_sha256"]
    )
    monkeypatch.setattr(
        authority_module, "REGISTRY_PAYLOAD_HASH", payload["base_registry_payload_hash"]
    )
    monkeypatch.setattr(
        authority_module,
        "REFERENCE_PROFILE_FILE_SHA256",
        payload["reference_profile_file_sha256"],
    )
    monkeypatch.setenv("OPERATIONAL_PEAK_AUTHORITY_PATH", str(path))
    monkeypatch.setenv("OPERATIONAL_PEAK_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    return payload


@pytest.fixture
async def factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/operational-peak.db",
        connect_args={"autocommit": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(OperationalPeakForecastRun.__table__.create)
        await connection.run_sync(OperationalPeakForecastDaily.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def request() -> OperationalPeakForecastRequest:
    return OperationalPeakForecastRequest("base-yangliu", "2026-2027", date(2027, 3, 31))


async def test_authority_is_hash_pinned_and_s5_parity_is_preserved(authority):
    snapshot = load_operational_peak_authority()
    assert snapshot.authority_hash == authority["authority_hash"]
    assert snapshot.policy_version == "OPERATIONAL_PEAK_POLICY_V1"
    assert snapshot.baseline_id == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    assert snapshot.weather_used is False


@pytest.mark.parametrize("failure", ["missing", "file", "payload"])
async def test_authority_fail_closed(authority, monkeypatch, failure):
    if failure == "missing":
        monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_PATH")
    elif failure == "file":
        monkeypatch.setenv("OPERATIONAL_PEAK_AUTHORITY_SHA256", "0" * 64)
    else:
        monkeypatch.setattr(authority_module, "BASELINE_ID", "changed")
    with pytest.raises(OperationalPeakAuthorityError):
        load_operational_peak_authority()


async def test_create_reload_idempotency_and_authority_independent_read(
    factory, authority, monkeypatch
):
    async with factory() as session:
        async with session.begin():
            first = await execute_operational_peak_forecast_run(session, request())
        snapshot = load_operational_peak_authority()
        direct = forecast_operational_peak(request(), snapshot.registry, snapshot.reference_profile)
        assert first.result["result_hash"] == direct.result_hash
        assert first.result["forecast_7d"]["total_kg"] == "2758.000000"
        assert first.result["forecast_15d"]["total_kg"] == "5910.000000"
        async with session.begin():
            second = await execute_operational_peak_forecast_run(session, request())
        assert second.reused_existing_run is True
        assert second.run.run_id == first.run.run_id
        assert (
            await session.scalar(select(func.count()).select_from(OperationalPeakForecastDaily))
            == 15
        )
        monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_PATH")
        loaded = await OperationalPeakRunRepository(session).get(first.run.run_id)
        assert loaded.result == first.result


async def test_reload_rejects_child_corruption(factory, authority):
    async with factory() as session:
        async with session.begin():
            saved = await execute_operational_peak_forecast_run(session, request())
        async with session.begin():
            await session.execute(
                update(OperationalPeakForecastDaily)
                .where(OperationalPeakForecastDaily.run_id == saved.run.run_id)
                .where(OperationalPeakForecastDaily.row_index == 2)
                .values(predicted_kg=Decimal("999"))
            )
        with pytest.raises(OperationalPeakPersistenceIntegrityError):
            await OperationalPeakRunRepository(session).get(saved.run.run_id)


async def test_rerun_scope_is_same_base_season_origin(factory, authority):
    async with factory() as session:
        async with session.begin():
            parent = await execute_operational_peak_forecast_run(session, request())
        async with session.begin():
            child = await execute_operational_peak_forecast_run(
                session,
                request(),
                rerun_of_run_id=parent.run.run_id,
            )
        assert child.reused_existing_run is True
