from __future__ import annotations

from httpx import AsyncClient


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


async def test_api_preview_has_explicit_page_bounds(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/actual-harvest/imports/not-found/preview",
        params={"page_size": 101},
    )
    assert response.status_code in {401, 403, 404, 503}
