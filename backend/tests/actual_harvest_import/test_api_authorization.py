from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.tests.actual_harvest_import.test_api_schemas import (
    _create_payload,
    _record_payload,
)


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


def _operation_request(client: AsyncClient, operation: str, import_id: str):
    path = f"/api/v1/actual-harvest/imports/{import_id}"
    if operation == "get":
        return client.get(path)
    if operation == "preview":
        return client.get(f"{path}/preview", params={"page_size": 1})
    if operation == "append":
        return client.post(
            f"{path}/records",
            json={"records": [_record_payload()]},
            headers={"content-type": "application/json"},
        )
    if operation in {"seal", "cancel"}:
        return client.post(
            f"{path}/{operation}",
            json={},
            headers={"content-type": "application/json"},
        )
    raise AssertionError(f"unknown operation: {operation}")


async def _create_authorized_batch(api_client: AsyncClient, actor) -> str:
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: actor
    payload = _create_payload()
    payload["expected_record_count_or_null"] = None
    response = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    return response.json()["data_or_null"]["batch"]["import_id"]


@pytest.mark.parametrize("operation", ["get", "preview", "append", "seal", "cancel"])
async def test_same_source_different_actor_is_hidden_for_every_operation(
    api_client: AsyncClient,
    authorized_actor,
    operation: str,
) -> None:
    import_id = await _create_authorized_batch(api_client, authorized_actor)
    other_actor = ActualHarvestActorContext(
        identity="operator-2",
        allowed_source_systems=frozenset({"farm-system"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_create=True,
        may_append=True,
        may_preview=True,
        may_seal=True,
        may_cancel=True,
    )
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: other_actor

    response = await _operation_request(api_client, operation, import_id)

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "IMPORT_BATCH_NOT_FOUND"


@pytest.mark.parametrize("operation", ["get", "preview", "append", "seal", "cancel"])
async def test_same_actor_with_operation_permission_is_allowed(
    api_client: AsyncClient,
    authorized_actor,
    operation: str,
) -> None:
    import_id = await _create_authorized_batch(api_client, authorized_actor)

    response = await _operation_request(api_client, operation, import_id)

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("operation", "permission"),
    [
        ("get", "may_preview"),
        ("preview", "may_preview"),
        ("append", "may_append"),
        ("seal", "may_seal"),
        ("cancel", "may_cancel"),
    ],
)
async def test_same_actor_without_operation_permission_is_forbidden(
    api_client: AsyncClient,
    authorized_actor,
    operation: str,
    permission: str,
) -> None:
    import_id = await _create_authorized_batch(api_client, authorized_actor)
    denied_actor = authorized_actor.model_copy(update={permission: False})
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: denied_actor

    response = await _operation_request(api_client, operation, import_id)

    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "ACTUAL_HARVEST_SCOPE_FORBIDDEN"


async def test_different_source_same_actor_is_hidden(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    import_id = await _create_authorized_batch(api_client, authorized_actor)
    other_source_actor = authorized_actor.model_copy(
        update={"allowed_source_systems": frozenset({"other-system"})}
    )
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: other_source_actor

    response = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}")

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "IMPORT_BATCH_NOT_FOUND"


async def test_preview_only_actor_cannot_read_validation_errors(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    import_id = await _create_authorized_batch(api_client, authorized_actor)
    preview_only = authorized_actor.model_copy(update={"may_validate": False})
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: preview_only

    response = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/errors",
        params={"page_size": 1},
    )

    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "ACTUAL_HARVEST_SCOPE_FORBIDDEN"
