from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActualHarvestApiPolicy:
    policy_version: str = "actual-harvest-api-policy-v1"
    authorization_policy: str = "BATCH_OWNER"
    batch_owner_authorization: bool = True
    source_domain_shared_admin: bool = False
    max_request_body_bytes: int = 5_242_880
    max_records_per_append: int = 500
    default_page_size: int = 50
    max_page_size: int = 100
    max_identifier_length: int = 256
    max_source_note_length: int = 2_000
    max_dataset_length: int = 256
    max_version_length: int = 128
    max_actor_identity_length: int = 256


API_POLICY = ActualHarvestApiPolicy()


def _json_error(status_code: int, code: str, message: str) -> bytes:
    import json

    return json.dumps(
        {
            "request_id": None,
            "status": "ERROR",
            "data_or_null": None,
            "errors": [{"code": code, "message_template_id": code, "details": {}}],
            "warnings": [],
            "pagination_or_null": None,
            "canonical_hashes": {},
            "provenance": {"policy_version": API_POLICY.policy_version},
        },
        separators=(",", ":"),
    ).encode("utf-8")


class ActualHarvestRequestBodyLimitMiddleware:
    """Bound request bodies before FastAPI materializes JSON/Pydantic objects."""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        policy: ActualHarvestApiPolicy = API_POLICY,
    ) -> None:
        self.app = app
        self.policy = policy

    async def __call__(
        self,
        scope: Mapping[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or not self._is_write(scope):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").split(b";", 1)[0].lower()
        if content_type != b"application/json":
            await self._respond(send, 415, "API_CONTENT_TYPE_UNSUPPORTED")
            return
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.policy.max_request_body_bytes:
                    await self._respond(send, 413, "API_REQUEST_BODY_TOO_LARGE")
                    return
            except ValueError:
                pass

        total = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                total += len(body)
                if total > self.policy.max_request_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._respond(send, 413, "API_REQUEST_BODY_TOO_LARGE")

    def _is_write(self, scope: Mapping[str, Any]) -> bool:
        if scope.get("method") != "POST":
            return False
        path = scope.get("path")
        if not isinstance(path, str):
            return False
        prefix = "/api/v1/actual-harvest/imports"
        if path == prefix:
            return True
        if not path.startswith(prefix + "/"):
            return False
        remainder = path[len(prefix) + 1 :]
        parts = remainder.split("/")
        return (
            len(parts) == 2
            and bool(parts[0])
            and parts[1]
            in {
                "records",
                "seal",
                "cancel",
                "validate",
            }
        )

    async def _respond(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        status_code: int,
        code: str,
    ) -> None:
        body = _json_error(status_code, code, code)
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _RequestBodyTooLarge(Exception):
    pass


__all__ = ["API_POLICY", "ActualHarvestApiPolicy", "ActualHarvestRequestBodyLimitMiddleware"]
