"""Offline metadata validation for real historical archive proof; no network or labels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

STEPS = tuple(range(3, 145, 3)) + tuple(range(150, 361, 6))
REQUIRED = {(step, param) for step in STEPS for param in ("2t", "10u", "10v")} | {
    (step, param) for step in (168, 360) for param in ("tp", "ssrd")
}
UNITS = {"2t": "K", "10u": "m s**-1", "10v": "m s**-1", "tp": "m", "ssrd": "J m**-2"}
PARAM_IDS = {"2t": 167, "10u": 165, "10v": 166, "tp": 228, "ssrd": 169}


def validate_dense_metadata(report: dict[str, Any]) -> dict[str, Any]:
    """Completeness concerns decoded fields, never an index-only availability claim."""
    issued = datetime.fromisoformat(report["provider_issued_at"])
    if issued.tzinfo is None or issued.utcoffset() != timedelta(0):
        raise ValueError("UTC_ISSUE_REQUIRED")
    if not datetime(2023, 7, 1, tzinfo=UTC) <= issued < datetime(2026, 7, 1, tzinfo=UTC):
        raise ValueError("AUTHORIZED_HISTORICAL_PERIOD_REQUIRED")
    if issued.hour not in {0, 12} or any((issued.minute, issued.second, issued.microsecond)):
        raise ValueError("INELIGIBLE_CYCLE")
    if report["provider_run_id"] != issued.strftime("%Y%m%d%H%M%S"):
        raise ValueError("RUN_ID_MISMATCH")
    fields = report["fields"]
    identities = [(row["step"], row["parameter"]) for row in fields]
    if len(identities) != len(REQUIRED) or set(identities) != REQUIRED:
        raise ValueError("DENSE_SURFACE_INCOMPLETE_OR_MUTATED")
    grid = None
    total_bytes = 0
    for row in fields:
        step, parameter = row["step"], row["parameter"]
        metadata = row["metadata"]
        valid = issued + timedelta(hours=step)
        accum = parameter in {"tp", "ssrd"}
        expected = {
            "shortName": parameter,
            "paramId": PARAM_IDS[parameter],
            "units": UNITS[parameter],
            "stepType": "accum" if accum else "instant",
            "startStep": 0 if accum else step,
            "endStep": step,
            "dataDate": int(issued.strftime("%Y%m%d")),
            "dataTime": issued.hour * 100,
            "validityDate": int(valid.strftime("%Y%m%d")),
            "validityTime": valid.hour * 100,
            "marsClass": "od",
            "marsStream": "oper",
            "marsType": "fc",
            "centre": "ecmf",
            "edition": 2,
        }
        if any(metadata.get(k) != value for k, value in expected.items()):
            raise ValueError("DECODED_METADATA_MISMATCH")
        shape = tuple(
            metadata[k]
            for k in (
                "gridType",
                "iDirectionIncrementInDegrees",
                "jDirectionIncrementInDegrees",
                "numberOfDataPoints",
            )
        )
        if shape[:3] != ("regular_ll", 0.25, 0.25) or shape[3] <= 0:
            raise ValueError("GRID_MISMATCH")
        if grid is not None and grid != shape:
            raise ValueError("MIXED_GRID")
        grid = shape
        if metadata["values_decoded_count"] != shape[3] or row["file_size"] <= 0:
            raise ValueError("ACTUAL_DECODE_REQUIRED")
        if len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]):
            raise ValueError("RAW_HASH_INVALID")
        total_bytes += row["file_size"]
    return {
        "field_count": len(fields),
        "parameter_count": 5,
        "forecast_step_count": len(STEPS),
        "raw_field_bytes": total_bytes,
        "same_run": True,
        "all_required_fields_decoded": True,
        "radiation_semantics_match": True,
        "issue_time": issued.astimezone(UTC).isoformat(),
        "valid_time_start": (issued + timedelta(hours=3)).isoformat(),
        "valid_time_end": (issued + timedelta(hours=360)).isoformat(),
    }
