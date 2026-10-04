"""Frozen V0.13 four-feature-family experiment; no search or promotion."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.area_yield.gdd_features import sha256
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES, FEATURE_NAMES_B
from backend.app.area_yield.weather_value_conclusion import metric as metric

MODELS = {
    name: f"V0_13_{name}_{suffix}"
    for name, suffix in (("M0", "BASE"), ("M1", "WEATHER"), ("M2", "GDD"), ("M3", "WEATHER_GDD"))
}
FEATURES = {
    "M0": BASE_FEATURES,
    "M1": FEATURE_NAMES_B,
    "M2": BASE_FEATURES + ("gdd_w7", "gdd_w14", "gdd_w30"),
    "M3": FEATURE_NAMES_B + ("gdd_w7", "gdd_w14", "gdd_w30"),
}
COMPARISONS = {
    "WEATHER_VALUE": ("M0", "M1"),
    "GDD_VALUE": ("M0", "M2"),
    "COMBINED_VALUE": ("M0", "M3"),
    "GDD_ON_TOP_OF_WEATHER": ("M1", "M3"),
    "WEATHER_ON_TOP_OF_GDD": ("M2", "M3"),
}
CONTRACT = dict(
    alpha="10.000000",
    solver="numpy.linalg.solve",
    standardization="TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
    clip=True,
    tbase="7.0",
    windows=[7, 14, 30],
    upper_cap=None,
    lead_feature=False,
    impute=False,
    refit_leave_top=False,
    combined="POOLED_ERROR_OVER_POOLED_ACTUAL",
    primary_metric="DAILY_WAPE_IN_COMPLETE_H7_AND_H15_VIEWS",
    comparisons=list(COMPARISONS),
    feature_search=False,
    features={k: list(v) for k, v in FEATURES.items()},
)


class ExperimentError(ValueError):
    """Frozen experimental authority violation."""


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract != CONTRACT:
        raise ExperimentError("EXPERIMENT_CONTRACT_CHANGED")


def verify_keys(keys: Sequence[str], count: int, expected_hash: str) -> None:
    if len(keys) != count or len(set(keys)) != count or digest(list(keys)) != expected_hash:
        raise ExperimentError("FROZEN_ROW_UNIVERSE_MISMATCH")


def verify_artifact(artifact: Mapping[str, Any]) -> None:
    payload = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    model = next((k for k, v in MODELS.items() if v == artifact.get("model_id")), None)
    if (
        model is None
        or artifact.get("schema") != "V0_13_RIDGE_ARTIFACT_V1"
        or artifact.get("standardization") != CONTRACT["standardization"]
        or artifact.get("zero_std_policy") != "SCALE_1"
        or artifact.get("feature_names") != list(FEATURES[model])
        or artifact.get("alpha") != CONTRACT["alpha"]
        or artifact.get("solver") != CONTRACT["solver"]
        or artifact.get("nonnegative_output_clip") is not True
        or artifact.get("intercept_unpenalized") is not True
        or digest(payload) != artifact.get("artifact_hash")
    ):
        raise ExperimentError("MODEL_ARTIFACT_INTEGRITY_FAILURE")


def synthetic_artifact() -> dict[str, Any]:
    """Public deterministic contract fixture, not a fitted research artifact."""
    result: dict[str, Any] = dict(
        schema="V0_13_RIDGE_ARTIFACT_V1",
        model_id=MODELS["M0"],
        feature_names=list(FEATURES["M0"]),
        alpha=CONTRACT["alpha"],
        solver=CONTRACT["solver"],
        standardization=CONTRACT["standardization"],
        zero_std_policy="SCALE_1",
        nonnegative_output_clip=True,
        intercept_unpenalized=True,
        coefficients=["0"] * 10,
    )
    result["artifact_hash"] = digest(result)
    return result


class ExecutionGuard:
    """Release label access only against durable, integrity-checked prediction seals."""

    def __init__(self, root: Path):
        self.root = root
        self.scoring_started = False

    def verify_seal(self, fold: str) -> dict[str, Any]:
        path = self.root / fold / "prediction-seal.json"
        try:
            seal = json.loads(path.read_text())
            payload = {k: v for k, v in seal.items() if k != "seal_hash"}
            if (
                seal["fold_id"].lower() != fold
                or digest(payload) != seal["seal_hash"]
                or seal["sealed_before_validation_label_read"] is not True
                or set(seal["model_ids"]) != set(MODELS.values())
            ):
                raise ExperimentError("PREDICTION_SEAL_INVALID")
            inventory = seal["file_hashes"]
            if set(inventory) != {
                "predictions-before-scoring.jsonl",
                *(f"{m.lower()}-artifact.json" for m in MODELS),
            }:
                raise ExperimentError("PREDICTION_SEAL_INVENTORY_INVALID")
            for name, expected in inventory.items():
                if sha256(path.parent / name) != expected:
                    raise ExperimentError("SEALED_FILE_CHANGED")
            return dict(seal)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise ExperimentError("PREDICTION_SEAL_REQUIRED_OR_INVALID") from exc

    def allow_label_read(self, season: str) -> None:
        if season == "2024-2025":
            self.verify_seal("fold_a")
        elif season == "2025-2026":
            self.verify_seal("fold_a")
            self.verify_seal("fold_b")
        elif season != "2023-2024":
            raise ExperimentError("UNAUTHORIZED_LABEL_SEASON")

    def allow_fit(self) -> None:
        if self.scoring_started:
            raise ExperimentError("POST_SCORE_REFIT_FORBIDDEN")

    def begin_score(self) -> None:
        self.verify_seal("fold_a")
        self.verify_seal("fold_b")
        self.scoring_started = True


def authoritative_actual(actual: Any) -> Any:
    """Missing/unknown is never an implicit zero, even if a quantity is supplied."""
    if actual is None or actual.status not in {"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"}:
        return None
    if actual.quantity_kg is None:
        return None
    if not actual.quantity_kg.is_finite() or actual.quantity_kg < 0:
        raise ExperimentError("INVALID_ACTUAL_QUANTITY")
    return actual


def cumulative_metric(rows: Sequence[Mapping[str, Any]], model: str, days: int) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["season"]), str(row["base_id"]), str(row["forecast_origin"]))].append(row)
    windows = []
    for group in groups.values():
        if len(group) == days and {int(r["lead_day"]) for r in group} == set(range(days)):
            windows.append(
                {
                    "actual_daily_kg": str(
                        sum((Decimal(str(r["actual_daily_kg"])) for r in group), Decimal(0))
                    ),
                    model: str(sum((Decimal(str(r[model])) for r in group), Decimal(0))),
                }
            )
    return metric(windows, model)


def compare(
    rows: Sequence[Mapping[str, Any]],
    reference: str,
    new: str,
    all_base_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    a, b = metric(rows, reference), metric(rows, new)

    def delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> str | None:
        if "pooled_wape" not in left or "pooled_wape" not in right:
            return None
        return str(Decimal(right["pooled_wape"]) - Decimal(left["pooled_wape"]))

    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["base_id"])].append(row)
    ids = sorted(set(all_base_ids or groups))
    counts = dict(
        improved_base_count=0,
        degraded_base_count=0,
        unchanged_base_count=0,
        not_computable_base_count=0,
    )
    actual = {"improved": Decimal(0), "degraded": Decimal(0), "unchanged": Decimal(0)}
    contributors = []
    for base in ids:
        left, right = metric(groups[base], reference), metric(groups[base], new)
        d = delta(left, right)
        if d is None:
            counts["not_computable_base_count"] += 1
            continue
        direction = "improved" if Decimal(d) < 0 else "degraded" if Decimal(d) > 0 else "unchanged"
        counts[f"{direction}_base_count"] += 1
        actual[direction] += Decimal(left["pooled_actual_kg"])
        reduction = Decimal(left["pooled_absolute_error_kg"]) - Decimal(
            right["pooled_absolute_error_kg"]
        )
        if reduction > 0:
            contributors.append((base, reduction))
    contributors.sort(key=lambda item: (-item[1], item[0]))
    total = sum(actual.values(), Decimal(0))
    comparable = len(ids) - counts["not_computable_base_count"]
    breadth: dict[str, Any] = {**counts, "comparable_base_count": comparable}
    for direction in ("improved", "degraded"):
        breadth[f"{direction}_base_share"] = (
            str(Decimal(counts[f"{direction}_base_count"]) / comparable) if comparable else None
        )
        breadth[f"{direction}_actual_kg_share"] = str(actual[direction] / total) if total else None
    result: dict[str, Any] = dict(
        reference=a,
        new=b,
        delta=delta(a, b),
        breadth=breadth,
        positive_contributors=[
            {"base_id": base, "reduction_kg": str(value)} for base, value in contributors
        ],
    )
    for n in (1, 2):
        removed = [base for base, _ in contributors[:n]]
        remaining = [r for r in rows if str(r["base_id"]) not in removed]
        result[f"leave_top{n}"] = dict(
            removed_base_ids=removed,
            removed_count=len(removed),
            refit=False,
            sample_count=len(remaining),
            delta=delta(metric(remaining, reference), metric(remaining, new)),
        )
    if result["delta"] is not None and Decimal(a["pooled_wape"]) != 0:
        result["relative_delta"] = str(Decimal(result["delta"]) / Decimal(a["pooled_wape"]))
        result["relative_improvement"] = str(-Decimal(result["relative_delta"]))
    return result


def predictive_gate(
    scopes: Mapping[str, Any],
    *,
    no_contract_violation: bool = True,
    no_leakage: bool = True,
    no_post_result_tuning: bool = True,
) -> dict[str, Any]:
    if not (no_contract_violation and no_leakage and no_post_result_tuning):
        raise ExperimentError("INVALID_EXPERIMENT_NOT_A_FEATURE_CLASSIFICATION")

    def negative(value: Any) -> bool:
        return value is not None and Decimal(str(value)).is_finite() and Decimal(str(value)) < 0

    conditions = {}
    for horizon in ("H7", "H15"):
        conditions[f"{horizon}_combined_improves"] = negative(scopes["combined"][horizon]["delta"])
        conditions[f"{horizon}_every_fold_improves"] = all(
            negative(scopes[f][horizon]["delta"]) for f in ("fold_a", "fold_b")
        )
        conditions[f"{horizon}_leave_top2_improves"] = negative(
            scopes["combined"][horizon]["leave_top2"]["delta"]
        )
        conditions[f"{horizon}_every_fold_breadth"] = all(
            scopes[f][horizon]["breadth"]["improved_actual_kg_share"] is not None
            and Decimal(scopes[f][horizon]["breadth"]["improved_actual_kg_share"]) > Decimal("0.50")
            for f in ("fold_a", "fold_b")
        )
    complete = (
        all(
            scopes[s][h]["delta"] is not None and Decimal(str(scopes[s][h]["delta"])).is_finite()
            for s in ("fold_a", "fold_b", "combined")
            for h in ("H7", "H15")
        )
        and all(
            scopes["combined"][h]["leave_top2"]["delta"] is not None
            and Decimal(str(scopes["combined"][h]["leave_top2"]["delta"])).is_finite()
            for h in ("H7", "H15")
        )
        and all(
            scopes[f][h]["breadth"]["improved_actual_kg_share"] is not None
            for f in ("fold_a", "fold_b")
            for h in ("H7", "H15")
        )
    )
    conditions.update(NO_CONTRACT_VIOLATION=True, NO_LEAKAGE=True, NO_POST_RESULT_TUNING=True)
    status = "INCONCLUSIVE_BY_FROZEN_RULE"
    if all(conditions.values()):
        status = "MEETS_SUPPORTED_CRITERIA"
    elif (
        complete
        and all(
            scopes["combined"][h]["delta"] is not None
            and Decimal(scopes["combined"][h]["delta"]) >= 0
            for h in ("H7", "H15")
        )
        and not all(
            conditions[f"{h}_every_fold_improves"] and conditions[f"{h}_leave_top2_improves"]
            for h in ("H7", "H15")
        )
    ):
        status = "MEETS_NOT_SUPPORTED_CRITERIA"
    return {"status": status, "conditions": conditions, "final_version_closeout": False}
