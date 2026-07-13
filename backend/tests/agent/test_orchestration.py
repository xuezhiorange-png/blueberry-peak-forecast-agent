import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.app.agent.canonical import sha256_payload
from backend.app.agent.enums import BlockerCode
from backend.app.agent.orchestration import (
    AgentOrchestrator,
    UnsupportedToolError,
)
from backend.app.agent.schemas import (
    AdvancedOverrides,
    AsOfOverride,
    Blocker,
    ForecastDailyCurveOutput,
    InferParametersOutput,
    LocationInput,
    MinimalInputRequest,
    MinimalVarietyInput,
    PeakMetricPolicy,
    ResolvedForecastSeasonIdentity,
    ResolvedLocation,
    ResolveLocationOutput,
    UncertaintyWideningPolicy,
)
from backend.app.agent.season_resolution import (
    SEASON_RESOLUTION_POLICY_CONFIG_HASH,
    SEASON_RESOLUTION_POLICY_VERSION,
    SeasonResolutionResult,
)
from backend.app.harvest_state.canonical import make_season_record_hash
from backend.app.harvest_state.schemas import ForecastSeasonIdentitySnapshot


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


class _SeasonResolver:
    def __init__(self, *, policy_hash: str = SEASON_RESOLUTION_POLICY_CONFIG_HASH) -> None:
        self.policy_hash = policy_hash

    async def resolve(
        self,
        session: object,
        *,
        effective_as_of_date: date,
        requested_forecast_season: int | str | None,
    ) -> SeasonResolutionResult:
        if requested_forecast_season == 2027 or (
            requested_forecast_season is None and effective_as_of_date >= date(2027, 1, 1)
        ):
            season_id, code = 2, "2027"
            start_date, end_date = date(2027, 1, 1), date(2027, 4, 30)
        else:
            season_id, code = 1, "2026"
            start_date, end_date = date(2026, 1, 1), date(2026, 4, 30)
        snapshot = ForecastSeasonIdentitySnapshot(
            season_id=season_id,
            season_code=code,
            start_date=start_date,
            end_date=end_date,
            season_record_hash=make_season_record_hash(
                season_id=season_id,
                season_code=code,
                start_date=start_date,
                end_date=end_date,
            ),
        )
        return SeasonResolutionResult(
            identity=ResolvedForecastSeasonIdentity(
                season_snapshot=snapshot,
                season_resolution_policy_version=SEASON_RESOLUTION_POLICY_VERSION,
                season_resolution_policy_config_hash=self.policy_hash,
            )
        )


class _Location:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> ResolveLocationOutput:
        self.calls.append("RESOLVE_LOCATION")
        return ResolveLocationOutput(
            resolved_location=ResolvedLocation(
                status="resolved",
                location_reference_id=601,
                matched_location_method="REFERENCE_ID",
            ),
            location_catalog_version="catalog/v1",
        )


class _BrokenLocation:
    async def execute(self, session: object, *, input: object) -> ResolveLocationOutput:
        raise RuntimeError("secret traceback must not escape")


class _BlockedLocation:
    def __init__(self, *, status: str, code: BlockerCode) -> None:
        self.status = status
        self.code = code

    async def execute(self, session: object, *, input: object) -> ResolveLocationOutput:
        return ResolveLocationOutput(
            resolved_location=ResolvedLocation(
                status=self.status,
                matched_location_method="REFERENCE_ID",
            ),
            location_catalog_version="catalog/v1",
            blockers=[
                Blocker(
                    code=self.code,
                    message="location adapter blocker",
                    retry_hint="FIX_INPUT",
                )
            ],
        )


class _Parameters:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> InferParametersOutput:
        self.calls.append("INFER_PARAMETERS")
        return InferParametersOutput(
            parameters=[],
            uncertainty_widening_policy_version="uncertainty-widening/v1",
            uncertainty_widening_policy_config_hash="b" * 64,
            parameters_hash="d" * 64,
        )


class _Daily:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> ForecastDailyCurveOutput:
        self.calls.append("FORECAST_DAILY_CURVE")
        return ForecastDailyCurveOutput(per_day=[], agent_daily_curve_hash="e" * 64)


class _Peak:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def execute(self, *, input: object) -> object:
        self.calls.append("FORECAST_PEAK")
        return type(
            "PeakOutput",
            (),
            {
                "agent_peak_hash": "f" * 64,
                "model_dump": lambda self, mode="json": {"agent_peak_hash": self.agent_peak_hash},
                "blockers": [],
            },
        )()


class _Scenario:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> object:
        self.calls.append("SIMULATE_SCENARIO")
        return type("ScenarioOutput", (), {"scenario_config_hash": "1" * 64, "blockers": []})()


def _request() -> MinimalInputRequest:
    return MinimalInputRequest(
        request_id="request-1",
        location=LocationInput(raw_text="Yunnan, China"),
        varieties=[MinimalVarietyInput(variety_id="101", planting_area_mu="100.0")],
    )


def _orchestrator(
    calls: list[str], *, season_resolver: _SeasonResolver | None = None
) -> AgentOrchestrator:
    return AgentOrchestrator(
        season_resolver=season_resolver or _SeasonResolver(),
        location_adapter=_Location(calls),
        parameter_adapter=_Parameters(calls),
        daily_curve_adapter=_Daily(calls),
        peak_adapter=_Peak(calls),
        scenario_adapter=_Scenario(calls),
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
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_threshold_ratio="0.900",
        ),
    )


@pytest.mark.asyncio
async def test_orchestration_is_ordered_and_byte_stable() -> None:
    first_calls: list[str] = []
    second_calls: list[str] = []
    received_at = datetime(2026, 3, 1, 8, tzinfo=UTC)
    first = await _orchestrator(first_calls).execute(
        None, request=_request(), request_received_at=received_at
    )
    second = await _orchestrator(second_calls).execute(
        None, request=_request(), request_received_at=received_at
    )

    assert first_calls == [
        "RESOLVE_LOCATION",
        "INFER_PARAMETERS",
        "FORECAST_DAILY_CURVE",
        "FORECAST_PEAK",
        "SIMULATE_SCENARIO",
    ]
    assert first.model_dump_json() == second.model_dump_json()
    assert first.provenance["agent_forecast_output_hash"]
    assert first.normalized_request.effective_forecast_season_id == 1


@pytest.mark.asyncio
async def test_production_wiring_output_matches_full_golden() -> None:
    from backend.app.models.harvest_state import HarvestStateRun
    from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
    from backend.app.models.maturity import (
        MaturityForecastRun,
        MaturityModelArtifact,
        MaturityModelRun,
    )
    from backend.app.models.planning import (
        AgroClimateZone,
        LocationReference,
        ParameterLibraryVersion,
        ParameterObservation,
    )
    from backend.app.models.production_plan import FarmSeasonVarietyPlan
    from backend.tests.agent.conftest import _harvest_state_tables, _residual_tables
    from backend.tests.integration.agent.test_orchestration_postgres import (
        _production_orchestrator,
        _production_request,
        test_slice_b_orchestration_uses_real_postgres_session,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        AgroClimateZone.__table__,
        Farm.__table__,
        Subfarm.__table__,
        Season.__table__,
        Variety.__table__,
        Factory.__table__,
        LocationReference.__table__,
        ParameterLibraryVersion.__table__,
        ParameterObservation.__table__,
        FarmSeasonVarietyPlan.__table__,
        MaturityModelRun.__table__,
        MaturityModelArtifact.__table__,
        MaturityForecastRun.__table__,
        *_harvest_state_tables(),
        *_residual_tables(),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: HarvestStateRun.metadata.create_all(
                sync_connection,
                tables=list(dict.fromkeys(tables)),
            )
        )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        await test_slice_b_orchestration_uses_real_postgres_session(session)
        output = await _production_orchestrator().execute(
            session,
            request=_production_request(),
            request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
    await engine.dispose()

    golden = json.loads(
        (Path(__file__).parent / "golden" / "slice_b_ordinary_user.json").read_text()
    )
    assert json.loads(output.model_dump_json()) == golden


def test_policy_hashes_are_derived_from_policy_payload() -> None:
    orchestrator = _orchestrator([])
    uncertainty = orchestrator._uncertainty_policy
    peak = orchestrator._peak_policy
    assert uncertainty is not None
    assert peak is not None
    changed_uncertainty = uncertainty.model_copy(
        update={
            "factors_by_source_level": {
                **uncertainty.factors_by_source_level,
                "step_5_variety_document_prior_only": "2.100",
            }
        }
    )
    changed_uncertainty = changed_uncertainty.model_copy(
        update={
            "config_hash": sha256_payload(
                changed_uncertainty.model_dump(mode="python", exclude={"config_hash"})
            )
        }
    )
    changed_peak = peak.model_copy(update={"high_load_threshold_ratio": "0.800"})
    changed_peak = changed_peak.model_copy(
        update={
            "policy_config_hash": sha256_payload(
                changed_peak.model_dump(mode="python", exclude={"policy_config_hash"})
            )
        }
    )
    assert uncertainty.config_hash != changed_uncertainty.config_hash
    assert peak.policy_config_hash != changed_peak.policy_config_hash


def test_unsupported_tool_is_blocked_before_dispatch() -> None:
    assert AgentOrchestrator.supported_tool("SIMULATE_SCENARIO") == "SIMULATE_SCENARIO"
    with pytest.raises(UnsupportedToolError):
        AgentOrchestrator.supported_tool("RUN_BACKTEST")


@pytest.mark.asyncio
async def test_as_of_override_is_applied_before_season_resolution() -> None:
    request = _request().model_copy(
        update={
            "requested_as_of_date": date(2026, 12, 31),
            "requested_forecast_season": None,
            "advanced_overrides": AdvancedOverrides(
                as_of_overrides=[
                    AsOfOverride(
                        value=date(2027, 1, 1),
                        source_attestation="test-attestation",
                    )
                ]
            ),
        }
    )
    normalized, _, blocker = await _orchestrator([])._normalize(
        None, request, datetime(2026, 12, 31, tzinfo=UTC)
    )
    assert blocker is None
    assert normalized.effective_as_of_date == date(2027, 1, 1)
    assert normalized.effective_forecast_season_id == 2
    assert normalized.effective_forecast_season_code == "2027"
    assert normalized.requested_as_of_date_provenance.override_applied is True


@pytest.mark.asyncio
async def test_resolver_policy_provenance_changes_agent_hash() -> None:
    received_at = datetime(2026, 3, 1, tzinfo=UTC)
    first = await _orchestrator([]).execute(
        None,
        request=_request(),
        request_received_at=received_at,
    )
    second = await _orchestrator([], season_resolver=_SeasonResolver(policy_hash="f" * 64)).execute(
        None,
        request=_request(),
        request_received_at=received_at,
    )
    assert (
        first.normalized_request.effective_forecast_season_id
        == second.normalized_request.effective_forecast_season_id
    )
    assert (
        first.normalized_request.season_record_hash == second.normalized_request.season_record_hash
    )
    assert (
        first.normalized_request.canonical_request_hash
        != second.normalized_request.canonical_request_hash
    )


@pytest.mark.asyncio
async def test_missing_runtime_policies_are_blockers() -> None:
    calls: list[str] = []
    orchestrator = AgentOrchestrator(
        season_resolver=_SeasonResolver(),
        location_adapter=_Location(calls),
        parameter_adapter=_Parameters(calls),
        daily_curve_adapter=_Daily(calls),
        peak_adapter=_Peak(calls),
    )
    output = await orchestrator.execute(
        None, request=_request(), request_received_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert output.request_status == "BLOCKED"
    assert {blocker.code.value for blocker in output.blockers} == {
        "UNCERTAINTY_WIDENING_POLICY_MISSING",
        "PEAK_POLICY_MISSING",
    }
    assert output.uncertainty_widening_policy_version == "unresolved"
    assert output.peak_metric_policy_version == "unresolved"
    assert output.provenance["uncertainty_widening_policy_version"] == "unresolved"
    assert output.provenance["peak_metric_policy_version"] == "unresolved"
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert calls == ["RESOLVE_LOCATION"]


@pytest.mark.asyncio
async def test_unexpected_adapter_error_is_stable_internal_failure() -> None:
    orchestrator = _orchestrator([])
    orchestrator._location = _BrokenLocation()
    output = await orchestrator.execute(
        None, request=_request(), request_received_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert output.request_status == "BLOCKED"
    assert [blocker.code.value for blocker in output.blockers] == ["INTERNAL_FAILURE"]
    assert "secret traceback" not in output.blockers[0].message


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("unresolved", BlockerCode.LOCATION_UNRESOLVED),
        ("ambiguous", BlockerCode.LOCATION_AMBIGUOUS),
    ],
)
@pytest.mark.asyncio
async def test_location_blocker_is_not_duplicated(
    status: str,
    code: BlockerCode,
) -> None:
    orchestrator = _orchestrator([])
    orchestrator._location = _BlockedLocation(status=status, code=code)
    output = await orchestrator.execute(
        None,
        request=_request(),
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    repeated = await orchestrator.execute(
        None,
        request=_request(),
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    matching = [blocker for blocker in output.blockers if blocker.code == code]
    assert len(matching) == 1
    assert output.model_dump_json() == repeated.model_dump_json()
