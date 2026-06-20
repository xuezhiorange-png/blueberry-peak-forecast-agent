import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _require_postgres()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _create(client: AsyncClient, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(f"/api/v1/master-data/{resource}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


MASTER_DATA_CASES = [
    (
        "seasons",
        lambda: {"code": _unique("season"), "start_date": "2026-01-01", "end_date": "2026-04-30"},
        lambda item: {"code": f"{item['code']}-u"},
        "code",
    ),
    (
        "factories",
        lambda: {
            "code": _unique("factory"),
            "name": _unique("Factory"),
            "region_name": "Yunnan",
            "latitude": "24.123456",
            "longitude": "102.123456",
            "altitude_m": "1800.50",
            "active": True,
        },
        lambda item: {"region_name": "Updated Region", "active": False},
        "name",
    ),
    (
        "farms",
        lambda: {
            "name": _unique("Farm"),
            "latitude": "25.123456",
            "longitude": "103.123456",
            "altitude_m": "1900.00",
        },
        lambda item: {"altitude_m": "1950.25"},
        "name",
    ),
    (
        "varieties",
        lambda: {"code": _unique("variety"), "name": _unique("Variety")},
        lambda item: {"name": f"{item['name']} Updated"},
        "code",
    ),
    (
        "grades",
        lambda: {"code": _unique("grade"), "is_analysis_eligible_default": True},
        lambda item: {"is_analysis_eligible_default": False},
        "code",
    ),
]


@pytest.mark.parametrize(
    ("resource", "payload_factory", "update_factory", "unique_field"), MASTER_DATA_CASES
)
async def test_master_data_crud_and_conflict(
    client: AsyncClient,
    resource: str,
    payload_factory,
    update_factory,
    unique_field: str,
) -> None:
    payload = payload_factory()
    created = await _create(client, resource, payload)

    get_response = await client.get(f"/api/v1/master-data/{resource}/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]

    list_response = await client.get(
        f"/api/v1/master-data/{resource}", params={"limit": 10, "offset": 0}
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1
    assert any(item["id"] == created["id"] for item in list_response.json()["items"])

    conflict_payload = payload_factory()
    conflict_payload[unique_field] = payload[unique_field]
    conflict_response = await client.post(f"/api/v1/master-data/{resource}", json=conflict_payload)
    assert conflict_response.status_code == 409

    update_response = await client.patch(
        f"/api/v1/master-data/{resource}/{created['id']}",
        json=update_factory(created),
    )
    assert update_response.status_code == 200

    not_found_response = await client.get(f"/api/v1/master-data/{resource}/999999999")
    assert not_found_response.status_code == 404

    invalid_response = await client.post(f"/api/v1/master-data/{resource}", json={})
    assert invalid_response.status_code == 422

    delete_response = await client.delete(f"/api/v1/master-data/{resource}/{created['id']}")
    assert delete_response.status_code == 204


async def test_subfarm_crud_filters_and_farm_delete_conflict(client: AsyncClient) -> None:
    farm = await _create(client, "farms", {"name": _unique("Farm")})
    payload = {"farm_id": farm["id"], "name": _unique("Block"), "altitude_m": "1850.00"}
    subfarm = await _create(client, "subfarms", payload)

    get_response = await client.get(f"/api/v1/master-data/subfarms/{subfarm['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == subfarm["id"]

    list_response = await client.get("/api/v1/master-data/subfarms", params={"farm_id": farm["id"]})
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [subfarm["id"]]

    update_response = await client.patch(
        f"/api/v1/master-data/subfarms/{subfarm['id']}",
        json={"altitude_m": "1860.00"},
    )
    assert update_response.status_code == 200

    conflict_response = await client.post("/api/v1/master-data/subfarms", json=payload)
    assert conflict_response.status_code == 409

    missing_fk_response = await client.post(
        "/api/v1/master-data/subfarms",
        json={"farm_id": 999999999, "name": _unique("Block")},
    )
    assert missing_fk_response.status_code == 409

    not_found_response = await client.get("/api/v1/master-data/subfarms/999999999")
    assert not_found_response.status_code == 404

    invalid_response = await client.post("/api/v1/master-data/subfarms", json={})
    assert invalid_response.status_code == 422

    farm_delete_response = await client.delete(f"/api/v1/master-data/farms/{farm['id']}")
    assert farm_delete_response.status_code == 409

    subfarm_delete_response = await client.delete(f"/api/v1/master-data/subfarms/{subfarm['id']}")
    assert subfarm_delete_response.status_code == 204

    farm_delete_response = await client.delete(f"/api/v1/master-data/farms/{farm['id']}")
    assert farm_delete_response.status_code == 204


async def test_holiday_crud_filters_and_constraints(client: AsyncClient) -> None:
    season = await _create(
        client,
        "seasons",
        {"code": _unique("season"), "start_date": "2026-01-01", "end_date": "2026-04-30"},
    )
    payload = {
        "season_id": season["id"],
        "code": _unique("holiday"),
        "name": "春节窗口",
        "start_date": "2026-02-10",
        "end_date": "2026-02-17",
        "region_name": "Yunnan",
        "active": True,
    }
    holiday = await _create(client, "holidays", payload)

    get_response = await client.get(f"/api/v1/master-data/holidays/{holiday['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == holiday["id"]

    list_response = await client.get(
        "/api/v1/master-data/holidays",
        params={"season_id": season["id"], "region_name": "Yunnan", "active": True},
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [holiday["id"]]

    update_response = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"active": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["active"] is False

    conflict_response = await client.post("/api/v1/master-data/holidays", json=payload)
    assert conflict_response.status_code == 409

    missing_season_response = await client.post(
        "/api/v1/master-data/holidays",
        json={**payload, "season_id": 999999999, "code": _unique("holiday")},
    )
    assert missing_season_response.status_code == 409

    invalid_dates_response = await client.post(
        "/api/v1/master-data/holidays",
        json={
            **payload,
            "code": _unique("holiday"),
            "start_date": "2026-02-20",
            "end_date": "2026-02-10",
        },
    )
    assert invalid_dates_response.status_code == 422

    not_found_response = await client.get("/api/v1/master-data/holidays/999999999")
    assert not_found_response.status_code == 404

    invalid_response = await client.post("/api/v1/master-data/holidays", json={})
    assert invalid_response.status_code == 422

    delete_response = await client.delete(f"/api/v1/master-data/holidays/{holiday['id']}")
    assert delete_response.status_code == 204


async def test_factory_active_filter_and_pagination_stable_order(client: AsyncClient) -> None:
    active_factory = await _create(
        client,
        "factories",
        {"code": _unique("factory"), "name": _unique("Factory"), "active": True},
    )
    inactive_factory = await _create(
        client,
        "factories",
        {"code": _unique("factory"), "name": _unique("Factory"), "active": False},
    )

    active_response = await client.get(
        "/api/v1/master-data/factories", params={"active": True, "limit": 100}
    )
    assert active_response.status_code == 200
    active_ids = [item["id"] for item in active_response.json()["items"]]
    assert active_factory["id"] in active_ids
    assert inactive_factory["id"] not in active_ids
    assert active_ids == sorted(active_ids)

    page_response = await client.get(
        "/api/v1/master-data/factories", params={"limit": 1, "offset": 0}
    )
    assert page_response.status_code == 200
    assert len(page_response.json()["items"]) <= 1


async def test_coordinate_and_date_validation(client: AsyncClient) -> None:
    bad_season = await client.post(
        "/api/v1/master-data/seasons",
        json={"code": _unique("season"), "start_date": "2026-05-01", "end_date": "2026-01-01"},
    )
    assert bad_season.status_code == 422

    bad_farm = await client.post(
        "/api/v1/master-data/farms",
        json={"name": _unique("Farm"), "latitude": "91", "longitude": "103"},
    )
    assert bad_farm.status_code == 422


async def test_season_patch_single_date_range_validation(client: AsyncClient) -> None:
    season = await _create(
        client,
        "seasons",
        {"code": _unique("season"), "start_date": "2026-01-01", "end_date": "2026-04-30"},
    )

    invalid_start = await client.patch(
        f"/api/v1/master-data/seasons/{season['id']}",
        json={"start_date": "2026-05-01"},
    )
    assert invalid_start.status_code == 422

    invalid_end = await client.patch(
        f"/api/v1/master-data/seasons/{season['id']}",
        json={"end_date": "2025-12-31"},
    )
    assert invalid_end.status_code == 422

    valid_start = await client.patch(
        f"/api/v1/master-data/seasons/{season['id']}",
        json={"start_date": "2026-01-15"},
    )
    assert valid_start.status_code == 200
    assert valid_start.json()["start_date"] == "2026-01-15"

    valid_end = await client.patch(
        f"/api/v1/master-data/seasons/{season['id']}",
        json={"end_date": "2026-05-15"},
    )
    assert valid_end.status_code == 200
    assert valid_end.json()["end_date"] == "2026-05-15"


async def test_holiday_patch_single_date_range_validation(client: AsyncClient) -> None:
    season = await _create(
        client,
        "seasons",
        {"code": _unique("season"), "start_date": "2026-01-01", "end_date": "2026-04-30"},
    )
    holiday = await _create(
        client,
        "holidays",
        {
            "season_id": season["id"],
            "code": _unique("holiday"),
            "name": "春节窗口",
            "start_date": "2026-02-10",
            "end_date": "2026-02-17",
        },
    )

    invalid_start = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"start_date": "2026-02-18"},
    )
    assert invalid_start.status_code == 422

    invalid_end = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"end_date": "2026-02-09"},
    )
    assert invalid_end.status_code == 422

    valid_start = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"start_date": "2026-02-11"},
    )
    assert valid_start.status_code == 200
    assert valid_start.json()["start_date"] == "2026-02-11"

    valid_end = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"end_date": "2026-02-18"},
    )
    assert valid_end.status_code == 200
    assert valid_end.json()["end_date"] == "2026-02-18"


async def test_referenced_season_and_patch_missing_foreign_keys_return_conflict(
    client: AsyncClient,
) -> None:
    season = await _create(
        client,
        "seasons",
        {"code": _unique("season"), "start_date": "2026-01-01", "end_date": "2026-04-30"},
    )
    holiday = await _create(
        client,
        "holidays",
        {
            "season_id": season["id"],
            "code": _unique("holiday"),
            "name": "春节窗口",
            "start_date": "2026-02-10",
            "end_date": "2026-02-17",
        },
    )
    farm = await _create(client, "farms", {"name": _unique("Farm")})
    subfarm = await _create(client, "subfarms", {"farm_id": farm["id"], "name": _unique("Block")})

    season_delete = await client.delete(f"/api/v1/master-data/seasons/{season['id']}")
    assert season_delete.status_code == 409

    subfarm_missing_farm = await client.patch(
        f"/api/v1/master-data/subfarms/{subfarm['id']}",
        json={"farm_id": 999999999},
    )
    assert subfarm_missing_farm.status_code == 409

    holiday_missing_season = await client.patch(
        f"/api/v1/master-data/holidays/{holiday['id']}",
        json={"season_id": 999999999},
    )
    assert holiday_missing_season.status_code == 409
