"""R2 role-separated inputs; unchanged R1 objectives, basis and numeric certificate."""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    import conditional_growth_core as core  # type: ignore[import-not-found]
except ImportError:
    from backend.app.area_yield import conditional_growth as core

Record = dict[str, Any]


def weather_reference(weather: dict[str, list[float]], seasons: list[str]) -> Record:
    """Fixed fit-cutoff regional reference, never queried-season realized weather."""
    bases = sorted({k.split("|")[0] for k in weather})
    result = {}
    for base in bases:
        available = [s for s in seasons if base + "|" + s in weather]
        if available:
            result[base] = {
                "values": np.mean([weather[base + "|" + s] for s in available], axis=0).tolist(),
                "source_seasons": available,
                "role": "FIXED_TRAINING_PERIOD_REGIONAL_REFERENCE",
            }
    return result


def raw_features(
    query: Record, context: Record, reference: Record, version: str
) -> tuple[np.ndarray, list[Record]]:
    values, lineage = [], []
    for group in core.groups(version):
        if group != "W":
            row, origins = core.raw_features(query, context, version, group)
        else:
            r = reference.get(query["base_id"])
            row = np.asarray((r["values"] if r else [np.nan] * 4) + [float(r is None)])
            origins = [
                {
                    "base_id": query["base_id"],
                    "season": query["season"],
                    "group": "W",
                    "feature": name,
                    "source_seasons": ";".join(r["source_seasons"]) if r else "",
                    "missing": r is None,
                    "source_role": "FIXED_TRAINING_PERIOD_REGIONAL_REFERENCE",
                }
                for name in core.GROUP_NAMES["W"]
            ]
        values.extend(row.tolist())
        lineage.extend(origins)
    return np.asarray(values), lineage


def prepare(
    targets: list[Record], history: list[Record], reference: Record, mix: Record, version: str
) -> tuple[Record, list[Record]]:
    core.prepare(targets, {}, {}, "CG0")  # Existing identity/value validation only.
    ctx = core.context(history, {}, mix)
    pairs = [raw_features(s, ctx, reference, version) for s in targets]
    raw = np.asarray([r for r, _ in pairs]).reshape(len(targets), 5 * len(core.groups(version)))
    transform = core.fit_transform(raw)
    x = core.transform(raw, transform)
    status = {}
    for j, group in enumerate(core.groups(version)):
        section = raw[:, j * 5 : (j + 1) * 5]
        columns = [k for k in transform["active"] if j * 5 <= k < (j + 1) * 5]
        selected = x[:, [transform["active"].index(k) for k in columns]]
        status[group] = {
            "nonmissing_samples": int((section[:, 4] == 0).sum()),
            "varying_dimensions": len(columns),
            "rank": int(np.linalg.matrix_rank(selected)) if columns else 0,
            "fit_target_count": len(targets),
            "status": "ESTIMABLE_VARIATION"
            if columns
            else "NOT_IDENTIFIABLE_IN_THIS_TRAINING_SCOPE",
        }
    return {"context": ctx, "transform": transform, "x": x, "raw": raw, "group_status": status}, [
        r for _, origins in pairs for r in origins
    ]


def fit_model(
    targets: list[Record],
    history: list[Record],
    reference: Record,
    mix: Record,
    shape: Record,
    total: Record,
    m0_density: list[float],
    contract_hash: str,
    role: str = "DIAGNOSTIC_ONLY",
) -> tuple[Record, list[Record], list[Record]]:
    shape_version = "CG0" if shape["version"] == "M0" else shape["version"]
    sp, sl = prepare(targets, history, reference, mix, shape_version)
    # Independently constructed even when SHAPE=M0/CG0. Never shape-selected x.
    tp, tl = prepare(targets, history, reference, mix, "CGHWV")
    audits = []
    fitted_shape, fitted_total = dict(shape), dict(total)
    if shape["version"] != "M0":
        valid = [i for i, s in enumerate(targets) if s["total"] > 0]
        bases = [
            core.basis(core.positions(targets[i]["dates"], targets[i]["season"]), shape["basis"])
            for i in valid
        ]
        truth = [np.asarray(targets[i]["quantities"]) / targets[i]["total"] for i in valid]
        x = sp["x"][valid]
        fit = core.cached_solve(
            core.shape_objective(bases, x, truth, shape["lambda"]),
            (x.shape[1] + 1) * (shape["basis"] - 1),
            shape["lambda"],
            [x, *bases, *truth],
            "R2_SHAPE",
        )
        audits.append({"layer": "SHAPE", "active_dimensions": x.shape[1], **fit})
        if not fit["accepted"]:
            raise ValueError("SHAPE_NUMERICAL_UNVERIFIED")
        fitted_shape["theta"] = fit["theta"]
    areas, totals = (
        np.asarray([s["area"] for s in targets]),
        np.asarray([s["total"] for s in targets]),
    )
    if totals.sum() <= 0:
        raise ValueError("TOTAL_ALL_ZERO_UNAVAILABLE")
    if total["version"] == "TY1":
        x = tp["x"]
        fit = core.cached_solve(
            core.total_objective(x, areas, totals, total["lambda"]),
            x.shape[1],
            total["lambda"],
            [x, areas, totals],
            "R2_TOTAL",
        )
        audits.append({"layer": "TOTAL", "active_dimensions": x.shape[1], **fit})
        if not fit["accepted"]:
            raise ValueError("TOTAL_NUMERICAL_UNVERIFIED")
        fitted_total.update(
            beta=fit["theta"],
            alpha=core.total_intercept(np.asarray(fit["theta"]), x, areas, totals),
            training_loss_scale=float(totals.sum()),
        )
    model = {
        "schema": "CONDITIONAL_GROWTH_RESEARCH_R2",
        "role": role,
        "contract_hash": contract_hash,
        "shape": fitted_shape,
        "total": fitted_total,
        "shape_transform": sp["transform"],
        "total_transform": tp["transform"],
        "shape_group_status": sp["group_status"],
        "total_group_status": tp["group_status"],
        "context": sp["context"],
        "weather_reference": reference,
        "W_SEMANTICS_CHANGED_FROM_R1": True,
        "m0_density": m0_density,
        "pooled_yield": float(totals.sum() / areas.sum()),
        "training_count": len(targets),
        "training_cutoff": max(d for s in targets for d in s["dates"]),
        "actual_shape_groups": core.groups(shape_version),
        "actual_total_groups": "HWV",
    }
    model["artifact_hash"] = core.artifact_hash(model)
    return (
        model,
        audits,
        [
            {**r, "pipeline": pipeline}
            for origins, pipeline in ((sl, "SHAPE"), (tl, "TOTAL"))
            for r in origins
        ],
    )


def forecast(model: Record, request: Record, *, group_cv: bool = False) -> Record:
    if core.artifact_hash(model) != model["artifact_hash"]:
        raise ValueError("MODEL_HASH_INTEGRITY")
    query = {"base_id": request["base_id"], "season": request["target_season"]}
    version = "CG0" if model["shape"]["version"] == "M0" else model["shape"]["version"]
    raw, sl = raw_features(query, model["context"], model["weather_reference"], version)
    sx = core.transform(raw.reshape(1, -1), model["shape_transform"])[0]
    raw, tl = raw_features(query, model["context"], model["weather_reference"], "CGHWV")
    tx = core.transform(raw.reshape(1, -1), model["total_transform"])[0]
    shape = dict(model["shape"])
    if shape["version"] != "M0":
        coefficients = np.asarray(shape["theta"]).reshape(len(sx) + 1, shape["basis"] - 1)
        shape.update(version="CG0", theta=(np.r_[1.0, sx] @ coefficients).tolist())
    yield_hat = (
        model["pooled_yield"]
        if model["total"]["version"] == "TY0"
        else float(np.exp(model["total"]["alpha"] + tx @ np.asarray(model["total"]["beta"])))
    )
    # Compile learned conditional coefficients, then reuse canonical curve/request service.
    virtual = {
        "shape": shape,
        "total": {"version": "TY0"},
        "m0_density": model["m0_density"],
        "context": {"history": [], "seasons": [], "weather": {}, "mix": {}},
        "included_groups": "",
        "transform": {"means": [], "sd": [], "active": []},
        "pooled_yield": yield_hat,
        "training_cutoff": model["training_cutoff"],
        "role": model["role"],
    }
    virtual["artifact_hash"] = core.artifact_hash(virtual)
    output = core.forecast(virtual, request, group_cv=group_cv)
    output.update(
        feature_provenance=tl,
        shape_feature_provenance=sl,
        transformed_shape_features=sx.tolist(),
        transformed_total_features=tx.tolist(),
        W_SEMANTICS_CHANGED_FROM_R1=True,
        PRODUCTION_PROMOTION_GRANTED=False,
    )
    return dict(output)
