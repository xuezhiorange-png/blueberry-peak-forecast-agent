from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload, _record_payload


async def test_api_rejects_unsupported_content_type_before_parsing(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/actual-harvest/imports",
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 415
    assert response.json()["errors"][0]["code"] == "API_CONTENT_TYPE_UNSUPPORTED"


async def test_api_body_limit_runs_before_json_validation(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/actual-harvest/imports",
        content=b"{" + b"a" * (5_242_880 + 1) + b"}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["errors"][0]["code"] == "API_REQUEST_BODY_TOO_LARGE"


async def test_api_preview_has_explicit_page_bounds(
    api_client: AsyncClient,
    authorized_actor,
) -> None:
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    payload = _create_payload()
    payload["expected_record_count_or_null"] = 2
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=payload,
        headers={"content-type": "application/json"},
    )
    assert created.status_code == 201
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    first = _record_payload()
    second = _record_payload()
    second["external_logical_record_id"] = "logical-2"
    second["external_revision_id"] = "revision-2"
    appended = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [first, second]},
        headers={"content-type": "application/json"},
    )
    assert appended.status_code == 200

    for invalid_size in (0, 101):
        response = await api_client.get(
            f"/api/v1/actual-harvest/imports/{import_id}/preview",
            params={"page_size": invalid_size},
        )
        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "API_PAGE_SIZE_INVALID"

    invalid_type = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/preview",
        params={"page_size": "abc"},
    )
    assert invalid_type.status_code == 422
    assert invalid_type.json()["errors"][0]["code"] == "API_REQUEST_INVALID"

    first_page = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/preview",
        params={"page_size": 1},
    )
    assert first_page.status_code == 200
    first_data = first_page.json()["data_or_null"]
    assert len(first_data["records"]) == 1
    token = first_page.json()["pagination_or_null"]["next_page_token"]
    assert token

    second_page = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/preview",
        params={"page_size": 1, "page_token": token},
    )
    assert second_page.status_code == 200
    second_data = second_page.json()["data_or_null"]
    assert len(second_data["records"]) == 1
    assert (
        first_data["records"][0]["external_revision_id"]
        != second_data["records"][0]["external_revision_id"]
    )
    assert second_page.json()["pagination_or_null"]["next_page_token"] is None

    for valid_size in (1, 100):
        response = await api_client.get(
            f"/api/v1/actual-harvest/imports/{import_id}/preview",
            params={"page_size": valid_size},
        )
        assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/other/records", "/other/seal", "/planning/cancel"])
async def test_body_middleware_does_not_match_unrelated_suffix_paths(
    api_client: AsyncClient,
    path: str,
) -> None:
    response = await api_client.post(path, content=b"{}")
    assert response.status_code == 404
