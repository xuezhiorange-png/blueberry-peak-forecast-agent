"""API routers."""

from __future__ import annotations

from typing import Any

__all__ = ["materialized_datasets_router"]


def __getattr__(name: str) -> Any:
    if name == "materialized_datasets_router":
        from backend.app.api.materialized_datasets import router as materialized_datasets_router

        return materialized_datasets_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
