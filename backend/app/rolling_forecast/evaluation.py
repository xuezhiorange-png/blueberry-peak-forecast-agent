"""Independent mature-label review; delegates all ten metrics to frozen S1 math."""

from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.local_auth.sessions import AuthError, Principal, now
from backend.app.rolling_forecast import application, observations
from backend.app.rolling_forecast.policy import Catalog
from backend.research import v019_research_evaluation as arithmetic
from backend.research.v019_origin_evaluation import curve, errors
from backend.research.v019_synthetic_validation import digest


async def review(
    db: AsyncSession, catalog: Catalog, principal: Principal, run_id: int, reference: str
) -> dict[str, Any]:
    saved = await application.get(db, catalog, principal, run_id, "evaluate")
    context = next(
        c
        for c in application.contexts(catalog, principal, "evaluate")
        if c.reference == saved["input"]["context_reference"]
    )
    sources = [s for s in context.review_snapshots if s.reference == reference]
    if len(sources) != 1:
        raise AuthError("FORBIDDEN")
    source = sources[0]
    start = date.fromisoformat(saved["origin_date"]) + timedelta(days=1)
    end = start + timedelta(days=14)
    if source.mature_through < end or (
        source.label_cutoff_at > now() and source.provenance != "SYNTHETIC_TEST_FIXTURE"
    ):
        raise ValueError("LABELS_NOT_MATURE")
    # Admit against the model's target, never against its observed feature units.
    # No cross-source conversion authority is implemented or inferred here.
    for model in saved["result"]["models"].values():
        target = model.get("forecast_target_quantity_basis")
        if (
            not target
            or target != source.quantity_basis
            or model.get("model_training_target_quantity_basis") != target
            or model.get("model_provenance") not in {"REAL_FROZEN_S6", "SYNTHETIC_TEST_FIXTURE"}
            or (
                model.get("model_provenance") == "SYNTHETIC_TEST_FIXTURE"
                and source.provenance != "SYNTHETIC_TEST_FIXTURE"
            )
            or (
                model.get("model_provenance") == "REAL_FROZEN_S6"
                and target != "RECORDED_INBOUND_WEIGHT"
            )
        ):
            raise ValueError("CROSS_SOURCE_TARGET_BASIS_UNVERIFIED")
    rows = await observations.load(
        db, context, source, end + timedelta(days=1), source.label_cutoff_at, start
    )
    result = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for window, count in (("H7_PREFIX", 7), ("H15_LOCAL", 15)):
            selected = rows[:count]
            reason = None
            model_errors = {}
            bias = {}
            total = Decimal(0)
            if len(selected) != count or any(
                r.observation_completeness != "COMPLETE" for r in selected
            ):
                reason = "INCOMPLETE_TARGET_LABELS"
            elif any(v["status"] != "COMPUTED" for v in saved["result"]["models"].values()):
                reason = "INCOMPLETE_MATCHED_MODEL_PREDICTIONS"
            else:
                actual = curve(
                    [{"date": str(r.business_date), "kg": str(r.quantity_kg)} for r in selected]
                )
                total = sum((r.kg for r in actual), Decimal(0))
                for name, model in saved["result"]["models"].items():
                    model_errors["baseline" if name == "M0" else "candidate"] = errors(
                        curve(model["daily_forecast_kg"][:count]), actual, str(run_id) + window
                    )
                    # Same signed mean-error definition as forecast-quality's daily_bias_kg.
                    # Its legacy P50/grain wrapper does not accept these H15 point forecasts;
                    # do not fabricate a P50 or farm/variety identity to call that wrapper.
                    signed = sum(
                        (
                            Decimal(p["kg"]) - a.kg
                            for p, a in zip(model["daily_forecast_kg"][:count], actual, strict=True)
                        ),
                        Decimal(0),
                    )
                    bias[name] = {
                        "status": "COMPUTED",
                        "numerator_kg": str(signed),
                        "denominator_days": count,
                        "value_kg": str(signed / count),
                        "definition": "MEAN_PREDICTED_MINUS_ACTUAL_KG",
                    }
            accumulator = arithmetic._accumulator()
            arithmetic._add(
                accumulator,
                {
                    "candidate_id": str(run_id) + window,
                    "base_id": saved["base_id"],
                    "window": window,
                },
                reason,
                total,
                model_errors,
                total > 0,
            )
            result[window] = arithmetic._finish(accumulator)
            result[window]["BIAS"] = bias or {
                m: {"status": "NOT_COMPUTABLE", "reason": reason} for m in ("M0", "M1")
            }
            change = "NOT_COMPUTABLE"
            if not reason:
                delta = (
                    model_errors["candidate"]["DAILY_MAE"] - model_errors["baseline"]["DAILY_MAE"]
                )
                change = "IMPROVED" if delta < 0 else "DEGRADED" if delta > 0 else "TIED"
            result[window]["base_outcomes"] = {
                "base_id": saved["base_id"],
                "criterion": "MATCHED_DAILY_MAE",
                "outcome": change,
                "counts": {
                    k: int(k == change) for k in ("IMPROVED", "DEGRADED", "TIED", "NOT_COMPUTABLE")
                },
            }
    body = {
        "run_id": run_id,
        "forecast_result_hash": saved["result_hash"],
        "label_snapshot_hash": source.snapshot_hash,
        "feature_observation_quantity_basis": saved["result"]["feature_snapshot"]["quantity_basis"],
        "model_training_target_quantity_basis": {
            m: v["model_training_target_quantity_basis"]
            for m, v in saved["result"]["models"].items()
        },
        "forecast_target_quantity_basis": {
            m: v["forecast_target_quantity_basis"] for m, v in saved["result"]["models"].items()
        },
        "evaluation_label_quantity_basis": source.quantity_basis,
        "model_provenance": {
            m: v["model_provenance"] for m, v in saved["result"]["models"].items()
        },
        "maturity_authority_hash": source.maturity_authority_hash,
        "groups": result,
        "actual_daily": [r.model_dump(mode="json") for r in rows],
        "strict_pit": False,
        "production_accuracy_validated": False,
        "H7_rolling_start_zero_is_structural": True,
    }
    return {**body, "review_hash": digest(body)}
