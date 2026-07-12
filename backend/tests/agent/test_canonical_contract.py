"""Canonical JSON / hash contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.app.agent.canonical import (
    advanced_overrides_hash,
    canonical_json_dumps,
    canonical_json_value,
    parameters_hash,
    sha256_payload,
)
from backend.app.agent.schemas import (
    AdvancedOverrides,
    ParameterEstimate,
)


def test_canonical_json_rejects_float():
    with pytest.raises(TypeError):
        canonical_json_value(1.23)


def test_canonical_json_rejects_set():
    with pytest.raises(TypeError):
        canonical_json_value({1, 2, 3})


def test_canonical_json_rejects_non_string_dict_keys():
    with pytest.raises(TypeError):
        canonical_json_value({1: "a"})


def test_canonical_json_accepts_aware_datetime():
    s = canonical_json_value(datetime(2026, 3, 1, tzinfo=UTC))
    assert "2026-03-01" in s


def test_canonical_json_rejects_naive_datetime():
    with pytest.raises(ValueError):
        canonical_json_value(datetime(2026, 3, 1, 0, 0, 0))


def test_canonical_json_canonicalizes_decimal():
    s = canonical_json_dumps(Decimal("1.50"))
    assert s in ('"1.5"', '"1.50"')  # canonical_decimal_string may strip trailing zero


def test_canonical_json_sorts_object_keys():
    payload = {"b": 1, "a": 2}
    s = canonical_json_dumps(payload)
    assert s == '{"a":2,"b":1}'


def test_sha256_payload_is_hex_64():
    h = sha256_payload({"x": 1})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_advanced_overrides_hash_none_stable():
    assert advanced_overrides_hash(None) == advanced_overrides_hash(None)


def test_advanced_overrides_hash_deterministic():
    a = AdvancedOverrides()
    b = AdvancedOverrides()
    assert advanced_overrides_hash(a) == advanced_overrides_hash(b)


def test_parameters_hash_deterministic():
    pe = ParameterEstimate(
        parameter_name="expected_per_mu_yield",
        variety_id="101",
        p50="1.50",
        p80_lower="1.30",
        p80_upper="1.70",
        source_level=1,
        confidence="HIGH",
        confidence_score=None,
        sample_count=10,
        season_count=2,
        farm_count=1,
        source_observation_ids=[],
        fallback_below_minimum=False,
        missing_evidence=[],
    )
    h1 = parameters_hash([pe])
    h2 = parameters_hash([pe])
    assert h1 == h2


def test_parameters_hash_differs_for_different_lists():
    pe1 = ParameterEstimate(
        parameter_name="expected_per_mu_yield",
        variety_id="101",
        p50="1.50",
        source_level=1, confidence="HIGH",
        confidence_score=None,
        sample_count=10, season_count=2, farm_count=1,
        source_observation_ids=[], fallback_below_minimum=False, missing_evidence=[],
    )
    pe2 = pe1.model_copy(update={"p50": "1.60"})
    assert parameters_hash([pe1]) != parameters_hash([pe2])
