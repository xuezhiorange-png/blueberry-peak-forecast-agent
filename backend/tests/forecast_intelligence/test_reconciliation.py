"""Synthetic-only contracts for exact bottom-up hierarchy reconciliation."""

from copy import deepcopy

import pytest

from backend.app.forecast_intelligence.hierarchy import COMPANY_ID, build_hierarchy
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun


def registry():
    return {
        "bases": [
            {"base_id": b, "canonical_base_name": b, "region_scope": r}
            for r, b in (("A", "A1"), ("A", "A2"), ("B", "B1"), ("B", "B2"))
        ]
    }


def hierarchy():
    return build_hierarchy(registry(), "a" * 64, "b" * 64)


def sources():
    return [
        {
            "run_id": i,
            "execution_hash": str(i) * 64,
            "authority_hash": "a" * 64,
            "result_hash": str(i) * 64,
            "base_id": b,
            "result": {
                "policy_version": "OPERATIONAL_PEAK_POLICY_V1",
                "baseline_id": "BASELINE",
                "authority_hash": "a" * 64,
                "target_season": "2025-2026",
                "origin_date": "2026-01-01",
                "business_season_start": "2025-07-01",
                "business_season_end": "2026-04-15",
                "weather_used": False,
                "daily_forecast": [
                    {"date": f"2026-01-{d:02}", "predicted_kg": str(i)} for d in range(2, 17)
                ],
            },
        }
        for i, b in enumerate(("A1", "A2", "B1", "B2"), 1)
    ]


def request(ids=None, kind="COMPANY", entity=COMPANY_ID):
    return CreateHierarchicalRun(
        target_entity_type=kind, target_entity_id=entity, source_run_ids=ids or [1, 2, 3, 4]
    )


def test_exact_company_and_region_paths_and_order():
    value = reconcile(hierarchy(), request(), sources())
    assert value["daily_forecast"][0]["predicted_kg"] == "10"
    assert value["company_path_parity"] is True
    assert value == reconcile(hierarchy(), request([4, 3, 2, 1]), list(reversed(sources())))
    region = reconcile(hierarchy(), request([1, 2], "REGION", "A"), sources()[:2])
    assert region["daily_forecast"][0]["predicted_kg"] == "3"
    assert value["forecast_7d"]["total_kg"] == "70.000000"
    assert value["forecast_15d"]["total_kg"] == "150.000000"
    assert value["single_day_peak"]["date"] == "2026-01-02"
    assert value["rolling_7day_peak"]["start_date"] == "2026-01-02"
    assert value["season_total_kg"] is None


def test_missing_is_not_zero():
    value = reconcile(hierarchy(), request([1, 2, 3]), sources()[:3])
    assert value["status"] == "INCOMPLETE_CHILD_COVERAGE"
    assert value["missing_base_ids"] == ["B2"]
    for key in (
        "official_aggregate_kg",
        "aggregate_total_kg",
        "single_day_peak",
        "rolling_7day_peak",
        "forecast_7d",
        "forecast_15d",
    ):
        assert value[key] is None
    assert value["daily_forecast"] == []


def test_hierarchy_order_and_active_semantics():
    original = registry()
    reversed_registry = deepcopy(original)
    reversed_registry["bases"].reverse()
    assert build_hierarchy(original, "a" * 64, "b" * 64) == build_hierarchy(
        reversed_registry, "a" * 64, "b" * 64
    )
    original["bases"][0]["active"] = False
    value = build_hierarchy(original, "a" * 64, "b" * 64)
    assert "A1" not in value["regions"][0]["active_child_base_ids"]


@pytest.mark.parametrize("bad", [None, "", 12])
def test_bad_region_fails(bad):
    value = registry()
    value["bases"][0]["region_scope"] = bad
    with pytest.raises(ValueError, match="HIERARCHY_AUTHORITY_INCOMPLETE"):
        build_hierarchy(value, "a" * 64, "b" * 64)


@pytest.mark.parametrize(
    "field",
    [
        "policy_version",
        "baseline_id",
        "target_season",
        "origin_date",
        "business_season_start",
        "business_season_end",
        "weather_used",
    ],
)
def test_compatibility_fails(field):
    values = sources()
    values[1]["result"][field] = "different"
    with pytest.raises(ValueError, match="INCOMPATIBLE_SOURCE_FORECASTS"):
        reconcile(hierarchy(), request(), values)


@pytest.mark.parametrize("days, h7, h15", [(6, False, False), (10, True, False), (15, True, True)])
def test_short_window(days, h7, h15):
    values = sources()
    for item in values:
        item["result"]["daily_forecast"] = item["result"]["daily_forecast"][:days]
        item["result"]["business_season_end"] = f"2026-01-{days + 1:02}"
    value = reconcile(hierarchy(), request(), values)
    assert (value["forecast_7d"]["total_kg"] is not None) == h7
    assert (value["forecast_15d"]["total_kg"] is not None) == h15


@pytest.mark.parametrize(
    "kind,code",
    [
        ("duplicate", "DUPLICATE_BASE_FORECAST"),
        ("unknown", "SOURCE_BASE_NOT_IN_HIERARCHY"),
        ("inactive", "INACTIVE_SOURCE_BASE"),
        ("authority", "HIERARCHY_SOURCE_AUTHORITY_MISMATCH"),
        ("dates", "SOURCE_DAILY_WINDOW_MISMATCH"),
        ("negative", "SOURCE_FORECAST_INTEGRITY_FAILED"),
        ("infinite", "SOURCE_FORECAST_INTEGRITY_FAILED"),
    ],
)
def test_source_failure_matrix(kind, code):
    values, snapshot = sources(), hierarchy()
    if kind == "duplicate":
        values[1]["base_id"] = "A1"
    elif kind == "unknown":
        values[1]["base_id"] = "unknown"
    elif kind == "inactive":
        source_registry = registry()
        source_registry["bases"][1]["active"] = False
        snapshot = build_hierarchy(source_registry, "a" * 64, "b" * 64)
    elif kind == "authority":
        values[1]["authority_hash"] = "c" * 64
    elif kind == "dates":
        values[1]["result"]["daily_forecast"].pop()
    else:
        values[1]["result"]["daily_forecast"][0]["predicted_kg"] = (
            "-1" if kind == "negative" else "NaN"
        )
    with pytest.raises(ValueError, match=code):
        reconcile(snapshot, request(), values)


def test_target_and_duplicate_registry_fail_closed():
    for target in (request(kind="REGION", entity="unknown"), request(entity="legal-company")):
        with pytest.raises(ValueError, match="TARGET_ENTITY_NOT_FOUND"):
            reconcile(hierarchy(), target, sources())
    with pytest.raises(ValueError, match="SOURCE_BASE_OUTSIDE_TARGET"):
        reconcile(hierarchy(), request(kind="REGION", entity="A"), sources())
    value = registry()
    value["bases"].append(deepcopy(value["bases"][0]))
    with pytest.raises(ValueError, match="HIERARCHY_AUTHORITY_INCOMPLETE"):
        build_hierarchy(value, "a" * 64, "b" * 64)
    for kind in ("FARM", "FACTORY"):
        with pytest.raises(ValueError):
            request(kind=kind)


def test_peak_recomputed_not_summed_and_rolling7_earliest_tie():
    values = sources()[:2]
    for source in values:
        for row in source["result"]["daily_forecast"]:
            row["predicted_kg"] = "0"
    values[0]["result"]["daily_forecast"][0]["predicted_kg"] = "10"
    values[1]["result"]["daily_forecast"][1]["predicted_kg"] = "10"
    result = reconcile(hierarchy(), request([1, 2], "REGION", "A"), values)
    assert result["single_day_peak"] == {"date": "2026-01-02", "predicted_kg": "10"}
    assert result["single_day_peak"]["predicted_kg"] != "20"
    assert result["rolling_7day_peak"] == {
        "start_date": "2026-01-02",
        "end_date": "2026-01-08",
        "total_kg": "20",
    }


def test_identity_hash_sensitivity():
    baseline = reconcile(hierarchy(), request(), sources())
    values = sources()
    values[0]["result_hash"] = "c" * 64
    changed = reconcile(hierarchy(), request(), values)
    assert baseline["execution_hash"] != changed["execution_hash"]
    assert baseline["result_hash"] != changed["result_hash"]
    snapshot = build_hierarchy(registry(), "a" * 64, "c" * 64)
    assert reconcile(snapshot, request(), sources())["execution_hash"] != baseline["execution_hash"]
    assert (
        reconcile(hierarchy(), request([1, 2, 3]), sources()[:3])["execution_hash"]
        != baseline["execution_hash"]
    )


def test_current_actual_and_model_pipeline_not_imported():
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[2] / "app" / "forecast_intelligence"
    for file in package.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(
                    token in (node.module or "")
                    for token in (
                        "label_vault",
                        "prospective_actual",
                        "v0_15",
                        "training",
                        "actual_harvest",
                    )
                )
                assert "forecast_operational_peak" not in {n.name for n in node.names}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"fit", "train", "refit", "tune"}
