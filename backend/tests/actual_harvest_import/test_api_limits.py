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
    payload["expected_record_count_or_null"] = 3
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=payload,
        headers={"content-type": "application/json"},
    )
    assert created.status_code == 201
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    records = []
    for logical_id, revision_id in (
        ("logical-1", "revision-1"),
        ("logical-2", "revision-2"),
        ("logical-3", "revision-3"),
    ):
        record = _record_payload()
        record["external_logical_record_id"] = logical_id
        record["external_revision_id"] = revision_id
        records.append(record)
    expected_keys = [
        (
            record["source_system"],
            record["external_logical_record_id"],
            record["revision_number"],
            record["external_revision_id"],
        )
        for record in records
    ]
    appended = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [records[2], records[0], records[1]]},
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

    actual_keys = []
    page_token = None
    final_next_page_token = object()
    for _ in range(len(expected_keys) + 1):
        params = {"page_size": 1}
        if page_token is not None:
            params["page_token"] = page_token
        page = await api_client.get(
            f"/api/v1/actual-harvest/imports/{import_id}/preview",
            params=params,
        )
        assert page.status_code == 200
        page_json = page.json()
        page_records = page_json["data_or_null"]["records"]
        assert len(page_records) <= 1
        actual_keys.extend(
            (
                record["source_system"],
                record["external_logical_record_id"],
                record["revision_number"],
                record["external_revision_id"],
            )
            for record in page_records
        )
        final_next_page_token = page_json["pagination_or_null"]["next_page_token"]
        if final_next_page_token is None:
            break
        page_token = final_next_page_token
    else:
        pytest.fail("keyset pagination did not terminate")

    assert actual_keys == sorted(expected_keys)
    assert len(actual_keys) == len(set(actual_keys))
    assert set(actual_keys) == set(expected_keys)
    assert final_next_page_token is None

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
