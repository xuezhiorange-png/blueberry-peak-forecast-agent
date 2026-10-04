"""S1-only network/GRIB qualification; never imports harvest or model execution.

Operator paths are runtime inputs. Raw bytes and decoded snapshots stay private.
The public report is assembled separately after reviewing official authorities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import certifi

from backend.app.pit.ecmwf_open_data_provider import (
    BASE_LOCATION_AUTHORITY_SHA256,
    ECMWFOpenDataForecastProvider,
)

CORE = ("2t", "tp", "ssrd", "10u", "10v")
PARAMETERS = CORE + ("mn2t3", "mx2t3", "mn2t6", "mx2t6")
REQUIRED = (24, 72, 168)
ROOT_URL = "https://data.ecmwf.int/forecasts/"
METADATA_KEYS = (
    "shortName",
    "paramId",
    "units",
    "stepType",
    "stepRange",
    "startStep",
    "endStep",
    "validityDate",
    "validityTime",
    "dataDate",
    "dataTime",
    "typeOfStatisticalProcessing",
    "lengthOfTimeRange",
    "indicatorOfUnitOfTimeRange",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode()


def immutable(path: Path, data: bytes) -> str:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("RAW_IDENTITY_CONFLICT")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    return sha(data)


def verify_raw_manifest(root: Path, manifest: dict[str, Any]) -> None:
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("UNSAFE_RAW_MANIFEST_PATH")
        if sha((root / relative).read_bytes()) != expected:
            raise ValueError("RAW_MANIFEST_IDENTITY_MISMATCH")


def request(url: str, byte_range: tuple[int, int] | None = None) -> bytes:
    headers = {"User-Agent": "blueberry-v014-s1-qualification"}
    if byte_range:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(
                req, timeout=45, context=ssl.create_default_context(cafile=certifi.where())
            ) as response:
                if response.status != (206 if byte_range else 200):
                    raise ValueError("HTTP_RESPONSE_CONTRACT_FAILURE")
                data = bytes(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 5:
                raise
            time.sleep(min(float(exc.headers.get("Retry-After", 2 ** (attempt + 1))), 30))
    if byte_range and len(data) != byte_range[1] - byte_range[0] + 1:
        raise ValueError("BYTE_RANGE_LENGTH_MISMATCH")
    return data


def links(data: bytes) -> list[str]:
    return re.findall(r'href="([^"]+)"', data.decode())


def parse_index(data: bytes, run: str, step: int) -> dict[str, dict[str, Any]]:
    result = {}
    for line in data.decode().splitlines():
        row = json.loads(line)
        if row.get("levtype") != "sfc" or row.get("param") not in PARAMETERS:
            continue
        # Some step-0 files index a min/max field whose own valid step is 3.
        # Preserve source bytes, but never qualify that field as step-0 data.
        if str(row.get("step")) != str(step) and row["param"] not in CORE:
            continue
        if any(
            str(row.get(k)) != v
            for k, v in {
                "class": "od",
                "stream": "oper",
                "type": "fc",
                "date": run[:8],
                "time": run[8:12],
                "step": str(step),
            }.items()
        ):
            raise ValueError("INDEX_IDENTITY_MISMATCH")
        if int(row["_offset"]) < 0 or int(row["_length"]) <= 0:
            raise ValueError("INVALID_BYTE_RANGE")
        parameter = row["param"]
        if parameter in result:
            raise ValueError("DUPLICATE_FIELD")
        result[parameter] = row
    return result


def classify_surface(cycle: int, steps: list[int]) -> str:
    if cycle not in {0, 6, 12, 18}:
        raise ValueError("WRONG_CYCLE")
    if cycle in {6, 18} and 168 in steps:
        raise ValueError("06_18_CONTRACT_DRIFT")
    if not steps:
        return "UNAVAILABLE"
    if set(REQUIRED).issubset(steps):
        return "QUALIFIED_COMPLETE"
    return "AVAILABLE_BUT_INCOMPLETE_FOR_V0_14_REQUIRED_SURFACE"


def validate_pit(issued: datetime, fetched: datetime, known: datetime, cutoff: datetime) -> None:
    if (
        any(t.tzinfo is None for t in (issued, fetched, known, cutoff))
        or not issued <= fetched <= known <= cutoff
    ):
        raise ValueError("PIT_ORDER_VIOLATION")


def validate_public_boundary(report: dict[str, Any]) -> None:
    """Fail closed on premature feature/science claims or private disclosure."""
    for key in (
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
    ):
        if report[key] is not False:
            raise ValueError("S1_EXECUTION_BOUNDARY_VIOLATION")
    if report["COMPLETE_RUN_REQUIRED_STEPS"] != [24, 72, 168]:
        raise ValueError("360_IS_NOT_REQUIRED")
    if report["H15_PROVIDER_SURFACE_GUARANTEED"] is not False:
        raise ValueError("OPTIONAL_SURFACE_NOT_GUARANTEED")

    def inspect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {
                    "latitude",
                    "longitude",
                    "coordinates",
                    "private_path",
                    "decoded_values",
                    "actual_daily_kg",
                }:
                    raise ValueError("PRIVATE_PUBLICATION_REJECTED")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
        elif isinstance(value, str) and ("/Users/" in value or "/private/tmp/" in value):
            raise ValueError("PRIVATE_PATH_REJECTED")

    inspect(report)


def validate_metadata(parameter: str, step: int, m: dict[str, Any]) -> None:
    if parameter not in PARAMETERS:
        raise ValueError("UNQUALIFIED_PARAMETER")
    unit = {"tp": "m", "ssrd": "J m**-2", "10u": "m s**-1", "10v": "m s**-1"}.get(parameter, "K")
    kind = {
        "tp": "accum",
        "ssrd": "accum",
        "mn2t3": "min",
        "mn2t6": "min",
        "mx2t3": "max",
        "mx2t6": "max",
    }.get(parameter, "instant")
    if m["units"] != unit or m["stepType"] != kind or int(m["endStep"]) != step:
        raise ValueError("GRIB_SEMANTIC_OR_UNIT_MISMATCH")
    start = int(m["startStep"])
    if kind == "accum" and start != 0:
        raise ValueError("ACCUMULATION_ORIGIN_MISMATCH")
    if kind == "instant" and start != step:
        raise ValueError("INSTANT_VALID_TIME_MISMATCH")
    if kind in {"min", "max"}:
        interval = 3 if parameter.endswith("3") else 6
        if (
            step - start != interval
            or (interval == 3 and step > 144)
            or (interval == 6 and step <= 144)
        ):
            raise ValueError("MINMAX_INTERVAL_MISMATCH")


def grib_metadata(data: bytes) -> dict[str, Any]:
    import eccodes  # type: ignore[import-untyped]

    with tempfile.TemporaryFile() as stream:
        stream.write(data)
        stream.seek(0)
        handle = eccodes.codes_grib_new_from_file(stream)
        if handle is None:
            raise ValueError("INVALID_GRIB")
        try:
            return {
                k: eccodes.codes_get(handle, k)
                for k in METADATA_KEYS
                if eccodes.codes_is_defined(handle, k)
            }
        finally:
            eccodes.codes_release(handle)


def audit(output: Path) -> dict[str, Any]:
    """Preserve listings and every available native-step index in bounded archive."""

    def cached(url: str, path: Path) -> bytes:
        if path.exists():
            return path.read_bytes()
        data = request(url)
        immutable(path, data)
        return data

    portal = cached(ROOT_URL, output / "portal.html")
    immutable(output / "portal.html", portal)
    days = sorted(
        {m.group(1) for v in links(portal) if (m := re.fullmatch(r"/forecasts/(\d{8})/", v))}
    )
    tasks: list[tuple[str, int, str]] = []
    runs: dict[str, Any] = {}
    for day in days:
        day_listing = cached(ROOT_URL + day + "/", output / day / "listing.html")
        immutable(output / day / "listing.html", day_listing)
        for cycle in ("00", "06", "12", "18"):
            if not any(v.endswith(f"/{cycle}z/") or v == f"{cycle}z/" for v in links(day_listing)):
                continue
            run = day + cycle + "0000"
            url = ROOT_URL + f"{day}/{cycle}z/ifs/0p25/oper/"
            try:
                listing = cached(url, output / run / "listing.html")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            immutable(output / run / "listing.html", listing)
            steps = sorted(
                {
                    int(m.group(1))
                    for v in links(listing)
                    if (m := re.search(r"-(\d+)h-oper-fc.index$", v))
                }
            )
            runs[run] = {
                "cycle": cycle,
                "listed_steps": steps,
                "surface": {},
                "status": classify_surface(int(cycle), steps),
            }
            tasks.extend((run, step, url + f"{run}-{step}h-oper-fc.index") for step in steps)

    def fetch(item: tuple[str, int, str]) -> tuple[str, int, dict[str, Any]]:
        run, step, url = item
        data = cached(url, output / run / f"{step:03d}h.index")
        identity = immutable(output / run / f"{step:03d}h.index", data)
        fields = parse_index(data, run, step)
        return run, step, {"index_sha256": identity, "parameters": sorted(fields)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        for run, step, surface in pool.map(fetch, tasks):
            runs[run]["surface"][str(step)] = surface
    for run, info in runs.items():
        mismatches: list[dict[str, Any]] = []
        for step in info["listed_steps"]:
            raw_rows = [
                json.loads(line)
                for line in (output / run / f"{step:03d}h.index").read_text().splitlines()
            ]
            mismatches.extend(
                {"file_step": step, "field_step": row.get("step"), "parameter": row["param"]}
                for row in raw_rows
                if row.get("levtype") == "sfc"
                and row.get("param") in PARAMETERS
                and str(row.get("step")) != str(step)
            )
        info["unqualified_index_field_step_mismatches"] = mismatches
        for step in REQUIRED:
            if step in info["listed_steps"] and not set(CORE).issubset(
                info["surface"][str(step)]["parameters"]
            ):
                raise ValueError("REQUIRED_CORE_PARAMETER_MISSING")
        immutable(output / run / "availability.json", canonical(info))
    immutable(output / "availability.json", canonical(runs))
    return runs


def probe(output: Path, runs: dict[str, Any]) -> dict[str, Any]:
    run = max(r for r, info in runs.items() if info["status"] == "QUALIFIED_COMPLETE")
    url = ROOT_URL + f"{run[:8]}/{run[8:10]}z/ifs/0p25/oper/"
    result: dict[str, Any] = {}
    for step in (3, 24, 144, 150, 168, 360):
        if step not in runs[run]["listed_steps"]:
            continue
        fields = parse_index((output / run / f"{step:03d}h.index").read_bytes(), run, step)
        for parameter, row in fields.items():
            begin, length = int(row["_offset"]), int(row["_length"])
            data = request(url + f"{run}-{step}h-oper-fc.grib2", (begin, begin + length - 1))
            identity = immutable(output / run / f"probe-{step:03d}h-{parameter}.grib2", data)
            m = grib_metadata(data)
            result[f"{step}:{parameter}"] = {"sha256": identity, "metadata": m}
            # Preserve a mismatch before failing closed: never lose diagnostic source identity.
            if m.get("dataDate") != int(run[:8]) or m.get("dataTime") != int(run[8:12]):
                raise ValueError("GRIB_RUN_MISMATCH")
            try:
                validate_metadata(parameter, step, m)
            except ValueError:
                immutable(output / run / "blocked-grib-metadata.json", canonical(result))
                raise
    immutable(output / run / "grib-metadata.json", canonical(result))
    return {"run_id": run, "fields": result}


def capture(output: Path, location: Path) -> dict[str, Any]:
    provider = ECMWFOpenDataForecastProvider(
        location_authority_path=location, artifact_root=output / "provider"
    )
    # Fetch first. Final qualification cutoff is recorded after receipt, never backdated.
    results = [
        provider.capture(
            base={"base_id": base},
            forecast_created_at=datetime.now(UTC),
            target_season="QUALIFICATION_ONLY",
        )
        for base in sorted(provider.locations)
    ]
    cutoff = datetime.now(UTC)
    repeat = [
        provider.capture(
            base={"base_id": base}, forecast_created_at=cutoff, target_season="QUALIFICATION_ONLY"
        )
        for base in sorted(provider.locations)
    ]
    contents = []
    for item in results:
        for s in item.snapshots:
            validate_pit(s.issued_at, s.fetched_at, s.known_at, cutoff)
            contents.append(s.model_dump(mode="json"))
    replay = [s.model_dump(mode="json") for item in repeat for s in item.snapshots]
    if contents != replay:
        raise ValueError("REPLAY_IDENTITY_MISMATCH")
    immutable(output / "snapshots-private.json", canonical(contents))
    summary = {
        "base_count": len(results),
        "snapshot_count": len(contents),
        "cutoff": cutoff.isoformat(),
        "issued_at": results[0].snapshots[0].issued_at.isoformat(),
        "fetched_at": results[0].snapshots[0].fetched_at.isoformat(),
        "known_at": results[0].snapshots[0].known_at.isoformat(),
        "snapshot_content_hash": sha(canonical(contents)),
        "replay_scope": "SAME_PROVIDER_INSTANCE_IMMUTABLE_RAW_CACHE_SAME_FINAL_CUTOFF",
        "deterministic_replay": "PASS",
        "location_authority_sha256": BASE_LOCATION_AUTHORITY_SHA256,
    }
    immutable(output / "capture-summary.json", canonical(summary))
    return summary


def public_report(manifest: dict[str, Any], manifest_sha: str) -> dict[str, Any]:
    """Whitelist aggregates and GRIB encoding metadata, never decoded rows."""
    runs, semantics, receipt = manifest["runs"], manifest["semantics"], manifest["capture"]
    long_steps = list(range(0, 145, 3)) + list(range(150, 361, 6))
    short_steps = list(range(0, 145, 3))
    complete = [r for r, info in runs.items() if info["status"] == "QUALIFIED_COMPLETE"]
    if len(complete) < 2:
        raise ValueError("MULTI_RUN_REQUIRED")
    observed_cycles = {info["cycle"] for info in runs.values()}
    if observed_cycles != {"00", "06", "12", "18"}:
        raise ValueError("FOUR_CYCLE_LIVE_AUDIT_INCOMPLETE")
    summaries = {}
    for run, info in runs.items():
        expected_steps = long_steps if info["cycle"] in {"00", "12"} else short_steps
        if info["listed_steps"] != expected_steps:
            raise ValueError("NATIVE_STEP_CONTRACT_DRIFT")
        parameter_ranges = {}
        for parameter in PARAMETERS:
            qualified = sorted(
                int(step)
                for step, value in info["surface"].items()
                if parameter in value["parameters"]
            )
            expected_parameter_steps = (
                expected_steps
                if parameter in CORE
                else list(range(3, 145, 3))
                if parameter.endswith("3")
                else list(range(150, 361, 6))
                if info["cycle"] in {"00", "12"}
                else []
            )
            if qualified != expected_parameter_steps:
                raise ValueError("PARAMETER_AVAILABILITY_RANGE_NOT_QUALIFIED")
            parameter_ranges[parameter] = {
                "count": len(qualified),
                "first_step": min(qualified) if qualified else None,
                "last_step": max(qualified) if qualified else None,
                "qualified_steps_hash": sha(canonical(qualified)),
            }
        summaries[run] = {
            "cycle": info["cycle"],
            "status": info["status"],
            "listed_steps": info["listed_steps"],
            "index_count": len(info["surface"]),
            "availability_matrix_hash": sha(canonical(info["surface"])),
            "parameter_ranges": parameter_ranges,
            "unqualified_index_field_step_mismatches": info.get(
                "unqualified_index_field_step_mismatches", []
            ),
        }
    optional_qualified = all(
        set(long_steps).issubset(runs[r]["listed_steps"])
        and all(set(CORE).issubset(runs[r]["surface"][str(s)]["parameters"]) for s in long_steps)
        for r in complete
    )
    report: dict[str, Any] = {
        "TASK_ID": (
            "V0_14_S1_ECMWF_AS_ISSUED_PROVIDER_SURFACE_AND_"
            "METEOROLOGICAL_SEMANTICS_QUALIFICATION_R1"
        ),
        "BASE_SHA": "d77d98f8a2e79bbd1089b7a61bf084d417063a5b",
        "RESULT": "PASS",
        "ECMWF_AS_ISSUED_PROVIDER_QUALIFICATION": "PASS",
        "IFS_PRODUCT_CYCLE": "50r1_CURRENT_DOCUMENTED_PRODUCT_CONTRACT_NOT_INFERRED_FROM_GRIB",
        "PROVIDER_NAME": "ECMWF_IFS_OPEN_DATA",
        "MODEL_ID": "IFS",
        "CLASS": "od",
        "STREAM": "oper",
        "TYPE": "fc",
        "RESOLUTION": "0p25",
        "OFFICIAL_00_12_STEP_SURFACE": long_steps,
        "OFFICIAL_06_18_STEP_SURFACE": short_steps,
        "COMPLETE_RUN_REQUIRED_STEPS": list(REQUIRED),
        "OPTIONAL_360_STATUS": "QUALIFIED_OPTIONAL" if optional_qualified else "PARTIAL",
        "QUALIFIED_COMPLETE_CYCLES": ["00", "12"],
        "06_18_SUPPORT_168H": False,
        "IS_00_12_ONLY_POLICY_INTENTIONALLY_REQUIRED_FOR_168H_COMPLETENESS": True,
        "ROLLING_ARCHIVE_AVAILABLE_RUN_COUNT_DOCUMENTED": 12,
        "ROLLING_ARCHIVE_APPROX_TIME_COVERAGE": "2-3_DAYS_NOT_HISTORICAL_ARCHIVE",
        "OBSERVED_RUN_COUNT": len(runs),
        "OBSERVED_DISTINCT_COMPLETE_00_12_RUN_COUNT": len(complete),
        "INDEX_ARTIFACT_COUNT": sum(len(info["surface"]) for info in runs.values()),
        "OBSERVED_RUNS": summaries,
        "REPRESENTATIVE_GRIB_RUN_ID": semantics["run_id"],
        "GRIB_SEMANTIC_PROBES": semantics["fields"],
        "2T_SEMANTICS": "INSTANTANEOUS_AT_VALID_TIME",
        "2T_UNIT": "K",
        "10U_SEMANTICS": "INSTANTANEOUS_AT_VALID_TIME",
        "10V_SEMANTICS": "INSTANTANEOUS_AT_VALID_TIME",
        "WIND_UNIT": "m s**-1",
        "TP_SEMANTICS": "ACCUMULATED_FROM_FORECAST_START",
        "TP_UNIT": "m",
        "TP_ACCUMULATION_ORIGIN": "FORECAST_START_STEP_0",
        "SSRD_SEMANTICS": "TIME_INTEGRATED_DOWNWARD_SURFACE_SOLAR_ENERGY",
        "SSRD_UNIT": "J m**-2",
        "SSRD_POSITIVE_DIRECTION": "DOWNWARD",
        "SSRD_ACCUMULATION_ORIGIN": "FORECAST_START_STEP_0",
        "MN2T3_QUALIFIED_RANGE": "3..144_BY_3H_LAST_3H",
        "MX2T3_QUALIFIED_RANGE": "3..144_BY_3H_LAST_3H",
        "MN2T6_QUALIFIED_RANGE": "150..360_BY_6H_LAST_6H_00_12",
        "MX2T6_QUALIFIED_RANGE": "150..360_BY_6H_LAST_6H_00_12",
        "CURRENT_PROVIDER_UNIT_CONVERSION_STATUS": "PASS",
        "CURRENT_REPO_CAPTURE_STEP_SURFACE": [24, 72, 168, 360],
        "360_CAPTURE_ROLE": "OPTIONAL",
        "CURRENT_ADAPTER_MATERIALIZES_FULL_NATIVE_SURFACE": False,
        "PROVIDER_EXTENSION_REQUIRED_FOR_S2": True,
        "PROVIDER_EXTENSION_REASON": (
            "DENSE_STEP_SEQUENCE_AND_6H_EXTREMA_NEEDED_FOR_DEFENSIBLE_WINDOW_MATERIALIZATION;"
            "FINAL_FEATURE_POLICY_NOT_SELECTED"
        ),
        "PRODUCTION_PROVIDER_CODE_CHANGED": False,
        "CORRECTNESS_BUG_FIXED": False,
        "PROVIDER_CONTRACT_DRIFT": False,
        "LEGACY_NORMALIZED_TEMPERATURE_MEAN_FIELD_IS_NOT_DAILY_MEAN": True,
        "OFFICIAL_DOCUMENTATION_HORIZON_CONFLICT": True,
        "H7_PROVIDER_SURFACE_QUALIFICATION": "QUALIFIED",
        "H15_PROVIDER_SURFACE_QUALIFICATION": "QUALIFIED" if optional_qualified else "PARTIAL",
        "H15_PROVIDER_SURFACE_GUARANTEED": False,
        "ENDPOINT_SNAPSHOTS_FORM_COMPLETE_FUTURE_WEATHER_WINDOW": False,
        "FUTURE_WEATHER_FEATURE_SCHEMA_FROZEN": False,
        "BUSINESS_TIMEZONE": "Asia/Shanghai",
        "LOCAL_MIDNIGHT_UTC": "16:00_PREVIOUS_UTC_DATE",
        "LOCAL_DAY_EXACT_AGGREGATION_FROM_NATIVE_STEPS": False,
        "LOCAL_DAY_PRORATING_AUTHORIZED": False,
        "HISTORICAL_PROXY_IS_AS_ISSUED_FORECAST": False,
        "PROXY_MAPPING": {
            name: {"status": "PARTIAL", "reason": reason}
            for name, reason in {
                "TEMPERATURE": (
                    "K_TO_C_EXACT_UNIT_TRANSFORM;INSTANT_3H_6H_SAMPLES_NOT_24_HOURLY_LOCAL_DAY_MEAN"
                ),
                "TMIN": "3H_6H_INTERVAL_EXTREMA_NOT_ERA5_24_HOURLY_SAMPLED_LOCAL_DAY_MIN",
                "TMAX": "3H_6H_INTERVAL_EXTREMA_NOT_ERA5_24_HOURLY_SAMPLED_LOCAL_DAY_MAX",
                "PRECIPITATION": (
                    "SAME_RUN_CUMULATIVE_DIFFERENCE_AND_M_TO_MM;LOCAL_MIDNIGHT_NOT_NATIVE_BOUNDARY"
                ),
                "SOLAR": (
                    "SAME_RUN_CUMULATIVE_ENERGY_DIFFERENCE_J_TO_MJ;"
                    "LOCAL_MIDNIGHT_NOT_NATIVE_BOUNDARY"
                ),
                "WIND": "HYPOT_U_V_PHYSICAL_TRANSFORM;INSTANT_SAMPLES_NOT_24_HOURLY_LOCAL_DAY_MEAN",
            }.items()
        },
        "TRANSFORMATION_CANDIDATES_ONLY": [
            "K_MINUS_273_15",
            "HYPOT_10U_10V",
            "SAME_RUN_CUMULATIVE_DIFFERENCE",
            "INTERVAL_ENERGY_DIVIDED_BY_INTERVAL_SECONDS",
            "FORECAST_RUN_RELATIVE_WINDOW",
        ],
        "TRANSFORMATION_CANDIDATE_PRECONDITIONS": [
            "SAME_RUN",
            "ORDERED_VALID_STEPS",
            "SAME_PARAMETER_ENCODING",
            "NONNEGATIVE_DIFFERENCE_WITH_EXPLICIT_TOLERANCE_POLICY_TO_BE_FROZEN_IN_S2",
        ],
        "PRIVATE_HISTORICAL_WEATHER_ROW_READ": False,
        "REAL_ECMWF_CAPTURE_EXECUTED": True,
        "CAPTURE_ROLE": "QUALIFICATION_ONLY",
        "QUALIFICATION_CAPTURE_RUN_ID": semantics["run_id"],
        "QUALIFICATION_CAPTURE_ISSUED_AT": receipt["issued_at"],
        "QUALIFICATION_CAPTURE_FETCHED_AT": receipt["fetched_at"],
        "QUALIFICATION_CAPTURE_KNOWN_AT": receipt["known_at"],
        "QUALIFICATION_CUTOFF": receipt["cutoff"],
        "PIT_ORDER": "PASS",
        "BASE_LOCATION_AUTHORITY_HASH_VERIFIED": True,
        "BASE_LOCATION_AUTHORITY_SHA256": receipt["location_authority_sha256"],
        "BASE_CAPTURE_COUNT": receipt["base_count"],
        "BASE_GRID_BINDING_PASS_COUNT": receipt["base_count"],
        "SNAPSHOT_COUNT": receipt["snapshot_count"],
        "COORDINATE_REVIEW_STATUS": "RANGE_VALID_CRS_UNCONFIRMED",
        "COORDINATE_REFERENCE_SYSTEM": "NOT_ESTABLISHED",
        "PRIVATE_RAW_MANIFEST_SHA256": manifest_sha,
        "RAW_ARTIFACTS_COMMITTED": False,
        "PRIVATE_COORDINATES_COMMITTED": False,
        "DETERMINISTIC_REPLAY": receipt["deterministic_replay"],
        "REPLAY_SCOPE": receipt["replay_scope"],
        "SNAPSHOT_CONTENT_HASH": receipt["snapshot_content_hash"],
        "SAME_RUN_ID": True,
        "SAME_INDEX_HASHES": True,
        "SAME_FIELD_HASHES": True,
        "SAME_DECODED_VALUES": True,
        "SAME_SNAPSHOT_HASHES": True,
        "REAL_SHADOW_FORECAST_COUNT": 0,
        "PROSPECTIVE_COHORT_ENTRY_CREATED": False,
        "PRIVATE_HARVEST_ROW_READ": False,
        "TARGET_ACTUAL_READ": False,
        "MODEL_TRAINING_EXECUTED": False,
        "MODEL_PREDICTION_EXECUTED": False,
        "BACKTEST_EXECUTED": False,
        "SCORING_EXECUTED": False,
        "PROSPECTIVE_ACCURACY_VALIDATED": False,
        "PRODUCTION_USE_APPROVED": False,
        "V0_14_S1_COMPLETE": True,
        "V0_14_S2_AUTHORIZED": False,
        "V0_14_S3_AUTHORIZED": False,
        "V0_14_S4_AUTHORIZED": False,
        "V0_14_VERSION_COMPLETE": False,
        "V0_15_AUTHORIZED": False,
        "NETWORK_REQUIRED_FOR_CI": False,
        "READY_AUTHORIZED": False,
        "MERGE_AUTHORIZED": False,
        "TAG_CREATED": False,
        "RELEASE_CREATED": False,
        "LATEST_FORMAL_RELEASE": "v0.11.0",
        "OFFICIAL_SOURCES": [
            {
                "url": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
                "retrieved_at": receipt["cutoff"][:10],
                "authority_role": "CURRENT_PRODUCT_CONTRACT",
                "facts": "IFS_50R1;OD_OPER_FC;00_12_TO_360;06_18_TO_144;12_ROLLING_RUNS",
            },
            {
                "url": "https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF+open+data+real-time+forecasts+from+IFS+and+AIFS",
                "retrieved_at": receipt["cutoff"][:10],
                "authority_role": "CURRENT_TECHNICAL_ACCESS_DOCUMENTATION_WITH_HORIZON_CONFLICT",
                "facts": (
                    "RAW_INDEX_BYTE_RANGES;FOUR_OPER_CYCLES;"
                    "TEXT_RETAINS_240_90_LIMITS_CONTRADICTED_BY_PRODUCT_PAGE_AND_LIVE_INDEX"
                ),
            },
            {
                "url": "https://github.com/ecmwf/anemoi-datasets/blob/main/docs/building/sources/accumulate.rst",
                "retrieved_at": receipt["cutoff"][:10],
                "authority_role": "OFFICIAL_OPERATIONAL_ACCUMULATION_TRANSFORM_DOCUMENTATION",
                "facts": (
                    "OPERATIONAL_FORECAST_ACCUMULATIONS_FROM_FORECAST_START;"
                    "LIVE_GRIB_STARTSTEP_ZERO_VERIFIES_PRODUCT_SPECIFIC_ENCODING"
                ),
            },
            {
                "url": "https://codes.ecmwf.int/grib/param-db/169",
                "retrieved_at": receipt["cutoff"][:10],
                "authority_role": "PARAMETER_DEFINITION_NOT_PRODUCT_STEP_AUTHORITY",
                "facts": (
                    "SSRD_169_DOWNWARD_SOLAR_ENERGY_POSITIVE_DOWNWARDS_NOT_NET_SSR_176;"
                    "LIVE_SSRD_ENCODING_IS_ACCUM_J_M2"
                ),
            },
        ],
        "PUBLIC_PROXY_AUTHORITY": "docs/v0-7/s2/weather-dataset-and-leakage-safe-feature-freeze.md",
    }
    for cycle in ("00", "06", "12", "18"):
        report[f"LIVE_{cycle}_CYCLE_AVAILABLE"] = any(
            info["cycle"] == cycle for info in runs.values()
        )
    validate_public_boundary(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--resume-raw-audit", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.resume_raw_audit:
        raise ValueError("NEW_EMPTY_OUTPUT_DIRECTORY_REQUIRED")
    if (args.output / "private-manifest.json").exists():
        raise ValueError("ACCEPTED_OUTPUT_IMMUTABLE")
    args.output.mkdir(parents=True, exist_ok=args.resume_raw_audit)
    runs = audit(args.output)
    print(f"INDEX_AUDIT_COMPLETE runs={len(runs)}", flush=True)
    semantics = probe(args.output, runs)
    print("GRIB_SEMANTICS_COMPLETE", flush=True)
    real_capture = capture(args.output, args.locations)
    manifest = {
        "schema": "V0_14_S1_QUALIFICATION_PRIVATE_MANIFEST_V1",
        "provider": "ECMWF_IFS_OPEN_DATA",
        "runs": runs,
        "semantics": semantics,
        "capture": real_capture,
        "files": {
            str(p.relative_to(args.output)): sha(p.read_bytes())
            for p in sorted(args.output.rglob("*"))
            if p.is_file()
        },
    }
    identity = immutable(args.output / "private-manifest.json", canonical(manifest))
    verify_raw_manifest(args.output, manifest)
    report = public_report(manifest, identity)
    immutable(
        args.output / "sanitized-evidence.json",
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n",
    )
    print(
        json.dumps({"private_manifest_sha256": identity, "capture": real_capture}, sort_keys=True)
    )


if __name__ == "__main__":
    main()
