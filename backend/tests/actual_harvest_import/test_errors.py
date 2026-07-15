from __future__ import annotations

import pytest

from backend.app.actual_harvest_import.enums import ActualHarvestValidationErrorCode
from backend.app.actual_harvest_import.errors import ActualHarvestValidationError

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_validation_error_exposes_stable_identity_without_traceback_payload() -> None:
    error = ActualHarvestValidationError(
        ActualHarvestValidationErrorCode.UNKNOWN_FIELD,
        "unknown field",
        field_path="/unexpected",
        details={"field": "unexpected"},
    )

    assert str(error) == "unknown field"
    assert error.code is ActualHarvestValidationErrorCode.UNKNOWN_FIELD
    assert error.field_path == "/unexpected"
    assert error.details == {"field": "unexpected"}
    assert "traceback" not in repr(error).lower()
