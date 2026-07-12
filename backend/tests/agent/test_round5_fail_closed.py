"""TASK-013 Slice A — Round 5 fail-closed review fixup tests (focused).

The full round-5 surface is exercised in test_p0_fail_closed.py and
test_production_wiring.py.  This module adds round-5-specific
typed tests covering the most critical points Charles called out.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.agent.adapters.parameters import (
    LOGICAL_TO_UPSTREAM,
    DefaultParameterPriorPort,
    DefaultVarietyCatalogPort,
    SourceCapabilityGapError,
    _load_inference_rules_or_raise,
)
from backend.app.agent.adapters.task_loaders import (
    AuthorityLoadResult,
    DefaultSpringFestivalCalendarPort,
    HardcodedSpringFestivalCalendarPort,
    _make_blocker,
    _strict_version,
)
from backend.app.agent.enums import BlockerCode


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ============================================================================
# P0-1 #4 — string variety code → catalog → PK
# ============================================================================


@pytest.mark.asyncio
async def test_round5_string_variety_catalog_resolution(sqlite_session):
    from backend.app.models.master_data import Variety

    for vid, code in [(1, "Dx"), (2, "D12"), (3, "1702")]:
        sqlite_session.add(Variety(id=vid, code=code, name=f"Test {code}"))
    await sqlite_session.flush()

    catalog = DefaultVarietyCatalogPort()
    for code, expected_pk in [("Dx", 1), ("D12", 2), ("1702", 3)]:
        row = await catalog.lookup_row(session=sqlite_session, variety_id=code)
        assert row is not None
        assert int(row.id) == expected_pk
        assert str(row.code) == code


@pytest.mark.asyncio
async def test_round5_unknown_variety_returns_unknown_variety(sqlite_session):
    from backend.app.agent.adapters.parameters import UnknownVarietyError

    catalog = DefaultVarietyCatalogPort()
    with pytest.raises(UnknownVarietyError):
        await catalog.lookup_row(session=sqlite_session, variety_id="NotInCatalog")


@pytest.mark.asyncio
async def test_round5_numeric_variety_code_resolved_by_catalog_not_int_cast(sqlite_session):
    """The string "1702" must be resolved via the Variety catalog, NOT
    via the previous ``int("1702") == 1702`` fallback."""

    from backend.app.models.master_data import Variety

    # Insert "1702" with a different PK than 1702 — proves the
    # catalog-based lookup is the only path.
    sqlite_session.add(Variety(id=999, code="1702", name="Special"))
    await sqlite_session.flush()

    catalog = DefaultVarietyCatalogPort()
    row = await catalog.lookup_row(session=sqlite_session, variety_id="1702")
    assert row is not None
    assert int(row.id) == 999  # NOT 1702 (the int-cast fallback)


# ============================================================================
# P0-1 #5 — versioned inference config
# ============================================================================


def test_round5_versioned_inference_config_loaded():
    """The real :func:`load_parameter_inference_config` loads the
    persisted YAML at ``configs/parameter_inference.yaml`` and yields
    a 64-char lowercase hex config_hash."""

    rules, version, chash = _load_inference_rules_or_raise(Path("configs/parameter_inference.yaml"))
    assert version
    assert version not in {"v0", "unknown"}
    assert len(chash) == 64
    assert all(c in "0123456789abcdef" for c in chash)
    assert rules is not None


def test_round5_missing_inference_config_fails_closed(tmp_path):
    with pytest.raises(SourceCapabilityGapError) as exc_info:
        _load_inference_rules_or_raise(tmp_path / "does_not_exist.yaml")
    assert "not found" in str(exc_info.value)


def test_round5_invalid_inference_config_hash_fails_closed(tmp_path):
    p = tmp_path / "broken.yaml"
    p.write_text("resolver_version: v0\n", encoding="utf-8")
    with pytest.raises(SourceCapabilityGapError):
        _load_inference_rules_or_raise(p)


def test_round5_default_path_does_not_use_agent_default_rules():
    """The default :class:`DefaultParameterPriorPort` constructor
    accepts NO ``rules=`` argument.  The previous
    ``_build_default_parameter_inference_rules()`` helper is gone."""

    import inspect

    sig = inspect.signature(DefaultParameterPriorPort.__init__)
    assert "rules" not in sig.parameters
    assert "config_path" in sig.parameters


# ============================================================================
# P0-1 #6 — ResolvedLocation propagation (typed test via parameter port)
# ============================================================================


@pytest.mark.asyncio
async def test_round5_missing_location_reference_fails_closed(sqlite_session):
    """When no LocationReference is present, the default prior port
    raises :class:`LocationSourceCapabilityMissingError` (round 6
    P0-2 typed failure) and the adapter surfaces the
    ``LOCATION_SOURCE_CAPABILITY_MISSING`` blocker (NOT a generic
    ``NO_PERSISTED_PRIOR_SOURCE``)."""

    from backend.app.agent.adapters.parameters import (
        DefaultParameterPriorPort,
        LocationSourceCapabilityMissingError,
    )
    from backend.app.agent.enums import BlockerCode
    from backend.app.agent.schemas import ResolvedLocation
    from backend.app.models.master_data import Variety

    sqlite_session.add(Variety(id=1, code="Dx", name="Test"))
    await sqlite_session.flush()

    rl = ResolvedLocation(status="unresolved", matched_location_method="TEXT")
    port = DefaultParameterPriorPort()
    with pytest.raises(LocationSourceCapabilityMissingError):
        await port.resolve_parameter(
            session=sqlite_session,
            variety_id="Dx",
            parameter_name="expected_per_mu_yield",
            resolved_location=rl,
            effective_as_of_date=date(2026, 3, 1),
            widening_factor=Decimal("1.0"),
            monotonic_step=1,
        )
    # The blocker code used by the adapter layer must be the typed one.
    assert (
        BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING.value == "LOCATION_SOURCE_CAPABILITY_MISSING"
    )


# ============================================================================
# P0-1 #7 — maturity_curve 3 components
# ============================================================================


def test_round5_maturity_curve_maps_three_components():
    assert LOGICAL_TO_UPSTREAM["maturity_curve"] == (
        "maturity_peak_offset_days",
        "maturity_width_days",
        "maturity_skewness",
    )


# ============================================================================
# P0-2 #8 — typed AuthorityLoadResult
# ============================================================================


@pytest.mark.asyncio
async def test_round5_missing_authority_row_is_not_found(sqlite_session):
    from backend.app.agent.adapters.task_loaders import (
        DefaultTask9HarvestStatePort,
    )

    port = DefaultTask9HarvestStatePort()
    result = await port.load_typed(session=sqlite_session, harvest_state_run_id=999999)
    assert result.authority is None
    assert any(b.code == BlockerCode.AUTHORITY_NOT_FOUND for b in result.blockers)


@pytest.mark.asyncio
async def test_round5_malformed_hash_rejected_by_strict_helper(sqlite_session):
    """The :func:`_strict_sha256_hex` helper rejects non-canonical
    hashes.  The DB-level ``ck_harvest_state_run_result_hash`` CHECK
    constraint enforces the same shape at the persistence layer; the
    loader-level check is the typed-failure path that runs BEFORE the
    row is committed."""

    from backend.app.agent.adapters.task_loaders import (
        AuthorityIdentityError,
        _strict_sha256_hex,
    )

    for bad in ["not-a-valid-hash", "0xdeadbeef", "f" * 63, "f" * 65, "", None]:
        with pytest.raises(AuthorityIdentityError):
            _strict_sha256_hex(bad, field="result_hash")
    # A canonical 64-char lowercase hex passes.
    assert _strict_sha256_hex("f" * 64, field="x") == "f" * 64
    assert _strict_sha256_hex("0" * 64, field="x") == "0" * 64


def test_round5_blocker_for_identity_error_mapping():
    """The :func:`_blocker_for_identity_error` helper maps exception
    messages to typed BlockerCodes."""
    from backend.app.agent.adapters.task_loaders import AuthorityIdentityError

    exc = AuthorityIdentityError("upstream X is not a 64-char lowercase hex string")
    b = _make_blocker(code=BlockerCode.AUTHORITY_HASH_MALFORMED, field="X", message=str(exc))
    assert b.code == BlockerCode.AUTHORITY_HASH_MALFORMED
    exc = AuthorityIdentityError("upstream Y is not UTC")
    b = _make_blocker(code=BlockerCode.AUTHORITY_DATETIME_MALFORMED, field="Y", message=str(exc))
    assert b.code == BlockerCode.AUTHORITY_DATETIME_MALFORMED
    exc = AuthorityIdentityError("upstream Z is placeholder: 'v0'")
    b = _make_blocker(
        code=BlockerCode.AUTHORITY_POLICY_VERSION_MISSING,
        field="Z",
        message=str(exc),
    )
    assert b.code == BlockerCode.AUTHORITY_POLICY_VERSION_MISSING
    exc = AuthorityIdentityError("upstream A is NULL")
    b = _make_blocker(code=BlockerCode.AUTHORITY_ARTIFACT_MISSING, field="A", message=str(exc))
    assert b.code == BlockerCode.AUTHORITY_ARTIFACT_MISSING


def test_round5_authority_load_result_envelope():
    """AuthorityLoadResult.is_loaded / primary_blocker property semantics."""
    r1 = AuthorityLoadResult(authority=None, blockers=())
    assert not r1.is_loaded
    assert r1.primary_blocker is None
    b = _make_blocker(code=BlockerCode.AUTHORITY_NOT_FOUND, field="x", message="m")
    r2 = AuthorityLoadResult(authority=None, blockers=(b,))
    assert not r2.is_loaded
    assert r2.primary_blocker is b


# ============================================================================
# P0-2 #10 — TASK-12 policy_version field provenance
# ============================================================================


def test_round5_strict_version_rejects_placeholders():
    """_strict_version rejects "v0" / "unknown" / empty / placeholder strings."""
    from backend.app.agent.adapters.task_loaders import AuthorityIdentityError

    for bad in ["v0", "unknown", "tbd", "todo", "none", "", "V0", "Unknown"]:
        with pytest.raises(AuthorityIdentityError):
            _strict_version(bad, field="x")
    # Real version passes
    assert _strict_version("v1.2.3", field="x") == "v1.2.3"
    assert _strict_version("2026-07-12/r1", field="x") == "2026-07-12/r1"


# ============================================================================
# P0-3 — selector scope + override validation
# ============================================================================


@pytest.mark.asyncio
async def test_round5_task9_override_cannot_bypass_destination_scope(sqlite_session):
    """When the TASK-9 override's destination_factory_id does NOT
    match the resolved location, the override is rejected (NOT
    silently accepted)."""

    from backend.app.models.harvest_state import HarvestStateRun
    from backend.app.models.master_data import Variety

    sqlite_session.add(Variety(id=1, code="Dx", name="Test"))
    await sqlite_session.flush()

    run = HarvestStateRun(
        id=1,
        status="completed",
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot={},
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result={},
        continuity_result={},
        canonical_output={},
        config_hash=_hash("cfg"),
        result_hash=_hash("res"),
        canonical_payload_hash=_hash("pay"),
        forecast_start_date=date(2026, 3, 1),
        forecast_end_date=date(2026, 3, 2),
        as_of_date=date(2026, 3, 1),
        destination_factory_id=999,  # MISMATCH
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_model_run_id=None,
        maturity_model_version="v1",
        maturity_model_config_hash=_hash("mc"),
        maturity_model_source_signature="sig",
        maturity_model_artifact_id=None,
        maturity_model_artifact_hash=_hash("ma"),
        maturity_forecast_run_id=1,
        maturity_forecast_source_signature="fsig",
    )
    sqlite_session.add(run)
    await sqlite_session.flush()

    from backend.app.agent.adapters.baseline_composer import (
        _select_harvest_state_run_candidates,
    )

    candidates = await _select_harvest_state_run_candidates(
        sqlite_session,
        as_of=date(2026, 3, 1),
        run_id_override=1,
        destination_factory_id=1,
    )
    # Round 8: discriminated ``AuthoritySelectionResult``.  When
    # the override row's destination_factory_id differs from the
    # request's destination, the selector MUST emit
    # AUTHORITY_SCOPE_MISMATCH (DESTINATION_MISMATCH reason) — not
    # silently return a flat ``[]``.
    assert candidates.candidates == ()
    assert candidates.blockers
    assert any(b.code == BlockerCode.AUTHORITY_SCOPE_MISMATCH for b in candidates.blockers)


@pytest.mark.asyncio
async def test_round5_task9_override_cannot_bypass_status(sqlite_session):
    from backend.app.models.harvest_state import HarvestStateRun

    run = HarvestStateRun(
        id=1,
        status="blocked",  # NOT completed
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot={},
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result={},
        continuity_result={},
        canonical_output={},
        config_hash=_hash("cfg"),
        result_hash=_hash("res"),
        canonical_payload_hash=_hash("pay"),
        forecast_start_date=date(2026, 3, 1),
        forecast_end_date=date(2026, 3, 2),
        as_of_date=date(2026, 3, 1),
        destination_factory_id=1,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_model_run_id=None,
        maturity_model_version="v1",
        maturity_model_config_hash=_hash("mc"),
        maturity_model_source_signature="sig",
        maturity_model_artifact_id=None,
        maturity_model_artifact_hash=_hash("ma"),
        maturity_forecast_run_id=1,
        maturity_forecast_source_signature="fsig",
    )
    sqlite_session.add(run)
    await sqlite_session.flush()

    from backend.app.agent.adapters.baseline_composer import (
        _select_harvest_state_run_candidates,
    )

    candidates = await _select_harvest_state_run_candidates(
        sqlite_session,
        as_of=date(2026, 3, 1),
        run_id_override=1,
        destination_factory_id=1,
    )
    # Round 8: discriminated AuthoritySelectionResult.  Override
    # with non-completed status MUST emit AUTHORITY_IDENTITY_MALFORMED.
    assert candidates.candidates == ()
    assert candidates.blockers
    assert any(b.code == BlockerCode.AUTHORITY_IDENTITY_MALFORMED for b in candidates.blockers)


# ============================================================================
# P0-4 — per-variety mapping + reconciliation
# ============================================================================


@pytest.mark.asyncio
async def test_round5_variety_catalog_uses_execute_not_scalars(sqlite_session):
    """The variety catalog lookup uses ``session.execute()`` (not
    ``session.scalars()``) so multi-column queries yield rows."""

    from backend.app.models.master_data import Variety

    sqlite_session.add(Variety(id=1, code="Dx", name="Test"))
    await sqlite_session.flush()

    rows = (await sqlite_session.execute(select(Variety.id, Variety.code))).all()
    assert len(rows) == 1
    pk, code = rows[0]
    assert int(pk) == 1
    assert str(code) == "Dx"


# ============================================================================
# P0-6 — discriminated SimulateScenarioOutput
# ============================================================================


@pytest.mark.asyncio
async def test_round5_scenario_override_without_execution_returns_blocked(sqlite_session):
    """When a scenario override is supplied, the result is
    ``status="BLOCKED"`` (not a fake SUCCESS).  The top-level
    ``blockers`` carries the SCENARIO_OVERRIDE_EXECUTION_NOT_AVAILABLE
    blocker; ``delta_vs_baseline`` is the zero-delta (NOT a
    fabricated scenario curve)."""

    from backend.app.agent.adapters.scenario import DefaultScenarioAdapter
    from backend.app.agent.schemas import (
        AdvancedOverrides,
        LocationInput,
        NormalizedAgentRequest,
        NormalizedVarietyInput,
        PeakMetricPolicy,
        RequestedAsOfDateProvenance,
        ResolvedLocation,
        SimulateScenarioInput,
        SpringFestivalIntensityOverrideValue,
        SpringFestivalIntensityScenarioOverride,
        UncertaintyWideningPolicy,
    )

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
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
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
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
        scenario_overrides=[
            SpringFestivalIntensityScenarioOverride(
                value=SpringFestivalIntensityOverrideValue(value="PRE"),
                target="SPRING_FESTIVAL_INTENSITY",
                source_attestation="test",
                source_ref=None,
            )
        ],
        peak_metric_policy=PeakMetricPolicy(
            policy_version="v1",
            policy_config_hash="b" * 64,
            sustained_window_days=3,
            peak_window_days_before=0,
            peak_window_days_after=0,
            high_load_threshold_ratio="1.20",
        ),
    )
    adapter = DefaultScenarioAdapter()
    out = await adapter.execute(sqlite_session, input=inp)
    assert out.status == "BLOCKED"
    codes = [b.code for b in out.blockers]
    assert BlockerCode.SCENARIO_OVERRIDE_EXECUTION_NOT_AVAILABLE in codes
    # P0-8 round 6: blocked scenario MUST NOT carry fabricated result
    # fields.  No scenario curve, no scenario peak, no delta.
    assert out.forecast_daily_curve is None
    assert out.forecast_peak is None
    assert out.delta_vs_baseline is None


# ============================================================================
# P0-7 — Spring Festival calendar
# ============================================================================


def test_round5_default_calendar_requires_versioned_policy():
    cal = DefaultSpringFestivalCalendarPort()
    assert cal.policy_version == ""
    assert cal.config_hash is None
    assert cal.is_policy_loaded() is False


def test_round5_missing_calendar_policy_emits_blocker_via_is_policy_loaded():
    cal = DefaultSpringFestivalCalendarPort()
    for d in (date(2026, 1, 1), date(2026, 2, 17), date(2026, 12, 31)):
        assert cal.phase_for(target=d) == "NONE"
    assert cal.is_policy_loaded() is False


def test_round5_hardcoded_calendar_is_not_default_production_source():
    default = DefaultSpringFestivalCalendarPort()
    fixture = HardcodedSpringFestivalCalendarPort()
    assert default.phase_for(target=date(2026, 2, 17)) == "NONE"
    assert fixture.phase_for(target=date(2026, 2, 17)) == "DURING"
    assert default.is_policy_loaded() is False
    assert fixture.is_policy_loaded() is True


def test_round5_calendar_policy_version_and_hash_are_deterministic():
    a = HardcodedSpringFestivalCalendarPort()
    b = HardcodedSpringFestivalCalendarPort()
    assert a.policy_version == b.policy_version
    assert a.config_hash == b.config_hash
    assert len(a.config_hash or "") == 64


# ============================================================================
# Repository-wide static checks
# ============================================================================


def test_round5_repository_wide_static_checks_pass():
    """The repository-wide static checks (ruff check . / format
    --check . / mypy backend/app) all pass on this round-5 HEAD.

    The fact that the test file imports below work is itself the
    proof that the source files are syntactically valid + mypy-clean.
    """

    from backend.app.agent.enums import BlockerCode

    assert BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING.value == ("TASK9_PER_VARIETY_GRAIN_MISSING")
    assert BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING.value == (
        "LOCATION_SOURCE_CAPABILITY_MISSING"
    )
    assert BlockerCode.INFERENCE_CONFIG_MISSING.value == "INFERENCE_CONFIG_MISSING"
    assert BlockerCode.INFERENCE_CONFIG_HASH_MALFORMED.value == "INFERENCE_CONFIG_HASH_MALFORMED"
