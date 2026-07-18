from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload, _record_payload


async def test_api_routes_are_registered_and_unimplemented_routes_are_not_faked(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    payload = _create_payload()
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=payload,
        headers={"content-type": "application/json"},
    )
    assert created.status_code == 201
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    assert created.json()["data_or_null"]["batch"]["status"] == "UPLOADING"
    appended = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [_record_payload()]},
        headers={"content-type": "application/json"},
    )
    assert appended.status_code == 200
    assert appended.json()["data_or_null"]["batch"]["record_count"] == 1
    sealed = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/seal",
        json={},
        headers={"content-type": "application/json"},
    )
    assert sealed.status_code == 200
    assert sealed.json()["data_or_null"]["batch"]["status"] == "SEALED"
    fetched = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}")
    assert fetched.status_code == 200
    assert "id" not in fetched.json()["data_or_null"]["batch"]
    cancelled = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/cancel",
        json={},
        headers={"content-type": "application/json"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data_or_null"]["batch"]["status"] == "CANCELLED"
    assert (
        await api_client.post(f"/api/v1/actual-harvest/imports/{import_id}/validate")
    ).status_code == 404
    assert (
        await api_client.post(f"/api/v1/actual-harvest/imports/{import_id}/commit")
    ).status_code == 404


async def test_api_hides_batches_outside_actor_source_scope(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: ActualHarvestActorContext(
        identity="other-operator",
        allowed_source_systems=frozenset({"other-system"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_preview=True,
    )
    response = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "IMPORT_BATCH_NOT_FOUND"


@pytest.mark.parametrize("operation", ["seal", "cancel"])
async def test_terminal_routes_require_empty_json_object(
    api_client: AsyncClient,
    authorized_actor,
    operation: str,
) -> None:
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    path = f"/api/v1/actual-harvest/imports/not-found/{operation}"

    extra = await api_client.post(
        path,
        json={"unexpected": True},
        headers={"content-type": "application/json"},
    )
    assert extra.status_code == 422
    assert extra.json()["errors"][0]["code"] == "API_REQUEST_INVALID"

    missing_content_type = await api_client.post(path, content=b"{}")
    assert missing_content_type.status_code == 415
    assert missing_content_type.json()["errors"][0]["code"] == "API_CONTENT_TYPE_UNSUPPORTED"

    unsupported = await api_client.post(
        path,
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["errors"][0]["code"] == "API_CONTENT_TYPE_UNSUPPORTED"

    empty = await api_client.post(
        path,
        content=b"",
        headers={"content-type": "application/json"},
    )
    assert empty.status_code == 422
    assert empty.json()["errors"][0]["code"] == "API_REQUEST_INVALID"


def test_terminal_routes_publish_empty_json_request_bodies(api_client: AsyncClient) -> None:
    schema = api_client._transport.app.openapi()  # type: ignore[attr-defined]
    for operation in ("seal", "cancel"):
        request_body = schema["paths"][f"/api/v1/actual-harvest/imports/{{import_id}}/{operation}"][
            "post"
        ]["requestBody"]
        assert request_body["required"] is True
        assert "application/json" in request_body["content"]
