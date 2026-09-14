"""Research-only climate profiles and unsupervised zone candidate calculations."""

from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from scripts.climate_source_r2 import (
    converted_months,
    digest,
    expected_months,
    verify_months,
)

FEATURE_ALLOWLIST = frozenset(
    {
        "elevation_m",
        "annual_mean_temperature_c",
        "annual_precipitation_mm",
        "annual_temperature_range_c",
        "precipitation_seasonality",
        "monsoon_fraction",
        "dewpoint_depression_c",
        "annual_radiation_mj_m2",
        "coldest_month_mean_temperature_c",
    }
)


def geography(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop every production/area field at the input boundary."""
    keys = (
        "base_id",
        "canonical_base_name",
        "longitude",
        "latitude",
        "elevation_m",
        "elevation_review_status",
    )
    bases = [
        {k: b[k] for k in keys} for b in registry["bases"] if b["region_scope"] == "YUNNAN_CORE"
    ]
    if len(bases) != 38 or len({b["base_id"] for b in bases}) != 38:
        raise ValueError("POPULATION_MISMATCH")
    return sorted(bases, key=lambda b: b["base_id"])


def grid_index(coordinates: Any, value: float) -> int:
    if not np.isfinite(value) or value < min(coordinates) or value > max(coordinates):
        raise ValueError("COORDINATE_OUTSIDE_SOURCE_GRID")
    # Numerical ties choose lower coordinate, independent of grid storage order.
    distance = np.abs(coordinates - value)
    candidates = np.flatnonzero(np.isclose(distance, distance.min(), rtol=0, atol=1e-10))
    return int(min(candidates, key=lambda i: coordinates[i]))


def period_summary(
    months: list[str], values: dict[str, Any], first: int, last: int, final_month: int = 12
) -> dict[str, Any]:
    wanted = expected_months(first, last, final_month)
    positions = [i for i, m in enumerate(months) if m in set(wanted)]
    verify_months([months[i] for i in positions], wanted)
    a = {k: np.asarray(v)[positions] for k, v in values.items()}
    if not all(np.isfinite(v).all() for v in a.values()):
        raise ValueError("MISSING_CLIMATE_VALUES_NO_IMPUTATION")
    years = last - first + 1
    t = a["temperature_c"]
    td = a["dewpoint_c"]
    p = a["precipitation_mm"]
    day = a["days"]
    return {
        "month_count": len(wanted),
        "period": f"{first}-{last}",
        "temperature_c": float(np.average(t, weights=day)),
        "precipitation_mm": float(p.sum() / years),
        "dewpoint_depression_c": float(np.average(t - td, weights=day)),
        "radiation_mj_m2": float(a["radiation_mj_m2"].sum() / years),
    }


def normal(months: list[str], values: dict[str, Any], first: int, last: int) -> dict[str, Any]:
    annual = period_summary(months, values, first, last)
    ix = [i for i, m in enumerate(months) if first <= int(m[:4]) <= last]
    tm, pm = [], []
    for m in range(1, 13):
        sel = [i for i in ix if int(months[i][5:]) == m]
        tm.append(float(np.mean(values["temperature_c"][sel])))
        pm.append(float(np.mean(values["precipitation_mm"][sel])))
    return {
        "annual_mean_temperature_c": annual["temperature_c"],
        "coldest_month_mean_temperature_c": min(tm),
        "warmest_month_mean_temperature_c": max(tm),
        "annual_temperature_range_c": max(tm) - min(tm),
        "annual_precipitation_mm": annual["precipitation_mm"],
        "wettest_month_precipitation_mm": max(pm),
        "driest_month_precipitation_mm": min(pm),
        "precipitation_seasonality": float(np.std(pm) / np.mean(pm)),
        "monsoon_fraction": sum(pm[4:10]) / sum(pm),
        "dewpoint_depression_c": annual["dewpoint_depression_c"],
        "annual_radiation_mj_m2": annual["radiation_mj_m2"],
        "monthly_temperature_climatology": tm,
        "monthly_precipitation_climatology": pm,
        "month_count": annual["month_count"],
    }


def extract(ds: Any, base: dict[str, Any], dx: float = 0, dy: float = 0) -> dict[str, Any]:
    lon, lat = float(base["longitude"]) + dx, float(base["latitude"]) + dy
    i, j = grid_index(ds.latitude.values, lat), grid_index(ds.longitude.values, lon)
    point = ds.isel(latitude=i, longitude=j)
    months = [str(v)[:7] for v in point.valid_time.values]
    values = converted_months(months, {v: point[v].values for v in ("t2m", "tp", "d2m", "ssrd")})
    baseline, recent = normal(months, values, 1991, 2020), normal(months, values, 1996, 2025)
    drift = period_summary(months, values, 2021, 2025)
    reference = period_summary(months, values, 1991, 2020)
    drift_delta = {
        k: drift[k] - reference[k]
        for k in ("temperature_c", "precipitation_mm", "dewpoint_depression_c", "radiation_mj_m2")
    }
    drift_delta["precipitation_pct"] = (
        100 * drift_delta["precipitation_mm"] / reference["precipitation_mm"]
    )
    annual = [period_summary(months, values, y, y) for y in range(1991, 2021)]
    z = max(
        abs(drift_delta[k]) / float(np.std([a[k] for a in annual], ddof=1))
        for k in ("temperature_c", "precipitation_mm")
    )
    drift_delta["severity_z"] = z
    ytd = period_summary(months, values, 2026, 2026, 8)
    # Each baseline year uses exactly Jan-Aug, never its full year.
    same = [period_summary(months, values, y, y, 8) for y in range(1991, 2021)]
    anomalies = {
        k: ytd[k] - float(np.mean([v[k] for v in same]))
        for k in ("temperature_c", "precipitation_mm", "dewpoint_depression_c", "radiation_mj_m2")
    }
    glat, glon = float(point.latitude), float(point.longitude)
    p1, p2 = np.radians([lat, glat])
    dl = np.radians(glon - lon)
    distance = (
        6371.0088
        * 2
        * np.arcsin(
            np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2)
        )
    )
    return {
        "baseline": baseline,
        "recent": recent,
        "drift": drift_delta,
        "drift_severity": "LOW" if z < 1 else "MODERATE" if z < 2 else "HIGH",
        "ytd": {"latest_month": "2026-08", "month_count": 8, "same_month_anomalies": anomalies},
        "grid": {
            "latitude": glat,
            "longitude": glon,
            "distance_km": float(distance),
            "method": "NEAREST_GRID_LOWER_COORDINATE_TIE_BREAK",
        },
    }


def matrix(profiles: list[dict[str, Any]], features: list[str], period: str) -> Any:
    if not set(features).issubset(FEATURE_ALLOWLIST):
        raise ValueError("PRODUCTION_OR_UNKNOWN_FEATURE_FORBIDDEN")
    a = np.array(
        [
            [float(p["elevation_m"]) if f == "elevation_m" else p[period][f] for f in features]
            for p in profiles
        ],
        dtype=float,
    )
    if not np.isfinite(a).all():
        raise ValueError("MISSING_FEATURE_NO_IMPUTATION")
    return a


def fit(x: Any, k: int, method: str, config: dict[str, Any]) -> Any:
    if method == "ward":
        return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(x)
    if method != "kmeans":
        raise ValueError("METHOD_NOT_AUTHORIZED")
    return KMeans(
        n_clusters=k, n_init=config["kmeans_n_init"], random_state=config["seed"]
    ).fit_predict(x)


def centers(x: Any, labels: Any) -> Any:
    return np.array([x[labels == i].mean(axis=0) for i in range(max(labels) + 1)])


def classify(x: Any, centroids: Any) -> Any:
    return ((np.asarray(x)[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)


def aligned(reference: Any, other: Any, k: int) -> Any:
    overlap = np.array(
        [[np.sum((reference == i) & (other == j)) for j in range(k)] for i in range(k)]
    )
    rows, cols = linear_sum_assignment(-overlap)
    lookup = dict(zip(cols.tolist(), rows.tolist(), strict=True))
    return np.array([lookup[v] for v in other])


def study(
    profiles: list[dict[str, Any]],
    perturbations: list[list[dict[str, Any]]],
    config: dict[str, Any],
) -> dict[str, Any]:
    features: list[str] = []
    exclusions: dict[str, str] = {}
    for f in config["feature_priority"]:
        trial = matrix(profiles, features + [f], "baseline")
        if np.std(trial[:, -1]) == 0:
            exclusions[f] = "ZERO_VARIANCE"
        elif (
            features
            and np.max(np.abs(np.corrcoef(trial.T)[-1, :-1]))
            >= config["correlation_exclusion_abs_r"]
        ):
            exclusions[f] = "CORRELATED_WITH_HIGHER_PRIORITY_FEATURE"
        else:
            features.append(f)
    raw = matrix(profiles, features, "baseline")
    scaler = StandardScaler().fit(raw)
    x = scaler.transform(raw)
    pert = np.array([scaler.transform(matrix(ps, features, "baseline")) for ps in perturbations])
    scores, mappings = [], {}
    for k in config["candidate_k"]:
        labels = {m: fit(x, k, m, config) for m in config["methods"]}
        agreement = float(adjusted_rand_score(labels["ward"], labels["kmeans"]))
        for method in config["methods"]:
            lab = labels[method]
            centroid = centers(x, lab)
            # Ward has no predict: classify a perturbation by its nearest fitted centroid;
            # retain original assignment where its grid/features do not change.
            predictions = np.array(
                [np.where(np.all(p == x, axis=1), lab, classify(p, centroid)) for p in pert]
            )
            coord = float(np.mean(predictions == lab))
            rng = np.random.default_rng(config["seed"])
            stability = []
            for _ in range(config["resamples"]):
                ix = np.sort(
                    rng.choice(len(x), int(len(x) * config["resample_fraction"]), replace=False)
                )
                fitted = fit(x[ix], k, method, config)
                predicted = classify(x, centers(x[ix], fitted))
                stability.append(float(adjusted_rand_score(lab, predicted)))
            coherence = {}
            for f in (
                "elevation_m",
                "annual_mean_temperature_c",
                "annual_precipitation_mm",
                "dewpoint_depression_c",
                "annual_radiation_mj_m2",
            ):
                v = matrix(profiles, [f], "baseline")[:, 0]
                within = sum(
                    float(np.sum((v[lab == g] - v[lab == g].mean()) ** 2)) for g in range(k)
                )
                coherence[f] = within / float(np.sum((v - v.mean()) ** 2))
            sizes = np.bincount(lab, minlength=k).tolist()
            row = {
                "k": k,
                "method": method,
                "sizes": sizes,
                "silhouette": float(silhouette_score(x, lab)),
                "calinski_harabasz": float(calinski_harabasz_score(x, lab)),
                "davies_bouldin": float(davies_bouldin_score(x, lab)),
                "method_ari": agreement,
                "resample_ari_mean": float(np.mean(stability)),
                "resample_ari_min": min(stability),
                "coordinate_agreement": coord,
                "coherence": coherence,
                "tiny_cluster_warning": min(sizes) < 3,
                "geographic_extents": [
                    {
                        coordinate: [
                            min(
                                float(p[coordinate]) for i, p in enumerate(profiles) if lab[i] == g
                            ),
                            max(
                                float(p[coordinate]) for i, p in enumerate(profiles) if lab[i] == g
                            ),
                        ]
                        for coordinate in ("latitude", "longitude")
                    }
                    for g in range(k)
                ],
            }
            gate = config["selection_gate"]
            row["eligible"] = min(sizes) >= gate["minimum_cluster_size"] and all(
                row[key] >= gate[key]
                for key in ("resample_ari_mean", "coordinate_agreement", "method_ari")
            )
            scores.append(row)
            mappings[f"{method}_{k}"] = lab.tolist()
    criteria = [
        (-np.array([r["silhouette"] for r in scores])),
        np.array([r["davies_bouldin"] for r in scores]),
        -np.array([r["resample_ari_mean"] for r in scores]),
        -np.array([r["coordinate_agreement"] for r in scores]),
        np.array(
            [
                np.mean(
                    [
                        r["coherence"][f]
                        for f in (
                            "elevation_m",
                            "annual_mean_temperature_c",
                            "annual_precipitation_mm",
                        )
                    ]
                )
                for r in scores
            ]
        ),
    ]
    from scipy.stats import rankdata

    ranks = np.mean([rankdata(v, method="average") for v in criteria], axis=0)
    for row, rank in zip(scores, ranks, strict=True):
        row["combined_rank"] = float(rank)
    eligible = [r for r in scores if r["eligible"]]
    selected = (
        min(eligible, key=lambda r: (r["combined_rank"], r["k"], r["method"])) if eligible else None
    )
    output = {
        "features": features,
        "exclusions": exclusions,
        "correlation_matrix": np.corrcoef(raw.T).tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "scores": scores,
        "mappings": mappings,
        "selected": selected,
        "recommendation_status": "CANDIDATE_FOR_REVIEW" if selected else "INSUFFICIENT_STABILITY",
    }
    if selected:
        key, k = f"{selected['method']}_{selected['k']}", selected["k"]
        lab = np.array(mappings[key])
        rx = StandardScaler().fit_transform(matrix(profiles, features, "recent"))
        recent_scaler = StandardScaler().fit(matrix(profiles, features, "recent"))
        rlab = aligned(lab, fit(rx, k, selected["method"], config), k)
        temporal = float(np.mean(lab == rlab))
        coord_rows = []
        for i, base in enumerate(profiles):
            changed, cell_changed, max_delta = False, False, 0.0
            for ps in perturbations:
                pb = scaler.transform(matrix(ps, features, "baseline"))
                pr = recent_scaler.transform(matrix(ps, features, "recent"))
                bp = (
                    lab[i]
                    if np.array_equal(pb[i], x[i])
                    else classify(pb[i : i + 1], centers(x, lab))[0]
                )
                rp = (
                    rlab[i]
                    if np.array_equal(pr[i], rx[i])
                    else classify(pr[i : i + 1], centers(rx, rlab))[0]
                )
                changed |= bool(bp != lab[i] or rp != rlab[i])
                cell_changed |= (
                    ps[i]["grid"]["latitude"] != base["grid"]["latitude"]
                    or ps[i]["grid"]["longitude"] != base["grid"]["longitude"]
                )
                max_delta = max(
                    max_delta,
                    float(np.max(np.abs(pb[i] - x[i]))),
                    float(np.max(np.abs(pr[i] - rx[i]))),
                )
            coord_rows.append(
                {
                    "base_id": base["base_id"],
                    "grid_changed": cell_changed,
                    "maximum_standardized_profile_delta": max_delta,
                    "zone_changed": changed,
                    "status": "LOCATION_SENSITIVITY_REVIEW_REQUIRED"
                    if changed
                    else "LOCATION_SENSITIVITY_STABLE",
                }
            )
        output.update(
            {
                "baseline_labels": lab.tolist(),
                "recent_labels": rlab.tolist(),
                "temporal_agreement": temporal,
                "coordinate_sensitivity": coord_rows,
            }
        )
        if temporal < config["recent_temporal_agreement_minimum"]:
            output["recommendation_status"] = "INSUFFICIENT_STABILITY"
    output["hash"] = digest(output)
    return output
