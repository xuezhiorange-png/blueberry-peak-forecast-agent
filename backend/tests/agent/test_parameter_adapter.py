"""SQLite-backed tests for ``infer_parameters`` adapter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from backend.app.agent.adapters.parameters import (
    DefaultParameterAdapter,
    DefaultParameterPriorPort,
    ParameterPrior,
    SourceCapabilityGapError,
    confidence_for_step,
    is_visible_prior,
    source_level_step,
    widening_factor_for,
)
from backend.app.agent.schemas import (
    AdvancedOverrides,
    InferParametersInput,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    UncertaintyWideningPolicy,
)

# --- Unit tests on pure helpers -----------------------------------------


def test_is_visible_prior_no_bounds():
    assert is_visible_prior(
        effective_from=None,
        effective_to=None,
        available_at=None,
        effective_as_of_date=date(2026, 3, 1),
    )


def test_is_visible_prior_effective_from_future():
    assert not is_visible_prior(
        effective_from=date(2026, 4, 1),
        effective_to=None,
        available_at=None,
        effective_as_of_date=date(2026, 3, 1),
    )


def test_is_visible_prior_effective_to_past():
    assert not is_visible_prior(
        effective_from=None,
        effective_to=date(2026, 2, 1),
        available_at=None,
        effective_as_of_date=date(2026, 3, 1),
    )


def test_is_visible_prior_available_at_future():
    assert not is_visible_prior(
        effective_from=None,
        effective_to=None,
        available_at=date(2026, 4, 1),
        effective_as_of_date=date(2026, 3, 1),
    )


def test_confidence_for_step():
    assert confidence_for_step(1) == "HIGH"
    assert confidence_for_step(2) == "MEDIUM"
    assert confidence_for_step(3) == "MEDIUM"
    assert confidence_for_step(4) == "LOW"
    assert confidence_for_step(5) == "LOW"


@pytest.mark.parametrize(
    ("source_level", "expected"),
    [
        ("same_farm_variety", 1),
        ("same_township_altitude_variety", 2),
        ("same_county_climate_zone_variety", 3),
        ("same_province_variety", 4),
        ("literature_variety_prior", 5),
    ],
)
def test_source_level_step_maps_upstream_taxonomy(source_level: str, expected: int) -> None:
    assert source_level_step(source_level, fallback_step=5) == expected


def test_source_level_step_rejects_unknown_upstream_level() -> None:
    with pytest.raises(SourceCapabilityGapError, match="unknown upstream source_level"):
        source_level_step("same_farm_same_variety", fallback_step=1)


def test_widening_factor_monotonic():
    policy = UncertaintyWideningPolicy(
        policy_version="uncertainty-widening/v1",
        config_hash="d" * 64,
        factors_by_source_level={
            "step_1_same_farm_same_variety_high_evidence": "1.000",
            "step_2_same_township_similar_altitude": "1.250",
            "step_3_same_county_same_climate_zone": "1.500",
            "step_4_province_level_same_variety": "1.750",
            "step_5_variety_document_prior_only": "2.000",
        },
        monotonicity_invariant=True,
    )
    f1 = widening_factor_for(1, policy)
    f2 = widening_factor_for(2, policy)
    f3 = widening_factor_for(3, policy)
    f4 = widening_factor_for(4, policy)
    f5 = widening_factor_for(5, policy)
    assert f1 < f2 < f3 < f4 < f5


def test_widening_factor_missing_raises():
    policy = UncertaintyWideningPolicy(
        policy_version="v1",
        config_hash="d" * 64,
        factors_by_source_level={"step_1_same_farm_same_variety_high_evidence": "1.000"},
        monotonicity_invariant=True,
    )
    with pytest.raises(SourceCapabilityGapError):
        widening_factor_for(5, policy)


# --- Adapter tests with a deterministic fake port -------------------------


class _FakePort(DefaultParameterPriorPort):
    def __init__(self, *, prior: ParameterPrior | None = None, raise_gap: bool = False):
        self._prior = prior
        self._raise_gap = raise_gap

    async def resolve_parameter(self, **kwargs: Any) -> ParameterPrior:

        param_name = kwargs.get("parameter_name", "")
        # The 4 categories with no persisted upstream source must surface
        # SourceCapabilityGapError to trigger per-variety NO_PERSISTED_PRIOR_SOURCE
        # blockers.  When ``raise_gap`` is True ALL parameters raise.
        if self._raise_gap or param_name not in {
            "expected_per_mu_yield",
            "commodity_fruit_rate",
            "first_harvest_date",
            "maturity_curve",
        }:
            raise SourceCapabilityGapError(f"no persisted prior source for {param_name}")
        if self._prior is not None:
            return self._prior
        return ParameterPrior(
            parameter_name=param_name,
            variety_id=str(kwargs.get("variety_id")),
            p50=Decimal("1.50"),
            p80_lower=Decimal("1.30"),
            p80_upper=Decimal("1.70"),
            source_level=kwargs["monotonic_step"],
            confidence=confidence_for_step(kwargs["monotonic_step"]),
            sample_count=10,
            season_count=2,
            farm_count=1,
            source_observation_ids=(1, 2, 3),
            missing_evidence=(),
        )


class _FakeCatalog:
    """Default-fake VarietyCatalogPort used by the tests below.

    All string variety codes are considered known so the adapter proceeds
    to the inference stage.
    """

    async def is_known(self, *, session: Any, variety_id: str) -> bool:
        return True


def _mk_nr(variety_ids: list[str] | None = None) -> NormalizedAgentRequest:
    return NormalizedAgentRequest(
        request_id="r1",
        request_received_at=__import__("datetime").datetime(
            2026, 3, 1, tzinfo=__import__("datetime").UTC
        ),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        location_input=LocationInput(
            raw_text="云南曲靖",
            location_reference_id=1,
        ),
        varieties=[
            NormalizedVarietyInput(variety_id=v, planting_area_mu="100.0")
            for v in (variety_ids or ["101"])
        ],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


def _mk_input() -> InferParametersInput:
    return InferParametersInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="uncertainty-widening/v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )


@pytest.mark.asyncio
async def test_infer_parameters_step1_high_confidence(sqlite_session):
    adapter = DefaultParameterAdapter(port=_FakePort(), catalog=_FakeCatalog())
    out = await adapter.execute(sqlite_session, input=_mk_input())
    # Round 6 (P0-3): the frozen public ParameterEstimate schema
    # cannot carry the 3-component maturity_curve.  The adapter
    # excludes ``maturity_curve`` from the public output and surfaces
    # MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING.  The other 3
    # supported categories remain in the public output.
    supported = [
        p
        for p in out.parameters
        if p.parameter_name
        in {
            "expected_per_mu_yield",
            "commodity_fruit_rate",
            "first_harvest_date",
        }
    ]
    assert len(supported) == 3
    pe = supported[0]
    assert pe.source_level == 1
    assert pe.confidence == "HIGH"
    assert pe.p50 == "1.50"
    # The 4 unsupported categories must surface NO_PERSISTED_PRIOR_SOURCE
    # blockers (one per variety × parameter), AND maturity_curve must
    # surface MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING.
    unsupported_blockers = [b for b in out.blockers if b.code.value == "NO_PERSISTED_PRIOR_SOURCE"]
    assert len(unsupported_blockers) == 4
    maturity_curve_blockers = [
        b for b in out.blockers if b.code.value == "MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING"
    ]
    assert len(maturity_curve_blockers) == 1


@pytest.mark.asyncio
async def test_infer_parameters_unknown_variety_no_numerical_output(sqlite_session):
    # Pass a non-numeric variety_id to trigger UNKNOWN_VARIETY.
    nr = _mk_nr(variety_ids=["variety-x"])
    inp = InferParametersInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )

    class _RejectCatalog:
        async def is_known(self, *, session, variety_id):
            from backend.app.agent.adapters.parameters import (
                UnknownVarietyError,
            )

            raise UnknownVarietyError(f"unknown: {variety_id}")

    adapter = DefaultParameterAdapter(port=_FakePort(), catalog=_RejectCatalog())
    out = await adapter.execute(sqlite_session, input=inp)
    assert "variety-x" in out.blocked_variety_ids
    assert out.parameters == []


@pytest.mark.asyncio
async def test_infer_parameters_no_visible_prior_raises_blocker(sqlite_session):
    # Port that raises SourceCapabilityGapError -> adapter records a
    # NO_PERSISTED_PRIOR_SOURCE blocker per (variety, parameter).
    adapter = DefaultParameterAdapter(port=_FakePort(raise_gap=True), catalog=_FakeCatalog())
    out = await adapter.execute(sqlite_session, input=_mk_input())
    # All 8 logical schemas raise; the variety is NOT in blocked_variety_ids
    # (only unknown varieties are recorded there).  The adapter emits
    # per-(variety, parameter) NO_PERSISTED_PRIOR_SOURCE blockers instead.
    assert out.blocked_variety_ids == []
    no_persisted = [b for b in out.blockers if b.code.value == "NO_PERSISTED_PRIOR_SOURCE"]
    assert len(no_persisted) == 8
    assert out.parameters == []


@pytest.mark.asyncio
async def test_infer_parameters_deterministic(sqlite_session):
    adapter = DefaultParameterAdapter(port=_FakePort(), catalog=_FakeCatalog())
    out1 = await adapter.execute(sqlite_session, input=_mk_input())
    out2 = await adapter.execute(sqlite_session, input=_mk_input())
    assert out1.parameters_hash == out2.parameters_hash
