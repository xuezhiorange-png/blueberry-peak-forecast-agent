from __future__ import annotations

from httpx import AsyncClient

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload


async def test_default_authorization_provider_fails_closed(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 503
    assert response.json()["errors"][0]["code"] == "ACTUAL_HARVEST_AUTHORIZATION_UNAVAILABLE"


async def test_authorization_dependency_is_injectable(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    api_client._transport.app.dependency_overrides[get_actual_harvest_actor] = (  # type: ignore[attr-defined]
        lambda: authorized_actor
    )
    response = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json={"source_system": "farm-system"},
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "API_REQUEST_INVALID"
