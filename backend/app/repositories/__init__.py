"""Repository layer."""

from __future__ import annotations

from typing import Any

__all__ = [
    "load_materialized_dataset_result",
    "load_upstream_bundle_from_storage",
    "persist_materialized_dataset",
    "rebuild_materialized_dataset_from_storage",
    "verify_storage_rebuild_parity",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from backend.app.s2_materialized_dataset.lane_d import service as lane_d_service

        return getattr(lane_d_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
