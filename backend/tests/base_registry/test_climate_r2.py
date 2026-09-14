"""Research-only climate contracts; synthetic data never become study evidence."""

import json

import numpy as np
import pytest
import xarray as xr

from scripts.climate_source_r2 import converted_months, digest, expected_months, verify_months
from scripts.climate_study_r2 import aligned, geography, grid_index, matrix, period_summary

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "period,count",
    [((1991, 2020), 360), ((1996, 2025), 360), ((2021, 2025), 60), ((2026, 2026, 8), 8)],
)
def test_exact_month_count(period, count):
    months = expected_months(*period)
    assert len(months) == count
    verify_months(months, months)


@pytest.mark.parametrize("bad", [["2020-01", "2020-01"], ["2020-01"], ["2020-02", "2020-01"]])
def test_missing_duplicate_or_order_fails_closed(bad):
    with pytest.raises(ValueError, match="MONTH_COVERAGE"):
        verify_months(bad, ["2020-01", "2020-02"])


def test_units_include_month_length_and_leap_year():
    a = {
        "t2m": np.array([273.15, 283.15]),
        "d2m": np.array([273.15, 273.15]),
        "tp": np.array([0.001, 0.001]),
        "ssrd": np.array([1e6, 1e6]),
    }
    result = converted_months(["2020-02", "2021-02"], a)
    np.testing.assert_allclose(result["temperature_c"], [0, 10])
    np.testing.assert_allclose(result["precipitation_mm"], [29, 28])
    np.testing.assert_allclose(result["radiation_mj_m2"], [29, 28])


def test_hash_order_independent_and_nonfinite_rejected():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        digest({"x": float("nan")})


def test_cutoff_discovered_from_constraints_not_current_month():
    from scripts.climate_source_r2 import available_months

    constraints = [
        {
            "year": ["2026"],
            "month": [f"{m:02d}" for m in range(1, 9)],
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": ["t", "p"],
        }
    ]
    assert available_months(constraints, ["t", "p"], 2026, 2026, 9)[-1] == "08"
    assert available_months(constraints, ["t"], 2026, 2026, 8)[-1] == "07"
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        available_months(constraints, ["missing"], 2026, 2026, 9)


def test_geographic_allowlist_excludes_outside_and_production():
    bases = [
        {
            "base_id": str(i),
            "canonical_base_name": str(i),
            "longitude": "101",
            "latitude": "25",
            "elevation_m": "1000",
            "elevation_review_status": "REVIEW",
            "productive_area_mu": "99",
            "harvest_kg": 100,
            "region_scope": "YUNNAN_CORE" if i < 38 else "OUT_OF_YUNNAN",
        }
        for i in range(39)
    ]
    selected = geography({"bases": bases})
    assert len(selected) == 38
    assert all("productive_area_mu" not in b and "harvest_kg" not in b for b in selected)
    with pytest.raises(ValueError, match="POPULATION"):
        geography({"bases": bases[:37]})


@pytest.mark.parametrize("field", ["productive_area_mu", "harvest_kg", "yield", "peak_date"])
def test_production_features_forbidden(field):
    with pytest.raises(ValueError, match="FORBIDDEN"):
        matrix([], [field], "baseline")


def test_grid_deterministic_tie_and_perturbation():
    a = np.array([25.2, 25.1, 25.0])
    assert a[grid_index(a, 25.05)] == 25.0
    assert a[grid_index(a, 25.06)] == 25.1
    assert a[::-1][grid_index(a[::-1], 25.05)] == 25.0
    with pytest.raises(ValueError, match="OUTSIDE"):
        grid_index(a, 26)


def test_ytd_never_compares_partial_to_full_year():
    months = expected_months(2020, 2021)
    values = {
        "temperature_c": np.array([10.0] * 24),
        "dewpoint_c": np.array([5.0] * 24),
        "precipitation_mm": np.array([1.0] * 8 + [100.0] * 4 + [2.0] * 8 + [1000.0] * 4),
        "radiation_mj_m2": np.array([1.0] * 24),
        "days": np.array([30.0] * 24),
    }
    old = period_summary(months, values, 2020, 2020, 8)
    new = period_summary(months, values, 2021, 2021, 8)
    assert old["precipitation_mm"] == 8
    assert new["precipitation_mm"] == 16
    assert new["month_count"] == 8


def test_cluster_labels_are_aligned_not_compared_as_raw_ids():
    np.testing.assert_array_equal(
        aligned(np.array([0, 0, 1, 1]), np.array([1, 1, 0, 0]), 2), [0, 0, 1, 1]
    )


def test_missing_feature_not_imputed():
    with pytest.raises(ValueError, match="NO_IMPUTATION"):
        matrix([{"elevation_m": float("nan")}], ["elevation_m"], "baseline")


@pytest.fixture
def climate_source(tmp_path):
    from scripts.climate_source_r2 import VARIABLE_UNITS, file_hash, write_json

    plans = []
    for i, (start, end, stop) in enumerate(
        [(1991, 2000, 12), (2001, 2010, 12), (2011, 2020, 12), (2021, 2025, 12), (2026, 2026, 8)]
    ):
        months = expected_months(start, end, stop)
        request = {
            "year": [str(y) for y in range(start, end + 1)],
            "month": [f"{m:02d}" for m in range(1, stop + 1)],
            "product_type": "monthly_averaged_reanalysis",
        }
        plans.append(request)
        ds = xr.Dataset(
            {
                v: (
                    ("valid_time", "latitude", "longitude"),
                    np.ones((len(months), 2, 2)),
                    {"units": unit, "long_name": v},
                )
                for v, unit in VARIABLE_UNITS.items()
            },
            coords={
                "valid_time": np.array([m + "-01" for m in months], dtype="datetime64[ns]"),
                "latitude": [25.0, 25.1],
                "longitude": [100.0, 100.1],
            },
        )
        path = tmp_path / f"regional-{i}.nc"
        ds.to_netcdf(path, engine="h5netcdf")
        write_json(tmp_path / f"request-{i}.json", request)
        write_json(
            tmp_path / f"receipt-{i}.json", {"sha256": file_hash(path), "size": path.stat().st_size}
        )
    write_json(
        tmp_path / "retrieval-plan.json",
        {
            "dataset": "reanalysis-era5-land-monthly-means",
            "latest_month": "2026-08",
            "requests": plans,
        },
    )
    for name in ("catalogue.json", "constraints.json"):
        write_json(tmp_path / name, {})
    return tmp_path


def test_physical_netcdf_source_gate_replay_without_network(climate_source, monkeypatch):
    import socket

    from scripts.climate_source_r2 import inspect_source

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    first, _ = inspect_source(climate_source)
    second, _ = inspect_source(climate_source)
    assert first == second
    assert first["month_count"] == 428
    assert first["period_month_counts"]["baseline_1991_2020"]["t2m"] == 360
    assert first["period_month_counts"]["recent_1996_2025"]["tp"] == 360
    assert first["period_month_counts"]["drift_2021_2025"]["ssrd"] == 60
    assert first["period_month_counts"]["ytd_2026"]["d2m"] == 8


def test_raw_file_mutation_rejected(climate_source):
    from scripts.climate_source_r2 import inspect_source

    with (climate_source / "regional-0.nc").open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="RAW_SOURCE_HASH_MISMATCH"):
        inspect_source(climate_source)


def test_candidate_k_seed_deterministic_and_every_base_once():
    from pathlib import Path

    from threadpoolctl import threadpool_limits

    from scripts.climate_study_r2 import FEATURE_ALLOWLIST, study

    config = json.loads(Path("configs/climate_zone_r2.json").read_text())
    assert config["candidate_k"] == list(range(3, 9))
    assert config["climate_zone_mapping_frozen"] is False
    assert config["climate_zone_profile_authority_frozen"] is False
    config["resamples"] = 2  # synthetic unit-test runtime only; real config stays 30
    rng = np.random.default_rng(321)
    profiles = []
    for i in range(38):
        features = {f: float(rng.normal()) for f in sorted(FEATURE_ALLOWLIST)}
        profiles.append(
            {
                "base_id": str(i),
                "latitude": 25 + i * 0.01,
                "longitude": 100 + i * 0.01,
                "elevation_m": features["elevation_m"],
                "baseline": features,
                "recent": features.copy(),
                "grid": {"latitude": 25, "longitude": 100},
            }
        )
    with threadpool_limits(limits=1):
        first = study(profiles, [profiles] * 8, config)
        second = study(profiles, [profiles] * 8, config)
    assert first == second
    assert len(first["mappings"]) == 12
    assert len(first["scores"]) == 12
    for key, labels in first["mappings"].items():
        assert len(labels) == 38
        assert len(set(labels)) == int(key.rsplit("_", 1)[1])
    assert all(s["coordinate_agreement"] == 1 for s in first["scores"])
