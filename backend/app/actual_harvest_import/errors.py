from __future__ import annotations

from typing import Any

from backend.app.actual_harvest_import.enums import ActualHarvestValidationErrorCode


class ActualHarvestContractError(ValueError):
    """Base exception for deterministic contract validation failures."""


class ActualHarvestValidationError(ActualHarvestContractError):
    """A stable validation failure carrying its canonical error identity."""

    def __init__(
        self,
        code: ActualHarvestValidationErrorCode,
        message: str,
        *,
        field_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path
        self.details = details
