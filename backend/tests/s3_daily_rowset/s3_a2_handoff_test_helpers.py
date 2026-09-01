"""Test helpers for disabling canonical forecast-port handoff in fallback tests."""

from __future__ import annotations

from unittest.mock import patch

HANDOFF_TARGET = (
    "backend.app.s3_daily_rowset.s3_a2_default_catalog_forecast_port_envelope_handoff."
    "deterministic_coordinator_reviewed_grains_forecast_artifact"
)


def patch_handoff_disabled() -> patch:
    """Disable reviewed-grains handoff so lower-priority fallback paths can be exercised."""
    return patch(HANDOFF_TARGET, return_value=None)
