"""TASK-013 Slice C deterministic explanation and recommendation foundation."""

from backend.app.agent.slice_c.engine import build_slice_c_outputs, validate_citation
from backend.app.agent.slice_c.json_pointer import (
    JsonPointerResolutionError,
    resolve_json_pointer,
)

__all__ = [
    "JsonPointerResolutionError",
    "build_slice_c_outputs",
    "resolve_json_pointer",
    "validate_citation",
]
