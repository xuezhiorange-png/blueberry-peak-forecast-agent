"""SYNTHETIC=true DB fixtures; public historical evidence only, no real data IO."""

import ast
import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import localcontext
from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence import read_service
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.read_schemas import (
    ForecastReadQuery,
    QualityReadQuery,
    ReadError,
)
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.forecast_quality.operational_peak_persistence import OperationalPeakRunRepository
from backend.app.main import create_app
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request

FORECAST_ENDPOINTS = ["overview", "curve", "hierarchy", "uncertainty", "attribution"]
ROOT = Path(__file__).resolve().parents[3]


def test_s1_execution_evidence_source_binding_and_governance():
    path = ROOT / "docs/v0-17/evidence/v0.17-s1-forecast-intelligence-service-read-api-r1.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert value["version"] == "0.17.0"
    assert value["base_main_sha"] == "1cabff0887b1525f15409b7bdc88ed2396a147d8"
    assert len(value["read_capabilities"]) == 6
    assert value["source_evidence_count"] == len(value["source_evidence_sha256"])
    for name, expected in value["source_evidence_sha256"].items():
        assert not Path(name).is_absolute()
        assert ".." not in Path(name).parts
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert value["governance"]["s1_authorized"] is True
    for field in (
        "s1_formal_complete",
        "s2_authorized",
        "s3_authorized",
        "s4_authorized",
        "s5_authorized",
        "s6_authorized",
        "ready_authorized",
        "merge_authorized",
        "tag_authorized",
        "release_authorized",
    ):
        assert value["governance"][field] is False
    assert all(flag is False for flag in value["isolation"].values())
    for forbidden in ("postgresql://", "password=", "/private/", "/Users/", "row_key", "base_id"):
        assert forbidden not in raw.decode()
    assert value["authority_inventory"]["uncertainty"]["runtime_binding_available"] is False
    assert value["authority_inventory"]["attribution"]["runtime_binding_available"] is False
    assert value["read_contract"]["unbound_interval_fallback_allowed"] is False
    assert value["read_contract"]["unbound_attribution_fallback_allowed"] is False


def configured_app(factory, monkeypatch, permissions="may_read_forecast,may_read_quality"):
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "synthetic-reader")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "synthetic")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", permissions)
    app = create_app()

    async def sessions():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = sessions
    return app


def params(selected):
    return selected.model_dump(mode="json", exclude_none=True)


def hierarchy_query(saved):
    return query(
        saved.run.run_id,
        source_kind="HIERARCHICAL",
        hierarchy_level=saved.run.target_entity_type,
        entity_id=saved.run.target_entity_id,
    )


def query(run_id=1, **updates):
    return ForecastReadQuery.model_validate(
        {
            "source_kind": "OPERATIONAL_PEAK",
            "forecast_family": "OPERATIONAL_PEAK_FORECAST_RUN_V1",
            "run_id": run_id,
            "hierarchy_level": "BASE",
            "entity_id": "A1",
            "target_season": "2025-2026",
            "origin_date": "2026-01-01",
            "baseline_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
            "policy_version": "OPERATIONAL_PEAK_POLICY_V1",
            **updates,
        }
    )


async def test_base_repository_service_and_http_exact_parity(
    hierarchy_factory, source_ids, monkeypatch
):
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "synthetic-reader")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "synthetic")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_read_forecast,may_read_quality")
    app = create_app()

    async def sessions():
        async with hierarchy_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = sessions
    selected = query(source_ids[0])
    async with hierarchy_factory() as session:
        saved = await OperationalPeakRunRepository(session).get(source_ids[0])
        service = ForecastIntelligenceReadService(session)
        curve = await service.curve(selected)
        assert curve.status == "READY"
        assert [r.point_forecast_kg for r in curve.data.daily_rows] == [
            r["predicted_kg"] for r in saved.result["daily_forecast"]
        ]
        overview = await service.overview(selected)
        assert overview.data.forecast_7d_total_kg == saved.result["forecast_7d"]["total_kg"]
        assert overview.data.forecast_15d_total_kg == saved.result["forecast_15d"]["total_kg"]
        assert overview.data.peak_date == date(2026, 1, 2)
        assert (await service.overview(selected)).model_dump_json() == overview.model_dump_json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/forecast-intelligence/curve",
            params=selected.model_dump(mode="json", exclude_none=True),
        )
        assert response.status_code == 200, response.text
        assert response.json() == curve.model_dump(mode="json")
        for name in ("uncertainty", "attribution"):
            response = await client.get(
                f"/api/v1/forecast-intelligence/{name}",
                params=selected.model_dump(mode="json", exclude_none=True),
            )
            assert response.status_code == 200
            assert response.json()["status"] == "NOT_AVAILABLE"
            assert response.json()["data"] is None


async def test_quality_is_frozen_historical_not_current_actual():
    service = ForecastIntelligenceReadService(None)
    response = await service.quality(QualityReadQuery())
    assert response.status == "READY"
    assert [r.horizon for r in response.data.horizons] == ["H1", "H3", "H7", "H15"]
    assert response.data.horizons[0].interval_status == "NOT_AVAILABLE"
    assert response.data.horizons[2].interval_coverage[0].empirical_coverage.startswith("0.538927")
    current = await service.quality(QualityReadQuery(mode="CURRENT_PRODUCTION_ACCURACY"))
    assert current.status == "NO_CURRENT_ACTUAL"
    assert current.data is None


@pytest.mark.parametrize(
    "updates",
    [
        {"run_id": 0},
        {"hierarchy_level": "FARM"},
        {"entity_id": "x" * 201},
        {"cursor": "bad"},
        {"expected_source_result_hash": "bad"},
    ],
)
def test_invalid_selection_rejected(updates):
    with pytest.raises(ValueError):
        query(**updates)


@pytest.mark.parametrize("endpoint", FORECAST_ENDPOINTS)
@pytest.mark.parametrize(
    "updates",
    [
        {"forecast_family": "OTHER"},
        {"entity_id": "A2"},
        {"target_season": "2024-2025"},
        {"origin_date": "2026-01-02"},
        {"baseline_id": "V0_15_S5_M1_RIDGE"},
        {"policy_version": "OTHER"},
        {"expected_source_result_hash": "a" * 64},
        {"source_kind": "HIERARCHICAL"},
    ],
)
async def test_all_forecast_capabilities_reject_scope_mismatch(
    hierarchy_factory, source_ids, monkeypatch, endpoint, updates
):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/forecast-intelligence/{endpoint}",
            params=params(query(source_ids[0], **updates)),
        )
    assert result.status_code == 409, result.text
    assert result.json()["status"] == "AUTHORITY_MISMATCH"
    assert result.json()["data"] is None


async def test_saved_hierarchy_complete_and_incomplete_without_registry(
    hierarchy_factory, source_ids, monkeypatch
):
    async with hierarchy_factory() as session, session.begin():
        complete = await execute_hierarchical_run(session, hierarchy_request(source_ids))
        partial = await execute_hierarchical_run(session, hierarchy_request(source_ids[:-1]))
        region = await execute_hierarchical_run(
            session, hierarchy_request(source_ids[:2], "REGION", "A")
        )
    monkeypatch.setattr(
        "backend.app.forecast_intelligence.application.current_hierarchy",
        lambda: (_ for _ in ()).throw(AssertionError("NO_CURRENT_REGISTRY_READ")),
    )
    async with hierarchy_factory() as session:
        service = ForecastIntelligenceReadService(session)
        for saved in (complete, region):
            selected = hierarchy_query(saved)
            stored = await HierarchicalRunRepository(session).get(saved.run.run_id)
            curve = await service.curve(selected)
            assert [r.point_forecast_kg for r in curve.data.daily_rows] == [
                r["predicted_kg"] for r in stored.result["daily_forecast"]
            ]
            assert (
                await service.hierarchy(selected)
            ).data.reconciliation_method == "BOTTOM_UP_EXACT_SUM"
            overview = await service.overview(selected)
            assert (
                overview.data.peak_daily_quantity_kg
                == saved.result["single_day_peak"]["predicted_kg"]
            )
            assert overview.data.forecast_7d_total_kg == saved.result["forecast_7d"]["total_kg"]
            for method in (service.uncertainty, service.attribution):
                assert (await method(selected)).status == "NOT_AVAILABLE"
        selected = hierarchy_query(partial)
        output = await service.hierarchy(selected)
        assert output.status == "PARTIAL"
        assert output.data.daily_rows == []
        assert output.data.data_completeness == "INCOMPLETE_CHILD_COVERAGE"
        assert output.data.missing_child_count == 1
        overview = await service.overview(selected)
        assert overview.data.forecast_15d_total_kg is None
        assert overview.data.peak_date is None


@pytest.mark.parametrize("endpoint", FORECAST_ENDPOINTS + ["quality"])
async def test_permission_denial_before_any_repository_read(
    hierarchy_factory, source_ids, monkeypatch, endpoint
):
    permissions = "may_read_forecast" if endpoint == "quality" else "may_read_quality"
    app = configured_app(hierarchy_factory, monkeypatch, permissions)

    async def forbidden(*args):
        raise AssertionError("NO_UNAUTHORIZED_READ")

    monkeypatch.setattr(OperationalPeakRunRepository, "get", forbidden)
    monkeypatch.setattr(
        read_service,
        "public_evidence",
        lambda: (_ for _ in ()).throw(AssertionError("NO_UNAUTHORIZED_EVIDENCE_READ")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/forecast-intelligence/{endpoint}",
            params={} if endpoint == "quality" else params(query(source_ids[0])),
        )
    assert result.status_code == 403
    assert result.json()["code"] == "FORBIDDEN"


@pytest.mark.parametrize("endpoint", FORECAST_ENDPOINTS + ["quality"])
async def test_trusted_unauthenticated_dependency(hierarchy_factory, monkeypatch, endpoint):
    app = configured_app(hierarchy_factory, monkeypatch)

    async def unauthenticated():
        raise HTTPException(401, "secret should not escape")

    app.dependency_overrides[get_actual_harvest_actor] = unauthenticated
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/forecast-intelligence/{endpoint}",
            params={} if endpoint == "quality" else params(query()),
        )
    assert result.status_code == 401
    assert result.json()["code"] == "UNAUTHENTICATED"
    assert "secret" not in result.text


async def test_missing_server_actor_config_is_not_fabricated_login(hierarchy_factory, monkeypatch):
    app = configured_app(hierarchy_factory, monkeypatch)
    monkeypatch.delenv("TRIAL_ACTOR_IDENTITY")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/v1/forecast-intelligence/quality")
    assert result.status_code == 503
    assert result.json()["code"] == "AUTHORIZATION_UNAVAILABLE"


@pytest.mark.parametrize("endpoint", FORECAST_ENDPOINTS)
async def test_missing_run_is_404(hierarchy_factory, monkeypatch, endpoint):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/forecast-intelligence/{endpoint}", params=params(query(9999))
        )
    assert result.status_code == 404
    assert result.json()["code"] == "SAVED_RUN_NOT_FOUND"


@pytest.mark.parametrize(
    "updates",
    [
        {"run_id": -1},
        {"run_id": 2**63},
        {"hierarchy_level": "FACTORY"},
        {"cursor": "invalid"},
        {"entity_id": "x" * 10000},
        {"expected_source_result_hash": "A" * 64},
    ],
)
async def test_http_invalid_query_sanitized(hierarchy_factory, monkeypatch, updates):
    app = configured_app(hierarchy_factory, monkeypatch)
    values = {**params(query()), **updates}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/v1/forecast-intelligence/curve", params=values)
    assert result.status_code == 422
    assert result.json()["code"] == "INVALID_REQUEST"
    assert "input" not in result.json()


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("postgresql://secret /private/path"),
        OperationalError("query", {}, RuntimeError("secret")),
    ],
)
async def test_controlled_internal_failures(hierarchy_factory, monkeypatch, failure):
    app = configured_app(hierarchy_factory, monkeypatch)

    async def broken(*args):
        raise failure

    monkeypatch.setattr(OperationalPeakRunRepository, "get", broken)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/v1/forecast-intelligence/curve", params=params(query()))
    assert result.status_code == 503
    for text_value in ("secret", "postgresql", "/private", "Traceback"):
        assert text_value not in result.text


@pytest.mark.parametrize("kind", ["daily", "hash", "summary", "origin"])
async def test_damaged_persisted_authority_rejected(
    hierarchy_factory, source_ids, monkeypatch, kind
):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with hierarchy_factory() as session, session.begin():
        table = (
            "operational_peak_forecast_daily"
            if kind == "daily"
            else "operational_peak_forecast_run"
        )
        await session.execute(text(f"DROP TRIGGER {table}_update"))
        assignment = {
            "daily": "predicted_kg='999'",
            "hash": "result_hash='" + "a" * 64 + "'",
            "summary": "forecast_7d='{}'",
            "origin": "origin_date='2026-01-03'",
        }[kind]
        await session.execute(
            text(
                f"UPDATE {table} SET {assignment} WHERE {'run_id' if kind == 'daily' else 'id'}=:id"
            ),
            {"id": source_ids[0]},
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            "/api/v1/forecast-intelligence/overview", params=params(query(source_ids[0]))
        )
    assert result.status_code == 409, result.text
    assert result.json()["code"] == "SAVED_RUN_INTEGRITY_FAILED"


async def test_quality_http_exact_frozen_parity_and_no_actual_or_db_read(
    hierarchy_factory, monkeypatch
):
    app = configured_app(hierarchy_factory, monkeypatch)
    queries = []
    event.listen(
        hierarchy_factory.kw["bind"].sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, *args: queries.append(statement),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        historical = await client.get("/api/v1/forecast-intelligence/quality")
        current = await client.get(
            "/api/v1/forecast-intelligence/quality", params={"mode": "CURRENT_PRODUCTION_ACCURACY"}
        )
    assert historical.status_code == current.status_code == 200
    assert queries == []
    assert current.json()["status"] == "NO_CURRENT_ACTUAL"
    source = json.loads(
        (
            ROOT / "docs/v0-16/evidence/forecastops-monitoring-r1/point-quality-summary-r1.json"
        ).read_bytes()
    )["horizons"]
    for row in historical.json()["data"]["horizons"]:
        assert row["wape"] == source[row["horizon"]]["daily_wape"]
        assert row["bias_kg"] == source[row["horizon"]]["daily_bias_kg"]
        assert row["mae_kg"] == source[row["horizon"]]["daily_mae_kg"]
        assert row["cumulative_wape"] == source[row["horizon"]]["cumulative_wape"]
    assert historical.json()["evidence_mode"] == "RETROSPECTIVE_OBSERVATION"
    assert historical.json()["forecast_identity"] is None


@pytest.mark.parametrize("filename", list(read_service.PUBLIC_EVIDENCE_HASHES))
async def test_every_public_authority_tamper_rejected(monkeypatch, filename):
    original = Path.read_bytes

    def tampered(path):
        raw = original(path)
        return raw + b" " if str(path).endswith(filename) else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(ReadError, match="PUBLIC_EVIDENCE_AUTHORITY_MISMATCH"):
        await ForecastIntelligenceReadService(None).quality(QualityReadQuery())


async def test_unpackaged_historical_evidence_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(read_service, "EVIDENCE_ROOT", tmp_path)
    result = await ForecastIntelligenceReadService(None).quality(QualityReadQuery())
    assert result.status == "NOT_AVAILABLE"
    assert result.data is None


async def test_quality_expected_hash_and_invalid_model(hierarchy_factory, monkeypatch):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mismatch = await client.get(
            "/api/v1/forecast-intelligence/quality",
            params={"expected_source_result_hash": "a" * 64},
        )
        invalid = await client.get(
            "/api/v1/forecast-intelligence/quality", params={"model_id": "OPERATIONAL_PEAK"}
        )
    assert mismatch.status_code == 409
    assert invalid.status_code == 422


async def test_read_is_deterministic_context_independent_and_performs_no_dml(
    hierarchy_factory, source_ids
):
    queries = []
    event.listen(
        hierarchy_factory.kw["bind"].sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, *args: queries.append(statement),
    )
    async with hierarchy_factory() as session:
        service = ForecastIntelligenceReadService(session)
        first = await service.overview(query(source_ids[0]))
        with localcontext() as context:
            context.prec = 2
            second = await service.overview(query(source_ids[0]))
        assert first.model_dump_json() == second.model_dump_json()
        assert first.projection_hash != first.source_result_hash
        assert (
            read_service.projection_digest(
                first.model_dump(mode="json", exclude={"projection_hash"})
            )
            == first.projection_hash
        )
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in queries)


def test_only_six_get_routes_no_engine_execution_and_frozen_boundaries():
    app = create_app()
    paths = app.openapi()["paths"]
    owned = {p: v for p, v in paths.items() if p.startswith("/api/v1/forecast-intelligence/")}
    assert set(owned) == {
        f"/api/v1/forecast-intelligence/{p}" for p in FORECAST_ENDPOINTS + ["quality"]
    }
    assert all(set(operations) == {"get"} for operations in owned.values())
    forbidden_calls = {
        "fit",
        "fit_predict",
        "fit_ridge_artifact",
        "forecast_operational_peak",
        "calibrate",
        "score",
        "reconcile",
        "save",
        "add",
        "add_all",
        "flush",
        "commit",
        "execute_hierarchical_run",
        "execute_operational_peak_forecast_run",
    }
    for name in (
        "backend/app/forecast_intelligence/read_service.py",
        "backend/app/forecast_intelligence/read_schemas.py",
        "backend/app/api/forecast_intelligence_read.py",
    ):
        tree = ast.parse((ROOT / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                assert called not in forbidden_calls
    frozen = json.loads(
        (
            ROOT / "docs/v0-17/evidence/v0.17.0-version-plan-and-product-scope-freeze-r1.json"
        ).read_bytes()
    )
    assert frozen["S1_AUTHORIZED"] is False
    for path, expected in frozen["SOURCE_EVIDENCE_SHA256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    for path, expected in read_service.PUBLIC_EVIDENCE_HASHES.items():
        full_path = "docs/v0-16/evidence/" + path
        if full_path in frozen["SOURCE_EVIDENCE_SHA256"]:
            assert frozen["SOURCE_EVIDENCE_SHA256"][full_path] == expected
        else:
            # S4 source-binding is transitively pinned by its S0-bound manifest.
            manifest = json.loads(
                (
                    ROOT / "docs/v0-16/evidence/forecastops-monitoring-r1/manifest-r1.json"
                ).read_bytes()
            )
            assert manifest["files"][Path(path).name] == expected


@pytest.mark.parametrize(
    "origin,expected_status,count",
    [(date(2026, 4, 14), "PARTIAL", 1)],
)
async def test_short_and_empty_saved_windows_are_not_complete(
    hierarchy_factory, synthetic_authority, origin, expected_status, count
):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        execution_hash,
        request_snapshot,
    )

    # Explicit SYNTHETIC=true setup only; the read service never calls this engine.
    request = OperationalPeakForecastRequest("A1", "2025-2026", origin)
    value = forecast_operational_peak(
        request, synthetic_authority.registry, synthetic_authority.reference_profile
    )
    snapshot = request_snapshot(request)
    async with hierarchy_factory() as session, session.begin():
        saved = await OperationalPeakRunRepository(session).save(
            snapshot=snapshot,
            result=value,
            execution_id=execution_hash(
                snapshot, synthetic_authority.authority_hash, synthetic_authority.policy_version
            ),
            authority_hash=synthetic_authority.authority_hash,
            rerun_of_run_id=None,
        )
    async with hierarchy_factory() as session:
        service = ForecastIntelligenceReadService(session)
        selected = query(saved.run.run_id, origin_date=origin)
        overview = await service.overview(selected)
        curve = await service.curve(selected)
    assert overview.status == curve.status == expected_status
    assert len(curve.data.daily_rows) == count
    assert overview.data.forecast_7d_total_kg is None
    assert overview.data.forecast_15d_total_kg is None
    assert (overview.data.peak_date is None) == (count == 0)


async def test_no_inference_or_actual_read_after_fixture_setup(
    hierarchy_factory, source_ids, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("NO_FORECAST_OR_ACTUAL_EXECUTION")

    monkeypatch.setattr(
        "backend.app.forecast_quality.operational_peak.forecast_operational_peak", forbidden
    )
    monkeypatch.setattr("backend.app.forecast_intelligence.uncertainty.calibrate", forbidden)
    monkeypatch.setattr("backend.app.forecast_intelligence.forecast_ops.monitor", forbidden)
    async with hierarchy_factory() as session:
        service = ForecastIntelligenceReadService(session)
        for name in FORECAST_ENDPOINTS:
            await getattr(service, name)(query(source_ids[0]))
        await service.quality(QualityReadQuery())


async def test_read_does_not_autoflush_caller_pending_state(hierarchy_factory, source_ids):
    from backend.app.models.operational_peak import OperationalPeakForecastRun

    async with hierarchy_factory() as session:
        pending = OperationalPeakForecastRun()  # deliberately incomplete, never flushable
        session.add(pending)
        assert (
            await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
        ).status == "READY"
        assert pending in session.new and pending.id is None
        await session.rollback()


@pytest.mark.parametrize("endpoint", FORECAST_ENDPOINTS + ["quality"])
async def test_no_mutating_methods(hierarchy_factory, monkeypatch, endpoint):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            result = await client.request(method, f"/api/v1/forecast-intelligence/{endpoint}")
            assert result.status_code == 405


@pytest.mark.parametrize(
    "kind,entity,indices", [("COMPANY", "COMPANY_AGGREGATE_ROOT_V1", None), ("REGION", "A", [0, 1])]
)
async def test_hierarchy_repository_service_http_parity(
    hierarchy_factory, source_ids, monkeypatch, kind, entity, indices
):
    ids = source_ids if indices is None else [source_ids[i] for i in indices]
    async with hierarchy_factory() as session, session.begin():
        saved = await execute_hierarchical_run(session, hierarchy_request(ids, kind, entity))
    selected = hierarchy_query(saved)
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for endpoint in ("overview", "curve", "hierarchy"):
            async with hierarchy_factory() as session:
                projected = await getattr(ForecastIntelligenceReadService(session), endpoint)(
                    selected
                )
            result = await client.get(
                f"/api/v1/forecast-intelligence/{endpoint}", params=params(selected)
            )
            assert result.status_code == 200, result.text
            assert result.json() == projected.model_dump(mode="json")


async def test_empty_projection_is_safe_but_empty_saved_run_not_admitted(
    hierarchy_factory, synthetic_authority, source_ids, monkeypatch
):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        OperationalPeakPersistenceConflictError,
        execution_hash,
        request_snapshot,
    )

    request = OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 4, 15))
    value = forecast_operational_peak(
        request, synthetic_authority.registry, synthetic_authority.reference_profile
    )
    snapshot = request_snapshot(request)
    async with hierarchy_factory() as session, session.begin():
        with pytest.raises(OperationalPeakPersistenceConflictError):
            await OperationalPeakRunRepository(session).save(
                snapshot=snapshot,
                result=value,
                execution_id=execution_hash(
                    snapshot, synthetic_authority.authority_hash, synthetic_authority.policy_version
                ),
                authority_hash=synthetic_authority.authority_hash,
                rerun_of_run_id=None,
            )
    async with hierarchy_factory() as session:
        service = ForecastIntelligenceReadService(session)
        # Isolated SYNTHETIC projection test, deliberately not a saved-run admission.
        source, common = await service._source(query(source_ids[0]))
        empty = {
            **deepcopy(source),
            "daily_forecast": [],
            "forecast_7d": None,
            "forecast_15d": None,
        }

        async def synthetic_empty(selected):
            return empty, common

        monkeypatch.setattr(service, "_source", synthetic_empty)
        result = await service.overview(query(source_ids[0]))
        assert result.status == "EMPTY"
        assert result.data.peak_date is result.data.peak_daily_quantity_kg is None
        assert result.data.forecast_7d_total_kg is result.data.forecast_15d_total_kg is None


async def test_curve_peak_is_not_remaining_season_peak(hierarchy_factory, synthetic_authority):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        execution_hash,
        request_snapshot,
    )

    request = OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 1, 1))
    profile = {i: "1" if i < 30 else "9" for i in range(42)}
    value = forecast_operational_peak(request, synthetic_authority.registry, profile)
    snapshot = request_snapshot(request)
    async with hierarchy_factory() as session, session.begin():
        saved = await OperationalPeakRunRepository(session).save(
            snapshot=snapshot,
            result=value,
            execution_id=execution_hash(
                snapshot, synthetic_authority.authority_hash, synthetic_authority.policy_version
            ),
            authority_hash=synthetic_authority.authority_hash,
            rerun_of_run_id=None,
        )
    async with hierarchy_factory() as session:
        result = await ForecastIntelligenceReadService(session).overview(query(saved.run.run_id))
    assert result.data.peak_daily_quantity_kg == "1.000000"
    assert saved.result["remaining_business_window"]["peak_kg"] == "9.000000"
    assert result.data.peak_scope == "SAVED_DAILY_CURVE_D1_THROUGH_AVAILABLE_D15"
