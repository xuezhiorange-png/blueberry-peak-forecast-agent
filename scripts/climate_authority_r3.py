"""Offline, fixed-K authority diagnostics; never activation or model selection."""

from itertools import permutations
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import silhouette_samples
from sklearn.preprocessing import StandardScaler

from scripts.climate_study_r2 import aligned, centers, classify, fit, matrix

FEATURES = (
    "annual_mean_temperature_c",
    "annual_precipitation_mm",
    "annual_temperature_range_c",
    "precipitation_seasonality",
    "dewpoint_depression_c",
    "annual_radiation_mj_m2",
    "elevation_m",
)


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "k": 5,
        "method": "kmeans",
        "seed": 42,
        "kmeans_n_init": 20,
        "resamples": 200,
        "resample_fraction": 0.8,
        "core_frequency_min": 0.9,
        "core_lofo_min": 6,
        "boundary_frequency_min": 0.7,
        "boundary_lofo_min": 4,
        "climate_zone_mapping_frozen": False,
        "climate_zone_profile_authority_frozen": False,
    }
    if any(config.get(k) != v for k, v in required.items()):
        raise ValueError("R3_FROZEN_CONFIG_MISMATCH")


def align_labels(reference: Any, fitted: Any, predictions: Any) -> tuple[Any, list[int]]:
    """Align using only supplied reference rows, with explicit optimal-tie rule."""
    overlap = np.array(
        [[np.sum((reference == i) & (fitted == j)) for j in range(5)] for i in range(5)]
    )
    rows, cols = linear_sum_assignment(-overlap)
    optimum = int(overlap[rows, cols].sum())
    lookup = next(
        p for p in permutations(range(5)) if sum(overlap[p[j], j] for j in range(5)) == optimum
    )
    return np.array([lookup[int(v)] for v in predictions]), list(lookup)


def assignment_class(
    frequency: float, lofo: int, temporal: bool, coordinate: bool, integrity: bool = True
) -> str:
    if not integrity or not coordinate or frequency < 0.70 or lofo < 4:
        return "UNSTABLE"
    if frequency >= 0.90 and lofo >= 6 and temporal:
        return "CORE"
    return "BOUNDARY"


def centroid_margin(point: Any, centroids: Any, assigned: int) -> dict[str, Any]:
    distances = np.linalg.norm(centroids - point, axis=1)
    other = min(
        (i for i in range(len(centroids)) if i != assigned), key=lambda i: (distances[i], i)
    )
    d1, d2 = float(distances[assigned]), float(distances[other])
    return {
        "assigned_centroid_distance": d1,
        "runner_up_centroid_distance": d2,
        "centroid_absolute_margin": d2 - d1,
        "centroid_relative_margin": (d2 - d1) / max(d2, 1e-12),
        "runner_up_zone": other,
    }


def diagnose(
    profiles: list[dict[str, Any]], frozen: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    validate_config(config)
    if (
        frozen["features"] != list(FEATURES)
        or len(profiles) != 38
        or len({p["base_id"] for p in profiles}) != 38
    ):
        raise ValueError("R2_FEATURE_POPULATION_MISMATCH")
    raw = matrix(profiles, list(FEATURES), "baseline")
    mean, scale = np.array(frozen["scaler_mean"]), np.array(frozen["scaler_scale"])
    check = StandardScaler().fit(raw)
    if not np.array_equal(check.mean_, mean) or not np.array_equal(check.scale_, scale):
        raise ValueError("R2_SCALER_MISMATCH")
    x = (raw - mean) / scale
    lab = np.array(frozen["baseline_labels"])
    if not np.array_equal(fit(x, 5, "kmeans", config), lab):
        raise ValueError("R2_MAPPING_MISMATCH")
    centroid = centers(x, lab)
    silhouettes = silhouette_samples(x, lab)
    rng = np.random.default_rng(42)
    resamples = []
    for ordinal in range(200):
        ix = np.sort(rng.choice(38, 30, replace=False))
        fitted = fit(x[ix], 5, "kmeans", config)
        prediction = classify(x, centers(x[ix], fitted))
        # Included rows retain their actual fitted label. Omitted rows use nearest centroid.
        prediction[ix] = fitted
        prediction, lookup = align_labels(lab[ix], fitted, prediction)
        resamples.append(
            {
                "resample_index": ordinal,
                "sample_indices": ix.tolist(),
                "label_alignment": lookup,
                "aligned_assignments": prediction.tolist(),
            }
        )
    lofo_runs = []
    for removed in FEATURES:
        retained = [f for f in FEATURES if f != removed]
        reduced = StandardScaler().fit_transform(matrix(profiles, retained, "baseline"))
        prediction = fit(reduced, 5, "kmeans", config)
        prediction, lookup = align_labels(lab, prediction, prediction)
        lofo_runs.append(
            {
                "removed_feature": removed,
                "retained_features": retained,
                "label_alignment": lookup,
                "aligned_assignments": prediction.tolist(),
            }
        )
    ward = fit(x, 5, "ward", config)
    if ward.tolist() != frozen["mappings"]["ward_5"]:
        raise ValueError("R2_WARD_MAPPING_MISMATCH")
    ward, _ = align_labels(lab, ward, ward)
    recent_raw = matrix(profiles, list(FEATURES), "recent")
    recent_x = StandardScaler().fit_transform(recent_raw)
    # Keep R2 temporal alignment exactly, including its established label numbering.
    recent_labels = aligned(lab, fit(recent_x, 5, "kmeans", config), 5)
    if recent_labels.tolist() != frozen["recent_labels"]:
        raise ValueError("R2_RECENT_MAPPING_MISMATCH")
    recent_centroid = centers(recent_x, recent_labels)
    fixed_recent_x = (recent_raw - mean) / scale
    deltas = fixed_recent_x - x
    results, temporal = [], []
    for i, profile in enumerate(profiles):
        counts = np.bincount([r["aligned_assignments"][i] for r in resamples], minlength=5)
        alternative = min((j for j in range(5) if j != lab[i]), key=lambda j: (-counts[j], j))
        probabilities = counts[counts > 0] / 200
        removals = [
            r["removed_feature"] for r in lofo_runs if r["aligned_assignments"][i] != lab[i]
        ]
        coord = frozen["coordinate_sensitivity"][i]
        if coord["base_id"] != profile["base_id"]:
            raise ValueError("R2_COORDINATE_ORDER_MISMATCH")
        same_time = bool(lab[i] == recent_labels[i])
        row = {
            "base_id": profile["base_id"],
            "canonical_base_name": profile["canonical_base_name"],
            "baseline_zone": int(lab[i]),
            "recent_zone": int(recent_labels[i]),
            "bootstrap_same_zone_count": int(counts[lab[i]]),
            "bootstrap_assignment_frequency": float(counts[lab[i]] / 200),
            "aligned_zone_counts": counts.tolist(),
            "most_common_alternative_zone": int(alternative) if counts[alternative] else None,
            "alternative_zone_frequency": float(counts[alternative] / 200),
            "assignment_entropy_nats": float(-np.sum(probabilities * np.log(probabilities))),
            "lofo_stable_count": 7 - len(removals),
            "lofo_stability_rate": (7 - len(removals)) / 7,
            "features_whose_removal_changes_zone": removals,
            "sample_silhouette": float(silhouettes[i]),
            "ward_k5_aligned_zone": int(ward[i]),
            "method_assignment_agreement": bool(lab[i] == ward[i]),
            "temporal_zone_stability": "STABLE" if same_time else "RECENT_SHIFT",
            "coordinate_zone_stable": not coord["zone_changed"],
            "grid_cell_changed_under_perturbation": coord["grid_changed"],
            "max_feature_delta_under_coordinate_perturbation": coord[
                "maximum_standardized_profile_delta"
            ],
            "source_integrity_pass": True,
            "coordinate_crs_status": "SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION",
        }
        row.update(centroid_margin(x[i], centroid, int(lab[i])))
        row["assignment_class"] = assignment_class(
            row["bootstrap_assignment_frequency"],
            row["lofo_stable_count"],
            same_time,
            row["coordinate_zone_stable"],
        )
        results.append(row)
        order = sorted(range(7), key=lambda j: (-abs(deltas[i, j]), j))
        squared = deltas[i] ** 2
        groups = {
            "temperature": float(squared[[0, 2]].sum()),
            "precipitation": float(squared[[1, 3]].sum()),
            "moisture": float(squared[4]),
            "radiation": float(squared[5]),
            "elevation": float(squared[6]),
        }
        largest = max(groups, key=lambda g: groups[g])
        driver = largest if groups[largest] > 0.5 * sum(groups.values()) else "multiple_variables"
        recent_nearest = int(classify(recent_x[i : i + 1], recent_centroid)[0])
        temporal.append(
            {
                "base_id": profile["base_id"],
                "canonical_base_name": profile["canonical_base_name"],
                "baseline_zone": int(lab[i]),
                "recent_zone": int(recent_labels[i]),
                "baseline_features": dict(zip(FEATURES, raw[i].tolist(), strict=True)),
                "recent_features": dict(zip(FEATURES, recent_raw[i].tolist(), strict=True)),
                "standardized_deltas_baseline_scaler": dict(
                    zip(FEATURES, deltas[i].tolist(), strict=True)
                ),
                "baseline_assigned_centroid": centroid[lab[i]].tolist(),
                "recent_nearest_centroid_zone": recent_nearest,
                "recent_nearest_centroid": recent_centroid[recent_nearest].tolist(),
                "recent_refit_geometry": centroid_margin(
                    recent_x[i], recent_centroid, recent_nearest
                ),
                "recent_vector_frozen_baseline_geometry": centroid_margin(
                    fixed_recent_x[i], centroid, int(lab[i])
                ),
                "recent_vector_nearest_frozen_baseline_zone": int(
                    classify(fixed_recent_x[i : i + 1], centroid)[0]
                ),
                "largest_shift_features": [FEATURES[j] for j in order[:3]],
                "squared_standardized_shift_by_group": groups,
                "largest_geometric_shift_group": driver,
                "interpretation": (
                    "Geometric displacement, not causal attribution; elevation unchanged; "
                    "recent refit includes scaler/centroid relocation."
                ),
            }
        )
    return {
        "base_results": results,
        "resample_runs": resamples,
        "lofo_runs": lofo_runs,
        "temporal_diagnostics": temporal,
        "centroids": centroid.tolist(),
        "climate_zone_mapping_frozen": False,
        "climate_zone_profile_authority_frozen": False,
    }
