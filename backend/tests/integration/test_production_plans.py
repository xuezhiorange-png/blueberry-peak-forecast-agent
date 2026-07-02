from __future__ import annotations

import asyncio
import csv
import os
from collections.abc import AsyncIterator
from datetime import date
from numbers import Integral
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.main import create_app
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.planning.plan_config import load_production_plan_config
from backend.app.planning.plan_importer import import_production_plans_csv
from backend.app.planning.plan_schemas import (
    ProductionPlanIntervalConflictError,
    ProductionPlanVersionConflictError,
)
from backend.app.planning.plan_service import (
    create_plan_version,
    create_replacement_version,
    get_effective_plan,
)

pytestmark = [pytest.mark.integration]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _require_postgres()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _seed_master_data() -> dict[str, int]:
    async with AsyncSessionMaker() as session:
        season = Season(code="2025-2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        farm = Farm(name="农场A")
        variety = Variety(code="DX", name="Dx")
        session.add_all([season, farm, variety])
        await session.flush()
        subfarm = Subfarm(farm_id=farm.id, name="分场A")
        session.add(subfarm)
        await session.commit()
        return {
            "season_id": season.id,
            "farm_id": farm.id,
            "subfarm_id": subfarm.id,
            "variety_id": variety.id,
        }


def _payload(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "farm_id": ids["farm_id"],
        "subfarm_id": None,
        "season_id": ids["season_id"],
        "variety_id": ids["variety_id"],
        "planted_area_mu": "100",
        "expected_yield_kg_per_mu": "1000",
        "marketable_rate": "0.7",
        "tree_age_years": "3",
        "pruning_date": "2025-12-20",
        "flowering_start_date": "2026-02-01",
        "flowering_peak_date": "2026-02-10",
        "flowering_end_date": "2026-02-20",
        "first_pick_date": "2026-03-01",
        "expected_total_marketable_kg": "70000",
        "version": 1,
        "effective_from": "2026-01-01",
        "effective_to": None,
        "available_at": "2025-12-01",
        "source_type": "manual",
        "source_name": "planner",
        "source_version": "v1",
        "notes": "baseline",
    }
    payload.update(overrides)
    return payload


async def test_create_history_effective_and_idempotent_api(client: AsyncClient) -> None:
    ids = await _seed_master_data()
    payload = _payload(ids)

    create_response = await client.post("/planning/production-plans", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["planted_area_mu"] == "100"
    assert created["expected_yield_kg_per_mu"] == "1000"
    assert created["marketable_rate"] == "0.7"
    assert created["derived_total_marketable_kg"] == "70000"
    assert created["total_difference_kg"] == "0"
    assert created["warnings"] == []

    duplicate_response = await client.post("/planning/production-plans", json=payload)
    assert duplicate_response.status_code == 200
    assert duplicate_response.json() == created

    get_response = await client.get(f"/planning/production-plans/{created['plan_id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created

    history_response = await client.get(
        "/planning/production-plans/history",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
        },
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert history["total"] == 1
    assert history["items"][0] == created

    effective_response = await client.get(
        "/planning/production-plans/effective",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-01-05",
        },
    )
    assert effective_response.status_code == 200
    assert effective_response.json() == created


async def test_create_plan_validates_rate_and_dates(client: AsyncClient) -> None:
    ids = await _seed_master_data()

    invalid_rate = await client.post(
        "/planning/production-plans",
        json=_payload(ids, marketable_rate="1.5"),
    )
    assert invalid_rate.status_code == 422

    invalid_dates = await client.post(
        "/planning/production-plans",
        json=_payload(ids, flowering_start_date="2026-02-11", flowering_peak_date="2026-02-10"),
    )
    assert invalid_dates.status_code == 422


async def test_effective_plan_respects_available_at_and_effective_from(client: AsyncClient) -> None:
    ids = await _seed_master_data()
    await client.post(
        "/planning/production-plans",
        json=_payload(
            ids,
            version=1,
            effective_from="2026-01-01",
            available_at="2026-02-01",
        ),
    )
    await client.post(
        "/planning/production-plans",
        json=_payload(
            ids,
            version=2,
            effective_from="2026-03-01",
            available_at="2026-02-01",
            expected_total_marketable_kg="71000",
        ),
    )

    before_available = await client.get(
        "/planning/production-plans/effective",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-01-15",
        },
    )
    assert before_available.status_code == 404

    before_effective = await client.get(
        "/planning/production-plans/effective",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-02-15",
        },
    )
    assert before_effective.status_code == 200
    assert before_effective.json()["version"] == 1


async def test_replace_plan_closes_old_version_and_preserves_history(client: AsyncClient) -> None:
    ids = await _seed_master_data()
    first = (await client.post("/planning/production-plans", json=_payload(ids))).json()

    replace_response = await client.post(
        f"/planning/production-plans/{first['plan_id']}/replace",
        json=_payload(
            ids,
            version=2,
            effective_from="2026-03-01",
            available_at="2026-02-20",
            expected_total_marketable_kg="80000",
        ),
    )
    assert replace_response.status_code == 200
    replaced = replace_response.json()
    assert replaced["version"] == 2

    old_plan = await client.get(f"/planning/production-plans/{first['plan_id']}")
    assert old_plan.status_code == 200
    assert old_plan.json()["effective_to"] == "2026-03-01"

    old_effective = await client.get(
        "/planning/production-plans/effective",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-02-25",
        },
    )
    assert old_effective.status_code == 200
    assert old_effective.json()["plan_id"] == first["plan_id"]

    new_effective = await client.get(
        "/planning/production-plans/effective",
        params={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_id"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-03-05",
        },
    )
    assert new_effective.status_code == 200
    assert new_effective.json()["plan_id"] == replaced["plan_id"]


async def test_version_and_interval_conflicts_return_409(client: AsyncClient) -> None:
    ids = await _seed_master_data()
    created = await client.post("/planning/production-plans", json=_payload(ids))
    assert created.status_code == 201

    version_conflict = await client.post(
        "/planning/production-plans",
        json=_payload(ids, expected_total_marketable_kg="71000"),
    )
    assert version_conflict.status_code == 409
    assert "version" in version_conflict.text.lower()

    interval_conflict = await client.post(
        "/planning/production-plans",
        json=_payload(
            ids,
            version=2,
            effective_from="2026-01-15",
            expected_total_marketable_kg="72000",
        ),
    )
    assert interval_conflict.status_code == 409
    assert "interval" in interval_conflict.text.lower()


def _write_import_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "farm_code",
                "farm_name",
                "subfarm_code",
                "subfarm_name",
                "season_code",
                "variety_code",
                "planted_area_mu",
                "expected_yield_kg_per_mu",
                "marketable_rate",
                "tree_age_years",
                "pruning_date",
                "flowering_start_date",
                "flowering_peak_date",
                "flowering_end_date",
                "first_pick_date",
                "expected_total_marketable_kg",
                "version",
                "effective_from",
                "effective_to",
                "available_at",
                "source_type",
                "source_name",
                "source_version",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "farm_code": "",
                "farm_name": "农场A",
                "subfarm_code": "",
                "subfarm_name": "",
                "season_code": "2025-2026",
                "variety_code": "DX",
                "planted_area_mu": "100",
                "expected_yield_kg_per_mu": "1000",
                "marketable_rate": "0.7",
                "tree_age_years": "3",
                "pruning_date": "2025-12-20",
                "flowering_start_date": "2026-02-01",
                "flowering_peak_date": "2026-02-10",
                "flowering_end_date": "2026-02-20",
                "first_pick_date": "2026-03-01",
                "expected_total_marketable_kg": "70000",
                "version": "1",
                "effective_from": "2026-01-01",
                "effective_to": "",
                "available_at": "2025-12-01",
                "source_type": "import",
                "source_name": "csv",
                "source_version": "csv-v1",
                "notes": "",
            }
        )


async def test_importer_dry_run_and_idempotent_reimport(tmp_path: Path) -> None:
    _require_postgres()
    ids = await _seed_master_data()
    del ids
    csv_path = tmp_path / "production_plans.csv"
    _write_import_csv(csv_path)
    config = load_production_plan_config(Path("configs/production_plan.yaml"))

    async with AsyncSessionMaker() as session:
        dry_run = await import_production_plans_csv(
            session,
            file_path=csv_path,
            config=config,
            dry_run=True,
        )
        count_after_dry_run = await session.scalar(select(func.count(FarmSeasonVarietyPlan.id)))
        assert dry_run.status == "dry_run"
        assert dry_run.inserted_count == 1
        assert count_after_dry_run == 0

    async with AsyncSessionMaker() as session:
        first = await import_production_plans_csv(
            session,
            file_path=csv_path,
            config=config,
            dry_run=False,
        )
        second = await import_production_plans_csv(
            session,
            file_path=csv_path,
            config=config,
            dry_run=False,
        )
        count_after_import = await session.scalar(select(func.count(FarmSeasonVarietyPlan.id)))

    assert first.status == "completed"
    assert first.inserted_count == 1
    assert second.status == "completed"
    assert second.skipped_count == 1
    assert second.duplicate_count == 1
    assert count_after_import == 1


@pytest.mark.postgres_concurrency
async def test_concurrent_create_overlapping_versions_serializes_by_business_key() -> None:
    _require_postgres()
    ids = await _seed_master_data()
    config = load_production_plan_config(Path("configs/production_plan.yaml"))

    async def create(payload: dict[str, Any]) -> int:
        async with AsyncSessionMaker() as session:
            result = await create_plan_version(session, payload=payload, config=config)
            return result.record.id

    first_result, second_result = await asyncio.gather(
        create(_payload(ids, version=1)),
        create(
            _payload(
                ids,
                version=2,
                effective_from="2026-01-15",
                expected_total_marketable_kg="72000",
            )
        ),
        return_exceptions=True,
    )

    success_ids = [
        int(value)
        for value in (first_result, second_result)
        if isinstance(value, Integral) and not isinstance(value, bool)
    ]
    errors = [
        value
        for value in (first_result, second_result)
        if isinstance(value, ProductionPlanIntervalConflictError)
    ]
    unexpected = [
        f"{type(value).__name__}: {value!r}"
        for value in (first_result, second_result)
        if not (isinstance(value, Integral) and not isinstance(value, bool))
        and not isinstance(value, ProductionPlanIntervalConflictError)
    ]

    assert len(success_ids) == 1, unexpected
    assert len(errors) == 1, unexpected

    async with AsyncSessionMaker() as session:
        count = await session.scalar(select(func.count(FarmSeasonVarietyPlan.id)))
        effective = await get_effective_plan(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_id"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 2, 1),
            config=config,
        )

    assert count == 1
    assert effective.id == success_ids[0]


@pytest.mark.postgres_concurrency
async def test_concurrent_replace_same_current_plan_conflicts_without_overlap_history() -> None:
    _require_postgres()
    ids = await _seed_master_data()
    config = load_production_plan_config(Path("configs/production_plan.yaml"))

    async with AsyncSessionMaker() as session:
        created = await create_plan_version(
            session,
            payload=_payload(ids, version=1),
            config=config,
        )
    current_plan_id = created.record.id

    async def replace(version: int, effective_from: str, total: str) -> int:
        async with AsyncSessionMaker() as session:
            result = await create_replacement_version(
                session,
                plan_id=current_plan_id,
                payload=_payload(
                    ids,
                    version=version,
                    effective_from=effective_from,
                    available_at="2026-02-20",
                    expected_total_marketable_kg=total,
                ),
                config=config,
            )
            return result.record.id

    first_result, second_result = await asyncio.gather(
        replace(2, "2026-03-01", "80000"),
        replace(3, "2026-03-15", "82000"),
        return_exceptions=True,
    )

    success_ids = [
        int(value)
        for value in (first_result, second_result)
        if isinstance(value, Integral) and not isinstance(value, bool)
    ]
    errors = [
        value
        for value in (first_result, second_result)
        if isinstance(value, ProductionPlanIntervalConflictError)
    ]
    unexpected = [
        f"{type(value).__name__}: {value!r}"
        for value in (first_result, second_result)
        if not (isinstance(value, Integral) and not isinstance(value, bool))
        and not isinstance(value, ProductionPlanIntervalConflictError)
    ]

    assert len(success_ids) == 1, unexpected
    assert len(errors) == 1, unexpected

    async with AsyncSessionMaker() as session:
        rows = (
            await session.scalars(
                select(FarmSeasonVarietyPlan).order_by(FarmSeasonVarietyPlan.version.asc())
            )
        ).all()

    assert len(rows) == 2
    assert rows[0].version == 1
    assert rows[1].id == success_ids[0]
    # The winner is whichever replacement acquires the business-key lock first.
    # The old open-ended version must close exactly at that winning replacement's
    # effective_from boundary, regardless of whether version 2 or version 3 wins.
    assert rows[0].effective_to == rows[1].effective_from


async def test_non_overlapping_versions_still_create_successfully() -> None:
    _require_postgres()
    ids = await _seed_master_data()
    config = load_production_plan_config(Path("configs/production_plan.yaml"))

    async with AsyncSessionMaker() as session:
        first = await create_plan_version(
            session,
            payload=_payload(ids, version=1, effective_to="2026-02-01"),
            config=config,
        )
        second = await create_plan_version(
            session,
            payload=_payload(
                ids,
                version=2,
                effective_from="2026-02-01",
                expected_total_marketable_kg="71000",
            ),
            config=config,
        )

    assert first.created
    assert second.created


async def test_database_conflict_is_translated_and_session_remains_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    ids = await _seed_master_data()
    config = load_production_plan_config(Path("configs/production_plan.yaml"))

    from backend.app.planning import plan_service as service_module

    original_create = service_module.create_plan

    async def broken_create(*args: Any, **kwargs: Any) -> FarmSeasonVarietyPlan:
        raise IntegrityError("insert", {}, Exception("unique violation"))

    monkeypatch.setattr(service_module, "create_plan", broken_create)

    async with AsyncSessionMaker() as session:
        with pytest.raises(ProductionPlanVersionConflictError):
            await create_plan_version(session, payload=_payload(ids), config=config)

        count_after_failure = await session.scalar(select(func.count(FarmSeasonVarietyPlan.id)))

    assert count_after_failure == 0

    monkeypatch.setattr(service_module, "create_plan", original_create)

    async with AsyncSessionMaker() as session:
        result = await create_plan_version(session, payload=_payload(ids), config=config)

    assert result.created
