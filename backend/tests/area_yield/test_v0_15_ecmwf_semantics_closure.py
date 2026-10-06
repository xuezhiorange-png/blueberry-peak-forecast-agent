"""Synthetic, label-free publication/packing guards; no private data required."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.audit_v0_15_ecmwf_semantics import (
    availability,
    classify_delta,
    encoded,
    validate_accumulation,
)


@pytest.mark.parametrize(
    ("issue", "cutoff", "expected"),
    [
        ("2025-02-01T00:00:00+00:00", "2025-02-01T17:00:00+08:00", True),
        ("2025-02-01T12:00:00+00:00", "2025-02-01T17:00:00+08:00", False),
        ("2025-01-31T12:00:00+00:00", "2025-02-01T17:00:00+08:00", True),
        ("2025-01-30T00:00:00+00:00", "2025-02-01T17:00:00+08:00", False),
        ("2024-11-10T00:00:00+00:00", "2024-11-10T17:00:00+08:00", False),
        ("2025-02-01T00:00:00+00:00", "2025-02-01T16:00:00+08:00", True),
        ("2025-02-01T00:00:00+00:00", "2025-02-01T15:59:59+08:00", False),
    ],
)
def test_assumed_not_strict_publication(issue: str, cutoff: str, expected: bool) -> None:
    assert availability(datetime.fromisoformat(issue), datetime.fromisoformat(cutoff)) == expected


@pytest.mark.parametrize(
    "issue", ["2025-02-01T06:00:00+00:00", "2025-02-01T00:01:00+00:00", "2025-02-01T00:00:00"]
)
def test_invalid_cycle_or_naive(issue: str) -> None:
    with pytest.raises(ValueError):
        availability(
            datetime.fromisoformat(issue), datetime.fromisoformat("2025-02-01T17:00:00+08:00")
        )


def test_known_delay_must_override_schedule_assumption() -> None:
    issue = datetime.fromisoformat("2025-02-01T00:00:00+00:00")
    cutoff = datetime.fromisoformat("2025-02-01T17:00:00+08:00")
    late = datetime.fromisoformat("2025-02-01T10:00:00+00:00")
    assert not availability(issue, cutoff, late)


def test_invalid_publication_receipt_rejected() -> None:
    with pytest.raises(ValueError):
        availability(
            datetime.fromisoformat("2025-02-01T00:00:00+00:00"),
            datetime.fromisoformat("2025-02-01T17:00:00+08:00"),
            datetime.fromisoformat("2025-01-31T23:00:00+00:00"),
        )


def metadata(**changes: object) -> dict:
    return {
        "units": "m",
        "shortName": "tp",
        "stepType": "accum",
        "startStep": 0,
        "endStep": 168,
        "forecastTime": 0,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"startStep": 144},
        {"stepType": "instant"},
        {"units": "mm"},
        {"shortName": "ssr"},
        {"forecastTime": 12},
        {"endStep": 0},
    ],
)
def test_reset_mixed_units_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        validate_accumulation(metadata(**changes))


def test_continuous_from_zero() -> None:
    validate_accumulation(metadata())


@pytest.mark.parametrize(
    ("delta", "bound", "expected"),
    [
        ("1", ".01", "NONNEGATIVE"),
        ("0", ".01", "NONNEGATIVE"),
        ("-.01", ".01", "PACKING_COMPATIBLE_NOT_PROVEN"),
        ("-.011", ".01", "UNKNOWN_EXCEEDS_PACKING_BOUND"),
    ],
)
def test_no_unsupported_clipping(delta: str, bound: str, expected: str) -> None:
    assert classify_delta(Decimal(delta), Decimal(bound)) == expected


@pytest.mark.parametrize("delta,bound", [("NaN", ".01"), ("1", "-1"), ("Infinity", ".01")])
def test_invalid_numerics(delta: str, bound: str) -> None:
    with pytest.raises(ValueError):
        classify_delta(Decimal(delta), Decimal(bound))


def test_public_bundle_no_private_inputs_or_claimed_causal_closure() -> None:
    root = Path(__file__).resolve().parents[3]
    folder = root / "docs/v0-15/evidence/ecmwf-publication-precipitation-closure-r1"
    manifest = json.loads((folder / "manifest.json").read_bytes())
    expected = manifest.pop("manifest_hash")
    assert hashlib.sha256(encoded(manifest)).hexdigest() == expected
    for row in manifest["members"]:
        raw = (folder / row["name"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert len(raw) == row["size"]
        assert b"/Users/" not in raw and b"/tmp/" not in raw
        assert b"predicted_daily_kg" not in raw
    policy = json.loads((folder / "historical-run-availability-policy.json").read_bytes())
    expected = policy.pop("policy_hash")
    assert hashlib.sha256(encoded(policy)).hexdigest() == expected
    assert policy["tier_a_equivalence"] is False
    ready = json.loads((folder / "s0-weather-pit-readiness-recommendation.json").read_bytes())
    assert ready["result"] == "PARTIAL"
    assert ready["precipitation_accumulation_causal_semantics_closed"] is False
    assert ready["s0_weather_pit_ready"] is False
