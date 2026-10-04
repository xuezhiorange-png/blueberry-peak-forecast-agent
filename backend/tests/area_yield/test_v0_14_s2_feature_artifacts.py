"""Offline S2 tests: synthetic weather and labels only."""

import gzip
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield import v014_future_weather_features as f
from backend.app.area_yield.data import digest
from scripts import run_v0_14_s2_feature_artifacts as runner

pytestmark = pytest.mark.contract


def test_committed_public_evidence_matches_frozen_contract() -> None:
    evidence = runner.read(
        Path("docs/v0-14/evidence/v0.14-s2-future-weather-feature-and-artifact-freeze-r1.json")
    )
    f.validate_public_evidence(evidence)
    assert evidence["feature_policy"]["hash"] == digest(f.POLICY)
    assert evidence["feature_policy"]["feature_names"] == list(f.FEATURE_NAMES)
    assert evidence["authorities"]["s1_evidence_sha256"] == f.S1_SHA
    assert evidence["provider_extension"]["default_capture_behavior_changed"] is False
    assert (
        evidence["training_cohort"]["row_count"]
        + evidence["training_cohort"]["excluded_proxy_incomplete"]
        == runner.PARENT_COUNT
    )
    for field in (
        "historical_model_scoring_executed",
        "prospective_scoring_executed",
        "target_2026_2027_actual_read",
        "v0_14_s3_authorized",
        "production_use_approved",
    ):
        assert evidence["governance"][field] is False


def fields() -> dict[tuple[int, str], dict[str, object]]:
    result = {}
    for step, parameter in f.REQUIRED_FIELDS:
        accum = parameter in {"tp", "ssrd"}
        result[step, parameter] = {
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
    return result


def test_golden_dense_formula() -> None:
    values = f.aggregate_ifs(fields())
    assert list(values) == list(f.FEATURE_NAMES)
    assert list(values.values()) == [
        "10.000000000000",
        "168.000000000000",
        "16800.000000000000",
        "5.000000000000",
        "10.000000000000",
        "192.000000000000",
        "19200.000000000000",
        "5.000000000000",
    ]
    assert len(f.STEPS) == 84 and len(f.REQUIRED_FIELDS) == 256


@pytest.mark.parametrize(
    "parameter,step", [("2t", 3), ("10u", 144), ("10v", 150), ("tp", 360), ("ssrd", 360)]
)
def test_missing_field_fails_closed(parameter: str, step: int) -> None:
    data = fields()
    del data[step, parameter]
    with pytest.raises(ValueError):
        f.aggregate_ifs(data)


@pytest.mark.parametrize("parameter", ["2t", "tp", "ssrd", "10u", "10v"])
def test_wrong_unit_fails_closed(parameter: str) -> None:
    data = fields()
    data[next(k for k in data if k[1] == parameter)]["units"] = "wrong"
    with pytest.raises(ValueError):
        f.aggregate_ifs(data)


@pytest.mark.parametrize("parameter", ["tp", "ssrd"])
def test_cumulative_regression_fails_closed(parameter: str) -> None:
    data = fields()
    data[360, parameter]["value"] = "0"
    with pytest.raises(ValueError):
        f.aggregate_ifs(data)


@pytest.mark.parametrize("extra", [(0, "2t"), (168, "mn2t3"), (168, "gdd"), (1, "2t")])
def test_extra_fields_rejected(extra: tuple[int, str]) -> None:
    data = fields()
    data[extra] = data[3, "2t"]
    with pytest.raises(ValueError):
        f.aggregate_ifs(data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("feature_names", ["wrong"]),
        ("blocks", [[0, 24], [24, 360]]),
        ("native_steps", [0, 168, 360]),
        ("time_basis", "Asia/Shanghai"),
        ("interpolation", True),
        ("prorating", True),
        ("carry_forward", True),
        ("gdd", True),
        ("tmin_tmax", True),
        ("historical_layer", "BASE_WEATHER_DAILY_V1"),
        ("required_max_step", 168),
        ("alpha", "11"),
        ("model_family", "OTHER"),
        ("train_seasons", ["2025-2026"]),
        ("historical_scoring", True),
        ("target_2026_2027_actual_read", True),
    ],
)
def test_policy_mutations_rejected(key: str, value: object) -> None:
    policy = deepcopy(f.POLICY)
    policy[key] = value
    with pytest.raises(ValueError):
        f.validate_policy(policy)


def test_anchor_not_fake_pit() -> None:
    assert f.synthetic_anchor(datetime(2024, 1, 1, 16, tzinfo=UTC)) == datetime(
        2024, 1, 1, 12, tzinfo=UTC
    )
    assert f.synthetic_anchor(datetime(2024, 1, 1, 8, tzinfo=UTC)) == datetime(
        2024, 1, 1, 0, tzinfo=UTC
    )


def test_decimal_no_early_rounding() -> None:
    data = fields()
    for step in f.STEPS:
        data[step, "2t"]["value"] = "273.1500000000005"
    assert f.aggregate_ifs(data)[f.FEATURE_NAMES[0]] == "0.000000000000"


def test_native_duration_weights_and_nonoverlapping_blocks() -> None:
    data = fields()
    data[150, "2t"]["value"] = "451.15"
    data[174, "2t"]["value"] = "475.15"
    values = f.aggregate_ifs(data)
    assert values[f.FEATURE_NAMES[0]] == "16.000000000000"
    assert values[f.FEATURE_NAMES[4]] == "16.000000000000"


def test_tampered_artifact_and_pair_rejected() -> None:
    with pytest.raises(ValueError):
        f.verify_artifact({"artifact_hash": "wrong"})
    with pytest.raises(ValueError):
        f.verify_pair(
            {"training_row_key_hash": "a", "training_label_hash": "b"},
            {"training_row_key_hash": "c", "training_label_hash": "b"},
        )
    with pytest.raises(ValueError):
        f.verify_pair(
            {"training_row_key_hash": "a", "training_label_hash": "b"},
            {"training_row_key_hash": "a", "training_label_hash": "c"},
        )


def test_hourly_proxy_same_operator_without_redeaccumulation() -> None:
    hourly = {
        (s, p): Decimal({"t2m": "10", "u10": "3", "v10": "4"}[p])
        for s in f.STEPS
        for p in ("t2m", "u10", "v10")
    }
    hourly.update(
        {
            (s, p): Decimal("1" if p == "tp" else "100")
            for s in range(1, 361)
            for p in ("tp", "ssrd")
        }
    )
    assert f.aggregate_proxy(hourly) == f.aggregate_ifs(fields())
    del hourly[100, "tp"]
    with pytest.raises(ValueError, match="PROXY_SUPPORT_INCOMPLETE"):
        f.aggregate_proxy(hourly)


@pytest.mark.parametrize(
    "key,value",
    [
        ("historical_artifact_sha256", "0" * 64),
        ("feature_names", list(reversed(f.FEATURE_NAMES))),
        ("decimal_precision", 28),
        ("round_once", False),
        ("ssrd_mean_flux", True),
    ],
)
def test_additional_policy_mutations(key: str, value: object) -> None:
    policy = deepcopy(f.POLICY)
    policy[key] = value
    with pytest.raises(ValueError):
        f.validate_policy(policy)


@pytest.mark.parametrize(
    "payload",
    [
        {"features": {"base": "weather-value"}},
        {"coordinates": [1, 2]},
        {"coefficients": [1]},
        {"training_row_keys": ["key"]},
        {"nested": {"latitude": "25"}},
        {"path": "/Users/private/file"},
    ],
)
def test_private_public_disclosure_rejected(payload: object) -> None:
    with pytest.raises(ValueError):
        f.validate_public_evidence(payload)


@pytest.mark.parametrize("layer", [f.HOURLY_LAYER, "WRONG", "BASE_WEATHER_DAILY_V1"])
def test_hourly_authority_fails_closed(tmp_path: Path, layer: str) -> None:
    path = tmp_path / "hourly.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(
            json.dumps(
                {"processing_version": layer, "base_id": "unused", "native_variable": "unused"}
            ).encode()
            + b"\n"
        )
    with pytest.raises(ValueError):
        runner.load_hourly(
            path, set(), datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_bundle_tamper_rejected(tmp_path: Path) -> None:
    runner.write(tmp_path / "bundle-manifest.json", {"files": [], "bundle_hash": "wrong"})
    with pytest.raises(ValueError, match="BUNDLE_HASH_MISMATCH"):
        runner.verify_bundle(tmp_path)


def test_standardization_omission_not_legacy_compatible() -> None:
    artifact = {"prospective_role": "C0"}
    artifact["artifact_hash"] = digest(artifact)
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        f.verify_artifact(artifact)


def test_no_scoring_or_target_source_in_runner() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(runner))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls.intersection({"score_curve", "score_predictions", "predict", "backtest"})
    assert "source25" not in inspect.getsource(runner)
    assert "source26" not in inspect.getsource(runner)


@pytest.mark.parametrize("operation", ["historical_wape", "historical_peak_scoring"])
def test_scoring_invocation_rejected_before_any_input_access(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    monkeypatch.setattr("sys.argv", ["runner", operation, "--output", "unused"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_default_capture_is_exact_parent_method() -> None:
    assert f.ECMWFDenseFeatureSurfaceProvider.capture is f.ECMWFOpenDataForecastProvider.capture


@pytest.mark.parametrize(
    "issued", [datetime(2099, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 6, tzinfo=UTC)]
)
def test_dense_future_or_incomplete_cycle_rejected_before_network(issued: datetime) -> None:
    provider = object.__new__(f.ECMWFDenseFeatureSurfaceProvider)
    with pytest.raises(Exception, match="DENSE_RUN_IDENTITY_INVALID"):
        provider.capture_feature_surface(issued_at=issued)


@pytest.mark.parametrize("missing360", [False, True])
def test_dense_surface_raw_identity_and_cache_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing360: bool,
) -> None:
    from backend.tests.v06_s2.test_ecmwf_open_data_provider import (
        _ECMWFFixtureTransport,
        _fixture_authority,
        _fixture_decode,
    )

    class DenseTransport(_ECMWFFixtureTransport):
        def _index(self, run_id: str, step: int) -> bytes:
            raw = super()._index(run_id, step)
            enriched = []
            for line in raw.splitlines():
                row = json.loads(line)
                row.update(
                    {
                        "class": "od",
                        "stream": "oper",
                        "type": "fc",
                        "date": run_id[:8],
                        "time": run_id[8:12],
                    }
                )
                enriched.append(json.dumps(row).encode())
            return b"\n".join(enriched) + b"\n"

    authority, authority_sha, _ = _fixture_authority(tmp_path, monkeypatch)
    run = datetime(2024, 1, 1, tzinfo=UTC)
    transport = DenseTransport(
        supported_runs={"20240101000000"}, missing_steps={360} if missing360 else set()
    )
    provider = f.ECMWFDenseFeatureSurfaceProvider(
        location_authority_path=authority,
        location_authority_sha256=authority_sha,
        artifact_root=tmp_path / "raw",
        urlopen=transport,
    )
    monkeypatch.setattr(provider, "_decode_grib", _fixture_decode)

    def metadata(payload: bytes) -> dict[str, object]:
        _, _, _, step_text, parameter = payload.rstrip(b"_").decode().split(":")
        step = int(step_text)
        valid = run + timedelta(hours=step)
        return {
            **fields()[step, parameter],
            "shortName": parameter,
            "dataDate": 20240101,
            "dataTime": 0,
            "validityDate": int(valid.strftime("%Y%m%d")),
            "validityTime": valid.hour * 100,
        }

    monkeypatch.setattr(provider, "_feature_surface_metadata", metadata)
    if missing360:
        with pytest.raises(f.WeatherForecastProviderError):
            provider.capture_feature_surface(issued_at=run)
        return
    first = provider.capture_feature_surface(issued_at=run)
    calls = len(transport.calls)
    second = provider.capture_feature_surface(issued_at=run)
    assert first == second and len(transport.calls) == calls
    assert len(first["raw_manifest"]["files"]) == 84 + 256
    assert len(first["fields_by_base"]) == 39
    assert all(len(rows) == 256 for rows in first["fields_by_base"].values())


def test_fresh_json_synthetic_request_prediction_parity(tmp_path: Path) -> None:
    from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

    artifact = {
        "prospective_role": "C0",
        "schema": "V0_14_C0_RIDGE_ARTIFACT_V1",
        "model_id": runner.MODELS["c0"],
        "feature_names": list(BASE_FEATURES),
        "alpha": "10.000000",
        "solver": "numpy.linalg.solve",
        "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
        "zero_std_policy": "SCALE_1",
        "intercept_unpenalized": True,
        "nonnegative_output_clip": True,
        "production_approved": False,
        "feature_policy_hash": digest(f.POLICY),
        "feature_means": ["0"] * 10,
        "feature_scales": ["1"] * 10,
        "coefficients": ["1"] * 10,
        "intercept": "2",
    }
    artifact["artifact_hash"] = digest(artifact)
    path = tmp_path / "artifact.json"
    runner.write(path, artifact)
    assert f.synthetic_request_check(artifact) == "57.000000000000"
    assert f.synthetic_request_check(runner.read(path)) == f.synthetic_request_check(artifact)
