"""Synthetic tests of Owner-frozen candidates and symmetric trace handling."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.audit_v0_15_precip_packing_policy import encoded, select_threshold, window_precip


@pytest.mark.parametrize(
    "magnitude,threshold",
    [
        ("0", ".04"),
        (".030517578125", ".04"),
        (".039999", ".04"),
        (".04", ".08"),
        (".079999", ".08"),
    ],
)
def test_minimum_official_candidate(magnitude: str, threshold: str) -> None:
    assert select_threshold(Decimal(magnitude)) == Decimal(threshold)


@pytest.mark.parametrize("magnitude", [".08", ".1", "-1", "NaN", "Infinity"])
def test_no_threshold_expansion(magnitude: str) -> None:
    with pytest.raises(ValueError):
        select_threshold(Decimal(magnitude))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("-0.015", "0"),
        ("0.015", "0"),
        ("0", "0"),
        ("0.039999", "0"),
        ("0.04", "0.04"),
        ("10", "10"),
    ],
)
def test_negative_and_positive_trace_rule(raw: str, expected: str) -> None:
    assert window_precip(Decimal(raw), Decimal(".04")) == Decimal(expected)


@pytest.mark.parametrize("raw", ["-.04", "-.08", "NaN", "Infinity"])
def test_uncovered_anomaly_not_silently_clipped(raw: str) -> None:
    with pytest.raises(ValueError):
        window_precip(Decimal(raw), Decimal(".04"))


@pytest.mark.parametrize("threshold", [".031", ".05", ".1"])
def test_unapproved_threshold(threshold: str) -> None:
    with pytest.raises(ValueError):
        window_precip(Decimal(".01"), Decimal(threshold))


def test_real_public_reports_integrity_and_evidence_grade() -> None:
    repo = Path(__file__).resolve().parents[3]
    root = repo / "docs/v0-15/evidence/precipitation-packing-policy-closure-r1"
    manifest = json.loads((root / "manifest.json").read_bytes())
    expected = manifest.pop("manifest_hash")
    assert hashlib.sha256(encoded(manifest)).hexdigest() == expected
    for member in manifest["members"]:
        content = (root / member["name"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == member["sha256"]
        assert len(content) == member["size"]
        assert b"/Users/" not in content and b"/tmp/" not in content
        assert b"base_values_m" not in content and b"predicted_daily_kg" not in content
        assert b'"trace_collapsed"' not in content
    policy = json.loads((root / "precipitation-packing-artifact-policy.json").read_bytes())
    expected = policy.pop("policy_hash")
    assert hashlib.sha256(encoded(policy)).hexdigest() == expected
    assert policy["threshold_selected_mm"] == "0.08"
    assert policy["ssrd_temperature_wind_threshold_applied"] is False
    coverage = json.loads((root / "pit-weather-coverage-finalization.json").read_bytes())
    assert coverage["total_required_origin_count"] == 847
    assert coverage["pit_weather8_complete_origin_count"] == 422
    assert coverage["strict_tier_a_publication_ready_count"] == 0
    assert coverage["all_eight_numerical_features_reconstructed_every_origin"] is False
