"""v0.2-S1 api_schemas export-contract test.

Prevents accidental removal of required public types from
`backend.app.actual_harvest_import.api_schemas.__all__`.
"""

from __future__ import annotations

from backend.app.actual_harvest_import import api_schemas


def test_api_schemas_all_exports_present() -> None:
    required = {
        "ActualHarvestApiAppendRecordsRequest",
        "ActualHarvestApiBatchSummary",
        "ActualHarvestApiCancelRequest",
        "ActualHarvestApiCommitRequest",
        "ActualHarvestApiCommitResponse",
        "ActualHarvestApiCreateImportRequest",
        "ActualHarvestApiEnvelope",
        "ActualHarvestApiPage",
        "ActualHarvestApiRecordInput",
        "ActualHarvestApiRecordOutput",
        "ActualHarvestApiSealRequest",
        "ActualHarvestApiValidateRequest",
        "ActualHarvestApiValidationSummary",
    }
    assert required.issubset(set(api_schemas.__all__))
