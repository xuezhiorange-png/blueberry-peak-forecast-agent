"""S8 source isolation and explicit recorded-weight semantics, SYNTHETIC only."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.rolling_forecast import engine, inbound, model_artifacts
from backend.tests.rolling_forecast.inbound_fixture import body, fixture


def compute(catalog, offset=0):
    c = catalog.contexts[0]
    request = body(offset)
    origin = date.fromisoformat(request["origin_date"])
    cutoff = datetime.fromisoformat(request["origin_cutoff_at"])
    inbound.require_target(c.snapshots[0], model_artifacts.load(c.models[0]))
    rows = inbound.load(c, c.snapshots[0], origin, cutoff)
    return engine.forecast(
        c.calendar,
        c.area,
        origin,
        cutoff,
        rows,
        model_artifacts.load(c.models[0]),
        "RESEARCH_SHADOW",
    )


def test_real_ridge_chain_and_date_before_quantity_io(tmp_path, monkeypatch):
    catalog = fixture(tmp_path)
    original = Path.read_bytes
    opened = []

    def read(path):
        opened.append(path.name)
        assert not (path.name.startswith("day-") and path.name[4:14] >= "2026-11-05")
        return original(path)

    with monkeypatch.context() as m:
        m.setattr(Path, "read_bytes", read)
        first = compute(catalog)
    assert "manifest.json" in opened and len([p for p in opened if p.startswith("day-")]) == 35
    assert first == compute(catalog)
    assert first["feature_snapshot"]["values"]["past_7d_harvest_kg"] == "224.000000"
    for model in first["models"].values():
        assert model["forecast_target_quantity_basis"] == "RECORDED_INBOUND_WEIGHT"
        assert Decimal(model["H7"]["forecast_total_kg"]) == sum(
            Decimal(x["kg"]) for x in model["daily_forecast_kg"][:7]
        )
    assert first["models"]["M1"]["H7"]["forecast_total_kg"] == "538.941049"
    assert compute(catalog, 1)["models"]["M1"]["H15"]["forecast_total_kg"] == "1002.702182"


@pytest.mark.parametrize(
    "problem", ["duplicate", "wrong_member", "wrong_basis", "unknown_grade", "float_quantity"]
)
def test_invalid_source_never_becomes_a_numeric_prediction(tmp_path, problem):
    def mutate(i, day):
        if i != 34:
            return
        if problem == "duplicate":
            day["records"] *= 2
        elif problem == "wrong_member":
            day["records"][0]["member"]["farm_business_key"] = "OTHER"
        elif problem == "wrong_basis":
            day["quantity_basis"] = "INBOUND_NET_WEIGHT"
        elif problem == "unknown_grade":
            day["records"][0]["grade"] = "UNKNOWN"
        else:
            day["records"][0]["quantity_kg"] = 1.25

    catalog = fixture(tmp_path, mutate=mutate)
    with pytest.raises(ValueError):
        compute(catalog)


@pytest.mark.parametrize("problem", ["missing", "late", "unproven_time"])
def test_missing_or_late_not_zero_filled(tmp_path, problem):
    def mutate(i, day):
        if i != 34:
            return
        if problem == "missing":
            day["records"] = []
        elif problem == "late":
            day["records"][0]["server_ingested_at"] = "2026-11-05T10:00:00Z"
        else:
            day["records"][0]["available_at_authority"] = "MISSING"

    value = compute(fixture(tmp_path, mutate=mutate))
    assert value["models"]["M0"]["status"] == "COMPUTED"
    assert value["models"]["M1"]["status"] == "NOT_COMPUTABLE"
    assert value["feature_snapshot"]["values"]["past_7d_harvest_kg"] is None


def test_future_perturbations_invariant_prior_change_explainable(tmp_path):
    base = compute(fixture(tmp_path / "a"))
    future = compute(
        fixture(
            tmp_path / "b",
            mutate=lambda i, d: (
                d["records"][0].update(quantity_kg="999999.000000") if i >= 35 else None
            ),
        )
    )
    # Snapshot identity changes, never feature values or predicted kg.
    assert base["models"] == future["models"]
    prior = compute(
        fixture(
            tmp_path / "c",
            mutate=lambda i, d: (
                d["records"][0].update(quantity_kg="38.000000") if i == 34 else None
            ),
        )
    )
    assert base["models"]["M0"] == prior["models"]["M0"]
    assert base["models"]["M1"]["daily_forecast_kg"] != prior["models"]["M1"]["daily_forecast_kg"]


def reindex(catalog, change, source_updates=None):
    """Register another explicitly sealed SYNTHETIC source; do not overwrite old objects."""
    import json

    from backend.app.rolling_forecast.policy import Catalog
    from backend.research.v019_synthetic_validation import digest
    from backend.tests.rolling_forecast.inbound_fixture import write

    source = catalog.contexts[0].snapshots[0]
    data = json.loads(Path(source.manifest_path).read_bytes())
    change(data)
    data = inbound.Index.model_validate(data).model_dump(mode="json")
    path = Path(source.manifest_path).with_name("new-index.json")
    sha = write(path, data)
    updated = {
        **source.model_dump(mode="json"),
        "manifest_path": str(path),
        "manifest_sha256": sha,
        "snapshot_hash": digest(data),
        **(source_updates or {}),
    }
    value = catalog.model_dump(mode="json")
    value["contexts"][0]["snapshots"] = [updated]
    return Catalog.model_validate(value)


def test_hash_drift_and_private_path_rejected(tmp_path):
    catalog = fixture(tmp_path)
    path = tmp_path / "day-2026-11-04.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_HASH_MISMATCH"):
        compute(catalog)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="SOURCE_PATH_UNSAFE"):
        inbound.read(link, "a" * 64, 100000)


def test_weight_name_does_not_substitute_for_source_fit_binding(tmp_path):
    catalog = fixture(tmp_path)
    c = catalog.contexts[0]
    pair = model_artifacts.load(c.models[0])
    for source in (
        c.snapshots[0].model_copy(update={"target_binding": None}),
        c.snapshots[0].model_copy(
            update={
                "target_binding": c.snapshots[0].target_binding.model_copy(
                    update={"fit_sha256": "9" * 64}
                )
            }
        ),
    ):
        with pytest.raises(ValueError, match="SOURCE_BASIS_UNVERIFIED"):
            inbound.require_target(source, pair)


def test_explicit_zero_missing_date_partial_coverage_and_basis(tmp_path):
    import json

    from backend.research.v019_synthetic_validation import digest

    catalog = fixture(tmp_path, mutate=lambda i, d: d.update(records=[]) if i == 34 else None)
    zero = reindex(catalog, lambda _: None, {"confirmed_zero_dates": ["2026-11-04"]})
    value = compute(zero)
    assert value["feature_snapshot"]["complete"]
    assert value["feature_snapshot"]["values"]["past_7d_harvest_kg"] == "189.000000"
    missing = reindex(catalog, lambda d: d["days"].pop(34))
    assert compute(missing)["models"]["M1"]["status"] == "NOT_COMPUTABLE"
    partial = reindex(catalog, lambda d: d["days"][34].update(member_coverage=[]))
    assert not compute(partial)["feature_snapshot"]["complete"]
    definition = json.loads(Path(catalog.contexts[0].snapshots[0].manifest_path).read_bytes())[
        "physical_definition"
    ]
    definition["measure"] = "NET_WEIGHT"
    wrong = reindex(
        catalog,
        lambda d: d.update(physical_definition=definition),
        {"physical_definition_hash": digest(definition)},
    )
    with pytest.raises(ValueError, match="SOURCE_BASIS_UNVERIFIED"):
        compute(wrong)


def test_label_admission_requires_fit_and_maturity_not_name_only(tmp_path):
    from backend.app.rolling_forecast.evaluation import admission
    from backend.app.rolling_forecast.policy import MatureSnapshot

    catalog = fixture(tmp_path)
    result = compute(catalog)
    c = catalog.contexts[0]
    saved = dict(
        origin_date="2026-11-05",
        result=result,
        input={"observation_snapshot": c.snapshots[0].model_dump(mode="json")},
    )
    label = c.review_snapshots[0]
    assert admission(saved, label) == []
    assert admission(saved, label.model_copy(update={"target_binding": None})) == [
        "CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"
    ]
    wrong = label.model_copy(
        update={"target_binding": label.target_binding.model_copy(update={"fit_sha256": "9" * 64})}
    )
    assert admission(saved, wrong) == ["CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"]
    assert admission(saved, label.model_copy(update={"mature_through": date(2026, 11, 19)})) == [
        "LABELS_NOT_MATURE"
    ]
    for model in result["models"].values():
        model["model_provenance"] = "REAL_FROZEN_S6"
    field = MatureSnapshot.model_validate(
        {
            k: v
            for k, v in label.model_dump(mode="json").items()
            if k
            not in {
                "source_kind",
                "manifest_path",
                "manifest_sha256",
                "physical_definition_hash",
                "target_binding",
                "quantity_basis",
            }
        }
    )
    assert admission(saved, field) == ["CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"]
