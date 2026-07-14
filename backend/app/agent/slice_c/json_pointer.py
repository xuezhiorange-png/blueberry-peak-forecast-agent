"""Pure RFC 6901 JSON Pointer resolution for canonical Agent payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_ARRAY_INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class JsonPointerResolutionError(ValueError):
    """Raised when a pointer cannot be resolved exactly and safely."""


def _decode_token(token: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(token):
        char = token[index]
        if char != "~":
            output.append(char)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise JsonPointerResolutionError("EVIDENCE_FIELD_PATH_INVALID: invalid escape")
        output.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(output)


def resolve_json_pointer(document: object, pointer: str) -> Any:
    """Resolve a non-root RFC 6901 pointer without mutating ``document``."""

    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise JsonPointerResolutionError("EVIDENCE_FIELD_PATH_INVALID: pointer must start with /")
    current: Any = document
    for raw_token in pointer.split("/")[1:]:
        token = _decode_token(raw_token)
        if isinstance(current, Mapping):
            if token not in current:
                raise JsonPointerResolutionError(
                    f"EVIDENCE_FIELD_PATH_INVALID: missing object token {token!r}"
                )
            current = current[token]
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if not _ARRAY_INDEX.fullmatch(token):
                raise JsonPointerResolutionError("EVIDENCE_FIELD_PATH_INVALID: invalid array index")
            index = int(token)
            if index >= len(current):
                raise JsonPointerResolutionError(
                    "EVIDENCE_FIELD_PATH_INVALID: array index out of bounds"
                )
            current = current[index]
            continue
        raise JsonPointerResolutionError(
            "EVIDENCE_FIELD_PATH_INVALID: cannot traverse scalar value"
        )
    return current


__all__ = ["JsonPointerResolutionError", "resolve_json_pointer"]
