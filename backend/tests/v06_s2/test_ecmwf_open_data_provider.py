from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import backend.app.pit.ecmwf_open_data_provider as ecmwf
from backend.app.pit.shadow_forecast import WeatherForecastProviderError


@pytest.mark.unit
def test_ecmwf_grid_selection_is_deterministic_and_tie_breaks_down() -> None:
    assert ecmwf.select_nearest_grid_point(Decimal("25.124"), Decimal("99.124")) == (
        ecmwf.GridPoint(Decimal("25.00"), Decimal("99.00"))
    )
    assert ecmwf.select_nearest_grid_point(Decimal("25.125"), Decimal("99.125")) == (
        ecmwf.GridPoint(Decimal("25.00"), Decimal("99.00"))
    )
    assert ecmwf.select_nearest_grid_point(Decimal("25.126"), Decimal("99.126")) == (
        ecmwf.GridPoint(Decimal("25.25"), Decimal("99.25"))
    )


@pytest.mark.unit
def test_location_authority_loader_binds_file_hash_and_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": "BASE_REGISTRY_V1",
        "hash": "payload-hash",
        "bases": [
            {
                "base_id": "base_aaaaaaaaaaaaaaaaaaaaaaaa",
                "canonical_base_name": "Test Base",
                "latitude": "25.19",
                "longitude": "99.00",
                "coordinate_review_status": "RANGE_VALID_CRS_UNCONFIRMED",
                "coordinate_reference_system": "NOT_ESTABLISHED",
            }
        ],
    }
    path = tmp_path / "base-registry.json"
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    monkeypatch.setattr(ecmwf, "BASE_LOCATION_COUNT", 1)
    monkeypatch.setattr(ecmwf, "BASE_LOCATION_AUTHORITY_PAYLOAD_HASH", "payload-hash")
    locations = ecmwf.load_base_location_authority(
        path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assert locations["base_aaaaaaaaaaaaaaaaaaaaaaaa"].latitude == Decimal("25.19")


@pytest.mark.unit
def test_location_authority_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "base-registry.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(Exception, match="BASE_LOCATION_AUTHORITY_HASH_MISMATCH"):
        ecmwf.load_base_location_authority(path, expected_sha256="0" * 64)


class _FixtureResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> _FixtureResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _ECMWFFixtureTransport:
    """Small, deterministic transport for the provider's index/range contract."""

    def __init__(
        self,
        *,
        supported_runs: set[str],
        missing_steps: set[int] | None = None,
        missing_parameters: set[str] | None = None,
        malformed_steps: dict[int, bytes] | None = None,
        value_variant: str = "v1",
    ) -> None:
        self.supported_runs = supported_runs
        self.missing_steps = missing_steps or set()
        self.missing_parameters = missing_parameters or set()
        self.malformed_steps = malformed_steps or {}
        self.value_variant = value_variant
        self.calls: list[tuple[str, str | None]] = []
        self._entries: dict[tuple[str, int, int], str] = {}

    @staticmethod
    def _run_id(url: str) -> str:
        match = re.search(r"/forecasts/(\d{8})/(\d{2})z/", url)
        if match is None:
            raise AssertionError(f"unexpected ECMWF fixture URL: {url}")
        return f"{match.group(1)}{match.group(2)}0000"

    @staticmethod
    def _step(url: str) -> int:
        match = re.search(r"-(\d+)h-oper-fc\.(?:index|grib2)$", url)
        if match is None:
            raise AssertionError(f"unexpected ECMWF fixture step URL: {url}")
        return int(match.group(1))

    def _index(self, run_id: str, step: int) -> bytes:
        if step in self.malformed_steps:
            return self.malformed_steps[step]
        parameters = list(ecmwf.PARAMETERS)
        if step in {24, 72, 168}:
            parameters.extend(ecmwf.OPTIONAL_PARAMETERS)
        rows: list[dict[str, object]] = []
        for parameter_index, parameter in enumerate(parameters):
            if parameter in self.missing_parameters:
                continue
            offset = step * 10000 + parameter_index * 100
            length = 64
            self._entries[(run_id, step, offset)] = parameter
            rows.append(
                {
                    "step": str(step),
                    "param": parameter,
                    "levtype": "sfc",
                    "_offset": offset,
                    "_length": length,
                }
            )
        return (
            b"\n".join(
                json.dumps(row, separators=(",", ":"), sort_keys=True).encode("utf-8")
                for row in rows
            )
            + b"\n"
        )

    def __call__(self, request: Request, **_: object) -> _FixtureResponse:
        url = request.full_url
        run_id = self._run_id(url)
        range_header = request.get_header("Range")
        self.calls.append((url, range_header))
        if run_id not in self.supported_runs:
            raise HTTPError(url, 404, "fixture run unavailable", hdrs=None, fp=None)
        step = self._step(url)
        if step in self.missing_steps:
            raise HTTPError(url, 404, "fixture step unavailable", hdrs=None, fp=None)
        if url.endswith(".index"):
            return _FixtureResponse(200, self._index(run_id, step))
        if range_header is None:
            raise AssertionError("ECMWF fixture field request omitted Range")
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
        if match is None:
            raise AssertionError(f"unexpected Range header: {range_header}")
        start, end = (int(value) for value in match.groups())
        parameter = self._entries[(run_id, step, start)]
        token = f"fixture:{self.value_variant}:{run_id}:{step}:{parameter}".encode("ascii")
        body = token.ljust(end - start + 1, b"_")
        if len(body) != end - start + 1:
            raise AssertionError("fixture token unexpectedly exceeds field length")
        return _FixtureResponse(206, body)


def _fixture_decode(payload: bytes) -> ecmwf._DecodedField:
    token = payload.rstrip(b"_").decode("ascii")
    _, variant, _run_id, step_text, parameter = token.split(":")
    step = int(step_text)
    value_delta = 0.5 if variant == "v2" else 0.0
    values = {
        "2t": 298.15 + step / 100.0 + value_delta,
        "tp": 0.001 + step / 1_000_000.0 + value_delta / 1000.0,
        "ssrd": 100.0 + step + value_delta,
        "10u": 3.0 + value_delta,
        "10v": 4.0 + value_delta,
        "mn2t3": 295.15 + value_delta,
        "mx2t3": 300.15 + value_delta,
    }
    first_value = values[parameter]
    return ecmwf._DecodedField(
        values=[first_value, first_value + 1.0],
        latitudes=[25.0, 25.25],
        longitudes=[99.0, 99.25],
        ni=1,
        nj=2,
    )


def _fixture_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    base_count: int = 39,
    latitude: str = "25.125",
    longitude: str = "99.125",
    base_ids: list[str] | None = None,
    base_names: list[str] | None = None,
) -> tuple[Path, str, list[dict[str, str]]]:
    if base_ids is not None:
        base_count = len(base_ids)
    if base_names is not None and len(base_names) != base_count:
        raise ValueError("base_names must match fixture base count")
    bases = [
        {
            "base_id": (base_ids[index] if base_ids is not None else f"base_fixture_{index:02d}"),
            "canonical_base_name": (
                base_names[index] if base_names is not None else f"Fixture Base {index:02d}"
            ),
            "latitude": latitude,
            "longitude": longitude,
            "coordinate_review_status": "RANGE_VALID_CRS_UNCONFIRMED",
            "coordinate_reference_system": "NOT_ESTABLISHED",
        }
        for index in range(base_count)
    ]
    payload = {
        "version": "BASE_REGISTRY_V1",
        "hash": "fixture-location-payload-hash",
        "bases": bases,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    path = tmp_path / "fixture-base-registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    monkeypatch.setattr(ecmwf, "BASE_LOCATION_COUNT", base_count)
    monkeypatch.setattr(
        ecmwf,
        "BASE_LOCATION_AUTHORITY_PAYLOAD_HASH",
        "fixture-location-payload-hash",
    )
    return path, hashlib.sha256(raw).hexdigest(), bases


def _fixture_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    supported_runs: set[str],
    missing_steps: set[int] | None = None,
    missing_parameters: set[str] | None = None,
    malformed_steps: dict[int, bytes] | None = None,
    value_variant: str = "v1",
    latitude: str = "25.125",
    longitude: str = "99.125",
    base_ids: list[str] | None = None,
    base_names: list[str] | None = None,
) -> tuple[ecmwf.ECMWFOpenDataForecastProvider, _ECMWFFixtureTransport, list[dict[str, str]]]:
    authority_path, authority_sha, bases = _fixture_authority(
        tmp_path,
        monkeypatch,
        latitude=latitude,
        longitude=longitude,
        base_ids=base_ids,
        base_names=base_names,
    )
    transport = _ECMWFFixtureTransport(
        supported_runs=supported_runs,
        missing_steps=missing_steps,
        missing_parameters=missing_parameters,
        malformed_steps=malformed_steps,
        value_variant=value_variant,
    )
    provider = ecmwf.ECMWFOpenDataForecastProvider(
        location_authority_path=authority_path,
        location_authority_sha256=authority_sha,
        artifact_root=tmp_path / "raw-artifacts",
        urlopen=transport,
    )
    monkeypatch.setattr(provider, "_decode_grib", _fixture_decode)
    return provider, transport, bases


def _base_mapping(row: dict[str, str]) -> dict[str, str]:
    return {
        "base_id": row["base_id"],
        "canonical_base_name": row["canonical_base_name"],
    }


def _issued(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _freeze_fixture_fetch_time(
    provider: ecmwf.ECMWFOpenDataForecastProvider,
    run_id: str,
    forecast_created_at: datetime,
) -> None:
    cache = provider._load_run(_issued(run_id))
    provider._run_cache[run_id] = replace(
        cache,
        fetched_at=forecast_created_at - timedelta(seconds=1),
    )


def _capture_fixture(
    provider: ecmwf.ECMWFOpenDataForecastProvider,
    row: dict[str, str],
    *,
    run_id: str = "20260919000000",
    forecast_created_at: datetime = datetime(2026, 9, 19, 11, tzinfo=UTC),
) -> ecmwf.WeatherForecastCaptureResult:
    _freeze_fixture_fetch_time(provider, run_id, forecast_created_at)
    return provider.capture(
        base=_base_mapping(row),
        forecast_created_at=forecast_created_at,
        target_season="2026-2027",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cutoff", "supported_runs", "expected_run", "forbidden_run"),
    (
        (
            datetime(2026, 9, 19, 11, tzinfo=UTC),
            {"20260919000000", "20260918120000"},
            "20260919000000",
            "20260919120000",
        ),
        (
            datetime(2026, 9, 19, 11, tzinfo=UTC),
            {"20260918120000"},
            "20260918120000",
            "20260919120000",
        ),
    ),
)
def test_run_selection_excludes_future_and_uses_nearest_valid_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cutoff: datetime,
    supported_runs: set[str],
    expected_run: str,
    forbidden_run: str,
) -> None:
    provider, transport, _ = _fixture_provider(
        tmp_path,
        monkeypatch,
        supported_runs=supported_runs,
    )
    selected = provider._select_run(cutoff)
    assert selected.run_id == expected_run
    assert all(forbidden_run not in url for url, _ in transport.calls)
    assert selected.provider_identity.endswith(f"run={expected_run}")


@pytest.mark.unit
def test_all_candidate_runs_unavailable_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _, _ = _fixture_provider(tmp_path, monkeypatch, supported_runs=set())
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NO_QUALIFIED_RUN"):
        provider._select_run(datetime(2026, 9, 19, 11, tzinfo=UTC))


@pytest.mark.unit
def test_index_entry_selection_and_malformed_or_missing_fields_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"step": "24", "param": "2t", "levtype": "sfc", "_offset": 10, "_length": 32},
        {"step": "24", "param": "2t", "levtype": "pl", "_offset": 20, "_length": 32},
    ]
    entry = ecmwf._find_index(rows, 24, "2t")
    assert entry == ecmwf._FieldIndex(step=24, parameter="2t", offset=10, length=32)
    assert ecmwf._find_index(rows, 24, "tp") is None

    provider, _, _ = _fixture_provider(
        tmp_path / "malformed",
        monkeypatch,
        supported_runs={"20260919000000"},
        malformed_steps={24: b"not-json\n"},
    )
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_INDEX_INVALID"):
        provider._load_run(_issued("20260919000000"))

    provider, _, _ = _fixture_provider(
        tmp_path / "missing",
        monkeypatch,
        supported_runs={"20260919000000"},
        missing_parameters={"10v"},
    )
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_REQUIRED_PARAMETER_MISSING"):
        provider._load_run(_issued("20260919000000"))


@pytest.mark.unit
def test_provider_unit_normalization_and_quality_gates() -> None:
    assert ecmwf._temperature_celsius(273.15) == Decimal("0.000000")
    assert ecmwf._precipitation_mm(0.001) == Decimal("1.000000")
    assert ecmwf._solar_radiation(12.5) == Decimal("12.500000")
    assert ecmwf._wind_speed(3.0, 4.0) == Decimal("5.000000")
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NONFINITE_TEMPERATURE"):
        ecmwf._temperature_celsius(float("nan"))
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NONFINITE_PRECIPITATION"):
        ecmwf._precipitation_mm(float("inf"))
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NEGATIVE_PRECIPITATION"):
        ecmwf._precipitation_mm(-0.000001)
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NEGATIVE_SOLAR_RADIATION"):
        ecmwf._solar_radiation(-1.0)
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_NONFINITE_WIND"):
        ecmwf._wind_speed(float("inf"), 0.0)


@pytest.mark.unit
def test_fixture_horizons_are_actual_valid_times_and_missing_d15_is_not_fabricated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _, bases = _fixture_provider(
        tmp_path,
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    result = _capture_fixture(provider, bases[0])
    by_horizon = {snapshot.forecast_horizon_hours: snapshot for snapshot in result.snapshots}
    assert set(by_horizon) == {24, 72, 168, 360}
    issued_at = by_horizon[24].issued_at
    for horizon, snapshot in by_horizon.items():
        assert snapshot.valid_at == issued_at + timedelta(hours=horizon)
        assert snapshot.forecast_horizon_hours == horizon
        assert snapshot.fetched_at <= snapshot.known_at

    provider, _, bases = _fixture_provider(
        tmp_path / "without-d15",
        monkeypatch,
        supported_runs={"20260919000000"},
        missing_steps={360},
    )
    result = _capture_fixture(provider, bases[0])
    assert {snapshot.forecast_horizon_hours for snapshot in result.snapshots} == {24, 72, 168}


@pytest.mark.unit
def test_raw_artifact_conflict_and_manifest_hash_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "artifact.bin"
    digest = ecmwf._write_immutable(path, b"fixture-bytes")
    assert ecmwf._write_immutable(path, b"fixture-bytes") == digest
    with pytest.raises(WeatherForecastProviderError, match="ECMWF_RAW_ARTIFACT_CONFLICT"):
        ecmwf._write_immutable(path, b"changed-bytes")

    provider_one, _, _ = _fixture_provider(
        tmp_path / "one",
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    provider_two, _, _ = _fixture_provider(
        tmp_path / "two",
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    first = provider_one._load_run(_issued("20260919000000"))
    second = provider_two._load_run(_issued("20260919000000"))
    assert first.artifact_manifest_hash == second.artifact_manifest_hash
    assert first.index_hashes == second.index_hashes
    assert first.field_hashes == second.field_hashes


@pytest.mark.unit
def test_snapshot_raw_and_normalized_hashes_bind_run_base_grid_horizon_and_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _, bases = _fixture_provider(
        tmp_path / "same",
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    first = _capture_fixture(provider, bases[0]).snapshots[0]
    same = _capture_fixture(provider, bases[0]).snapshots[0]
    second_base = _capture_fixture(provider, bases[1]).snapshots[0]
    horizon_three = _capture_fixture(provider, bases[0]).snapshots[1]
    assert first.weather_snapshot_id == same.weather_snapshot_id
    assert first.raw_payload_hash == same.raw_payload_hash
    assert first.normalized_payload_hash == same.normalized_payload_hash
    assert first.weather_snapshot_id != second_base.weather_snapshot_id
    assert first.normalized_payload_hash != second_base.normalized_payload_hash
    assert first.weather_snapshot_id != horizon_three.weather_snapshot_id
    assert first.normalized_payload_hash != horizon_three.normalized_payload_hash
    assert first.base_id == bases[0]["base_id"]
    assert first.location_id == "ecmwf-ifs-25.00-99.00"

    grid_changed, _, grid_bases = _fixture_provider(
        tmp_path / "changed-grid",
        monkeypatch,
        supported_runs={"20260919000000"},
        latitude="25.126",
        longitude="99.126",
    )
    changed_grid_snapshot = _capture_fixture(grid_changed, grid_bases[0]).snapshots[0]
    assert changed_grid_snapshot.location_id == "ecmwf-ifs-25.25-99.25"
    assert changed_grid_snapshot.raw_payload_hash != first.raw_payload_hash
    assert changed_grid_snapshot.normalized_payload_hash != first.normalized_payload_hash

    changed, _, changed_bases = _fixture_provider(
        tmp_path / "changed-value",
        monkeypatch,
        supported_runs={"20260919000000"},
        value_variant="v2",
    )
    changed_snapshot = _capture_fixture(changed, changed_bases[0]).snapshots[0]
    assert changed_snapshot.weather_snapshot_id == first.weather_snapshot_id
    assert changed_snapshot.raw_payload_hash != first.raw_payload_hash
    assert changed_snapshot.normalized_payload_hash != first.normalized_payload_hash

    changed_run, _, changed_run_bases = _fixture_provider(
        tmp_path / "changed-run",
        monkeypatch,
        supported_runs={"20260918120000"},
    )
    changed_run_snapshot = _capture_fixture(
        changed_run,
        changed_run_bases[0],
        run_id="20260918120000",
    ).snapshots[0]
    assert changed_run_snapshot.weather_snapshot_id != first.weather_snapshot_id
    assert changed_run_snapshot.raw_payload_hash != first.raw_payload_hash
    assert changed_run_snapshot.normalized_payload_hash != first.normalized_payload_hash


@pytest.mark.unit
def test_ecmwf_fixture_capture_contract_and_pit_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_at = datetime(2026, 9, 19, 11, tzinfo=UTC)
    provider, _, bases = _fixture_provider(
        tmp_path,
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    result = _capture_fixture(provider, bases[0], forecast_created_at=created_at)
    assert result.status == "CAPTURED"
    assert result.provider is not None
    assert result.provider.startswith("ECMWF_IFS_OPEN_DATA|model=IFS|stream=oper|resolution=0p25")
    assert len(result.snapshots) == 4
    for snapshot in result.snapshots:
        assert snapshot.base_id == bases[0]["base_id"]
        assert snapshot.provider == result.provider
        assert snapshot.issued_at <= snapshot.fetched_at <= snapshot.known_at <= created_at
        assert snapshot.valid_at == snapshot.issued_at + timedelta(
            hours=snapshot.forecast_horizon_hours
        )
        assert snapshot.raw_payload_hash != snapshot.normalized_payload_hash


@pytest.mark.unit
def test_offline_39_base_capture_is_complete_and_deterministically_ordered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, transport, bases = _fixture_provider(
        tmp_path,
        monkeypatch,
        supported_runs={"20260919000000"},
    )
    created_at = datetime(2026, 9, 19, 11, tzinfo=UTC)
    _freeze_fixture_fetch_time(provider, "20260919000000", created_at)
    ordered_bases = sorted(bases, key=lambda row: row["base_id"])
    captures = [
        provider.capture(
            base=_base_mapping(row),
            forecast_created_at=created_at,
            target_season="2026-2027",
        )
        for row in ordered_bases
    ]
    assert len(ordered_bases) == 39
    assert all(capture.status == "CAPTURED" for capture in captures)
    assert all(capture.provider == captures[0].provider for capture in captures)
    assert all(len(capture.snapshots) == 4 for capture in captures)
    assert [capture.snapshots[0].base_id for capture in captures] == [
        row["base_id"] for row in ordered_bases
    ]
    first_call_count = len(transport.calls)
    replayed = provider.capture(
        base=_base_mapping(ordered_bases[0]),
        forecast_created_at=created_at,
        target_season="2026-2027",
    )
    assert len(transport.calls) == first_call_count
    assert replayed.snapshots == captures[0].snapshots
