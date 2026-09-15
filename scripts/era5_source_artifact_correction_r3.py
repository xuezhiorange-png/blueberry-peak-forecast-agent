"""User-certified R3 envelope, applied to derived values only; R2 evidence is immutable."""

import math
from decimal import Decimal
from typing import Any

VERSION = "ERA5_LAND_TP_SSRD_SOURCE_ARTIFACT_R3_V1"
LIMITS = {"tp": Decimal("-3.0e-8"), "ssrd": Decimal("-4")}
OUTSIDE = "NEGATIVE_VALUE_OUTSIDE_CERTIFIED_ARTIFACT_ENVELOPE"
REASON = "USER_CERTIFIED_SOURCE_ARTIFACT_WITHIN_FROZEN_ENVELOPE"


def validate_policy(policy: dict[str, Any]) -> None:
    expected = {
        "source_artifact_correction_version": VERSION,
        "tp_negative_artifact_envelope_min_m": "-3.0e-8",
        "ssrd_negative_artifact_envelope_min_j_m2": "-4",
        "tp_negative_within_envelope_to_zero": True,
        "ssrd_negative_within_envelope_to_zero": True,
        "positive_value_thresholding": False,
        "automatic_tolerance_widening": False,
        "native_temperature_unit": "K",
        "normalized_temperature_unit": "degC",
        "automatic_request_retry_count": 0,
        "request_failure_policy": "STOP_PRESERVE_RECEIPTS_NO_AUTOMATIC_RESUBMISSION",
    }
    if any(policy.get(k) != v for k, v in expected.items()):
        raise ValueError("FROZEN_CORRECTION_POLICY_MISMATCH")


def correct_value(var: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("NONFINITE_NATIVE_VALUE")
    if var in LIMITS and value < 0:
        if Decimal.from_float(value) < LIMITS[var]:
            raise ValueError(OUTSIDE)
        return 0.0
    return value


def qualify(audit: dict[str, Any]) -> dict[str, Any]:
    records = []
    outside = []
    for negative in audit["negative_values"]:
        value = float.fromhex(negative["value_exact_hex"])
        try:
            corrected = correct_value(negative["variable"], value)
        except ValueError:
            outside.append(negative)
        else:
            records.append(
                {
                    **negative,
                    "corrected_value": "0",
                    "corrected_value_exact_hex": corrected.hex(),
                    "correction_reason": REASON,
                    "correction_version": VERSION,
                    "raw_artifact_sha256": audit["raw_sha256"],
                }
            )
    return {
        **audit,
        "correction_version": VERSION,
        "eligible_corrections": records,
        "outside_envelope_negatives": outside,
        "outside_envelope_negative_count": len(outside),
        "positive_value_thresholding": False,
        "automatic_tolerance_widening": False,
    }


def gate(audit: dict[str, Any]) -> None:
    if audit["outside_envelope_negative_count"]:
        raise ValueError(OUTSIDE)
    if audit["missing_interval_count"] or audit["unexpected_interval_count"]:
        raise ValueError("HOURLY_COVERAGE_MISMATCH")
