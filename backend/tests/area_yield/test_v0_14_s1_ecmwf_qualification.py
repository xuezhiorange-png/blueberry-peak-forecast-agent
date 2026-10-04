"""Offline qualification tests: no coordinates, network or harvest data."""

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.run_v0_14_s1_ecmwf_qualification import (
    classify_surface,
    immutable,
    parse_index,
    validate_metadata,
    validate_pit,
    validate_public_boundary,
    verify_raw_manifest,
)

pytestmark = pytest.mark.contract


def metadata(parameter: str, step: int = 168) -> dict[str, object]:
    accum = parameter in {"tp", "ssrd"}
    return {
        "units": {"tp": "m", "ssrd": "J m**-2"}.get(parameter, "K"),
        "stepType": "accum" if accum else "instant",
        "startStep": 0 if accum else step,
        "endStep": step,
    }


@pytest.mark.parametrize("parameter", ["2t", "tp", "ssrd"])
def test_semantics(parameter: str) -> None:
    validate_metadata(parameter, 168, metadata(parameter))


@pytest.mark.parametrize(
    ("parameter", "key", "value"),
    [
        ("tp", "stepType", "instant"),
        ("ssrd", "stepType", "instant"),
        ("tp", "units", "kg m**-2"),
        ("2t", "units", "C"),
        ("tp", "startStep", 165),
        ("ssrd", "endStep", 169),
    ],
)
def test_semantic_mutations(parameter: str, key: str, value: object) -> None:
    m = metadata(parameter)
    m[key] = value
    with pytest.raises(ValueError):
        validate_metadata(parameter, 168, m)


def test_mn2t3_cannot_claim_six_hour_interval() -> None:
    with pytest.raises(ValueError):
        validate_metadata(
            "mn2t3", 168, {"units": "K", "stepType": "min", "startStep": 162, "endStep": 168}
        )


def test_complete_cycle_not_latest_cycle() -> None:
    assert (
        classify_surface(6, [24, 72, 144]) == "AVAILABLE_BUT_INCOMPLETE_FOR_V0_14_REQUIRED_SURFACE"
    )
    assert classify_surface(0, [24, 72, 168]) == "QUALIFIED_COMPLETE"
    assert classify_surface(12, [24, 72, 168, 360]) == "QUALIFIED_COMPLETE"
    with pytest.raises(ValueError):
        classify_surface(18, [24, 72, 168])


def test_optional_360_not_required() -> None:
    assert classify_surface(0, [24, 72, 168]) == "QUALIFIED_COMPLETE"


@pytest.mark.parametrize("offsets", [(1, 0, 0, 0), (0, -1, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0)])
def test_timestamp_mutations(offsets: tuple[int, ...]) -> None:
    now = datetime(2026, 10, 4, tzinfo=UTC)
    with pytest.raises(ValueError):
        validate_pit(*(now + timedelta(hours=h) for h in offsets))


def test_same_run_raw_conflict(tmp_path: Path) -> None:
    p = tmp_path / "field.grib2"
    immutable(p, b"synthetic-source")
    assert immutable(p, b"synthetic-source")
    with pytest.raises(ValueError, match="RAW_IDENTITY_CONFLICT"):
        immutable(p, b"changed")


def test_index_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        parse_index(
            b'{"class":"od","stream":"oper","type":"fc","step":"24","param":"tp","levtype":"sfc"}',
            "20261004000000",
            24,
        )


def public_boundary() -> dict[str, object]:
    keys = [
        "FUTURE_WEATHER_FEATURE_SCHEMA_FROZEN",
        "ENDPOINT_SNAPSHOTS_FORM_COMPLETE_FUTURE_WEATHER_WINDOW",
        "PRIVATE_HARVEST_ROW_READ",
        "TARGET_ACTUAL_READ",
        "MODEL_TRAINING_EXECUTED",
        "MODEL_PREDICTION_EXECUTED",
        "SCORING_EXECUTED",
        "BACKTEST_EXECUTED",
        "PROSPECTIVE_COHORT_ENTRY_CREATED",
        "PRODUCTION_USE_APPROVED",
        "V0_14_S2_AUTHORIZED",
        "V0_14_S3_AUTHORIZED",
        "V0_14_S4_AUTHORIZED",
        "V0_15_AUTHORIZED",
        "H15_PROVIDER_SURFACE_GUARANTEED",
    ]
    return {**dict.fromkeys(keys, False), "COMPLETE_RUN_REQUIRED_STEPS": [24, 72, 168]}


@pytest.mark.parametrize("key", list(public_boundary()))
def test_premature_claims_rejected(key: str) -> None:
    c = public_boundary()
    c[key] = [24, 72, 168, 360] if key == "COMPLETE_RUN_REQUIRED_STEPS" else True
    with pytest.raises(ValueError):
        validate_public_boundary(c)


@pytest.mark.parametrize(
    "key,value",
    [
        ("latitude", "1"),
        ("longitude", "2"),
        ("private_path", "/Users/operator/private"),
        ("actual_daily_kg", "1"),
    ],
)
def test_private_content_rejected(key: str, value: str) -> None:
    c = public_boundary()
    c["nested"] = {key: value}
    with pytest.raises(ValueError):
        validate_public_boundary(c)


def test_public_boundary_accepts_sanitized_contract() -> None:
    validate_public_boundary(public_boundary())


def test_audit_uses_day_listing_for_all_four_cycles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import run_v0_14_s1_ecmwf_qualification as module

    def fetch(url: str) -> bytes:
        if url == module.ROOT_URL:
            return b'<a href="/forecasts/20261003/">day</a>'
        if url.endswith("20261003/"):
            return "".join(
                f'<a href="/forecasts/20261003/{h}z/">cycle</a>' for h in ["00", "06", "12", "18"]
            ).encode()
        cycle = url.split("/")[5][:2]
        run = "20261003" + cycle + "0000"
        if url.endswith("oper/"):
            steps = [24, 72, 168] if cycle in {"00", "12"} else [24, 72, 144]
            return "".join(
                f'<a href="{run}-{step}h-oper-fc.index">step</a>' for step in steps
            ).encode()
        step = url.split("-")[1][:-1]
        return b"\n".join(
            json.dumps(
                {
                    "class": "od",
                    "stream": "oper",
                    "type": "fc",
                    "date": "20261003",
                    "time": cycle + "00",
                    "step": step,
                    "param": p,
                    "levtype": "sfc",
                    "_offset": 0,
                    "_length": 1,
                }
            ).encode()
            for p in module.CORE
        )

    monkeypatch.setattr(module, "request", fetch)
    runs = module.audit(tmp_path)
    assert len(runs) == 4
    assert sum(info["status"] == "QUALIFIED_COMPLETE" for info in runs.values()) == 2
    assert runs["20261003180000"]["listed_steps"] == [24, 72, 144]


def test_qualification_runner_has_no_harvest_or_model_execution() -> None:
    from scripts import run_v0_14_s1_ecmwf_qualification as module

    tree = ast.parse(Path(module.__file__).read_text())
    forbidden = {"fit", "predict", "score_predictions", "fit_ridge_artifact", "read_excel"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            assert name not in forbidden
        if isinstance(node, ast.ImportFrom):
            assert not any(
                s in (node.module or "")
                for s in (
                    "weather_aware_backtest",
                    "v013_feature_value_experiment",
                    "xlrd",
                    "pandas",
                )
            )


def test_step_zero_index_does_not_qualify_future_extrema() -> None:
    row = {
        "class": "od",
        "stream": "oper",
        "type": "fc",
        "date": "20261004",
        "time": "0000",
        "step": "3",
        "param": "mn2t3",
        "levtype": "sfc",
        "_offset": 0,
        "_length": 1,
    }
    assert parse_index(json.dumps(row).encode(), "20261004000000", 0) == {}


def test_raw_manifest_drift_fails_closed(tmp_path: Path) -> None:
    identity = immutable(tmp_path / "raw.index", b"synthetic")
    verify_raw_manifest(tmp_path, {"files": {"raw.index": identity}})
    with pytest.raises(ValueError):
        verify_raw_manifest(tmp_path, {"files": {"raw.index": "0" * 64}})


def test_raw_manifest_cannot_read_outside_private_weather_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="UNSAFE_RAW_MANIFEST_PATH"):
        verify_raw_manifest(tmp_path, {"files": {"../private-labels.xls": "0" * 64}})


def frozen_evidence() -> dict[str, object]:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs/v0-14/evidence/v0.14-s1-ecmwf-as-issued-surface-qualification-r1.json"
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_public_live_metadata_and_execution_boundary() -> None:
    c = frozen_evidence()
    validate_public_boundary(c)
    assert c["BASE_SHA"] == "d77d98f8a2e79bbd1089b7a61bf084d417063a5b"
    assert c["FUTURE_WEATHER_FEATURE_SCHEMA_FROZEN"] is False
    assert c["PRIVATE_HISTORICAL_WEATHER_ROW_READ"] is False
    assert c["PRODUCTION_PROVIDER_CODE_CHANGED"] is False
    assert c["BASE_CAPTURE_COUNT"] == c["BASE_GRID_BINDING_PASS_COUNT"] == 39
    assert c["SNAPSHOT_COUNT"] == 156
    assert c["COORDINATE_REFERENCE_SYSTEM"] == "NOT_ESTABLISHED"
    assert c["REPLAY_SCOPE"] == "SAME_PROVIDER_INSTANCE_IMMUTABLE_RAW_CACHE_SAME_FINAL_CUTOFF"
    assert c["REAL_SHADOW_FORECAST_COUNT"] == 0
    for key, field in c["GRIB_SEMANTIC_PROBES"].items():  # type: ignore[union-attr]
        step, parameter = key.split(":")
        validate_metadata(parameter, int(step), field["metadata"])
    validate_pit(
        *(
            datetime.fromisoformat(str(c[k]))
            for k in [
                "QUALIFICATION_CAPTURE_ISSUED_AT",
                "QUALIFICATION_CAPTURE_FETCHED_AT",
                "QUALIFICATION_CAPTURE_KNOWN_AT",
                "QUALIFICATION_CUTOFF",
            ]
        )
    )


def test_four_cycle_native_surface_and_optional_360_public_fixture() -> None:
    c = frozen_evidence()
    runs = c["OBSERVED_RUNS"]
    assert c["OBSERVED_RUN_COUNT"] == len(runs) == 13  # type: ignore[arg-type]
    assert sum(v["index_count"] for v in runs.values()) == c["INDEX_ARTIFACT_COUNT"] == 889  # type: ignore[union-attr]
    assert {v["cycle"] for v in runs.values()} == {"00", "06", "12", "18"}  # type: ignore[union-attr]
    assert c["OFFICIAL_00_12_STEP_SURFACE"] == list(range(0, 145, 3)) + list(range(150, 361, 6))
    assert c["OFFICIAL_06_18_STEP_SURFACE"] == list(range(0, 145, 3))
    assert c["H15_PROVIDER_SURFACE_GUARANTEED"] is False
    assert c["OPTIONAL_360_STATUS"] == "QUALIFIED_OPTIONAL"
    for value in runs.values():  # type: ignore[union-attr]
        assert value["status"] == classify_surface(int(value["cycle"]), value["listed_steps"])
        if value["cycle"] in {"06", "18"}:
            assert 168 not in value["listed_steps"]
            assert value["parameter_ranges"]["mn2t6"]["count"] == 0
