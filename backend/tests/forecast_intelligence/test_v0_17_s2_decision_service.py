"""SYNTHETIC=true saved-run fixtures; no real actual or private artifact access."""

import ast
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal, Inexact, localcontext
from pathlib import Path

import pytest
from sqlalchemy import event

from backend.app.forecast_intelligence import what_if
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.decision_schemas import (
    ComparisonRequest,
    CostSelection,
    DecisionSelection,
    SimulationRequest,
)
from backend.app.forecast_intelligence.decision_service import (
    ADAPTER_POLICY,
    BASE_KIND,
    COST_HASHES,
    DecisionSupportService,
    adapt_saved_curve,
    base_scope_binding,
    cost_contract,
    make_scenario,
)
from backend.app.forecast_intelligence.read_schemas import ReadError
from backend.app.forecast_intelligence.read_service import (
    ForecastIntelligenceReadService,
    projection_digest,
)
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import (
    hierarchy_query,
    query,
)
from backend.tests.forecast_intelligence.test_what_if import scenario as synthetic_scenario

ROOT = Path(__file__).resolve().parents[3]


def request_payload(source, sid="A", mode="DIRECT", capacity="140"):
    return {
        "forecast_selection": source.forecast_identity.model_dump(mode="json"),
        "expected_source_result_hash": source.source_result_hash,
        "planning_level": "POINT",
        "cost_contract_id": "SYNTHETIC_BALANCED_R1",
        "expected_cost_contract_hash": COST_HASHES["SYNTHETIC_BALANCED_R1"],
        "scenario_id": sid,
        "scenario_version": "R1",
        "capacity_rows": [
            {
                "date": r.target_date.isoformat(),
                "capacity_mode": mode,
                **(
                    {"daily_handling_capacity_kg": capacity}
                    if mode == "DIRECT"
                    else {
                        "workforce_count": 10,
                        "productivity_kg_per_person_day": "12",
                    }
                ),
                "buffer_handling_capacity_kg": "0" if mode == "DIRECT" else "20",
            }
            for r in source.data.daily_rows
        ],
    }


def selection(payload):
    return DecisionSelection.model_validate(
        {k: v for k, v in payload.items() if k in DecisionSelection.model_fields}
    )


def comparison_payload(payload, count=3):
    return {
        **{k: v for k, v in payload.items() if k in DecisionSelection.model_fields},
        "scenarios": [
            {
                "scenario_id": f"S{i:02}",
                "scenario_version": "R1",
                "capacity_rows": deepcopy(payload["capacity_rows"]),
            }
            for i in range(count)
        ],
    }


def rehash(source, **updates):
    changed = source.model_copy(update=updates)
    return changed.model_copy(
        update={
            "projection_hash": projection_digest(
                changed.model_dump(mode="json", exclude={"projection_hash"})
            )
        }
    )


def test_adapter_policy_identity():
    assert ADAPTER_POLICY == "V0_17_S2_SAVED_FORECAST_DECISION_ADAPTER_R1"


@pytest.mark.parametrize("cost_id", COST_HASHES)
def test_explicit_cost_catalogue_has_no_loss_amount(cost_id):
    response = DecisionSupportService(None).business_loss(
        CostSelection(cost_contract_id=cost_id, expected_cost_contract_hash=COST_HASHES[cost_id])
    )
    value = response.model_dump(mode="json")
    assert value["data"]["total_business_loss"] is None
    assert value["data"]["cost_contract"]["contract_hash"] == COST_HASHES[cost_id]
    assert value["synthetic"] is True
    assert value["canonical_company_cost"] is False
    assert value["loss_unit"] == "SYNTHETIC_LOSS_UNIT"
    assert value["projection_hash"] == projection_digest(
        {k: v for k, v in value.items() if k != "projection_hash"}
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"cost_contract_id": "SYNTHETIC_BALANCED_R1"},
        {"cost_contract_id": "SYNTHETIC_BALANCED_R1", "expected_cost_contract_hash": "x"},
        {
            "cost_contract_id": "SYNTHETIC_BALANCED_R1",
            "expected_cost_contract_hash": "a" * 64,
            "c_under": "1",
        },
    ],
)
def test_no_default_or_override_cost(value):
    with pytest.raises(ValueError):
        CostSelection.model_validate(value)


@pytest.mark.parametrize(
    "cost_id,expected,status",
    [("UNKNOWN", "a" * 64, 404), ("SYNTHETIC_BALANCED_R1", "a" * 64, 409)],
)
def test_unknown_and_drifted_cost(cost_id, expected, status):
    with pytest.raises(ReadError) as error:
        cost_contract(CostSelection(cost_contract_id=cost_id, expected_cost_contract_hash=expected))
    assert error.value.status_code == status


async def test_base_adapter_full_engine_parity(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        payload = request_payload(source)
        curve, binding = adapt_saved_curve(source, selection(payload))
        assert binding["adapter_authority_kind"] == BASE_KIND
        assert binding["adapter_authority_hash"] == projection_digest(base_scope_binding(source))
        # Independently reconstruct canonical bytes, rather than reuse the adapter hasher.
        raw_binding = (
            json.dumps(
                base_scope_binding(source),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        assert hashlib.sha256(raw_binding).hexdigest() == binding["adapter_authority_hash"]
        assert binding["adapter_authority_hash"] not in (
            source.source_result_hash,
            source.authority_identity.authority_hash,
        )
        assert curve.forecast_origin.isoformat() == "2026-01-01T00:00:00+08:00"
        assert [str(r.point_forecast_kg) for r in curve.daily_rows] == [
            r.point_forecast_kg for r in source.data.daily_rows
        ]
        expected = what_if.simulate(
            make_scenario(
                curve,
                selection(payload),
                cost_contract(selection(payload)),
                SimulationRequest.model_validate(payload),
            )
        )
        response = await DecisionSupportService(reader).simulate(payload)
        assert response.status == "READY"
        assert response.data.model_dump(mode="json") == expected
        assert response.engine_result_hash == expected["result_hash"]
        assert response.date_anchor_not_issuance_timestamp is True
        assert (
            await DecisionSupportService(reader).simulate(payload)
        ).model_dump_json() == response.model_dump_json()
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.traps[Inexact] = True
            assert (
                await DecisionSupportService(reader).simulate(payload)
            ).model_dump_json() == response.model_dump_json()


@pytest.mark.parametrize(
    "kind,entity,indices", [("REGION", "A", [0, 1]), ("COMPANY", "ALL", [0, 1, 2, 3])]
)
async def test_hierarchy_saved_snapshot_not_current_registry(
    hierarchy_factory, source_ids, monkeypatch, kind, entity, indices
):
    from backend.app.forecast_intelligence.hierarchy import COMPANY_ID

    async with hierarchy_factory() as session, session.begin():
        saved = await execute_hierarchical_run(
            session,
            hierarchy_request(
                [source_ids[i] for i in indices], kind, COMPANY_ID if kind == "COMPANY" else entity
            ),
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_REGISTRY_OR_NEW_FORECAST")

    monkeypatch.setattr(
        "backend.app.forecast_intelligence.application.current_hierarchy", forbidden
    )
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(hierarchy_query(saved))
        payload = request_payload(source)
        response = await DecisionSupportService(reader).simulate(payload)
        assert response.status == "READY"
        assert response.adapter_authority_hash == source.hierarchy_identity.hierarchy_authority_hash
        assert response.adapter_authority_kind == "SAVED_HIERARCHY_SNAPSHOT"
        curve, _ = adapt_saved_curve(source, selection(payload))
        expected = what_if.simulate(
            make_scenario(
                curve,
                selection(payload),
                cost_contract(selection(payload)),
                SimulationRequest.model_validate(payload),
            )
        )
        assert response.data.model_dump(mode="json") == expected


async def test_incomplete_hierarchy_is_not_simulated(hierarchy_factory, source_ids, monkeypatch):
    async with hierarchy_factory() as session, session.begin():
        saved = await execute_hierarchical_run(session, hierarchy_request(source_ids[:-1]))
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(hierarchy_query(saved))
        payload = request_payload(source)
        payload["capacity_rows"] = [
            {"date": "2026-01-02", "capacity_mode": "DIRECT", "daily_handling_capacity_kg": "1"}
        ]

        def forbidden(*args):
            raise AssertionError("NO_INCOMPLETE_ENGINE_CALL")

        monkeypatch.setattr(what_if, "simulate", forbidden)
        result = await DecisionSupportService(reader).simulate(payload)
        assert result.status == "NOT_AVAILABLE"
        assert result.data is None
        assert result.unavailable_reason == "INCOMPLETE_CHILD_COVERAGE"


@pytest.mark.parametrize("level", ["UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"])
async def test_unbound_upper_no_fallback_or_engine(
    hierarchy_factory, source_ids, monkeypatch, level
):
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        payload = request_payload(source)
        payload["planning_level"] = level

        def forbidden(*args):
            raise AssertionError("NO_UNBOUND_ENGINE_CALL")

        monkeypatch.setattr(what_if, "simulate", forbidden)
        monkeypatch.setattr(what_if, "compare_and_rank", forbidden)
        for result in (
            await DecisionSupportService(reader).simulate(payload),
            await DecisionSupportService(reader).compare(comparison_payload(payload)),
        ):
            assert result.status == "NOT_AVAILABLE"
            assert result.data is None
            assert result.engine_result_hash is None


@pytest.mark.parametrize(
    "level,key",
    [
        ("POINT", "point_forecast_kg"),
        ("UPPER_PLANNING_BOUND_80", "upper_planning_bound_80_kg"),
        ("UPPER_PLANNING_BOUND_90", "upper_planning_bound_90_kg"),
    ],
)
def test_test_only_synthetic_bounds_engine_selection(level, key):
    s = replace(synthetic_scenario(), planning_level=level)
    result = what_if.simulate(s)
    assert [Decimal(r["planning_demand_kg"]) for r in result["daily_rows"]] == [
        getattr(r, key) for r in s.saved_forecast.daily_rows
    ]


@pytest.mark.parametrize(
    "field,bad",
    [
        ("daily_handling_capacity_kg", True),
        ("daily_handling_capacity_kg", 1.5),
        ("daily_handling_capacity_kg", "-1"),
        ("daily_handling_capacity_kg", "NaN"),
        ("daily_handling_capacity_kg", "Infinity"),
        ("daily_handling_capacity_kg", "1e6"),
        ("daily_handling_capacity_kg", None),
        ("workforce_count", True),
        ("workforce_count", 1.5),
        ("workforce_count", -1),
        ("productivity_kg_per_person_day", 12),
        ("productivity_kg_per_person_day", "-1"),
        ("productivity_kg_per_person_day", "NaN"),
        ("buffer_handling_capacity_kg", "Infinity"),
    ],
)
async def test_numeric_input_strict(hierarchy_factory, source_ids, field, bad):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
        payload = request_payload(
            source,
            mode="WORKFORCE_DERIVED"
            if field in ("workforce_count", "productivity_kg_per_person_day")
            else "DIRECT",
        )
        payload["capacity_rows"][0][field] = bad
        with pytest.raises(ValueError):
            SimulationRequest.model_validate(payload)


async def test_mode_conflicts_missing_fields_and_initial_backlog_reject(
    hierarchy_factory, source_ids
):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
        for mode, field in [
            ("DIRECT", "workforce_count"),
            ("WORKFORCE_DERIVED", "daily_handling_capacity_kg"),
        ]:
            payload = request_payload(source, mode=mode)
            payload["capacity_rows"][0][field] = 1 if mode == "DIRECT" else "1"
            with pytest.raises(ValueError):
                SimulationRequest.model_validate(payload)
        payload = request_payload(source, mode="WORKFORCE_DERIVED")
        del payload["capacity_rows"][0]["productivity_kg_per_person_day"]
        with pytest.raises(ValueError):
            SimulationRequest.model_validate(payload)
        payload = request_payload(source)
        payload["initial_backlog_kg"] = "1"
        with pytest.raises(ValueError):
            SimulationRequest.model_validate(payload)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "extra", "wrong"])
async def test_exact_capacity_date_set(hierarchy_factory, source_ids, mutation):
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        payload = request_payload(source)
        if mutation == "duplicate":
            payload["capacity_rows"][0] = deepcopy(payload["capacity_rows"][1])
        if mutation == "missing":
            payload["capacity_rows"].pop()
        if mutation == "extra":
            payload["capacity_rows"].append(deepcopy(payload["capacity_rows"][0]))
        if mutation == "wrong":
            payload["capacity_rows"][0]["date"] = "2026-02-01"
        with pytest.raises(ReadError) as error:
            await DecisionSupportService(reader).simulate(payload)
        assert error.value.status_code == 422


async def test_order_workforce_buffer_comparison_and_five_key_engine_parity(
    hierarchy_factory, source_ids
):
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        b = request_payload(source, sid="B")
        c = request_payload(source, sid="C", mode="WORKFORCE_DERIVED")
        service = DecisionSupportService(reader)
        rb, rc = await service.simulate(b), await service.simulate(c)
        for field in (
            "total_processed_kg",
            "cumulative_shortfall_kg",
            "max_backlog_kg",
            "ending_backlog_kg",
            "total_business_loss",
            "aggregate_capacity_utilization_decimal",
            "aggregate_capacity_utilization_numerator_kg",
            "aggregate_capacity_utilization_denominator_kg",
        ):
            assert getattr(rb.data, field) == getattr(rc.data, field)
        payload = comparison_payload(b)
        payload["scenarios"] = [
            {
                k: v
                for k, v in r.items()
                if k in ("scenario_id", "scenario_version", "capacity_rows")
            }
            for r in (request_payload(source, sid="A", capacity="120"), b, c)
        ]
        curve, _ = adapt_saved_curve(source, selection(payload))
        req = ComparisonRequest.model_validate(payload)
        expected = what_if.compare_and_rank(
            tuple(
                make_scenario(curve, selection(payload), cost_contract(selection(payload)), r)
                for r in req.scenarios
            )
        )
        result = await service.compare(payload)
        assert result.data.comparison.model_dump(mode="json") == expected
        payload["scenarios"].reverse()
        for r in payload["scenarios"]:
            r["capacity_rows"].reverse()
        assert (await service.compare(payload)).model_dump_json() == result.model_dump_json()


async def test_authority_independent_adapter_validation(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
        selected = selection(request_payload(source))
        corrupted = [
            source.model_copy(update={"projection_hash": "a" * 64}),
            rehash(source, source_run_id=999),
            rehash(source, source_result_hash="a" * 64),
            rehash(
                source,
                authority_identity=source.authority_identity.model_copy(
                    update={"authority_hash": "0" * 64}
                ),
            ),
            rehash(
                source,
                hierarchy_identity=source.hierarchy_identity.model_copy(
                    update={"hierarchy_authority_hash": "b" * 64}
                ),
            ),
        ]
        rows = list(source.data.daily_rows)
        rows[0] = rows[0].model_copy(update={"lead_day": 2})
        corrupted.append(rehash(source, data=source.data.model_copy(update={"daily_rows": rows})))
        for item in corrupted:
            with pytest.raises(ReadError):
                adapt_saved_curve(item, selected)
        changed = rehash(source, source_result_hash="b" * 64)
        assert projection_digest(base_scope_binding(changed)) != projection_digest(
            base_scope_binding(source)
        )
        for field, value in [
            ("baseline_id", "OTHER"),
            ("forecast_family", "OTHER"),
            ("target_season", "2024-2025"),
            ("origin_date", date(2026, 1, 2)),
        ]:
            changed = rehash(
                source, forecast_identity=source.forecast_identity.model_copy(update={field: value})
            )
            assert projection_digest(base_scope_binding(changed)) != projection_digest(
                base_scope_binding(source)
            )


async def test_no_autoflush_dml_or_actual_model_execution(
    hierarchy_factory, source_ids, monkeypatch
):
    from backend.app.models import OperationalPeakForecastRun

    def forbidden(*args, **kwargs):
        raise AssertionError("FORBIDDEN_SIDE_EFFECT")

    monkeypatch.setattr(
        "backend.app.forecast_quality.operational_peak.forecast_operational_peak", forbidden
    )
    monkeypatch.setattr(
        "backend.app.forecast_intelligence.uncertainty.calibrate", forbidden, raising=False
    )
    async with hierarchy_factory() as session:
        statements = []
        connection = await session.connection()
        event.listen(
            connection.sync_connection,
            "before_cursor_execute",
            lambda c, u, s, p, x, m: statements.append(s),
        )
        session.add(OperationalPeakForecastRun())
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        await DecisionSupportService(reader).simulate(request_payload(source))
        assert all(
            not s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements
        )
        assert session.new


def test_numeric_exception_isolation_and_engine_contract():
    s = synthetic_scenario(demands=("80",), capacities=("140",))
    result = what_if.simulate(s)
    row = result["daily_rows"][0]
    assert row["capacity_utilization_numerator_kg"] == "80"
    assert row["capacity_utilization_denominator_kg"] == "140"
    assert row["capacity_utilization_rounding_applied"] is True
    bad = replace(
        s,
        capacity_rows=(
            replace(
                s.capacity_rows[0],
                daily_handling_capacity_kg=Decimal("9" * 50),
                buffer_handling_capacity_kg=Decimal("0.1"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="AUTHORITATIVE_PRECISION_EXCEEDED"):
        what_if.simulate(bad)


async def test_cost_catalogue_tamper_fails_closed(monkeypatch):
    from backend.app.forecast_intelligence import decision_service
    from backend.app.forecast_intelligence.business_loss import synthetic_contracts

    changed = list(synthetic_contracts())
    changed[0] = replace(changed[0], c_under_per_kg=Decimal("2"))
    monkeypatch.setattr(decision_service, "synthetic_contracts", lambda: tuple(changed))
    with pytest.raises(ReadError, match="UPSTREAM_COST_AUTHORITY_DRIFT"):
        cost_contract(
            CostSelection(
                cost_contract_id="SYNTHETIC_BALANCED_R1",
                expected_cost_contract_hash=COST_HASHES["SYNTHETIC_BALANCED_R1"],
            )
        )


async def test_saved_rerun_is_explicit_not_latest(
    hierarchy_factory, source_ids, synthetic_authority
):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        OperationalPeakRunRepository,
        execution_hash,
    )

    async with hierarchy_factory() as session, session.begin():
        repo = OperationalPeakRunRepository(session)
        old = await repo.get(source_ids[0])
        # Explicit alternate SYNTHETIC authority creates a distinct execution, not latest wins.
        authority_hash = "c" * 64
        fixture_result = forecast_operational_peak(
            OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 1, 1)),
            synthetic_authority.registry,
            synthetic_authority.reference_profile,
        )
        new = await repo.save(
            snapshot=old.request_snapshot,
            result=fixture_result,
            execution_id=execution_hash(
                old.request_snapshot, authority_hash, fixture_result.policy_version
            ),
            authority_hash=authority_hash,
            rerun_of_run_id=source_ids[0],
        )
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(new.run.run_id))
        result = await DecisionSupportService(reader).simulate(request_payload(source))
        assert result.source_rerun_of_run_id == source_ids[0]
        assert result.forecast_identity.run_id == new.run.run_id
        first = await reader.curve(query(source_ids[0]))
        assert projection_digest(base_scope_binding(first)) != result.adapter_authority_hash


def test_no_forbidden_dependencies_or_copied_math():
    for relative in (
        "forecast_intelligence/decision_service.py",
        "forecast_intelligence/decision_schemas.py",
        "api/forecast_intelligence_decision.py",
    ):
        tree = ast.parse((ROOT / "backend/app" / relative).read_text())
        imported = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert all(
            not any(
                x in name
                for x in (
                    "actual_harvest_import.application",
                    "label",
                    "training",
                    "optimizer",
                    "mcp",
                )
            )
            for name in imported
        )
        calls = [
            n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
        ]
        assert not set(calls) & {
            "commit",
            "flush",
            "save",
            "fit",
            "predict",
            "calibrate",
            "reconcile",
            "execute",
            "row_loss",
        }
        assert not any(
            isinstance(n, ast.BinOp)
            and isinstance(n.op, (ast.Mult, ast.Div, ast.Sub))
            and not (
                isinstance(n.op, ast.Mult)
                and isinstance(n.left, ast.Constant)
                and isinstance(n.left.value, str)
            )
            for n in ast.walk(tree)
        )


def test_execution_evidence_frozen_sources_and_governance():
    raw = (ROOT / "docs/v0-17/evidence/v0.17-s2-decision-support-api-r1.json").read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert value["base_main_sha"] == "ac4e862aea8b87d072835bbc1b2ae98e60adcb3e"
    assert value["frozen_policy_pins"] == {
        "s5_policy_hash": "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7",
        "s6_policy_hash": "c1712c6596a813816eefbcb8d51c7088304549cfcc1899a637dff1b150be6463",
        "utilization_numeric_policy": "V0_16_EXACT_RATIO_WITH_DECIMAL50_HALF_EVEN_R1",
    }
    assert value["source_evidence_count"] == len(value["source_evidence_sha256"])
    for name, expected in value["source_evidence_sha256"].items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for policy_file, key in [
        ("business-loss-contract-r1/business-loss-policy-r1.json", "s5_policy_hash"),
        ("what-if-decision-simulator-r1/what-if-policy-r1.json", "s6_policy_hash"),
    ]:
        policy = json.loads((ROOT / "docs/v0-16/evidence" / policy_file).read_bytes())
        assert projection_digest(policy["policy"]) == value["frozen_policy_pins"][key]
    assert value["governance"]["s2_implementation_authorized"] is True
    assert all(not v for k, v in value["governance"].items() if k != "s2_implementation_authorized")
    assert all(v is False for v in value["isolation"].values())
    for forbidden in ("/private/", "/Users/", "postgresql://", "password=", "base_id", "row_key"):
        assert forbidden not in raw.decode()
