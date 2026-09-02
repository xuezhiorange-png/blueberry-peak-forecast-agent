"""CI-stable frozen blob authority helpers for S3-A2 family tests."""

from __future__ import annotations

import json
from pathlib import Path

HISTORICAL_FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"


def assert_forecast_artifact_py_historical_blob_pinned(expected_blob: str) -> None:
    """Assert the historical landed forecast artifact blob pin, not working-tree bytes."""
    assert expected_blob == HISTORICAL_FORECAST_ARTIFACT_PY_BLOB


def assert_evidence_frozen_python_blobs_match_constants(
    evidence_path: Path,
    *,
    catalog_artifact_py_blob: str,
    forecast_artifact_py_blob: str,
    content_producer_py_blob: str | None = None,
    content_for_reviewed_grains_py_blob: str | None = None,
    coordinator_reviewed_set_py_blob: str | None = None,
    catalog_no_versioned_closeout_py_blob: str | None = None,
    test_catalog_artifact_py_blob: str | None = None,
) -> None:
    """Verify test constants match frozen pins recorded in landed evidence JSON."""
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    blobs = payload["frozen_python_blobs"]
    assert blobs["catalog_artifact_py_blob"] == catalog_artifact_py_blob
    assert blobs["forecast_artifact_py_blob"] == forecast_artifact_py_blob
    if content_producer_py_blob is not None:
        assert blobs["content_producer_py_blob"] == content_producer_py_blob
    if content_for_reviewed_grains_py_blob is not None:
        assert blobs["content_for_reviewed_grains_py_blob"] == content_for_reviewed_grains_py_blob
    if coordinator_reviewed_set_py_blob is not None:
        assert blobs["coordinator_reviewed_set_py_blob"] == coordinator_reviewed_set_py_blob
    if catalog_no_versioned_closeout_py_blob is not None:
        assert (
            blobs["catalog_no_versioned_closeout_py_blob"] == catalog_no_versioned_closeout_py_blob
        )
    if test_catalog_artifact_py_blob is not None:
        assert blobs["test_catalog_artifact_py_blob"] == test_catalog_artifact_py_blob
