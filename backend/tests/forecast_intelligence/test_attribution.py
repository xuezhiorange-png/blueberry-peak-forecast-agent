"""Synthetic algebra/custody contracts; never loads private historical inputs."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from backend.app.area_yield.data import digest
from backend.app.forecast_intelligence import attribution as a


def model(**updates):
    value = dict(
        model_id=a.MODEL_ID,
        fold_id="S5_FIXED_RESEARCH",
        feature_names=list(a.FEATURES),
        alpha="10.000000",
        intercept_unpenalized=True,
        nonnegative_output_clip=True,
        solver="numpy.linalg.solve",
        standardization=a.STANDARDIZATION,
        feature_means=["10"] * 14,
        feature_scales=["2"] * 14,
        coefficients=["3"] * 14,
        intercept="1",
        training_row_keys=[],
        training_input_hash="a" * 64,
        training_label_hash="b" * 64,
    )
    value.update(updates)
    return {**value, "artifact_hash": digest(value)}


def test_standardized_mean_and_known_contribution():
    m = a.validate_model(model())
    r = a.attribute(m, dict.fromkeys(a.FEATURES, "14"), "85.000000000000")
    assert all(x["model_space_contribution_kg"] == "6" for x in r["feature_contributions"])
    assert r["raw_linear_score"] == "85"
    r = a.attribute(m, dict.fromkeys(a.FEATURES, "10"), "1.000000000000")
    assert all(x["model_space_contribution_kg"] == "0" for x in r["feature_contributions"])


@pytest.mark.parametrize("scale", ["0", "-1", "NaN", "Infinity"])
def test_invalid_scaler(scale):
    with pytest.raises(ValueError, match="ARTIFACT_SCALER_INVALID"):
        a.validate_model(model(feature_scales=[scale] * 14))


@pytest.mark.parametrize("field", ["coefficients", "feature_means", "intercept"])
@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_invalid_parameter(field, value):
    with pytest.raises(ValueError, match="ARTIFACT_NUMERIC_INVALID"):
        a.validate_model(model(**{field: value if field == "intercept" else [value] * 14}))


def test_schema_order_and_missing_extra():
    for names in [list(reversed(a.FEATURES)), list(a.FEATURES[:-1]), [*a.FEATURES, "extra"]]:
        with pytest.raises(ValueError, match="FEATURE_SCHEMA_DRIFT"):
            a.validate_model(model(feature_names=names))
    m = a.validate_model(model())
    for values in [
        dict.fromkeys(a.FEATURES[:-1], "1"),
        {**dict.fromkeys(a.FEATURES, "1"), "x": "1"},
    ]:
        with pytest.raises(ValueError, match="FEATURE_SCHEMA_DRIFT"):
            a.attribute(m, values, "0.000000000000")


def test_clip_serialization_groups_and_exact_prediction():
    m = a.validate_model(model(intercept="-5", coefficients=["0"] * 14))
    r = a.attribute(m, dict.fromkeys(a.FEATURES, "10"), "0.000000000000")
    assert r["clip_adjustment_kg"] == "5"
    assert all(Decimal(v) == 0 for v in r["family_group_contributions"].values())
    m = a.validate_model(model(intercept="0.1", coefficients=["0.1"] * 14))
    vector = dict.fromkeys(a.FEATURES, "11.1")
    sealed = format(max(0.0, a.raw_replay(m, vector)), ".12f")
    r = a.attribute(m, vector, sealed)
    with localcontext() as ctx:
        ctx.prec = 2000
        terms = sum(
            (Decimal(x["model_space_contribution_kg"]) for x in r["feature_contributions"]),
            Decimal(0),
        )
        assert terms == sum(map(Decimal, r["family_group_contributions"].values()))
        assert terms == sum(map(Decimal, r["business_semantic_group_contributions"].values()))
        assert Decimal(sealed) == terms + Decimal(r["model_intercept"]) + Decimal(
            r["clip_adjustment_kg"]
        ) + Decimal(r["serialization_adjustment_kg"])
    assert r["raw_binary_match"] and r["serialized_accounting_exact"]
    assert r["clip_adjustment_kg"] == "0"
    with pytest.raises(ValueError, match="SEALED_POINT_PREDICTION_RECONSTRUCTION_MISMATCH"):
        a.attribute(m, vector, sealed.rstrip("0"))


def test_group_partitions():
    assert list(a.FAMILY) == ["BASE10", "HARVEST_STATE"]
    assert [len(v) for v in a.SEMANTIC.values()] == [1, 5, 4, 4, 0]
    for groups in [a.FAMILY, a.SEMANTIC]:
        flat = [x for names in groups.values() for x in names]
        assert len(flat) == len(set(flat)) == 14 and set(flat) == set(a.FEATURES)


@pytest.mark.parametrize("days", [6, 7, 10, 15])
def test_horizon_exact_and_no_padding(days):
    m = a.validate_model(model())
    rows = [
        dict(a.attribute(m, dict.fromkeys(a.FEATURES, "14"), "85.000000000000"), lead_day=i)
        for i in range(1, days + 1)
    ]
    for h in [7, 15]:
        r = a.horizon(rows, h)
        assert r["status"] == ("COMPLETE" if days >= h else f"H{h}_NOT_COMPUTABLE")
        if days >= h:
            assert Decimal(r["point_total_kg"]) == 85 * h
            assert r["serialized_accounting_exact"]
        assert a.horizon(list(reversed(rows)), h) == r


def test_legacy_exact_allowlist(monkeypatch):
    full = model()
    legacy = {k: v for k, v in full.items() if k != "standardization"}
    raw = digest({k: v for k, v in legacy.items() if k != "artifact_hash"})
    monkeypatch.setattr(a, "LEGACY_INTERNAL_HASH", full["artifact_hash"])
    monkeypatch.setattr(a, "LEGACY_RAW_DIGEST", raw)
    before = deepcopy(legacy)
    kwargs = dict(
        file_hash=a.LEGACY_FILE_HASH,
        contract_standardization=a.STANDARDIZATION,
        config_standardization=a.STANDARDIZATION,
        historical_source_hash=a.LEGACY_SOURCE_HASH,
        historical_schema_proven=True,
    )
    assert a.validate_legacy_m1_artifact(legacy, **kwargs)["compat_reconstructed_digest_match"]
    assert legacy == before
    for key, value in [
        ("file_hash", "x"),
        ("contract_standardization", "x"),
        ("config_standardization", "x"),
        ("historical_source_hash", "x"),
        ("historical_schema_proven", False),
    ]:
        with pytest.raises(ValueError):
            a.validate_legacy_m1_artifact(legacy, **{**kwargs, key: value})
    for mutate in [
        lambda x: x.update(artifact_hash="x"),
        lambda x: x.update(model_id="OTHER_RIDGE"),
        lambda x: x.update(extra=True),
        lambda x: x.pop("intercept"),
        lambda x: x.update(coefficients=["4"] * 14),
    ]:
        bad = deepcopy(legacy)
        mutate(bad)
        with pytest.raises(ValueError):
            a.validate_legacy_m1_artifact(bad, **kwargs)
    with pytest.raises(ValueError):
        a.validate_legacy_m1_artifact(full, **kwargs)
    assert a.validate_model(full)["standardization"] == a.STANDARDIZATION


def test_normal_hash_tamper_and_feature_dict_order():
    m = model()
    bad = deepcopy(m)
    bad["intercept"] = "2"
    with pytest.raises(ValueError, match="ARTIFACT_INTERNAL_HASH_INVALID"):
        a.validate_model(bad)
    vector = dict.fromkeys(a.FEATURES, "14")
    assert a.attribute(m, vector, "85.000000000000") == a.attribute(
        m, dict(reversed(list(vector.items()))), "85.000000000000"
    )


def test_mixed_sign_terms_binary64_and_feature_numeric_rejection():
    m = a.validate_model(model(coefficients=["0.1", "-0.2"] * 7, intercept="10"))
    vector = dict.fromkeys(a.FEATURES, "13.7")
    raw = a.raw_replay(m, vector)
    r = a.attribute(m, vector, format(max(0.0, raw), ".12f"))
    terms = [float(x["model_space_contribution_kg"]) for x in r["feature_contributions"]]
    assert (float(m["intercept"]) + sum(terms)).hex() == raw.hex()
    assert any(x < 0 for x in terms) and any(x > 0 for x in terms)
    for value in ("NaN", "Infinity"):
        with pytest.raises(ValueError, match="FEATURE_NUMERIC_INVALID"):
            a.attribute(m, {**vector, a.FEATURES[0]: value}, "0.000000000000")
