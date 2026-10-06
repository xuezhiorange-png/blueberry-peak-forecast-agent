"""S5 fixed Ridge feature-increment experiment; no model/feature selection."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_base10_benchmark import flatten_features, ridge_rows, score
from backend.app.area_yield.v015_benchmark_custody import load, sha
from backend.app.area_yield.v015_harvest_state import FEATURES, policy, read_artifact
from backend.app.area_yield.v015_research_cohort import digest
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES, fit_ridge_artifact

COUNTS = {"TRAIN": 3705, "VALIDATION": 5412, "EXPOSED_OOT": 8775}
MANIFEST = "a71b4998d6242709433d6fea334270b4c439c0cdd6f7a4492a1d29533fe82567"
POLICY = "e692f0aaa4a92f87a51b1d886211e302290b1251d6a41f7460eccfe0b0cc1e2c"
ROWSET = "dbd37e02e19d1fc37942e0accae7d76198bc499d58d66e01104f6833c899445e"
STATE_HASHES = {
    "TRAIN": "75b5535bcf1b32ea1ebac45fbed2334f9900b4ee01a30b6b15d420e2ae800813",
    "VALIDATION": "6f45d6b8cc1ea4440bfa5a699c7d854f36dc7ac6d3fa6c25bc083abea6046d6e",
    "EXPOSED_OOT": "9d81338d2e17108b089f580a575a407387237d007815a1a83d056f1754e4488a",
}
ERROR_METRICS = (
    "DAILY_WAPE",
    "DAILY_MAE_KG",
    "H7_DAILY_WAPE",
    "H15_DAILY_WAPE",
    "H7_CUMULATIVE_WAPE",
    "H15_CUMULATIVE_WAPE",
    "SINGLE_DAY_PEAK_QUANTITY_MAE_KG",
    "SINGLE_DAY_PEAK_DATE_MAE_DAYS",
    "ROLLING7_PEAK_QUANTITY_MAE_KG",
    "ROLLING7_PEAK_START_DATE_MAE_DAYS",
    "CURVE_SHAPE_ERROR",
)


class HarvestCustody:
    """Only frozen feature files/common keys; never raw harvest or Weather8."""

    def __init__(self, root: Path) -> None:
        self.root = root
        m = load(root / "manifest.json")
        if (
            m.get("manifest_hash") != MANIFEST
            or digest({k: v for k, v in m.items() if k != "manifest_hash"}) != MANIFEST
            or m.get("policy_hash") != POLICY
            or digest(policy()) != POLICY
        ):
            raise ValueError("BLOCKED_INPUT_DRIFT")
        raw = (root / "audit/harvest-state-common-rowset.json").read_bytes()
        if sha(raw) != ROWSET:
            raise ValueError("BLOCKED_INPUT_DRIFT")
        self.common = load(root / "audit/harvest-state-common-rowset.json")
        if len(self.common) != sum(COUNTS.values()) or len(
            {r["row_key"] for r in self.common}
        ) != len(self.common):
            raise ValueError("FAIL_COMMON_ROWSET")
        for split, n in COUNTS.items():
            if sum(r["split"] == split and r["target_rows"] == 15 for r in self.common) != n:
                raise ValueError("FAIL_COMMON_ROWSET")
            name = f"feature_zone/harvest-state-v1-{split.lower().replace('_', '-')}.json"
            if m["private_members"][name]["sha256"] != STATE_HASHES[split]:
                raise ValueError("BLOCKED_INPUT_DRIFT")

    def bind(
        self, split: str, full: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        name = f"harvest-state-v1-{split.lower().replace('_', '-')}.json"
        path = self.root / "feature_zone" / name
        checked = read_artifact(path, STATE_HASHES[split])
        envelope = load(path)
        states = {r["row_key"]: r for r in checked}
        metadata = {r["row_key"]: r for r in envelope}
        if len(states) != len(full) or set(states) != {r["row_key"] for r in full}:
            raise ValueError("FAIL_COMMON_ROWSET")
        keys = {r["row_key"] for r in self.common if r["split"] == split}
        rows = [r for r in full if r["row_key"] in keys]
        if len(rows) != COUNTS[split]:
            raise ValueError("FAIL_COMMON_ROWSET")
        for r in full:
            meta = metadata[r["row_key"]]
            if any(r[k] != meta[k] for k in ("base_id", "season", "forecast_origin", "split")):
                raise ValueError("FAIL_COMMON_ROWSET")
            if states[r["row_key"]]["harvest_state_complete"] != (r["row_key"] in keys):
                raise ValueError("FAIL_COMMON_ROWSET")
        vectors = {r["row_key"]: states[r["row_key"]]["harvest_state_v1"] for r in rows}
        return rows, vectors


def target_rows(rows: list[dict[str, Any]], states: dict[str, Any], model: str) -> list[Any]:
    if model not in ("M0", "M1"):
        raise ValueError("MODEL_NOT_FROZEN")
    flatten_features(rows)
    result = ridge_rows(rows)
    if model == "M0":
        return result
    for r in rows:
        state = states[r["row_key"]]
        if set(state) != set(FEATURES) or any(
            not Decimal(state[k]).is_finite() or Decimal(state[k]) < 0 for k in FEATURES
        ):
            raise ValueError("HARVEST_STATE_INVALID")
    return [
        replace(
            r,
            feature_values=r.feature_values
            + tuple((k, states[r.key.rsplit("#D", 1)[0]][k]) for k in FEATURES),
        )
        for r in result
    ]


def fit_predict(
    model: str,
    train: list[dict[str, Any]],
    states: dict[str, Any],
    labels: list[list[str]],
    predict: list[dict[str, Any]],
    prediction_states: dict[str, Any],
) -> tuple[Any, list[list[str]]]:
    tr = target_rows(train, states, model)
    y = [Decimal(v) for row in labels for v in row]
    if len(y) != len(tr) or any(not v.is_finite() or v < 0 for v in y):
        raise ValueError("COMMON_LABELSET")
    artifact = fit_ridge_artifact(
        model_id=f"V0_15_S5_{model}_RIDGE",
        fold_id="S5_FIXED_RESEARCH",
        rows=list(zip(tr, y, strict=True)),
        feature_names=BASE_FEATURES + (FEATURES if model == "M1" else ()),
        training_input_hash=digest([r.payload() for r in tr]),
    )
    values = [
        format(artifact.predict(r), ".12f") for r in target_rows(predict, prediction_states, model)
    ]
    return artifact, [values[i : i + 15] for i in range(0, len(values), 15)]


def deltas(m0: dict[str, Any], m1: dict[str, Any]) -> dict[str, Any]:
    with localcontext() as ctx:
        ctx.prec = 50
        result = {}
        for name in ERROR_METRICS:
            if name not in m0 or name not in m1:
                continue
            a, b = m0[name], m1[name]
            delta = Decimal(b) - Decimal(a) if a is not None and b is not None else None
            result[name] = {
                "absolute_delta": str(delta) if delta is not None else None,
                "relative_delta": str(delta / Decimal(a))
                if delta is not None and Decimal(a) != 0
                else "NOT_COMPUTABLE",
            }
        return result


def breadth(m0: dict[str, Any], m1: dict[str, Any]) -> dict[str, Any]:
    if not m0 or set(m0) != set(m1):
        raise ValueError("COMMON_BASES")
    with localcontext() as ctx:
        ctx.prec = 50
        result = {}
        for h in (7, 15):
            counts = {"improved": 0, "degraded": 0, "unchanged": 0}
            kg = {k: Decimal(0) for k in counts}
            unavailable = 0
            for base in sorted(m0):
                a, b = m0[base], m1[base]
                actual = Decimal(a[f"actual{h}"])
                if actual != Decimal(b[f"actual{h}"]):
                    raise ValueError("COMMON_LABELSET")
                if actual <= 0:
                    unavailable += 1
                    continue
                delta = Decimal(b[f"error{h}"]) - Decimal(a[f"error{h}"])
                category = "improved" if delta < 0 else ("degraded" if delta > 0 else "unchanged")
                counts[category] += 1
                kg[category] += actual
            total = sum(kg.values(), Decimal(0))
            result[f"H{h}"] = {
                **{k + "_base_count": v for k, v in counts.items()},
                "undefined_base_count": unavailable,
                "improved_base_share": str(Decimal(counts["improved"]) / len(m0))
                if not unavailable
                else None,
                "improved_actual_kg_share": str(kg["improved"] / total)
                if total > 0 and not unavailable
                else None,
                "degraded_actual_kg_share": str(kg["degraded"] / total)
                if total > 0 and not unavailable
                else None,
            }
        return result


def robustness(
    rows: list[dict[str, Any]], p0: list[list[str]], p1: list[list[str]], labels: list[list[str]]
) -> dict[str, Any]:
    _, a = score(rows, p0, labels)
    _, b = score(rows, p1, labels)
    with localcontext() as ctx:
        ctx.prec = 50
        ranked = sorted(
            (k for k in a if Decimal(a[k]["error15"]) - Decimal(b[k]["error15"]) > 0),
            key=lambda k: (-(Decimal(a[k]["error15"]) - Decimal(b[k]["error15"])), k),
        )
    result: dict[str, Any] = {}
    for n in (1, 2):
        keep = [i for i, r in enumerate(rows) if r["base_id"] not in set(ranked[:n])]
        if len(ranked) < n or not keep:
            result[f"LEAVE_TOP{n}"] = {"available": False, "H7_delta": None, "H15_delta": None}
            continue
        r = [rows[i] for i in keep]
        y = [labels[i] for i in keep]
        m0, _ = score(r, [p0[i] for i in keep], y)
        m1, _ = score(r, [p1[i] for i in keep], y)
        d = deltas(m0, m1)
        result[f"LEAVE_TOP{n}"] = {
            "available": True,
            "removed_base_count": n,
            "remaining_origin_count": len(keep),
            "M0_H7_DAILY_WAPE": m0["H7_DAILY_WAPE"],
            "M1_H7_DAILY_WAPE": m1["H7_DAILY_WAPE"],
            "M0_H15_DAILY_WAPE": m0["H15_DAILY_WAPE"],
            "M1_H15_DAILY_WAPE": m1["H15_DAILY_WAPE"],
            "H7_delta": d["H7_DAILY_WAPE"]["absolute_delta"],
            "H15_delta": d["H15_DAILY_WAPE"]["absolute_delta"],
        }
    return result


def classify(
    direction: list[str | None], shares: list[str | None], robust: list[str | None]
) -> str:
    if (
        len(direction) != 4
        or len(shares) != 4
        or len(robust) != 2
        or any(v is None for v in direction + shares + robust)
    ):
        return "INCONCLUSIVE"
    d = [Decimal(str(v)) for v in direction]
    s = [Decimal(str(v)) for v in shares]
    r = [Decimal(str(v)) for v in robust]
    if not all(v.is_finite() for v in d + s + r):
        return "INCONCLUSIVE"
    stable = all(v < 0 for v in r)
    if all(v < 0 for v in d) and all(v > Decimal(".50") for v in s) and stable:
        return "SUPPORTED"
    if all(v >= 0 for v in d) and not stable:
        return "NOT_SUPPORTED"
    return "INCONCLUSIVE"
