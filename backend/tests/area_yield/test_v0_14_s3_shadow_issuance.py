"""Synthetic issuance contracts; never real weather or harvest data."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield import v014_shadow_issuance as s
from backend.app.area_yield.v014_future_weather_features import FEATURE_NAMES
from backend.app.pit.schemas import AreaRevisionInput
from scripts.materialize_v0_14_s3a_area_authority import build_revision, revision_input


def fixture():
    area = build_revision(revision_input())
    created = datetime(2026, 10, 4, 17, tzinfo=UTC)
    origin = s.model_origin(created)
    weather = {k: "1.000000000000" for k in FEATURE_NAMES}
    rows = s.target_rows(area, origin, weather)
    return area, created, origin, rows


def test_midnight_six_hour_rule_and_fifteen_targets():
    area, created, origin, rows = fixture()
    assert origin.isoformat() == "2026-10-06T00:00:00+08:00"
    assert origin - created >= timedelta(hours=6)
    assert len(rows) == len({r["key"] for r in rows}) == 15
    assert rows[-1]["target_date"] == "2026-10-20"
    s.verify_area_time(area, created, origin)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("payload_hash", "0" * 64),
        ("base_id", "wrong"),
        ("season", "2025-2026"),
        ("area_type", "PLANNED_AREA"),
        ("area_type", "ACTUAL_PRODUCTIVE_AREA"),
        ("area_mu", Decimal("393.4")),
        ("known_at", datetime(2027, 1, 1, tzinfo=UTC)),
        ("effective_from", datetime(2027, 1, 1, tzinfo=UTC)),
    ],
)
def test_area_mutations_rejected(field, value):
    area, created, origin, _ = fixture()
    changed = area.model_copy(update={field: value})
    with pytest.raises(ValueError):
        s.verify_scope(changed, [changed])
        s.verify_area_time(changed, created, origin)


@pytest.mark.parametrize("mode", ["superseded", "conflict"])
def test_terminal_revision_gate(mode):
    area, _, _, _ = fixture()
    raw = area.model_dump()
    raw.update(area_revision_id="new", payload_hash=None)
    if mode == "superseded":
        raw.update(supersedes_revision_id=area.area_revision_id, area_type="PLANTED_AREA")
    else:
        raw.update(area_mu=Decimal("395"))
    child = AreaRevisionInput.model_validate(raw)
    child = child.model_copy(update={"payload_hash": child.computed_payload_hash()})
    with pytest.raises(ValueError):
        s.verify_scope(area, [area, child])


@pytest.mark.parametrize("mode", ["six_hour", "not_midnight", "seal_after", "seal_before"])
def test_timing_mutations(mode):
    _, created, origin, _ = fixture()
    sealed = created + timedelta(seconds=1)
    if mode == "six_hour":
        created = origin - timedelta(hours=5)
        sealed = created + timedelta(seconds=1)
    elif mode == "not_midnight":
        origin += timedelta(hours=1)
    elif mode == "seal_after":
        sealed = origin
    else:
        sealed = created
    with pytest.raises(ValueError):
        s.verify_timing(created, origin, sealed)


def test_target_outside_business_boundary():
    area, _, _, _ = fixture()
    origin = datetime.fromisoformat("2027-04-10T00:00:00+08:00")
    with pytest.raises(ValueError):
        s.target_rows(area, origin, {k: "1" for k in FEATURE_NAMES})


@pytest.mark.parametrize("mode", ["cycle", "known", "future", "manifest", "missing"])
def test_weather_mutations(mode):
    _, created, _, _ = fixture()
    surface = {
        "run_id": "20261004120000",
        "issued_at": "2026-10-04T12:00:00+00:00",
        "acquisition_receipt": {
            "fetched_at": created.isoformat(),
            "known_at": created.isoformat(),
            "manifest_sha256": "good",
        },
        "raw_manifest_sha256": "good",
    }
    if mode == "cycle":
        surface.update(run_id="20261004180000", issued_at="2026-10-04T18:00:00+00:00")
    elif mode == "known":
        surface["acquisition_receipt"]["known_at"] = (created + timedelta(hours=1)).isoformat()
    elif mode == "future":
        surface.update(run_id="20261005120000", issued_at="2026-10-05T12:00:00+00:00")
    elif mode == "manifest":
        surface["raw_manifest_sha256"] = "changed"
    else:
        del surface["run_id"]
    with pytest.raises((ValueError, KeyError)):
        s.verify_weather_receipt(surface, created)


@pytest.mark.parametrize("mode", ["count", "lane", "nonfinite", "weather_order", "key"])
def test_row_mutations(mode):
    _, _, _, rows = fixture()
    if mode == "count":
        rows.pop()
    elif mode == "lane":
        rows[0]["weather_lane"] = "PAST_OBSERVED_WEATHER"
    elif mode == "nonfinite":
        rows[0]["features"]["sin_1"] = "nan"
    elif mode == "weather_order":
        rows[0]["features"]["hidden_gdd"] = "1"
    else:
        rows[0]["key"] = rows[1]["key"]
    with pytest.raises(ValueError):
        s.verify_rows(rows)


@pytest.mark.parametrize(
    "operation", ["actual_content", "actual_hash", "actual_stat", "score", "fit", "refit"]
)
def test_forbidden_execution(operation):
    with pytest.raises(ValueError):
        s.operation_gate(operation)


@pytest.mark.parametrize(
    "key", ["predicted_daily_kg", "h7_total_kg", "coefficients", "coordinates"]
)
def test_public_privacy(key):
    with pytest.raises(ValueError):
        s.validate_public({key: "private"})


def test_private_path_rejected():
    with pytest.raises(ValueError):
        s.validate_public({"value": "/Users/operator/private"})


def test_seal_self_hash_and_tamper():
    body = {"shadow": True, "production": False}
    seal = s.self_seal(body)
    s.verify_seal(seal)
    seal["shadow"] = False
    with pytest.raises(ValueError):
        s.verify_seal(seal)


def test_immutable_idempotency(tmp_path):
    path = tmp_path / "predictions.json"
    s.write_immutable(path, {"hash": "same"})
    s.write_immutable(path, {"hash": "same"})
    with pytest.raises(ValueError):
        s.write_immutable(path, {"hash": "changed"})


def test_metric_contract_locked_and_no_threshold():
    m = s.metric_contract()
    assert m["primary"] == ["H7_DAILY_WAPE", "H15_DAILY_WAPE"]
    assert m["missing_is_zero"] is False
    assert m["business_promotion_threshold"] is None
    assert m["horizons"] == {"H7": list(range(7)), "H15": list(range(15))}


def test_runner_has_no_actual_training_scoring_imports_or_options():
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts/run_v0_14_s3_shadow_issuance.py"
    source = path.read_text()
    for flag in ("--actual", "--harvest", "--source25", "--source26"):
        assert flag not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not any(
                x in (node.module or "") for x in ("scoring", "training", "actual", "run_v0_14_s2")
            )


def synthetic_models():
    models = {}
    for role in ("C0", "W1"):
        names = list(s.BASE_FEATURES + (FEATURE_NAMES if role == "W1" else ()))
        body = {
            "schema": f"V0_14_{role}_RIDGE_ARTIFACT_V1",
            "model_id": f"V0_14_{role}_"
            + (
                "BASE_ONLY_PROSPECTIVE_COMPARATOR"
                if role == "C0"
                else "AS_ISSUED_WEATHER_PROSPECTIVE_CANDIDATE"
            ),
            "prospective_role": role,
            "feature_names": names,
            "feature_policy_hash": s.digest(s.POLICY),
            "alpha": "10.000000",
            "solver": "numpy.linalg.solve",
            "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
            "zero_std_policy": "SCALE_1",
            "intercept_unpenalized": True,
            "nonnegative_output_clip": True,
            "production_approved": False,
            "feature_means": ["0"] * len(names),
            "feature_scales": ["1"] * len(names),
            "coefficients": ["1"] * len(names),
            "intercept": "10",
            "training_row_key_hash": "synthetic_keys",
            "training_label_hash": "synthetic_labels",
            "training_cohort_hash": "synthetic_cohort",
            "training_row_count": 2,
        }
        models[role.lower()] = {**body, "artifact_hash": s.digest(body)}
    return models


def rehash(model):
    model["artifact_hash"] = s.digest({k: v for k, v in model.items() if k != "artifact_hash"})


def test_c0_cannot_consume_weather_and_pair_has_same_fifteen_keys():
    import copy

    _, _, _, rows = fixture()
    models = synthetic_models()
    first = s.predict_pair(models, rows)
    changed = copy.deepcopy(rows)
    for row in changed:
        for name in FEATURE_NAMES:
            row["features"][name] = "99"
    second = s.predict_pair(models, changed)
    assert first["c0"] == second["c0"]
    assert first["w1"] != second["w1"]
    assert [x[0] for x in first["c0"]] == [x[0] for x in first["w1"]]
    assert len(first["c0"]) == len(first["w1"]) == 15


def test_frozen_nonnegative_clip_and_twelve_decimal_output():
    _, _, _, rows = fixture()
    models = synthetic_models()
    for model in models.values():
        model["intercept"] = "-1"
        model["coefficients"] = ["0"] * len(model["feature_names"])
        rehash(model)
    assert all(p[1] == "0.000000000000" for ps in s.predict_pair(models, rows).values() for p in ps)


@pytest.mark.parametrize(
    "mutation",
    [
        "artifact_hash",
        "policy",
        "alpha",
        "solver",
        "scaler",
        "nonfinite",
        "feature_count",
        "feature_order",
        "c0_weather",
        "row_keys",
        "labels",
        "cohort",
    ],
)
def test_synthetic_artifact_mutations_rejected(mutation):
    _, _, _, rows = fixture()
    models = synthetic_models()
    model = models["w1"]
    if mutation == "artifact_hash":
        model["artifact_hash"] = "0" * 64
    elif mutation == "policy":
        model["feature_policy_hash"] = "0" * 64
    elif mutation in {"alpha", "solver"}:
        model[mutation] = "changed"
    elif mutation == "scaler":
        model["feature_scales"][0] = "0"
    elif mutation == "nonfinite":
        model["coefficients"][0] = "nan"
    elif mutation == "feature_count":
        model["feature_names"].pop()
    elif mutation == "feature_order":
        model["feature_names"].reverse()
    elif mutation == "c0_weather":
        model = models["c0"]
        model["feature_names"].append(FEATURE_NAMES[0])
    else:
        key = {
            "row_keys": "training_row_key_hash",
            "labels": "training_label_hash",
            "cohort": "training_cohort_hash",
        }[mutation]
        model[key] = "different"
    if mutation != "artifact_hash":
        rehash(model)
    with pytest.raises(ValueError):
        s.predict_pair(models, rows)


def test_synthetic_bundle_hash_mismatch_rejected(tmp_path):
    s.write_immutable(tmp_path / "bundle-manifest.json", {"files": [], "bundle_hash": "wrong"})
    with pytest.raises(ValueError, match="S2_BUNDLE_MISMATCH"):
        s.recover_bundle(tmp_path)


def test_actual_cli_argument_is_rejected_without_any_execution(monkeypatch):
    from scripts import run_v0_14_s3_shadow_issuance as runner

    monkeypatch.setattr("sys.argv", ["runner", "issue", "--actual", "synthetic"])
    with pytest.raises(SystemExit):
        runner.main()


@pytest.fixture
def synthetic_package(tmp_path, monkeypatch):
    from argparse import Namespace

    from backend.app.area_yield.v014_future_weather_features import REQUIRED_FIELDS
    from scripts import run_v0_14_s3_shadow_issuance as runner

    area, created, _, _ = fixture()
    data = {}
    for step, parameter in REQUIRED_FIELDS:
        accum = parameter in {"tp", "ssrd"}
        data[step, parameter] = {
            "value": {
                "2t": "283.15",
                "10u": "3",
                "10v": "4",
                "tp": str(Decimal(step) / 1000),
                "ssrd": str(step * 100),
            }[parameter],
            "units": {"2t": "K", "tp": "m", "ssrd": "J m**-2"}.get(parameter, "m s**-1"),
            "stepType": "accum" if accum else "instant",
            "startStep": 0 if accum else step,
            "endStep": step,
        }
    surface = {
        "run_id": "20261004120000",
        "issued_at": "2026-10-04T12:00:00+00:00",
        "raw_manifest_sha256": "synthetic_raw_hash",
        "raw_manifest": {"synthetic": True},
        "fields_by_base": {s.BASE_ID: data},
        "acquisition_receipt": {
            "fetched_at": created.isoformat(),
            "known_at": created.isoformat(),
            "manifest_sha256": "synthetic_raw_hash",
        },
    }

    class Clock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return created + timedelta(seconds=cls.calls)

    class Provider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def capture_feature_surface(self, **kwargs):
            assert kwargs["issued_at"] == datetime(2026, 10, 4, 12, tzinfo=UTC)
            return surface

    monkeypatch.setattr(runner, "datetime", Clock)
    monkeypatch.setattr(runner, "ECMWFDenseFeatureSurfaceProvider", Provider)
    monkeypatch.setattr(runner, "capture_latest", lambda p, t: (surface, []))
    args = Namespace(
        output=tmp_path / "package", locations=tmp_path / "location", cache=tmp_path / "cache"
    )
    models = synthetic_models()
    receipt = runner.issue(args, models, area)
    return runner, args, models, area, receipt


def test_full_synthetic_issuance_audit_and_idempotency(synthetic_package):
    runner, args, models, area, first = synthetic_package
    replay = runner.audit(args, models, area)
    assert replay["audit_replay"] == "PASS"
    assert replay["forecast_id"] == first["forecast_id"]
    assert replay["prediction_seal_hash"] == first["prediction_seal_hash"]
    assert replay["issuance_package_hash"] == first["issuance_package_hash"]
    old_seal = (args.output / "prediction-seal.json").read_bytes()
    assert (
        runner.issue(args, models, area)["idempotent_reissuance_gate"]
        == "PASS_REUSED_EXISTING_IDENTITY"
    )
    assert (args.output / "prediction-seal.json").read_bytes() == old_seal


@pytest.mark.parametrize(
    "member",
    [
        "request-snapshot.json",
        "c0-predictions.json",
        "w1-predictions.json",
        "prediction-seal.json",
        "weather-surface-manifest.json",
        "metric-contract.json",
        "cohort-entry.json",
    ],
)
def test_private_package_member_tamper_rejected(synthetic_package, member):
    runner, args, models, area, _ = synthetic_package
    # Synthetic secrets only; mutations must never touch real operator artifacts.
    (args.output / member).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="PACKAGE_MEMBER_TAMPER"):
        runner.audit(args, models, area)


def test_area_artifact_sha_mismatch_rejected(tmp_path):
    (tmp_path / "area-revision.json").write_bytes(b"synthetic mismatch")
    with pytest.raises(ValueError, match="S3A_ARTIFACT_MISMATCH"):
        s.recover_area(tmp_path, tmp_path)


def test_area_manifest_hash_mismatch_rejected(tmp_path, monkeypatch):
    import hashlib

    area, _, _, _ = fixture()
    raw = s.json_bytes(area.model_dump(mode="json"))
    (tmp_path / "area-revision.json").write_bytes(raw)
    monkeypatch.setattr(s, "AREA_FILE_SHA", hashlib.sha256(raw).hexdigest())
    s.write_immutable(tmp_path / "authority-manifest.json", {"manifest_hash": "wrong"})
    with pytest.raises(ValueError, match="S3A_MANIFEST_MISMATCH"):
        s.recover_area(tmp_path, tmp_path)


def test_missing_360_is_not_imputed(synthetic_package):
    runner, args, models, area, _ = synthetic_package
    # Mutate only the synthetic provider surface, not the immutable stored package.
    provider = runner.ECMWFDenseFeatureSurfaceProvider()
    surface = provider.capture_feature_surface(issued_at=datetime(2026, 10, 4, 12, tzinfo=UTC))
    del surface["fields_by_base"][s.BASE_ID][360, "tp"]
    with pytest.raises(ValueError):
        runner.audit(args, models, area)


def test_committed_public_anchor_preserves_privacy_and_frozen_boundaries():
    from pathlib import Path

    evidence = s.read_json(Path("docs/v0-14/evidence/v0.14-s3-real-shadow-prediction-seal-r2.json"))
    s.validate_public(evidence)
    assert evidence["scope"]["payload_hash"] == s.AREA_HASH
    assert evidence["models"]["private_artifact_bundle_hash"] == s.BUNDLE_HASH
    assert evidence["models"]["c0_artifact_hash"] == s.MODEL_HASHES["c0"]
    assert evidence["models"]["w1_artifact_hash"] == s.MODEL_HASHES["w1"]
    assert evidence["seal"]["real_issuance_count"] == 1
    assert evidence["custody"]["target_actual_artifact_access_count_preseal"] == 0
    assert evidence["custody"]["claims_external_world_has_no_actual"] is False
    assert evidence["seal"]["external_trusted_timestamp"] is False
    assert evidence["governance"]["v0_14_s4_authorized"] is False
    assert evidence["governance"]["production_use_approved"] is False
