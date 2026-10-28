"""Synthetic ASGI telemetry preserves payloads/errors and excludes their content."""

import json
from uuid import uuid4

import pytest

from frontend.e2e.support.owned_server import instrument_app

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def recorder():
    events = []

    def emit(phase, **metadata):
        events.append({"phase": phase, **metadata})

    return events, emit


async def test_http_payloads_pass_unchanged_but_only_metadata_is_recorded():
    secret = "SYNTHETIC_PRIVATE_REQUEST_BODY"
    request_id = str(uuid4())
    scope = {
        "type": "http",
        "path": "/private/source-name",
        "query_string": secret.encode(),
        "method": "POST",
        "headers": [
            (b"authorization", secret.encode()),
            (b"x-e2e-owned-request", request_id.encode()),
        ],
    }
    response = [
        {"type": "http.response.start", "status": 201, "headers": []},
        {"type": "http.response.body", "body": secret.encode()},
    ]
    sent = []
    received = {"type": "http.request", "body": secret.encode()}

    async def receive():
        return received

    async def send(event):
        sent.append(event)

    async def app(actual_scope, actual_receive, actual_send):
        assert actual_scope is scope
        assert await actual_receive() is received
        for event in response:
            await actual_send(event)

    events, emit = recorder()
    await instrument_app(app, emit)(scope, receive, send)
    assert sent == response
    assert [e["phase"] for e in events] == ["ASGI_REQUEST_BEGIN", "ASGI_REQUEST_END"]
    assert all(
        e["request_id"] == request_id and e["request_kind"] == "BUSINESS_HTTP" for e in events
    )
    assert events[-1]["status"] == 201
    assert secret not in json.dumps(events) and "/private/source-name" not in json.dumps(events)


async def test_invalid_correlation_and_method_are_not_echoed():
    events, emit = recorder()

    async def app(scope, receive, send):
        pass

    await instrument_app(app, emit)(
        {
            "type": "http",
            "path": "/",
            "method": "SECRET_METHOD",
            "headers": [(b"x-e2e-owned-request", b"PRIVATE_NON_UUID")],
        },
        None,
        None,
    )
    assert all(e["request_id"] is None and e["method"] == "UNKNOWN" for e in events)
    assert "SECRET_METHOD" not in json.dumps(events) and "PRIVATE_NON_UUID" not in json.dumps(
        events
    )


async def test_original_exception_is_rethrown_without_logging_its_message():
    error = RuntimeError("SYNTHETIC_PRIVATE_ERROR_MESSAGE")

    async def app(scope, receive, send):
        raise error

    events, emit = recorder()
    with pytest.raises(RuntimeError) as found:
        await instrument_app(app, emit)({"type": "http", "path": "/", "method": "GET"}, None, None)
    assert found.value is error
    assert [e["phase"] for e in events] == ["ASGI_REQUEST_BEGIN", "ASGI_ERROR", "ASGI_REQUEST_END"]
    assert events[1]["error_type"] == "RuntimeError"
    assert "SYNTHETIC_PRIVATE_ERROR_MESSAGE" not in json.dumps(events)


async def test_disconnect_is_observed_and_forwarded():
    original = {"type": "http.disconnect"}

    async def receive():
        return original

    async def app(scope, actual_receive, send):
        assert await actual_receive() is original

    events, emit = recorder()
    await instrument_app(app, emit)({"type": "http", "path": "/", "method": "GET"}, receive, None)
    assert [e["phase"] for e in events] == [
        "ASGI_REQUEST_BEGIN",
        "ASGI_DISCONNECT",
        "ASGI_REQUEST_END",
    ]


async def test_lifespan_failure_message_is_forwarded_but_not_published():
    original = {"type": "lifespan.startup.failed", "message": "SYNTHETIC_PRIVATE_LIFESPAN"}
    sent = []

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(event):
        sent.append(event)

    async def app(scope, actual_receive, actual_send):
        assert (await actual_receive())["type"] == "lifespan.startup"
        await actual_send(original)

    events, emit = recorder()
    await instrument_app(app, emit)({"type": "lifespan"}, receive, send)
    assert sent == [original]
    assert [e["phase"] for e in events] == ["LIFESPAN_STARTUP_BEGIN", "LIFESPAN_STARTUP_FAILED"]
    assert "SYNTHETIC_PRIVATE_LIFESPAN" not in json.dumps(events)


async def test_other_asgi_scopes_are_forwarded_without_introspection():
    scope = {"type": "websocket"}
    called = []

    async def app(actual_scope, receive, send):
        called.append(actual_scope)

    events, emit = recorder()
    await instrument_app(app, emit)(scope, None, None)
    assert called == [scope]
    assert events == []
