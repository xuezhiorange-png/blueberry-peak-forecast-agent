"""Characterize the frozen ERA5-Land source without accepting a dataset."""

from __future__ import annotations

import argparse
import json
import math
import socket
import time
from array import array
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_historical_dataset_r3 import (
    RESUBMISSION_REQUIRED_STATUSES,
    RecoveryFailure,
    _recovery_failure_from_exception,
    _submitted_receipts,
    audit_one,
    load,
)
from scripts.era5_source_artifact_correction_r3 import LIMITS
from scripts.normalize_era5_land_historical_weather_r1 import no_network
from scripts.normalize_era5_land_historical_weather_r2 import verified_source

CHARACTERIZATION_VERSION = "ERA5_LAND_SOURCE_ARTIFACT_CHARACTERIZATION_R1_V1"
SEASON_BY_START = {
    "2023-07-01": "2023-2024",
    "2024-07-01": "2024-2025",
    "2025-07-01": "2025-2026",
}


def _season_id(start: str) -> str:
    try:
        return SEASON_BY_START[start]
    except KeyError:
        raise ValueError("UNEXPECTED_FROZEN_SEASON_START") from None


def _value_text(value: float | Decimal | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, ".17g")
    return format(value, ".17g")


def _rate_text(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0"
    return format(Decimal(numerator) / Decimal(denominator), ".18g")


def _quantile(values: list[float], fraction: Decimal) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - Decimal(lower)
    return float(
        Decimal.from_float(ordered[lower])
        + (Decimal.from_float(ordered[upper]) - Decimal.from_float(ordered[lower])) * weight
    )


@dataclass
class ValueStats:
    total_count: int = 0
    negative_values: list[float] = field(default_factory=list)
    positive_values: array[float] = field(default_factory=lambda: array("d"))
    minimum_value: float | None = None

    def add(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("NONFINITE_NATIVE_VALUE")
        self.total_count += 1
        self.minimum_value = value if self.minimum_value is None else min(self.minimum_value, value)
        if value < 0:
            self.negative_values.append(value)
        elif value > 0:
            self.positive_values.append(value)

    def as_dict(self) -> dict[str, Any]:
        negatives = sorted(self.negative_values)
        positives = sorted(self.positive_values)
        return {
            "total_count": self.total_count,
            "negative_count": len(negatives),
            "negative_rate": _rate_text(len(negatives), self.total_count),
            "minimum": _value_text(self.minimum_value),
            "maximum_negative": _value_text(max(negatives) if negatives else None),
            "p01_negative": _value_text(_quantile(negatives, Decimal("0.01"))),
            "p05_negative": _value_text(_quantile(negatives, Decimal("0.05"))),
            "p50_negative": _value_text(_quantile(negatives, Decimal("0.50"))),
            "p95_negative": _value_text(_quantile(negatives, Decimal("0.95"))),
            "p99_negative": _value_text(_quantile(negatives, Decimal("0.99"))),
            "unique_negative_magnitude_count": len({v.hex() for v in negatives}),
            "minimum_positive": _value_text(min(positives) if positives else None),
            "p01_positive": _value_text(_quantile(positives, Decimal("0.01"))),
            "p05_positive": _value_text(_quantile(positives, Decimal("0.05"))),
            "p50_positive": _value_text(_quantile(positives, Decimal("0.50"))),
        }


def _negative_only_stats(values: list[float], total_count: int) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "total_count": total_count,
        "negative_count": len(ordered),
        "negative_rate": _rate_text(len(ordered), total_count),
        "minimum": _value_text(min(ordered) if ordered else None),
        "maximum_negative": _value_text(max(ordered) if ordered else None),
        "p01_negative": _value_text(_quantile(ordered, Decimal("0.01"))),
        "p05_negative": _value_text(_quantile(ordered, Decimal("0.05"))),
        "p50_negative": _value_text(_quantile(ordered, Decimal("0.50"))),
        "p95_negative": _value_text(_quantile(ordered, Decimal("0.95"))),
        "p99_negative": _value_text(_quantile(ordered, Decimal("0.99"))),
        "unique_negative_magnitude_count": len({v.hex() for v in ordered}),
    }


@dataclass
class GroupStats:
    total_count: int = 0
    negative_values: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.total_count += 1
        if value < 0:
            self.negative_values.append(value)


def _characterization_gate(audit: dict[str, Any]) -> None:
    """Apply integrity gates while deliberately not applying the provisional envelope."""
    if audit.get("provider_grid_selection_parity") != "PASS":
        raise ValueError("PROVIDER_GRID_SELECTION_MISMATCH")
    if audit.get("missing_interval_count") or audit.get("unexpected_interval_count"):
        raise ValueError("HOURLY_COVERAGE_MISMATCH")
    if audit.get("duplicate_interval_count"):
        raise ValueError("DUPLICATE_NATIVE_TIMESTAMP")
    if audit.get("nonfinite_value_count", 0):
        raise ValueError("NONFINITE_NATIVE_VALUE")


def _entry_context(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_hash": entry["request_hash"],
        "business_start": entry["business_start"],
        "business_end": entry["business_end"],
        "season_id": _season_id(entry["business_start"]),
        "base_ids": sorted(entry["base_ids"]),
        "grid_cell": {
            "latitude": entry["expected_selected_grid_latitude"],
            "longitude": entry["expected_selected_grid_longitude"],
        },
    }


def _audit_completed(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    audits: dict[str, dict[str, Any]] = {}
    for entry in manifest["requests"]:
        key = entry["request_hash"]
        if not (root / f"{key}.completed.json").exists():
            continue
        _, audit = verified_source(root, entry)
        persisted = audit_one(root, entry)
        _characterization_gate(persisted)
        audits[key] = persisted
    return audits


def _write_characterization_stop(
    root: Path,
    *,
    phase: str,
    request_hash: str | None,
    remote_id: str | None,
    status: str | None,
    reason: str,
    active: Iterable[str],
    pending_count: int,
) -> None:
    write_json(
        root / f"characterization-stop-{time.time_ns()}.json",
        {
            "dataset_build_status": "BLOCKED",
            "blocker": reason,
            "phase": phase,
            "request_hash": request_hash,
            "remote_request_id": remote_id,
            "cds_status": status,
            "active_request_hashes": sorted(active),
            "pending_count": pending_count,
            "automatic_resubmission": False,
            "replacement_request_ids_created": False,
            "characterization_mode": True,
            "provisional_envelope_stops_retrieval": False,
            "provisional_envelope_stops_acceptance": True,
            "partial_files_preserved": True,
        },
    )


def characterize_retrieve(root: Path, max_active: int = 3) -> dict[str, Any]:
    """Recover/submits only frozen requests, retaining envelope failures for analysis."""
    manifest, policy = load(root)
    audits = _audit_completed(root, manifest)
    receipts = _submitted_receipts(root, manifest)
    entries = {e["request_hash"]: e for e in manifest["requests"]}
    pending = [e for e in manifest["requests"] if e["request_hash"] not in audits]
    active: dict[str, Any] = {}
    current: str | None = None
    phase = "AUTHENTICATE"
    status: str | None = None
    remote_id: str | None = None

    def finish(key: str, remote: Any) -> None:
        raw = root / f"{key}.raw"
        if raw.exists():
            raise ValueError("UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW")
        remote.download(str(raw))
        raw.chmod(0o400)
        write_json(
            root / f"{key}.completed.json",
            {
                "request_hash": key,
                "remote_request_id": remote.request_id,
                "filename": raw.name,
                "raw_sha256": file_hash(raw),
            },
        )
        audit = audit_one(root, entries[key])
        _characterization_gate(audit)
        audits[key] = audit
        active.pop(key, None)

    try:
        import cdsapi  # type: ignore[import-untyped]

        client = cdsapi.Client(quiet=True, debug=False, timeout=60, retry_max=1)
        client.client.check_authentication()

        # Existing receipts are recovered first. This path can never submit them again.
        for entry in pending:
            key = entry["request_hash"]
            if key not in receipts:
                continue
            current = key
            phase = "QUERY_SUBMITTED"
            remote_id = receipts[key]["remote_request_id"]
            try:
                remote = client.client.get_remote(remote_id)
            except Exception as exc:
                raise _recovery_failure_from_exception(exc, remote_id) from None
            if getattr(remote, "request_id", remote_id) != remote_id:
                raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
            active[key] = remote

        while active:
            for key, remote in list(active.items()):
                current = key
                phase = "POLL_SUBMITTED"
                remote_id = remote.request_id
                try:
                    status = str(remote.status).lower()
                except Exception as exc:
                    raise _recovery_failure_from_exception(exc, remote_id) from None
                if status in RESUBMISSION_REQUIRED_STATUSES:
                    raise RecoveryFailure(
                        "CDS_RESUBMISSION_AUTHORIZATION_REQUIRED",
                        status=status,
                        remote_id=remote_id,
                    )
                if status == "successful":
                    phase = "DOWNLOAD_SUBMITTED"
                    finish(key, remote)
            if active:
                time.sleep(15)

        pending = [e for e in pending if e["request_hash"] not in audits]
        while pending or active:
            while pending and len(active) < max_active:
                entry = pending.pop(0)
                key = entry["request_hash"]
                current = key
                phase = "SUBMIT_FROZEN"
                receipt_path = root / f"{key}.submitted.json"
                if receipt_path.exists():
                    receipt = receipts.get(key)
                    if receipt is None:
                        raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
                    remote_id = receipt["remote_request_id"]
                    remote = client.client.get_remote(remote_id)
                    if getattr(remote, "request_id", remote_id) != remote_id:
                        raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
                else:
                    remote = client.client.submit(manifest["source_product"], entry["request"])
                    remote_id = getattr(remote, "request_id", None)
                    if not isinstance(remote_id, str) or not remote_id:
                        raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
                    write_json(
                        receipt_path,
                        {"request_hash": key, "remote_request_id": remote_id},
                    )
                    receipts[key] = {
                        "request_hash": key,
                        "remote_request_id": remote_id,
                    }
                active[key] = remote

            for key, remote in list(active.items()):
                current = key
                phase = "POLL_FROZEN"
                remote_id = remote.request_id
                try:
                    status = str(remote.status).lower()
                except Exception as exc:
                    raise _recovery_failure_from_exception(exc, remote_id) from None
                if status in RESUBMISSION_REQUIRED_STATUSES:
                    raise RecoveryFailure(
                        "CDS_RESUBMISSION_AUTHORIZATION_REQUIRED",
                        status=status,
                        remote_id=remote_id,
                    )
                if status == "successful":
                    phase = "DOWNLOAD_FROZEN"
                    finish(key, remote)
                    print(json.dumps({"completed": key}), flush=True)
            if active:
                time.sleep(15)
    except Exception as exc:
        if isinstance(exc, RecoveryFailure):
            reason = exc.reason
            status = exc.status
            remote_id = exc.remote_id
        else:
            reason = str(exc) if isinstance(exc, ValueError) else "CDS_REQUEST_OR_DOWNLOAD_FAILED"
            if reason not in {
                "UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW",
                "PROVIDER_GRID_SELECTION_MISMATCH",
                "HOURLY_COVERAGE_MISMATCH",
                "DUPLICATE_NATIVE_TIMESTAMP",
                "NONFINITE_NATIVE_VALUE",
            }:
                reason = "CDS_REQUEST_OR_DOWNLOAD_FAILED"
        _write_characterization_stop(
            root,
            phase=phase,
            request_hash=current,
            remote_id=remote_id,
            status=status,
            reason=reason,
            active=active,
            pending_count=len(pending),
        )
        raise RuntimeError(reason) from None

    return {
        "status": "PASS",
        "request_manifest_hash": manifest["manifest_hash"],
        "policy_hash": digest(policy),
        "planned_request_count": len(manifest["requests"]),
        "submitted_receipt_count": len(receipts),
        "completed_raw_file_count": len(audits),
        "resubmitted": False,
    }


def _record_key(variable: str, dimension: str, key: str) -> tuple[str, str, str]:
    return variable, dimension, key


def _group_rows(groups: dict[tuple[str, str, str], GroupStats]) -> list[dict[str, Any]]:
    rows = []
    for (variable, dimension, key), stats in sorted(groups.items()):
        rows.append(
            {
                "variable": variable,
                "dimension": dimension,
                "key": key,
                **_negative_only_stats(stats.negative_values, stats.total_count),
            }
        )
    return rows


def _raw_record(entry: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    context = _entry_context(entry)
    return {
        **context,
        "raw_sha256": audit["raw_sha256"],
        "native_row_count": audit["native_row_count"],
        "provider_grid_selection_parity": audit["provider_grid_selection_parity"],
        "missing_interval_count": audit["missing_interval_count"],
        "duplicate_interval_count": audit["duplicate_interval_count"],
        "negative_counts": {
            variable: sum(1 for item in audit["negative_values"] if item["variable"] == variable)
            for variable in ("tp", "ssrd")
        },
        "provisional_envelope_exceed_counts": {
            variable: sum(
                1 for item in audit["outside_envelope_negatives"] if item["variable"] == variable
            )
            for variable in ("tp", "ssrd")
        },
    }


def characterize(root: Path, output: Path) -> dict[str, Any]:
    """Build a deterministic source-only distribution report from local raw files."""
    manifest, policy = load(root)
    audits = _audit_completed(root, manifest)
    expected_keys = {e["request_hash"] for e in manifest["requests"]}
    if set(audits) != expected_keys:
        raise ValueError("CHARACTERIZATION_INCOMPLETE_FROZEN_REQUEST_SET")

    variables = {"tp", "ssrd"}
    global_stats = {variable: ValueStats() for variable in variables}
    groups: dict[tuple[str, str, str], GroupStats] = defaultdict(GroupStats)
    negative_request_sets = {variable: set[str]() for variable in variables}
    negative_grid_sets = {variable: set[str]() for variable in variables}
    negative_season_sets = {variable: set[str]() for variable in variables}
    outside_counts = {variable: 0 for variable in variables}
    outside_examples: list[dict[str, Any]] = []
    raw_records = []

    for entry in sorted(manifest["requests"], key=lambda item: item["request_hash"]):
        key = entry["request_hash"]
        native, audit = verified_source(root, entry)
        persisted = audit_one(root, entry)
        _characterization_gate(persisted)
        if audit["raw_sha256"] != persisted["raw_sha256"]:
            raise ValueError("SOURCE_AUDIT_REPLAY_MISMATCH")
        context = _entry_context(entry)
        raw_records.append(_raw_record(entry, persisted))
        for (variable, stamp), value in sorted(native.items()):
            if variable not in variables:
                continue
            global_stats[variable].add(value)
            grid_key = (
                f"{entry['expected_selected_grid_latitude']},"
                f"{entry['expected_selected_grid_longitude']}"
            )
            dimensions = (
                ("season", context["season_id"]),
                ("grid_cell", grid_key),
                ("month", stamp.strftime("%Y-%m")),
                ("hour_utc", f"{stamp.hour:02d}"),
            )
            for dimension, group_key in dimensions:
                groups[_record_key(variable, dimension, group_key)].add(value)
            if value < 0:
                negative_request_sets[variable].add(key)
                negative_grid_sets[variable].add(grid_key)
                negative_season_sets[variable].add(context["season_id"])
                if value < float(LIMITS[variable]):
                    outside_counts[variable] += 1
                    if len(outside_examples) < 20:
                        outside_examples.append(
                            {
                                "request_hash": key,
                                "season_id": context["season_id"],
                                "grid_cell": grid_key,
                                "variable": variable,
                                "valid_time_utc": stamp.isoformat(),
                                "raw_value": value.hex(),
                                "raw_value_decimal": format(value, ".17g"),
                                "raw_artifact_sha256": persisted["raw_sha256"],
                            }
                        )

    raw_artifact_records = sorted(raw_records, key=lambda item: item["request_hash"])
    raw_artifact_set_hash = digest(
        [
            {"request_hash": item["request_hash"], "raw_sha256": item["raw_sha256"]}
            for item in raw_artifact_records
        ]
    )
    body: dict[str, Any] = {
        "characterization_version": CHARACTERIZATION_VERSION,
        "task_id": "V0_5_S2_ERA5_LAND_SOURCE_ARTIFACT_CHARACTERIZATION_R1",
        "source_product": manifest["source_product"],
        "source_product_kind": "CDS_OFFICIAL_POINT_TIMESERIES",
        "weather_source_family": "ERA5_LAND",
        "weather_role": "REANALYSIS_REFERENCE",
        "request_manifest_hash": manifest["manifest_hash"],
        "config_hash": digest(policy),
        "planned_request_count": len(manifest["requests"]),
        "characterized_request_count": len(raw_artifact_records),
        "failed_request_count": 0,
        "raw_artifact_count": len(raw_artifact_records),
        "raw_artifact_set_hash": raw_artifact_set_hash,
        "raw_artifacts": raw_artifact_records,
        "integrity": {
            "missing_interval_count": sum(
                item["missing_interval_count"] for item in raw_artifact_records
            ),
            "duplicate_interval_count": sum(
                item["duplicate_interval_count"] for item in raw_artifact_records
            ),
            "provider_grid_selection_parity": "PASS_ALL_CHARACTERIZED_REQUESTS",
            "nonfinite_value_count": 0,
        },
        "provisional_envelope": {
            "tp_min_m": str(LIMITS["tp"]),
            "ssrd_min_j_m2": str(LIMITS["ssrd"]),
            "stops_retrieval": False,
            "stops_dataset_acceptance": True,
        },
        "variables": {
            variable: {
                **global_stats[variable].as_dict(),
                "negative_request_count": len(negative_request_sets[variable]),
                "negative_grid_count": len(negative_grid_sets[variable]),
                "negative_season_count": len(negative_season_sets[variable]),
                "provisional_envelope_exceed_count": outside_counts[variable],
            }
            for variable in sorted(variables)
        },
        "by_dimension": _group_rows(groups),
        "provisional_envelope_exceed_examples": sorted(
            outside_examples,
            key=lambda item: (item["variable"], item["valid_time_utc"], item["request_hash"]),
        ),
        "positive_value_thresholding": False,
        "positive_value_correction": False,
        "custom_deaccumulation": False,
        "normalization_generated": False,
        "offline_replay": True,
    }
    result = {**body, "characterization_hash": digest(body)}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "characterization.json", result)
    write_json(
        output / "raw-artifact-manifest.json",
        {
            "request_manifest_hash": manifest["manifest_hash"],
            "raw_artifact_count": len(raw_artifact_records),
            "raw_artifact_set_hash": raw_artifact_set_hash,
            "raw_artifacts": raw_artifact_records,
        },
    )
    write_json(
        output / "source-audit-replay.json",
        {
            "request_manifest_hash": manifest["manifest_hash"],
            "request_count": len(audits),
            "audit_hashes": [
                {"request_hash": key, "audit_hash": digest(audits[key])} for key in sorted(audits)
            ],
        },
    )
    return result


def compare_replays(first: Path, second: Path) -> dict[str, Any]:
    one = json.loads((first / "characterization.json").read_text())
    two = json.loads((second / "characterization.json").read_text())
    first_audit = json.loads((first / "source-audit-replay.json").read_text())
    second_audit = json.loads((second / "source-audit-replay.json").read_text())
    return {
        "raw_artifact_hash_replay": one["raw_artifact_set_hash"] == two["raw_artifact_set_hash"],
        "source_audit_replay": first_audit == second_audit,
        "characterization_hash_1": one["characterization_hash"],
        "characterization_hash_2": two["characterization_hash"],
        "characterization_hash_equal": one["characterization_hash"] == two["characterization_hash"],
        "deterministic_replay": one == two,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("retrieve", "characterize", "compare"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    args = parser.parse_args()
    if args.action == "retrieve":
        print(json.dumps(characterize_retrieve(args.root), sort_keys=True))
    elif args.action == "characterize":
        if args.output is None:
            parser.error("--output required for characterize")
        socket.socket.connect = no_network  # type: ignore[method-assign]
        socket.socket.connect_ex = no_network  # type: ignore[method-assign]
        socket.create_connection = no_network
        result = characterize(args.root, args.output)
        print(
            json.dumps(
                {
                    "characterization_hash": result["characterization_hash"],
                    "raw_artifact_count": result["raw_artifact_count"],
                    "raw_artifact_set_hash": result["raw_artifact_set_hash"],
                    "characterized_request_count": result["characterized_request_count"],
                    "normalization_generated": result["normalization_generated"],
                },
                sort_keys=True,
            )
        )
    else:
        if args.output is None or args.second is None:
            parser.error("--output and --second required for compare")
        comparison = compare_replays(args.output, args.second)
        if args.comparison_output is not None:
            write_json(args.comparison_output, comparison)
        print(json.dumps(comparison, sort_keys=True))


if __name__ == "__main__":
    main()
