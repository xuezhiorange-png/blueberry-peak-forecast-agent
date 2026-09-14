"""Authority diagnostics must not retune or silently freeze R2 candidates."""

import json
from pathlib import Path

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from scripts.climate_authority_r3 import (
    FEATURES,
    align_labels,
    assignment_class,
    centroid_margin,
    diagnose,
    validate_config,
)
from scripts.climate_source_r2 import digest
from scripts.climate_study_r2 import centers, classify, fit, matrix


@pytest.fixture
def config():
    return json.loads(Path("configs/climate_zone_r3.json").read_text())


@pytest.mark.parametrize(
    "frequency,lofo,temporal,coordinate,integrity,expected",
    [
        (0.90, 6, True, True, True, "CORE"),
        (0.899, 6, True, True, True, "BOUNDARY"),
        (0.90, 5, True, True, True, "BOUNDARY"),
        (1, 7, False, True, True, "BOUNDARY"),
        (0.70, 4, True, True, True, "BOUNDARY"),
        (0.699, 7, True, True, True, "UNSTABLE"),
        (1, 3, True, True, True, "UNSTABLE"),
        (1, 7, True, False, True, "UNSTABLE"),
        (1, 7, True, True, False, "UNSTABLE"),
    ],
)
def test_classification(frequency, lofo, temporal, coordinate, integrity, expected):
    assert assignment_class(frequency, lofo, temporal, coordinate, integrity) == expected


def test_alignment_permutation_and_ties():
    ref = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
    other = (ref + 2) % 5
    aligned, lookup = align_labels(ref, other, other)
    assert aligned.tolist() == ref.tolist()
    assert len(lookup) == 5
    _, tied = align_labels(np.arange(5), np.zeros(5, dtype=int), np.arange(5))
    assert tied == [0, 1, 2, 3, 4]


def test_margin_is_standardized_geometry_not_probability():
    result = centroid_margin(np.array([1.0, 0]), np.array([[0, 0], [4, 0]]), 0)
    assert result["assigned_centroid_distance"] == 1
    assert result["runner_up_centroid_distance"] == 3
    assert result["centroid_absolute_margin"] == 2
    assert result["centroid_relative_margin"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "key,value", [("k", 4), ("resamples", 30), ("seed", 43), ("kmeans_n_init", 10)]
)
def test_config_frozen(config, key, value):
    config[key] = value
    with pytest.raises(ValueError, match="FROZEN"):
        validate_config(config)


def test_production_feature_rejected():
    with pytest.raises(ValueError, match="FORBIDDEN"):
        matrix([], ["productive_area_mu"], "baseline")


def synthetic_inputs(config):
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(19)
    raw = np.vstack([rng.normal(i * 10, 0.2, (n, 7)) for i, n in enumerate([8, 4, 5, 15, 6])])
    scaler = StandardScaler().fit(raw)
    x = scaler.transform(raw)
    profiles = [
        {
            "base_id": f"B{i:02}",
            "canonical_base_name": f"Base {i}",
            "elevation_m": row[-1],
            "baseline": dict(zip(FEATURES[:-1], row[:-1], strict=True)),
            "recent": dict(zip(FEATURES[:-1], row[:-1], strict=True)),
        }
        for i, row in enumerate(raw)
    ]
    lab = fit(x, 5, "kmeans", config)
    ward = fit(x, 5, "ward", config)
    frozen = {
        "features": list(FEATURES),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "baseline_labels": lab.tolist(),
        "recent_labels": lab.tolist(),
        "mappings": {"ward_5": ward.tolist()},
        "coordinate_sensitivity": [
            {
                "base_id": p["base_id"],
                "grid_changed": True,
                "zone_changed": False,
                "maximum_standardized_profile_delta": 0.2,
            }
            for p in profiles
        ],
    }
    return profiles, frozen


def test_diagnostics_deterministic_and_fixed_experiments(config, monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", deny)
    with threadpool_limits(limits=1):
        profiles, frozen = synthetic_inputs(config)
        first = diagnose(profiles, frozen, config)
        second = diagnose(profiles, frozen, config)
    assert digest(first) == digest(second)
    assert len(first["resample_runs"]) == 200
    assert len(first["lofo_runs"]) == 7
    assert len(first["base_results"]) == 38
    for run in first["resample_runs"]:
        assert len(run["sample_indices"]) == 30
        assert len(set(run["sample_indices"])) == 30
        assert len(run["aligned_assignments"]) == 38
    # Reconstruct an omitted-base prediction independently from its sampled fit.
    x = (matrix(profiles, list(FEATURES), "baseline") - frozen["scaler_mean"]) / frozen[
        "scaler_scale"
    ]
    sample = np.array(first["resample_runs"][0]["sample_indices"])
    omitted = np.array(sorted(set(range(38)) - set(sample)))
    with threadpool_limits(limits=1):
        fitted = fit(x[sample], 5, "kmeans", config)
    predicted = classify(x[omitted], centers(x[sample], fitted))
    lookup = first["resample_runs"][0]["label_alignment"]
    assert [lookup[v] for v in predicted] == [
        first["resample_runs"][0]["aligned_assignments"][i] for i in omitted
    ]
    assert {r["removed_feature"] for r in first["lofo_runs"]} == set(FEATURES)
    assert all(len(r["retained_features"]) == 6 for r in first["lofo_runs"])
    for i, row in enumerate(first["base_results"]):
        count = sum(
            r["aligned_assignments"][i] == row["baseline_zone"] for r in first["resample_runs"]
        )
        assert row["bootstrap_same_zone_count"] == count
        assert row["bootstrap_assignment_frequency"] == count / 200
        assert row["coordinate_zone_stable"]
        assert row["grid_cell_changed_under_perturbation"]
        assert -1 <= row["sample_silhouette"] <= 1
        assert row["assignment_class"] == "CORE"
    assert not first["climate_zone_mapping_frozen"]
    assert not first["climate_zone_profile_authority_frozen"]
    assert np.array_equal(
        first["centroids"],
        centers(
            (matrix(profiles, list(FEATURES), "baseline") - frozen["scaler_mean"])
            / frozen["scaler_scale"],
            np.array(frozen["baseline_labels"]),
        ),
    )


def test_r2_mapping_mismatch_stops(config):
    with threadpool_limits(limits=1):
        profiles, frozen = synthetic_inputs(config)
        frozen["baseline_labels"][0] = (frozen["baseline_labels"][0] + 1) % 5
        with pytest.raises(ValueError, match="R2.*MISMATCH"):
            diagnose(profiles, frozen, config)


def test_candidate_hash_and_input_tamper(tmp_path, monkeypatch):
    from scripts import run_climate_authority_r3 as runner
    from scripts.climate_source_r2 import file_hash

    p = tmp_path / "payload.json"
    p.write_text('{"synthetic":true}')
    manifest = runner.payload_hash({"file_hashes": {p.name: file_hash(p)}})
    (tmp_path / "artifact-manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(runner, "R2_HASH", manifest["hash"])
    runner.verify_bundle(tmp_path, manifest)
    assert runner.payload_hash({"a": 1, "b": 2}) == runner.payload_hash({"b": 2, "a": 1})
    p.write_text('{"synthetic":false}')
    with pytest.raises(ValueError, match="BLOCKED_R2_AUTHORITY_INPUT_MISMATCH"):
        runner.verify_bundle(tmp_path, manifest)
