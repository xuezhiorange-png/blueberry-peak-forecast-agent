"""Frozen V0.15 Ridge reused for a matched Base10/Harvest State pair."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from backend.app.area_yield.data import digest as ridge_digest
from backend.app.area_yield.v015_base10_benchmark import RIDGE_CONFIG
from backend.app.area_yield.weather_aware_backtest import (
    BASE_FEATURES,
    RidgeArtifact,
    RollingTargetRow,
    fit_ridge_artifact,
)
from backend.research import v019_origin_features as features
from backend.research.v019_synthetic_validation import digest

MODELS = {"M0": "BASE10_RIDGE_MATCHED_CONTROL", "M1": "BASE10_PLUS_HARVEST_STATE_V1"}
CONFIG = {
    "models": MODELS,
    "ridge": RIDGE_CONFIG,
    "output_kg_dp": 6,
    "rounding": "ROUND_HALF_EVEN",
    "parameter_search": False,
    "strict_pit": False,
}


def rows(record: dict[str, Any], model: str) -> list[RollingTargetRow]:
    features.validate(record)
    if not record["complete"] or model not in MODELS:
        raise ValueError("INCOMPLETE_COMMON_MODEL_INPUT")
    vectors = features.base10(record)
    return [
        RollingTargetRow(
            key=record["row_key"] + f"#D{i + 1:02}",
            base_id=record["base_id"],
            base_name="",
            season=record["season"],
            forecast_origin=record["cutoff"],
            target_date=date.fromisoformat(d),
            lead_day=i + 1,
            reference_area_mu=Decimal(record["area_mu"]),
            feature_values=tuple((k, v[k]) for k in BASE_FEATURES)
            + (tuple((k, record["values"][k]) for k in features.FEATURES) if model == "M1" else ()),
            weather_feature_hash="",
            weather_source="NONE",
            weather_lane="NONE",
            feature_policy_version=features.VERSION,
        )
        for i, (d, v) in enumerate(zip(record["target_dates"], vectors, strict=True))
    ]


def fit_pair(
    records: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    allowed_seasons: tuple[str, ...],
    evaluation_start: date,
) -> dict[str, Any]:
    if (
        not allowed_seasons
        or set(allowed_seasons) - {"2023-2024", "2024-2025"}
        or any(r["season"] not in {"2023-2024", "2024-2025"} for r in labels)
    ):
        raise ValueError("UNAUTHORIZED_TRAINING_SEASON")
    selected = sorted(
        [
            r
            for r in records
            if r["season"] in allowed_seasons and r["complete"] and len(r["target_dates"]) == 15
        ],
        key=lambda r: r["row_key"],
    )
    if len({r["row_key"] for r in selected}) != len(selected) or not selected:
        raise ValueError("NO_UNIQUE_TRAINING_ORIGINS")
    idx = {}
    for r in labels:
        key = (r["base_id"], r["season"], r["date"])
        if key in idx:
            raise ValueError("DUPLICATE_TRAINING_LABEL")
        idx[key] = r["kg"]
    targets = []
    for r in selected:
        for d in r["target_dates"]:
            if date.fromisoformat(d) >= evaluation_start:
                raise ValueError("TEMPORAL_TRAINING_LABEL_LEAK")
            v = Decimal(idx[r["base_id"], r["season"], d])
            if not v.is_finite() or v < 0:
                raise ValueError("INVALID_TRAINING_LABEL")
            targets.append(v)
    fitted = {}
    for m in MODELS:
        tr = [rr for r in selected for rr in rows(r, m)]
        artifact = fit_ridge_artifact(
            model_id=MODELS[m],
            fold_id=str(evaluation_start),
            rows=list(zip(tr, targets, strict=True)),
            feature_names=BASE_FEATURES + (features.FEATURES if m == "M1" else ()),
            training_input_hash=digest([r.payload() for r in tr]),
        )
        fitted[m] = artifact.payload()
    if any(
        fitted["M0"][k] != fitted["M1"][k] for k in ("training_row_keys", "training_label_hash")
    ):
        raise ValueError("MATCHED_TRAINING_MEMBERS_OR_LABELS")
    body = {
        "config": CONFIG,
        "models": fitted,
        "training_seasons": sorted(allowed_seasons),
        "evaluation_start": str(evaluation_start),
        "training_origins": [r["row_key"] for r in selected],
        "training_origin_count": len(selected),
        "training_target_count": len(targets),
        "training_base_seasons": sorted({r["base_id"] + "|" + r["season"] for r in selected}),
        "training_bases": sorted({r["base_id"] for r in selected}),
        "training_last_date": max(d for r in selected for d in r["target_dates"]),
        "common_training_members_sha256": digest([r["row_key"] for r in selected]),
        "strict_pit": False,
    }
    return {**body, "sha256": digest(body)}


def restore(p: dict[str, Any]) -> RidgeArtifact:
    expected = ridge_digest(
        {
            **{k: v for k, v in p.items() if k != "artifact_hash"},
            "standardization": RIDGE_CONFIG["standardization"],
        }
    )
    if expected != p["artifact_hash"]:
        raise ValueError("RIDGE_PARAMETER_SEAL")
    kwargs: dict[str, Any] = {k: tuple(v) if isinstance(v, list) else v for k, v in p.items()}
    return RidgeArtifact(**kwargs)


def compile_pair(fitted: dict[str, Any]) -> PreparedPair:
    if (
        fitted["sha256"] != digest({k: v for k, v in fitted.items() if k != "sha256"})
        or fitted["config"] != CONFIG
    ):
        raise ValueError("FIT_SEAL")
    if set(fitted["models"]) != set(MODELS):
        raise ValueError("FIT_MODEL_SCHEMA")
    return PreparedPair(
        fitted["sha256"],
        fitted["evaluation_start"],
        fitted["training_last_date"],
        tuple((m, restore(p)) for m, p in fitted["models"].items()),
    )


@dataclass(frozen=True)
class PreparedPair:
    fit_sha256: str
    evaluation_start: str
    training_last_date: str
    artifacts: tuple[tuple[str, RidgeArtifact], ...]

    def predict(self, record: dict[str, Any]) -> dict[str, Any]:
        features.validate(record)
        if (
            record["target_dates"][0] < self.evaluation_start
            or self.training_last_date >= record["target_dates"][0]
        ):
            raise ValueError("TEMPORAL_PREDICTION_BOUNDARY")
        if not record["complete"]:
            return {
                "status": "NOT_COMPUTABLE",
                "feature_sha256": record["sha256"],
                "reasons": record["reasons"],
            }
        values = {
            model: [
                {
                    "date": str(r.target_date),
                    "kg": format(
                        artifact.predict(r).quantize(Decimal(".000001"), rounding=ROUND_HALF_EVEN),
                        "f",
                    ),
                }
                for r in rows(record, model)
            ]
            for model, artifact in self.artifacts
        }
        return {
            "status": "COMPUTED",
            "feature_sha256": record["sha256"],
            "fit_sha256": self.fit_sha256,
            "predictions": values,
        }


def predict_pair(fitted: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return compile_pair(fitted).predict(record)
