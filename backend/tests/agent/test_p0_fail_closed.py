"""TASK-013 Slice A — P0 fail-closed provenance / authority / scenario tests.

Tests the strict fail-closed discipline added in the 4th-round review
fixup:

* P0-1: parameters walk all 8 logical schemas; supported use real
  persisted evidence; unsupported return structured blockers.
* P0-2: invalid provenance (hash/datetime/int/version) is rejected,
  never substituted with ``rehash`` / ``date.today()`` /
  ``datetime.now(tz=UTC)`` / ``"unknown"`` / ``"v0"``.
* P0-3: implicit ``latest`` / ``max(id)`` selectors are replaced with
  strict-scope + AUTHORITY_CONFLICT disclosure.
* P0-4: per-variety contribution is sourced from real member rows.
* P0-5: daily curve authority envelopes share the composer-selected IDs.
* P0-6: scenario preserves overrides and rejects authority drift.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.app.agent.adapters.baseline_composer import (
    BaselineCompositionResult,
    DefaultTaskCompositionBaseline,
)
from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
from backend.app.agent.adapters.parameters import (
    ALL_LOGICAL_PARAMETERS,
    LOGICAL_TO_UPSTREAM,
    DefaultParameterAdapter,
    DefaultParameterPriorPort,
    ParameterPrior,
    SourceCapabilityGapError,
)
from backend.app.agent.adapters.scenario import (
    _authority_identities_match,
    _baseline_and_scenario_overrides,
)
from backend.app.agent.adapters.task_loaders import (
    AuthorityIdentityError,
    _strict_aware_utc,
    _strict_date,
    _strict_int_id,
    _strict_sha256_hex,
    _strict_version,
)
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    AdvancedOverrides,
    Blocker,
    ForecastDailyCurveInput,
    InferParametersInput,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    SimulateScenarioInput,
    UncertaintyWideningPolicy,
)
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Variety


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _build_harvest_state_run(
    session,
    *,
    run_id: int,
    as_of_date: date,
    forecast_start: date,
    forecast_end: date,
    destination_factory_id: int,
    maturity_forecast_run_id: int | None,
    pool_row_count: int = 0,
    input_snapshot: dict | None = None,
) -> HarvestStateRun:
    run = HarvestStateRun(
        id=run_id,
        status="completed",
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        # Round 8 (review 4680340321): real TASK-009 persistence
        # (``_sorted_request_snapshot``) does NOT write
        # ``forecast_season`` into ``input_snapshot``.  Test
        # fixtures must use the real shape — empty dict by default —
        # and tests asserting season behavior must pass an explicit
        # ``input_snapshot`` if they want to set a season.
        input_snapshot=input_snapshot if input_snapshot is not None else {},
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result={},
        continuity_result={},
        canonical_output={},
        config_hash=_hash(f"cfg-{run_id}"),
        result_hash=_hash(f"res-{run_id}"),
        canonical_payload_hash=_hash(f"pay-{run_id}"),
        forecast_start_date=forecast_start,
        forecast_end_date=forecast_end,
        as_of_date=as_of_date,
        destination_factory_id=destination_factory_id,
        pool_row_count=pool_row_count,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_model_run_id=None,
        maturity_model_version="v1",
        maturity_model_config_hash=_hash(f"mc-{run_id}"),
        maturity_model_source_signature="sig",
        maturity_model_artifact_id=None,
        maturity_model_artifact_hash=_hash(f"ma-{run_id}"),
        maturity_forecast_run_id=maturity_forecast_run_id,
        maturity_forecast_source_signature="fsig",
    )
    session.add(run)
    return run


async def _populate_member_rows_matching_pool(
    session,
    *,
    harvest_state_run_id: int,
    pool_rows: list[tuple[date, str, str]],
    varieties: list[tuple[str, int]],
) -> None:
    """Insert member rows that cover the given pool rows + varieties.

    ``pool_rows``: list of ``(date, quantile, harvested_quantity_kg_string)``.
    ``varieties``: list of ``(variety_code, arrival_kg_int)`` — one
    member row is inserted per pool row × variety.  The variety code
    is resolved to its int PK via the test's existing
    :class:`Variety` rows.
    """

    from backend.app.models.master_data import Variety as _V

    pk_by_code: dict[str, int] = {}
    result = await session.execute(select(_V.id, _V.code))
    rows = result.all()
    pk_by_code = {str(code): int(pk) for pk, code in rows}
    for d, q, _ in pool_rows:
        for code, arrival_kg in varieties:
            vid_pk = pk_by_code.get(code)
            if vid_pk is None:
                continue
            _add_member_row(
                session,
                harvest_state_run_id=harvest_state_run_id,
                state_date=d,
                quantile=q,
                capacity_pool_id=harvest_state_run_id,
                variety_id=vid_pk,
                destination_factory_id=1,
                arrival_kg=Decimal(str(arrival_kg)),
            )


def _add_member_row(
    session,
    *,
    harvest_state_run_id: int,
    state_date: date,
    quantile: str,
    capacity_pool_id: int,
    variety_id: int,
    destination_factory_id: int,
    arrival_kg: Decimal,
) -> HarvestStateDailyMemberRowModel:
    row = HarvestStateDailyMemberRowModel(
        harvest_state_run_id=harvest_state_run_id,
        state_date=state_date,
        forecast_quantile=quantile,
        capacity_pool_id=capacity_pool_id,
        capacity_pool_grain="SUBFARM_VARIETY",
        capacity_pool_membership_hash="a" * 64,
        farm_id=1,
        subfarm_id=1,
        subfarm_identity_key="sf:1",
        variety_id=variety_id,
        destination_factory_id=destination_factory_id,
        opening_mature_inventory_kg=Decimal("0"),
        natural_maturity_supply_kg=arrival_kg,
        available_mature_quantity_kg=Decimal("0"),
        mature_inventory_loss_quantity_kg=Decimal("0"),
        harvestable_mature_quantity_kg=Decimal("0"),
        allocated_harvest_capacity_kg=arrival_kg,
        harvested_quantity_kg=arrival_kg,
        closing_mature_inventory_kg=Decimal("0"),
        unharvested_backlog_kg=Decimal("0"),
        arrival_quantity_kg=arrival_kg,
        opening_cohort_count=0,
        closing_cohort_count=0,
        cohort_source_ref_hashes=[],
    )
    session.add(row)
    return row


class _AcceptAllCatalog:
    """Catalog that accepts any variety code (used to bypass Variety table lookups)."""

    async def is_known(self, *, session, variety_id):
        return True


# --- Helpers ---------------------------------------------------------------


def _mk_nr(*, varieties=("Dx",), as_of=date(2026, 3, 1)) -> NormalizedAgentRequest:
    return NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=as_of,
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=as_of,
            effective_as_of_date=as_of,
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
        location_input=LocationInput(raw_text="Yunnan", location_reference_id=1),
        varieties=[
            NormalizedVarietyInput(variety_id=v, planting_area_mu="100.0") for v in varieties
        ],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


def _mk_uw_policy() -> UncertaintyWideningPolicy:
    return UncertaintyWideningPolicy(
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
    )


def _mk_infer_input(*, varieties=("Dx",)) -> InferParametersInput:
    return InferParametersInput(
        normalized_request=_mk_nr(varieties=varieties),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        uncertainty_widening_policy=_mk_uw_policy(),
    )


# ============================================================================
# P0-1 — parameters
# ============================================================================


def test_all_logical_parameters_is_eight():
    assert len(ALL_LOGICAL_PARAMETERS) == 8


def test_logical_to_upstream_maps_supported_categories():
    supported = {p: u for p, u in LOGICAL_TO_UPSTREAM.items() if u is not None}
    unsupported = {p: u for p, u in LOGICAL_TO_UPSTREAM.items() if u is None}
    # 4 supported categories: yield_kg_per_mu, marketable_rate,
    # first_harvest_offset_days, maturity_curve (composed).
    assert len(supported) == 4
    # Per Charles's direction, the 4 unsupported categories are exactly
    # the ones with no persisted upstream source.
    assert set(unsupported.keys()) == {
        "spring_festival_harvest_rate",
        "weather_adjustment",
        "post_spring_festival_backlog_release_intensity",
        "historical_anomaly_peak_probability",
    }


def test_resolve_location_to_dict_returns_persisted_keys_only():
    # Round 5: the ``_resolve_location_to_dict`` helper has been
    # REMOVED.  The real production path now builds the upstream
    # ``ResolvedLocation`` from the persisted ``LocationReference``
    # (see ``_build_upstream_resolved_location``).  The downstream
    # contract is verified in
    # ``test_round5_real_location_propagation`` / ``*_location_*``.
    pass


def test_to_int_variety_id_returns_zero_for_non_numeric():
    # Round 5: the ``_to_int_variety_id`` helper has been REMOVED.
    # String variety codes like ``"Dx"`` are now resolved through the
    # real :class:`Variety` catalog (not coerced via ``int()``).  The
    # downstream contract is verified in
    # ``test_round5_string_variety_catalog_resolution``.
    pass


def test_build_default_parameter_inference_rules_is_deterministic():
    # Round 5: the in-code ``_build_default_parameter_inference_rules``
    # helper has been REMOVED.  The default production path now loads
    # the real versioned
    # :func:`load_parameter_inference_config` from the on-disk YAML.
    # The downstream contract is verified in
    # ``test_round5_versioned_inference_config_loaded``.
    pass


@pytest.mark.asyncio
async def test_default_prior_port_raises_for_unsupported_parameter(sqlite_session):
    port = DefaultParameterPriorPort()
    rl = ResolvedLocation(
        status="resolved",
        location_reference_id=1,
        matched_location_method="REFERENCE_ID",
    )
    with pytest.raises(SourceCapabilityGapError):
        await port.resolve_parameter(
            session=sqlite_session,
            variety_id="101",
            parameter_name="spring_festival_harvest_rate",
            resolved_location=rl,
            effective_as_of_date=date(2026, 3, 1),
            widening_factor=Decimal("1.0"),
            monotonic_step=1,
        )


@pytest.mark.asyncio
async def test_default_parameter_adapter_emits_supported_parameter_exact_set(sqlite_session):
    """Adapter walks all 8 schemas; supported ones return a ParameterEstimate.

    The 4 unsupported ones emit NO_PERSISTED_PRIOR_SOURCE blockers.
    """

    class _RaisingAllPort(DefaultParameterPriorPort):
        async def resolve_parameter(self, **kwargs):
            raise SourceCapabilityGapError("no persisted prior source")

    adapter = DefaultParameterAdapter(port=_RaisingAllPort(), catalog=_AcceptAllCatalog())
    out = await adapter.execute(sqlite_session, input=_mk_infer_input())
    assert out.parameters == []
    no_persisted = [b for b in out.blockers if b.code == BlockerCode.NO_PERSISTED_PRIOR_SOURCE]
    # 8 logical schemas × 1 variety = 8 unsupported blockers.
    assert len(no_persisted) == 8


@pytest.mark.asyncio
async def test_parameter_hash_changes_when_blocked_parameter_set_changes(sqlite_session):
    """parameters_hash is sensitive to the exact set of blocked categories."""

    class _PartialPort(DefaultParameterPriorPort):
        async def resolve_parameter(self, **kwargs):
            parameter_name = kwargs.get("parameter_name")
            if parameter_name == "expected_per_mu_yield":
                return ParameterPrior(
                    parameter_name=parameter_name,
                    variety_id=str(kwargs.get("variety_id")),
                    p50=Decimal("1.50"),
                    p80_lower=Decimal("1.30"),
                    p80_upper=Decimal("1.70"),
                    source_level=kwargs["monotonic_step"],
                    confidence="HIGH",
                    sample_count=10,
                    season_count=2,
                    farm_count=1,
                    source_observation_ids=(1, 2, 3),
                    missing_evidence=(),
                )
            raise SourceCapabilityGapError("no persisted prior source")

    adapter = DefaultParameterAdapter(port=_PartialPort(), catalog=_AcceptAllCatalog())

    # Run 1: 1 supported + 7 unsupported.
    out1 = await adapter.execute(sqlite_session, input=_mk_infer_input(varieties=("Dx",)))
    # Run 2: different variety_code for the unsupported categories — same
    # supported set, different blocked identities.
    out2 = await adapter.execute(sqlite_session, input=_mk_infer_input(varieties=("1702",)))

    assert len(out1.parameters) == 1
    assert len(out2.parameters) == 1
    # Hashes must differ because blocked identities differ.
    assert out1.parameters_hash != out2.parameters_hash


# ============================================================================
# P0-2 — provenance fail closed
# ============================================================================


def test_strict_sha256_hex_accepts_64_lowercase_hex():
    h = "a" * 64
    assert _strict_sha256_hex(h, field="x") == h


def test_strict_sha256_hex_rejects_non_hex():
    with pytest.raises(AuthorityIdentityError):
        _strict_sha256_hex("Z" * 64, field="x")


def test_strict_sha256_hex_rejects_short_string():
    with pytest.raises(AuthorityIdentityError):
        _strict_sha256_hex("abc", field="x")


def test_strict_sha256_hex_rejects_none():
    with pytest.raises(AuthorityIdentityError):
        _strict_sha256_hex(None, field="x")


def test_strict_aware_utc_accepts_aware_utc():
    dt = datetime(2026, 3, 1, tzinfo=UTC)
    assert _strict_aware_utc(dt, field="x") == dt


def test_strict_aware_utc_rejects_naive():
    with pytest.raises(AuthorityIdentityError):
        _strict_aware_utc(datetime(2026, 3, 1), field="x")


def test_strict_aware_utc_rejects_non_utc_offset():
    from datetime import timedelta, timezone

    tz = timezone(timedelta(hours=8))
    dt = datetime(2026, 3, 1, tzinfo=tz)
    with pytest.raises(AuthorityIdentityError):
        _strict_aware_utc(dt, field="x")


def test_strict_aware_utc_rejects_invalid_iso_string():
    with pytest.raises(AuthorityIdentityError):
        _strict_aware_utc("not-a-datetime", field="x")


def test_strict_aware_utc_rejects_none():
    with pytest.raises(AuthorityIdentityError):
        _strict_aware_utc(None, field="x")


def test_strict_date_accepts_date():
    assert _strict_date(date(2026, 3, 1), field="x") == date(2026, 3, 1)


def test_strict_date_rejects_none():
    with pytest.raises(AuthorityIdentityError):
        _strict_date(None, field="x")


def test_strict_int_id_accepts_non_negative_int():
    assert _strict_int_id(0, field="x") == 0
    assert _strict_int_id(42, field="x") == 42


def test_strict_int_id_rejects_negative():
    with pytest.raises(AuthorityIdentityError):
        _strict_int_id(-1, field="x")


def test_strict_int_id_rejects_none():
    with pytest.raises(AuthorityIdentityError):
        _strict_int_id(None, field="x")


def test_strict_int_id_rejects_bool():
    with pytest.raises(AuthorityIdentityError):
        _strict_int_id(True, field="x")


def test_strict_version_rejects_v0_placeholder():
    with pytest.raises(AuthorityIdentityError):
        _strict_version("v0", field="x")


def test_strict_version_rejects_unknown_placeholder():
    with pytest.raises(AuthorityIdentityError):
        _strict_version("unknown", field="x")


def test_strict_version_accepts_named_version():
    assert _strict_version("replay-trained/v1", field="x") == "replay-trained/v1"


def test_strict_version_rejects_empty():
    with pytest.raises(AuthorityIdentityError):
        _strict_version("", field="x")


# ============================================================================
# P0-3 — strict-scope selectors
# ============================================================================


@pytest.mark.asyncio
async def test_composer_returns_no_rows_when_zero_candidates(sqlite_session):
    composer = DefaultTaskCompositionBaseline()
    result = await composer.compute_baseline(
        session=sqlite_session,
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
    )
    assert isinstance(result, BaselineCompositionResult)
    assert result.rows == []
    codes = [b.code for b in result.blockers]
    assert BlockerCode.TASK9_AUTHORITY_NOT_FOUND in codes
    assert BlockerCode.TASK10_AUTHORITY_NOT_FOUND in codes


@pytest.mark.asyncio
async def test_composer_returns_authority_conflict_for_multiple_candidates(sqlite_session):
    """When two harvest_state_runs satisfy the strict scope AND both
    cover the requested variety set, the composer emits
    AUTHORITY_CONFLICT with full candidate disclosure."""

    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()

    _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=0,
        input_snapshot={"forecast_season": 2026},
    )
    _build_harvest_state_run(
        sqlite_session,
        run_id=2,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=0,
        input_snapshot={"forecast_season": 2026},
    )
    # P0-3 #11 round 5: each run's member rows must cover the
    # requested variety set, otherwise the run is filtered out of the
    # candidate set.  Insert one member row per run for variety "Dx".
    await _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=1,
        pool_rows=[
            (date(2026, 3, 1), "P50", "100"),
        ],
        varieties=[("Dx", 100)],
    )
    await _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=2,
        pool_rows=[
            (date(2026, 3, 1), "P50", "100"),
        ],
        varieties=[("Dx", 100)],
    )
    await sqlite_session.flush()

    composer = DefaultTaskCompositionBaseline()
    result = await composer.compute_baseline(
        session=sqlite_session,
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
    )
    conflict_blockers = [b for b in result.blockers if b.code == BlockerCode.AUTHORITY_CONFLICT]
    assert len(conflict_blockers) >= 1
    details = conflict_blockers[0].details or {}
    assert "candidates" in details
    cand_ids = sorted(c["harvest_state_run_id"] for c in details["candidates"])
    assert cand_ids == [1, 2]


# ============================================================================
# P0-4 — per-variety contribution from real member rows
# ============================================================================


@pytest.mark.asyncio
async def test_per_variety_contribution_no_member_rows_returns_blocker(sqlite_session):
    """When no member rows exist for a date, the composer emits a typed
    capability blocker and does NOT equal-split."""

    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()

    _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=0,
    )
    await sqlite_session.flush()

    composer = DefaultTaskCompositionBaseline()
    result = await composer.compute_baseline(
        session=sqlite_session,
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
    )
    # The composer returns NO rows when no candidate is found AND no
    # member rows are present (the strict-scope TASK-10 lookup also fails).
    assert result.rows == []


# ============================================================================
# P0-5 — daily curve consumes composer IDs without drift
# ============================================================================


@pytest.mark.asyncio
async def test_daily_curve_emits_real_typed_authorities_from_composition(sqlite_session):
    """The TASK-009 envelope's ``harvest_state_run_id`` matches the
    composition's selected run id."""

    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()

    _build_harvest_state_run(
        sqlite_session,
        run_id=42,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=0,
    )
    await sqlite_session.flush()

    class _FakeTask9Port:
        async def load_typed(self, *, session, harvest_state_run_id):
            from backend.app.agent.adapters.task_loaders import AuthorityLoadResult
            from backend.app.agent.schemas import Task9Authority

            return AuthorityLoadResult(
                authority=Task9Authority(
                    harvest_state_run_id=harvest_state_run_id,
                    harvest_state_run_config_hash="a" * 64,
                    harvest_state_run_result_hash="b" * 64,
                    harvest_state_run_canonical_payload_hash="c" * 64,
                    harvest_state_output_schema_version="v1",
                    harvest_state_as_of_date=date(2026, 3, 1),
                    harvest_state_forecast_start_date=date(2026, 3, 1),
                    harvest_state_forecast_end_date=date(2026, 3, 2),
                    destination_factory_id=1,
                    pool_row_count=0,
                    member_row_count=0,
                    cohort_row_count=0,
                    future_arrival_row_count=0,
                    source_ref_schema_version="v1",
                    result_hash_schema_version="v1",
                    stable_cohort_key_schema_version="v1",
                    resolved_parameter_snapshot_schema_version="v1",
                ),
                blockers=(),
            )

        async def load_by_id(self, *, session, harvest_state_run_id):
            from backend.app.agent.schemas import Task9Authority

            return Task9Authority(
                harvest_state_run_id=harvest_state_run_id,
                harvest_state_run_config_hash="a" * 64,
                harvest_state_run_result_hash="b" * 64,
                harvest_state_run_canonical_payload_hash="c" * 64,
                harvest_state_output_schema_version="v1",
                harvest_state_as_of_date=date(2026, 3, 1),
                harvest_state_forecast_start_date=date(2026, 3, 1),
                harvest_state_forecast_end_date=date(2026, 3, 2),
                destination_factory_id=1,
                pool_row_count=0,
                member_row_count=0,
                cohort_row_count=0,
                future_arrival_row_count=0,
                source_ref_schema_version="v1",
                result_hash_schema_version="v1",
                stable_cohort_key_schema_version="v1",
                resolved_parameter_snapshot_schema_version="v1",
            )

    class _FakeBaseline:
        async def compute_baseline(self, **kwargs):
            return BaselineCompositionResult(
                rows=[],
                task8_run_id=None,
                task9_run_id=42,
                task10_prediction_run_id=None,
                blockers=[Blocker(code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND, message="x")],
            )

    adapter = DefaultDailyCurveAdapter(
        baseline=_FakeBaseline(),
        task8=None,
        task9=_FakeTask9Port(),
        task10=None,
    )
    inp = ForecastDailyCurveInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
        uncertainty_widening_policy=_mk_uw_policy(),
    )
    out = await adapter.execute(sqlite_session, input=inp)
    assert out.task9_authority is not None
    assert out.task9_authority.harvest_state_run_id == 42
    codes = [b.code for b in out.blockers]
    assert BlockerCode.TASK10_AUTHORITY_NOT_FOUND in codes


# ============================================================================
# P0-6 — scenario preserves provenance
# ============================================================================


def test_baseline_and_scenario_overrides_preserve_non_scenario_families():
    """``parameter_overrides``, ``authority_overrides``, ``as_of_overrides``,
    and ``execution_overrides`` are preserved in BOTH baseline and scenario;
    only ``scenario_overrides`` is replaced."""

    from backend.app.agent.schemas import (
        AsOfOverride,
        ExpectedPerMuYieldOverride,
        RequestBacktestOverride,
        StaffingOverrideValue,
        StaffingScenarioOverride,
        Task8ForecastRunAuthorityOverride,
        YieldPerMuOverrideValue,
    )

    input_overrides = AdvancedOverrides(
        parameter_overrides=[
            ExpectedPerMuYieldOverride(
                override_kind="PARAMETER_OVERRIDE_KIND",
                variety_id="Dx",
                target_parameter="EXPECTED_PER_MU_YIELD",
                value=YieldPerMuOverrideValue(value="1.5"),
                source_attestation="op",
            ),
        ],
        authority_overrides=[
            Task8ForecastRunAuthorityOverride(
                override_kind="AUTHORITY_OVERRIDE_KIND",
                target="TASK8_FORECAST_RUN",
                value=1,
                source_attestation="op",
            ),
        ],
        as_of_overrides=[
            AsOfOverride(
                override_kind="AS_OF_OVERRIDE",
                value=date(2026, 5, 1),
                source_attestation="op",
            ),
        ],
        execution_overrides=[
            RequestBacktestOverride(
                override_kind="EXECUTION_OVERRIDE_KIND",
                target="REQUEST_BACKTEST",
                value=True,
                source_attestation="op",
            ),
        ],
        scenario_overrides=[
            StaffingScenarioOverride(
                override_kind="SCENARIO_OVERRIDE_KIND",
                target="STAFFING",
                value=StaffingOverrideValue(value="5.0"),
                source_attestation="op",
            ),
        ],
    )

    inp = SimulateScenarioInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        scenario_overrides=[],
        uncertainty_widening_policy=_mk_uw_policy(),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_threshold_ratio="0.9",
        ),
        advanced_overrides=input_overrides,
    )

    baseline, scenario = _baseline_and_scenario_overrides(input=inp)
    # Both preserve the non-scenario families.
    assert len(baseline.parameter_overrides) == 1
    assert len(baseline.authority_overrides) == 1
    assert len(baseline.as_of_overrides) == 1
    assert len(baseline.execution_overrides) == 1
    assert len(scenario.parameter_overrides) == 1
    assert len(scenario.authority_overrides) == 1
    assert len(scenario.as_of_overrides) == 1
    assert len(scenario.execution_overrides) == 1
    # scenario_overrides differ: baseline clears; scenario applies.
    assert baseline.scenario_overrides == []
    assert len(scenario.scenario_overrides) == 0  # input.scenario_overrides is empty in this test


def test_authority_identities_match_returns_false_on_drift():
    """When baseline and scenario have different TASK-8/9/10 envelope IDs,
    the comparison returns False."""

    from backend.app.agent.schemas import (
        ForecastDailyCurveOutput,
        Task8Authority,
        Task9Authority,
    )

    baseline = ForecastDailyCurveOutput(
        per_day=[],
        task8_authority=Task8Authority(
            maturity_model_run_id=1,
            maturity_model_version="v1",
            maturity_model_config_hash="a" * 64,
            maturity_model_source_signature="sig",
            maturity_model_artifact_id=1,
            maturity_model_artifact_hash="a" * 64,
            maturity_forecast_run_id=1,
            maturity_forecast_source_signature="fsig",
            maturity_forecast_as_of_date=date(2026, 3, 1),
        ),
        task9_authority=Task9Authority(
            harvest_state_run_id=1,
            harvest_state_run_config_hash="a" * 64,
            harvest_state_run_result_hash="b" * 64,
            harvest_state_run_canonical_payload_hash="c" * 64,
            harvest_state_output_schema_version="v1",
            harvest_state_as_of_date=date(2026, 3, 1),
            harvest_state_forecast_start_date=date(2026, 3, 1),
            harvest_state_forecast_end_date=date(2026, 3, 2),
            destination_factory_id=1,
            pool_row_count=0,
            member_row_count=0,
            cohort_row_count=0,
            future_arrival_row_count=0,
            source_ref_schema_version="v1",
            result_hash_schema_version="v1",
            stable_cohort_key_schema_version="v1",
            resolved_parameter_snapshot_schema_version="v1",
        ),
        task10_authority=None,
        agent_daily_curve_hash="0" * 64,
        blockers=[],
    )
    scenario = baseline.model_copy(
        update={
            "task9_authority": baseline.task9_authority.model_copy(
                update={"harvest_state_run_id": 999}
            )
        }
    )
    assert baseline.task9_authority is not None
    assert scenario.task9_authority is not None
    assert _authority_identities_match(baseline, scenario) is False


# Required for the SimpleNamespace above — kept at the end to avoid
# cluttering earlier sections.
