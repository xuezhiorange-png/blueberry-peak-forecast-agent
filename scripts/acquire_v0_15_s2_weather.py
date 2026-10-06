"""Private historical numeric cache from frozen S0 indexes, not prospective state.

GRIB messages are decoded in bounded memory, then discarded; point surfaces and
raw SHA/size/metadata receipts are kept for deterministic offline aggregation.
No harvest/labels/database input. Network opt-in is explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import eccodes  # type: ignore[import-untyped]
import httpx

from backend.app.area_yield.v014_future_weather_features import REQUIRED_FIELDS
from backend.app.area_yield.v015_research_cohort import digest, origin_time
from backend.app.pit.ecmwf_open_data_provider import select_nearest_grid_point
from scripts.audit_v0_15_ecmwf_semantics import availability
from scripts.audit_v0_15_historical_ecmwf_coverage import validate_run_evidence
from scripts.materialize_v0_15_s2_dataset import immutable, sources

LOCATION_SHA = "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
KEYS = (
    "units",
    "stepType",
    "startStep",
    "endStep",
    "shortName",
    "dataDate",
    "dataTime",
    "marsClass",
    "marsStream",
    "marsType",
    "experimentVersionNumber",
    "gridType",
    "Ni",
    "Nj",
    "latitudeOfFirstGridPointInDegrees",
    "longitudeOfFirstGridPointInDegrees",
    "iScansNegatively",
    "jScansPositively",
    "jPointsAreConsecutive",
    "iDirectionIncrementInDegrees",
    "jDirectionIncrementInDegrees",
)


def decode(
    raw: bytes, run_id: str, step: int, parameter: str, bases: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    g = eccodes.codes_new_from_message(raw)
    try:
        meta = {k: eccodes.codes_get(g, k) for k in KEYS}
        if (
            meta["shortName"] != parameter
            or int(meta["endStep"]) != step
            or meta["dataDate"] != int(run_id[:8])
            or meta["dataTime"] != int(run_id[8:10]) * 100
            or (meta["marsClass"], meta["marsStream"], meta["marsType"]) != ("od", "oper", "fc")
        ):
            raise ValueError("GRIB_RUN_IDENTITY_MISMATCH")
        if (
            meta["gridType"] != "regular_ll"
            or meta["iDirectionIncrementInDegrees"] != 0.25
            or meta["jDirectionIncrementInDegrees"] != 0.25
            or meta["iScansNegatively"] != 0
            or meta["jScansPositively"] != 0
            or meta["jPointsAreConsecutive"] != 0
        ):
            raise ValueError("GRID_NOT_FROZEN_025")
        indices = []
        lat0 = Decimal(str(meta["latitudeOfFirstGridPointInDegrees"]))
        lon0 = Decimal(str(meta["longitudeOfFirstGridPointInDegrees"]))
        for base in bases.values():
            point = select_nearest_grid_point(
                Decimal(str(base["latitude"])), Decimal(str(base["longitude"]))
            )
            j = (lat0 - point.latitude) / Decimal(".25")
            i = ((point.longitude - lon0) % Decimal(360) + 360) % 360 / Decimal(".25")
            if j != int(j) or i != int(i) or not (0 <= j < meta["Nj"] and 0 <= i < meta["Ni"]):
                raise ValueError("LOCATION_GRID_INDEX_INVALID")
            indices.append(int(j) * meta["Ni"] + int(i))
        values = eccodes.codes_get_elements(g, "values", indices)
        result = dict(zip(bases, (str(v) for v in values), strict=True))
        if any(
            not Decimal(v).is_finite() or abs(Decimal(v)) >= Decimal("1e20")
            for v in result.values()
        ):
            raise ValueError("NONFINITE_OR_MISSING_WEATHER")
        return meta, result
    finally:
        eccodes.codes_release(g)


def acquire(
    root: Path,
    catalogs: Path,
    locations: Path,
    output: Path,
    raw_roots: list[Path],
    network: bool,
    workers: int,
) -> None:
    os.umask(0o077)
    s, _ = sources(root)
    location_raw = locations.read_bytes()
    if hashlib.sha256(location_raw).hexdigest() != LOCATION_SHA:
        raise ValueError("LOCATION_AUTHORITY_CHANGED")
    bases = {r["base_id"]: r for r in json.loads(location_raw)["bases"]}
    origins = [
        r
        for r in s["research-forecast-origin-universe.json"]["rows"]
        if r["weather_comparable_eligible"]
    ]
    run_bases: dict[str, set[str]] = {}
    for r in origins:
        issue = datetime.strptime(r["selected_run_id"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        if not availability(issue, origin_time(r["forecast_origin"])):
            raise ValueError("PUBLICATION_CUTOFF_FAILED")
        run_bases.setdefault(r["selected_run_id"], set()).add(r["base_id"])
    bindings = json.loads(
        (
            root
            / "docs/v0-15/evidence/historical-ecmwf-coverage-sweep-r1/audit-source-manifest.json"
        ).read_bytes()
    )
    pins = {r["run_id"]: r["effective_derived_run_sha256"] for r in bindings["run_receipt_layers"]}
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    with httpx.Client(
        timeout=90, limits=httpx.Limits(max_connections=workers, max_keepalive_connections=workers)
    ) as client:

        def one(run_id: str) -> dict[str, Any]:
            dest = output / (run_id + ".json")
            if dest.exists():
                old = json.loads(dest.read_bytes())
                if digest({k: v for k, v in old.items() if k != "cache_hash"}) != old["cache_hash"]:
                    raise ValueError("CACHE_DRIFT")
                return {"run_id": run_id, "status": old["status"], "reused": True}
            raw = (catalogs / (run_id + ".json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != pins[run_id]:
                raise ValueError("S0_CATALOG_DRIFT")
            run = json.loads(raw)
            validate_run_evidence(run)
            if run["run_id"] != run_id:
                raise ValueError("CATALOG_RUN_CHANGED")
            product = next(
                p
                for p in run["products"]
                if p["status"] == "RUN_AVAILABLE" and p["resolution"] == "0p25"
            )
            catalog_fields = {
                (r["step"], e["param"]): (r, e) for r in product["fields"] for e in r["entries"]
            }
            wanted_bases = {b: bases[b] for b in sorted(run_bases[run_id])}
            surfaces: dict[str, list[Any]] = {b: [] for b in wanted_bases}
            receipts = []
            checked_steps = set()
            try:
                for step, parameter in REQUIRED_FIELDS:
                    row, entry = catalog_fields[step, parameter]
                    raw = b""
                    for raw_root in raw_roots:
                        p = raw_root / run_id / f"{step}-{parameter}.grib"
                        if p.exists():
                            raw = p.read_bytes()
                            break
                    stem = product["namespace"] + f"/{run_id}-{step}h-oper-fc"
                    source = "https://storage.googleapis.com/ecmwf-open-data/" + stem + ".grib2"
                    offset, length = int(entry["_offset"]), int(entry["_length"])
                    if not raw:
                        if not network:
                            raise ValueError("RAW_NOT_CACHED_NETWORK_DISABLED")
                        if step not in checked_steps:
                            current = client.get(source.removesuffix(".grib2") + ".index")
                            if (
                                current.status_code != 200
                                or hashlib.sha256(current.content).hexdigest()
                                != row["receipt"]["sha256"]
                            ):
                                raise ValueError("OFFICIAL_MIRROR_INDEX_CHANGED")
                            checked_steps.add(step)
                        response = client.get(
                            source, headers={"Range": f"bytes={offset}-{offset + length - 1}"}
                        )
                        if response.status_code != 206:
                            raise ValueError(f"ARCHIVE_HTTP_{response.status_code}")
                        raw = response.content
                    if (
                        len(raw) != length
                        or not raw.startswith(b"GRIB")
                        or not raw.endswith(b"7777")
                    ):
                        raise ValueError("RAW_GRIB_RANGE_SIZE_INVALID")
                    meta, values = decode(raw, run_id, step, parameter, wanted_bases)
                    if int(meta["experimentVersionNumber"]) != int(entry["expver"]):
                        raise ValueError("EXPERIMENT_VERSION_DRIFT")
                    for b, value in values.items():
                        surfaces[b].append(
                            {
                                "step": step,
                                "parameter": parameter,
                                "value": value,
                                **{
                                    k: meta[k]
                                    for k in ("units", "stepType", "startStep", "endStep")
                                },
                            }
                        )
                    receipts.append(
                        {
                            "step": step,
                            "parameter": parameter,
                            "raw_sha256": hashlib.sha256(raw).hexdigest(),
                            "raw_size": len(raw),
                            "index_sha256": row["receipt"]["sha256"],
                            "source": source,
                            "metadata": meta,
                        }
                    )
                status, reason = "COMPLETE", None
            except (ValueError, httpx.HTTPError) as exc:
                status, reason = "INCOMPLETE", type(exc).__name__ + ":" + str(exc)
            result = {
                "run_id": run_id,
                "provider": "ECMWF_IFS_OPEN_DATA",
                "catalog_sha256": pins[run_id],
                "location_authority_sha256": LOCATION_SHA,
                "status": status,
                "reason": reason,
                "base_fields": surfaces,
                "raw_receipts": receipts,
                "native_eccodes_version": str(eccodes.codes_get_api_version()),
                "raw_retention": (
                    "BOUNDED_MEMORY;SOURCE_HASH_RECEIPTS_AND_EXTRACTED_POINT_CACHE_RETAINED"
                ),
            }
            result["cache_hash"] = digest(result)
            immutable(dest, result)
            return {
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "decoded_fields": len(receipts),
                "decoded_bytes": sum(r["raw_size"] for r in receipts),
            }

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(one, run) for run in sorted(run_bases)]):
                print(json.dumps(future.result(), sort_keys=True), flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("repository", "catalogs", "locations", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--raw-root", type=Path, action="append", default=[])
    p.add_argument("--network", action="store_true")
    p.add_argument("--workers", type=int, default=4, choices=range(1, 13))
    a = p.parse_args()
    acquire(a.repository, a.catalogs, a.locations, a.output, a.raw_root, a.network, a.workers)


if __name__ == "__main__":
    main()
