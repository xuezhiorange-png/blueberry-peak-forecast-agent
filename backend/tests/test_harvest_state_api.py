from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.harvest_state.application import (
    HarvestStateDeliveryConflictError,
    HarvestStateDeliveryIntegrityError,
)
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.main import create_app
from backend.tests.harvest_state.conftest import make_request


@pytest.fixture
async def harvest_state_client(sqlite_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield sqlite_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _request_json() -> dict[str, object]:
    return Task9ARequest.model_validate(make_request()).model_dump(mode="json")


@pytest.mark.asyncio
async def test_post_completed_run(harvest_state_client: AsyncClient) -> None:
    response = await harvest_state_client.post(
        "/api/v1/harvest-state/runs",
        json=_request_json(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["output"]["status"] == "completed"


@pytest.mark.asyncio
async def test_post_blocked_run(harvest_state_client: AsyncClient) -> None:
    payload = _request_json()
    payload["farm_timezone"] = "Bad/Timezone"

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["output"]["blockers"] == ["INVALID_TIMEZONE"]


@pytest.mark.asyncio
async def test_post_repeated_request_returns_same_run_id(harvest_state_client: AsyncClient) -> None:
    first = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    second = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.asyncio
async def test_get_run_by_id_and_hash(harvest_state_client: AsyncClient) -> None:
    created = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]
    result_hash = created.json()["result_hash"]

    by_id = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}")
    by_hash = await harvest_state_client.get(
        f"/api/v1/harvest-state/runs/by-result-hash/{result_hash}"
    )

    assert by_id.status_code == 200
    assert by_hash.status_code == 200
    assert by_id.json() == created.json()
    assert by_hash.json() == created.json()


@pytest.mark.asyncio
async def test_get_missing_run_returns_404(harvest_state_client: AsyncClient) -> None:
    response = await harvest_state_client.get("/api/v1/harvest-state/runs/999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_RUN_NOT_FOUND",
            "message": "Harvest-state run was not found.",
        }
    }


@pytest.mark.asyncio
async def test_harvest_state_invalid_hash_uses_delivery_error_payload(
    harvest_state_client: AsyncClient,
) -> None:
    response = await harvest_state_client.get(
        "/api/v1/harvest-state/runs/by-result-hash/not-a-hash"
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_INPUT_ERROR",
            "message": "Harvest-state request is invalid.",
        }
    }
    assert "detail" not in response.json()


@pytest.mark.asyncio
async def test_harvest_state_invalid_body_uses_delivery_error_payload(
    harvest_state_client: AsyncClient,
) -> None:
    payload = _request_json()
    del payload["destination_factory_id"]

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_INPUT_ERROR",
            "message": "Harvest-state request is invalid.",
        }
    }
    assert "detail" not in response.json()


@pytest.mark.asyncio
async def test_harvest_state_invalid_run_id_uses_delivery_error_payload(
    harvest_state_client: AsyncClient,
) -> None:
    response = await harvest_state_client.get("/api/v1/harvest-state/runs/not-an-int")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_INPUT_ERROR",
            "message": "Harvest-state request is invalid.",
        }
    }
    assert "detail" not in response.json()


@pytest.mark.asyncio
async def test_validation_error_does_not_leak_internal_details(
    harvest_state_client: AsyncClient,
) -> None:
    response = await harvest_state_client.get(
        "/api/v1/harvest-state/runs/by-result-hash/not-a-hash"
    )

    body = response.json()
    serialized = str(body).lower()
    assert response.status_code == 422
    assert "detail" not in body
    assert "traceback" not in serialized
    assert "sqlalchemy" not in serialized
    assert "asyncpg" not in serialized


@pytest.mark.asyncio
async def test_non_harvest_state_validation_keeps_native_fastapi_payload(
    harvest_state_client: AsyncClient,
) -> None:
    response = await harvest_state_client.get("/api/v1/master-data/seasons", params={"limit": 0})

    body = response.json()
    serialized = str(body)
    assert response.status_code == 422
    assert "detail" in body
    assert "error" not in body
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" not in serialized
    assert "Harvest-state request is invalid." not in serialized


@pytest.mark.asyncio
async def test_non_harvest_state_path_validation_is_not_relabelled(
    harvest_state_client: AsyncClient,
) -> None:
    response = await harvest_state_client.get("/api/v1/master-data/seasons/not-an-int")

    body = response.json()
    serialized = str(body)
    assert response.status_code == 422
    assert "detail" in body
    assert "error" not in body
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" not in serialized
    assert "Harvest-state request is invalid." not in serialized


@pytest.mark.asyncio
async def test_json_and_csv_reports(harvest_state_client: AsyncClient) -> None:
    created = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]

    json_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.json")
    csv_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.csv")

    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    assert csv_report.status_code == 200
    assert csv_report.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(csv_report.content)) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "run.csv",
            "daily_pool_state_rows.csv",
            "daily_member_state_rows.csv",
            "cohort_transition_rows.csv",
            "future_arrival_schedule.csv",
            "source_ref_catalog.json",
            "warnings.csv",
            "blockers.csv",
        ]


@pytest.mark.asyncio
async def test_hash_conflict_returns_stable_error_payload(
    harvest_state_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_conflict(*args: object, **kwargs: object) -> object:
        raise HarvestStateDeliveryConflictError()

    monkeypatch.setattr(
        "backend.app.api.harvest_state.execute_harvest_state_run",
        _raise_conflict,
    )

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_CONFLICT",
            "message": "Harvest-state delivery detected a result-hash conflict.",
        }
    }


@pytest.mark.asyncio
async def test_integrity_error_returns_500_without_internal_details(
    harvest_state_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_integrity(*args: object, **kwargs: object) -> object:
        raise HarvestStateDeliveryIntegrityError("sqlalchemy asyncpg /tmp/path")

    monkeypatch.setattr(
        "backend.app.api.harvest_state.execute_harvest_state_run",
        _raise_integrity,
    )

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())

    body = response.json()
    serialized = str(body).lower()
    assert response.status_code == 500
    assert body == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_INTEGRITY_ERROR",
            "message": "Harvest-state delivery failed an integrity check.",
        }
    }
    assert "sqlalchemy" not in serialized
    assert "asyncpg" not in serialized
    assert "/tmp/path" not in serialized


@pytest.mark.asyncio
async def test_report_missing_run_uses_stable_error_payload(
    harvest_state_client: AsyncClient,
) -> None:
    for path in (
        "/api/v1/harvest-state/runs/999/report.json",
        "/api/v1/harvest-state/runs/999/report.csv",
    ):
        response = await harvest_state_client.get(path)
        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "HARVEST_STATE_RUN_NOT_FOUND",
                "message": "Harvest-state run was not found.",
            }
        }


def test_openapi_registers_harvest_state_routes() -> None:
    app = create_app()
    schema = app.openapi()

    assert "/api/v1/harvest-state/runs" in schema["paths"]
    assert "/api/v1/harvest-state/runs/{run_id}" in schema["paths"]
    assert "/api/v1/harvest-state/runs/by-result-hash/{result_hash}" in schema["paths"]
    assert "/api/v1/harvest-state/runs/{run_id}/report.json" in schema["paths"]
    assert "/api/v1/harvest-state/runs/{run_id}/report.csv" in schema["paths"]


def test_openapi_json_report_media_type() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/harvest-state/runs/{run_id}/report.json"]["get"]

    assert "application/json" in operation["responses"]["200"]["content"]


def test_openapi_csv_report_media_type_is_application_zip() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/harvest-state/runs/{run_id}/report.csv"]["get"]

    assert "application/zip" in operation["responses"]["200"]["content"]


def test_openapi_report_error_models() -> None:
    schema = create_app().openapi()
    for path in (
        "/api/v1/harvest-state/runs/{run_id}/report.json",
        "/api/v1/harvest-state/runs/{run_id}/report.csv",
    ):
        operation = schema["paths"][path]["get"]
        for status_code in ("404", "422", "500"):
            ref = operation["responses"][status_code]["content"]["application/json"]["schema"][
                "$ref"
            ]
            assert ref.endswith("/HarvestStateErrorResponse")


def test_openapi_operation_ids_are_unique() -> None:
    schema = create_app().openapi()
    operation_ids = []
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))


@pytest.mark.asyncio
async def test_report_content_disposition_is_stable(
    harvest_state_client: AsyncClient,
) -> None:
    created = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]

    json_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.json")
    csv_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.csv")

    assert json_report.headers["content-disposition"] == (
        f'attachment; filename="harvest-state-run-{run_id}.json"'
    )
    assert csv_report.headers["content-disposition"] == (
        f'attachment; filename="harvest-state-run-{run_id}.zip"'
    )
