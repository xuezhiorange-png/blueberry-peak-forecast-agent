"""Read-only frozen Ridge algebra. No IO, labels, fitting or causal inference."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from typing import Any

from backend.app.area_yield.data import digest as model_digest
from backend.app.area_yield.v015_research_cohort import digest

MODEL_ID = "V0_15_S5_M1_RIDGE"
POLICY_VERSION = "V0_16_M1_STANDARDIZED_LINEAR_ATTRIBUTION_R1"
STANDARDIZATION = "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD"
LEGACY_RULE = "V0_15_S5_M1_RIDGE_MISSING_STANDARDIZATION_HASH_COMPAT_R1"
LEGACY_FILE_HASH = "b382312d33e834ed1b0ec1b98bbb84dcba3ea0f37a31ae846c0a91387f415161"
LEGACY_INTERNAL_HASH = "ecfb9e7c1aa90a44cc3a2298118ebbbdd0fd285836a364e895813fb25011eeb2"
LEGACY_RAW_DIGEST = "925c28e3b7123f55d7b64fa2f9ae2369f73e867fe622f6d32b71246a60b97979"
LEGACY_SOURCE_HASH = "aae66403ddbc285c55c4133cf1379dfec00aaff17f22cf8f5f43bb9ab6e685f6"
FEATURES = (
    "reference_area_mu_div_1000",
    "season_progress",
    "sin_1",
    "cos_1",
    "sin_2",
    "cos_2",
    "area_x_sin_1",
    "area_x_cos_1",
    "area_x_sin_2",
    "area_x_cos_2",
    "past_7d_harvest_kg",
    "past_14d_harvest_kg",
    "past_28d_harvest_kg",
    "season_to_date_harvest_kg",
)
FAMILY = {"BASE10": FEATURES[:10], "HARVEST_STATE": FEATURES[10:]}
SEMANTIC = {
    "AREA": FEATURES[:1],
    "SEASON_POSITION": FEATURES[1:6],
    "AREA_SEASON_INTERACTION": FEATURES[6:10],
    "HARVEST_STATE": FEATURES[10:],
    "OTHER": (),
}


def validate_legacy_m1_artifact(
    artifact: dict[str, Any],
    *,
    file_hash: str,
    contract_standardization: str,
    config_standardization: str,
    historical_source_hash: str,
    historical_schema_proven: bool,
) -> dict[str, Any]:
    """Exact owner-approved identity, not a generic missing-field fallback."""
    payload = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    if (
        artifact.get("model_id") != MODEL_ID
        or file_hash != LEGACY_FILE_HASH
        or artifact.get("artifact_hash") != LEGACY_INTERNAL_HASH
        or "standardization" in artifact
        or model_digest(payload) != LEGACY_RAW_DIGEST
    ):
        raise ValueError("LEGACY_ARTIFACT_COMPATIBILITY_NOT_AUTHORIZED")
    if (
        contract_standardization != STANDARDIZATION
        or config_standardization != STANDARDIZATION
        or historical_source_hash != LEGACY_SOURCE_HASH
        or historical_schema_proven is not True
    ):
        raise ValueError("BLOCKED_STANDARDIZATION_AUTHORITY_CONFLICT")
    restored = model_digest({**payload, "standardization": STANDARDIZATION})
    if restored != LEGACY_INTERNAL_HASH:
        raise ValueError("ARTIFACT_INTERNAL_HASH_INVALID")
    return {
        "legacy_artifact_serialization_gap": True,
        "legacy_compatibility_rule_id": LEGACY_RULE,
        "model_artifact_file_hash": file_hash,
        "stored_artifact_hash": LEGACY_INTERNAL_HASH,
        "legacy_serialized_payload_digest": LEGACY_RAW_DIGEST,
        "missing_field": "standardization",
        "injected_compatibility_value": STANDARDIZATION,
        "compat_reconstructed_digest": restored,
        "compat_reconstructed_digest_match": True,
        "historical_ridge_source_sha256": historical_source_hash,
        "legacy_training_hash_included_standardization": True,
        "legacy_serializer_omitted_standardization": True,
        "source_artifact_mutation": False,
        "legacy_model_code_mutation": False,
        "inference_numeric_fields_changed": False,
        "second_compatibility_exception_used": False,
    }


def finite(value: Any, code: str = "ARTIFACT_NUMERIC_INVALID") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(code) from None
    if not math.isfinite(number):
        raise ValueError(code)
    return number


def validate_model(
    artifact: dict[str, Any], *, compatibility: dict[str, Any] | None = None
) -> dict[str, Any]:
    if artifact.get("feature_names") != list(FEATURES):
        raise ValueError("FEATURE_SCHEMA_DRIFT")
    for key, expected in {
        "model_id": MODEL_ID,
        "fold_id": "S5_FIXED_RESEARCH",
        "alpha": "10.000000",
        "intercept_unpenalized": True,
        "nonnegative_output_clip": True,
        "solver": "numpy.linalg.solve",
    }.items():
        if artifact.get(key) != expected:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
    if "standardization" in artifact:
        if artifact["standardization"] != STANDARDIZATION or model_digest(
            {k: v for k, v in artifact.items() if k != "artifact_hash"}
        ) != artifact.get("artifact_hash"):
            raise ValueError("ARTIFACT_INTERNAL_HASH_INVALID")
    elif (
        compatibility is None
        or compatibility.get("compat_reconstructed_digest_match") is not True
        or model_digest(
            {
                **{k: v for k, v in artifact.items() if k != "artifact_hash"},
                "standardization": STANDARDIZATION,
            }
        )
        != LEGACY_INTERNAL_HASH
    ):
        raise ValueError("ARTIFACT_INTERNAL_HASH_INVALID")
    for key in ("feature_means", "feature_scales", "coefficients"):
        if not isinstance(artifact.get(key), list) or len(artifact[key]) != 14:
            raise ValueError("FEATURE_SCHEMA_DRIFT")
        values = [
            finite(
                v,
                "ARTIFACT_SCALER_INVALID"
                if key == "feature_scales"
                else "ARTIFACT_NUMERIC_INVALID",
            )
            for v in artifact[key]
        ]
        if key == "feature_scales" and any(v <= 0 for v in values):
            raise ValueError("ARTIFACT_SCALER_INVALID")
    finite(artifact.get("intercept"))
    return artifact


def raw_replay(model: dict[str, Any], vector: dict[str, str]) -> float:
    """Independent expression faithful to the frozen RidgeArtifact.predict path."""
    if set(vector) != set(FEATURES):
        raise ValueError("FEATURE_SCHEMA_DRIFT")
    values = tuple(
        (finite(vector[n], "FEATURE_NUMERIC_INVALID") - float(mean)) / float(scale)
        for n, mean, scale in zip(
            FEATURES, model["feature_means"], model["feature_scales"], strict=True
        )
    )
    return finite(
        float(model["intercept"])
        + sum(
            float(coef) * value for coef, value in zip(model["coefficients"], values, strict=True)
        ),
        "MODEL_OUTPUT_INVALID",
    )


def partition(terms: dict[str, Decimal], groups: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {
        group: str(sum((terms[n] for n in names), Decimal(0))) for group, names in groups.items()
    }


def attribute(model: dict[str, Any], vector: dict[str, str], sealed: str) -> dict[str, Any]:
    replay = raw_replay(model, vector)
    contributions = []
    for n, mean, scale, coef in zip(
        FEATURES,
        model["feature_means"],
        model["feature_scales"],
        model["coefficients"],
        strict=True,
    ):
        z = finite((float(vector[n]) - float(mean)) / float(scale), "FEATURE_NUMERIC_INVALID")
        contributions.append(finite(float(coef) * z, "MODEL_OUTPUT_INVALID"))
    raw = float(model["intercept"]) + sum(contributions)
    if raw.hex() != replay.hex():
        raise ValueError("RAW_LINEAR_RECONSTRUCTION_MISMATCH")
    predicted = format(max(0.0, raw), ".12f")
    if predicted != sealed:
        raise ValueError("SEALED_POINT_PREDICTION_RECONSTRUCTION_MISMATCH")
    with localcontext() as ctx:
        # Exact finite serialized binary64 terms, including extreme exponent fixtures.
        ctx.prec = 2000
        terms = {
            n: Decimal(format(v, ".17g")) for n, v in zip(FEATURES, contributions, strict=True)
        }
        anchor = Decimal(format(float(model["intercept"]), ".17g"))
        clip = Decimal(format(-raw if raw < 0 else 0.0, ".17g"))
        adjustment = Decimal(sealed) - (anchor + sum(terms.values(), Decimal(0)) + clip)
        if anchor + sum(terms.values(), Decimal(0)) + clip + adjustment != Decimal(sealed):
            raise ValueError("SERIALIZED_ACCOUNTING_MISMATCH")
        return {
            "sealed_point_prediction_kg": sealed,
            "replayed_point_prediction_kg": predicted,
            "raw_linear_score": format(raw, ".17g"),
            "model_intercept": str(anchor),
            "feature_contributions": [
                {"feature_name": n, "model_space_contribution_kg": str(terms[n])} for n in FEATURES
            ],
            "family_group_contributions": partition(terms, FAMILY),
            "business_semantic_group_contributions": partition(terms, SEMANTIC),
            "clip_adjustment_kg": str(clip),
            "serialization_adjustment_kg": str(adjustment),
            "reconstruction_exact": True,
            "raw_binary_match": True,
            "serialized_accounting_exact": True,
            "feature_vector_hash": digest([[n, vector[n]] for n in FEATURES]),
        }


def horizon(rows: list[dict[str, Any]], length: int) -> dict[str, Any]:
    selected = sorted((r for r in rows if r["lead_day"] <= length), key=lambda r: r["lead_day"])
    if [r["lead_day"] for r in selected] != list(range(1, length + 1)):
        return {"status": f"H{length}_NOT_COMPUTABLE"}
    with localcontext() as ctx:
        ctx.prec = 2000
        terms = {
            n: sum(
                (
                    Decimal(r["feature_contributions"][j]["model_space_contribution_kg"])
                    for r in selected
                ),
                Decimal(0),
            )
            for j, n in enumerate(FEATURES)
        }
        sums = {
            k: sum((Decimal(r[k]) for r in selected), Decimal(0))
            for k in (
                "sealed_point_prediction_kg",
                "model_intercept",
                "clip_adjustment_kg",
                "serialization_adjustment_kg",
            )
        }
        exact = (
            sums["sealed_point_prediction_kg"]
            == sums["model_intercept"]
            + sum(terms.values(), Decimal(0))
            + sums["clip_adjustment_kg"]
            + sums["serialization_adjustment_kg"]
        )
        if not exact:
            raise ValueError("HORIZON_ACCOUNTING_MISMATCH")
        return {
            "status": "COMPLETE",
            "point_total_kg": str(sums["sealed_point_prediction_kg"]),
            "feature_contributions": {n: str(v) for n, v in terms.items()},
            "model_intercept_total_kg": str(sums["model_intercept"]),
            "clip_adjustment_kg": str(sums["clip_adjustment_kg"]),
            "serialization_adjustment_kg": str(sums["serialization_adjustment_kg"]),
            "family_group_contributions": partition(terms, FAMILY),
            "business_semantic_group_contributions": partition(terms, SEMANTIC),
            "serialized_accounting_exact": exact,
        }


def statistics(values: list[Decimal]) -> dict[str, Any]:
    with localcontext() as ctx:
        ctx.prec = 50
        absolute = sorted(abs(v) for v in values)
        count = len(values)
        return {
            "target_row_count": count,
            "mean_signed_contribution_kg": str(sum(values, Decimal(0)) / count),
            "mean_absolute_contribution_kg": str(sum(absolute, Decimal(0)) / count),
            "median_absolute_contribution_kg": str(
                (absolute[(count - 1) // 2] + absolute[count // 2]) / 2
            ),
            "positive_row_count": sum(v > 0 for v in values),
            "negative_row_count": sum(v < 0 for v in values),
            "zero_row_count": sum(v == 0 for v in values),
        }


def summaries(rows: list[dict[str, Any]], horizons: list[dict[str, Any]]) -> dict[str, Any]:
    features = [
        {
            "feature_name": n,
            **statistics(
                [
                    Decimal(r["feature_contributions"][j]["model_space_contribution_kg"])
                    for r in rows
                ]
            ),
        }
        for j, n in enumerate(FEATURES)
    ]
    ranked = sorted(
        features, key=lambda r: (-Decimal(r["mean_absolute_contribution_kg"]), r["feature_name"])
    )
    for rank, item in enumerate(ranked, 1):
        item["model_space_mean_absolute_contribution_rank"] = rank
    result: dict[str, Any] = {"feature-summary.json": features}
    for name, field, groups in [
        ("family-group-summary.json", "family_group_contributions", FAMILY),
        ("semantic-group-summary.json", "business_semantic_group_contributions", SEMANTIC),
    ]:
        result[name] = {
            "grouping_axis": field,
            "grouping_axes_are_independent": True,
            "groups": [
                {"group_name": g, **statistics([Decimal(r[field][g]) for r in rows])}
                for g in groups
            ],
        }
    result["horizon-summary.json"] = {
        f"H{h}": {
            "origin_count": len(horizons),
            "exact_reconstruction_count": sum(
                r[f"H{h}"]["serialized_accounting_exact"] for r in horizons
            ),
            **{
                axis: [
                    {
                        "group_name": g,
                        **statistics([Decimal(r[f"H{h}"][axis][g]) for r in horizons]),
                    }
                    for g in groups
                ]
                for axis, groups in [
                    ("family_group_contributions", FAMILY),
                    ("business_semantic_group_contributions", SEMANTIC),
                ]
            },
        }
        for h in (7, 15)
    }
    clipped = sum(Decimal(r["raw_linear_score"]) < 0 for r in rows)
    result["reconstruction-summary.json"] = {
        "origin_count": len(horizons),
        "target_row_count": len(rows),
        "exact_prediction_match_count": len(rows),
        "exact_prediction_mismatch_count": 0,
        "exact_prediction_match_rate": "1",
        "raw_linear_binary_match_count": len(rows),
        "clipped_target_row_count": clipped,
        "unclipped_target_row_count": len(rows) - clipped,
        "serialized_accounting_exact_count": len(rows),
        "serialized_accounting_mismatch_count": 0,
        "max_abs_serialization_adjustment_kg": str(
            max(abs(Decimal(r["serialization_adjustment_kg"])) for r in rows)
        ),
        "h7_exact_origin_count": len(horizons),
        "h15_exact_origin_count": len(horizons),
    }
    return result
