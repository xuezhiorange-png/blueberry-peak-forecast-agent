from __future__ import annotations

import pytest

from backend.app.agent.slice_c.json_pointer import (
    JsonPointerResolutionError,
    resolve_json_pointer,
)


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [
        ("/name", "root"),
        ("/nested/value", 7),
        ("/items/1", "second"),
        ("/escaped~0key", "tilde"),
        ("/escaped~1key", "slash"),
    ],
)
def test_resolve_rfc6901_json_pointer(pointer: str, expected: object) -> None:
    document = {
        "name": "root",
        "nested": {"value": 7},
        "items": ["first", "second"],
        "escaped~key": "tilde",
        "escaped/key": "slash",
    }
    assert resolve_json_pointer(document, pointer) == expected


@pytest.mark.parametrize(
    "pointer",
    [
        "/Name",
        "/missing",
        "/items/-1",
        "/items/2",
        "/items/-",
        "/items/01",
        "nested.value",
        "items[0]",
        "/escaped~2key",
    ],
)
def test_resolver_fails_closed_without_alias_or_fuzzy_fallback(pointer: str) -> None:
    with pytest.raises(JsonPointerResolutionError):
        resolve_json_pointer({"name": "root", "items": ["first"], "escaped~key": "tilde"}, pointer)


def test_resolver_does_not_mutate_or_depend_on_mapping_order() -> None:
    first = {"nested": {"value": 7}, "other": 1}
    second = {"other": 1, "nested": {"value": 7}}
    before = repr(first)
    assert resolve_json_pointer(first, "/nested/value") == 7
    assert resolve_json_pointer(second, "/nested/value") == 7
    assert repr(first) == before
