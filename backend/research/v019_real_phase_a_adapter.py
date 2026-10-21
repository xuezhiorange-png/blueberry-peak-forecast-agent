"""Read-only frozen-input review and hermetic Phase A contract rehearsal.

Real execution is deliberately unavailable, even with caller-supplied approval.
File hashes establish object identity, never permission, formal C0 or strict PIT.
No real baseline generation, label loader, scorer or CLI execution switch exists.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from backend.research.v019_daily_curve import canonical_bytes, generate_candidate, method_config
from backend.research.v019_retrospective_entry import (
    CandidateScope,
    Registration,
    SyntheticPermit,
    generate_synthetic,
    register_synthetic,
)
from backend.research.v019_synthetic_validation import digest

PROFILE_SHA256 = "a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b"
REGISTRY_SHA256 = "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
REGISTRY_PAYLOAD_HASH = "d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293"
H7_SHA256 = "ccf39c71786c5e1e9e6503aa9c7b7a76cab4c9e71144d080a85f66a8aa97b68f"
H15_SHA256 = "a9059f3d00c1ec9ed3e4fafda7ef41eb75fee7902e76e3a8ed87822cd0380042"
# Necessary metadata sidecar authenticates the existing candidate-id construction.
# No actual harvested quantities are included in this object.
BASE_METADATA_SHA256 = "6054c2166c5e9800033a34bacc660a96813d0515f3f89fc61380010c0de4bf61"
SOURCE_AREA_SHA256 = "73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7"
HEX = re.compile(r"[0-9a-f]{64}\Z")
START, END = date(2025, 8, 5), date(2026, 4, 15)
FIELDS = (
    "candidate_id",
    "base_id",
    "season",
    "window",
    "origin_date",
    "target_start",
    "target_end",
    "target_dates_sha256",
    "day_authority_sha256",
    "status",
)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _compact_hash(value: object) -> str:
    return _hash(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    )


def boundary() -> dict[str, Any]:
    """A fresh, immutable-by-reconstruction declaration, not an approval token."""
    scope = CandidateScope()
    scope.validate()
    return {
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK",
        "protocol_status": "PROPOSED_NOT_EFFECTIVE",
        "strict_pit": False,
        "production_eligible": False,
        "formally_admitted_c0_count": 0,
        "unresolved_farms": scope.unresolved_farms,
        "unresolved_disposition": scope.unresolved_disposition,
        "physical_basis_equivalence": "NOT_PROVEN",
        "historical_area_known_at": "NOT_PROVEN",
        "real_execution_available": False,
        "real_scoring_available": False,
    }


@dataclass(frozen=True)
class SupportProposal:
    """Explicit complete support proposal; cannot confer approval or execute."""

    season_start: date
    start: date
    end: date
    status: str = "PROPOSED_NOT_EFFECTIVE"

    def validate(self) -> None:
        if (
            any(type(x) is not date for x in (self.season_start, self.start, self.end))
            or self.season_start != date(2025, 7, 1)
            or not self.season_start <= self.start <= START
            or self.end != END
            or self.status != "PROPOSED_NOT_EFFECTIVE"
        ):
            raise ValueError("INVALID_COMPLETE_SUPPORT_PROPOSAL")


@dataclass(frozen=True)
class FrozenInputPaths:
    """Only explicit paths; no search, environment fallback or directory discovery."""

    profile: Path
    registry: Path
    h7: Path
    h15: Path
    base_metadata: Path


def _read_pinned(path: Path, expected: str, filename: str) -> bytes:
    if not path.is_absolute():
        raise ValueError("ABSOLUTE_EXPLICIT_PATH_REQUIRED")
    if path.name != filename or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SYMLINK_OR_FILENAME_REJECTED")
    # Bounded regular-file read, no FIFO/device, symlink leaf or open-ended read.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 8_000_000:
            raise ValueError("INVALID_INPUT_FILE")
        raw = handle.read(8_000_001)
        after = os.fstat(handle.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != before.st_size:
        raise ValueError("INPUT_CHANGED_DURING_READ")
    if _hash(raw) != expected:
        raise ValueError("HASH_MISMATCH")
    return raw


def _object(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_FIELD")
            result[key] = value
        return result

    def nonfinite(value: str) -> NoReturn:
        raise ValueError("NONFINITE_JSON")

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    if not isinstance(result, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return result


def _candidate_rows(raw: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("CANDIDATE_SCHEMA_NO_LABEL_COLUMNS")
    result = []
    for row in reader:
        if set(row) != set(FIELDS) or any(type(v) is not str or not v for v in row.values()):
            raise ValueError("INVALID_CANDIDATE_ROW")
        result.append(row)
    return result


def _candidate_hash(row: dict[str, str], metadata: dict[str, Any]) -> str:
    body = {k: v for k, v in row.items() if k != "candidate_id"}
    body.update(
        source_sha256=CandidateScope().source_sha256,
        base_members_sha256=metadata["accepted_member_identity_sha256"],
        area_authority_row_sha256=metadata["historical_area_authority_row_sha256"],
    )
    return _hash(canonical_bytes(body))


def _validate_member(
    row: dict[str, str],
    metadata: dict[str, dict[str, Any]],
    days: int,
    support: SupportProposal,
) -> None:
    support.validate()
    if (
        set(row) != set(FIELDS)
        or row["base_id"] not in metadata
        or days not in (7, 15)
        or row["season"] != "2025-2026"
        or row["status"] != "C0_CANDIDATE_ONLY"
        or row["window"] != ("H7_PREFIX" if days == 7 else "H15_LOCAL")
        or not all(HEX.fullmatch(row[k]) for k in FIELDS if k.endswith("sha256"))
    ):
        raise ValueError("CANDIDATE_IDENTITY_MISMATCH")
    origin, start, end = (
        date.fromisoformat(row[k]) for k in ("origin_date", "target_start", "target_end")
    )
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    if (
        start != origin + timedelta(days=1)
        or end != origin + timedelta(days=days)
        or not START <= start <= end <= END
        or not support.start <= start <= end <= support.end
        or row["target_dates_sha256"] != _hash(canonical_bytes(dates))
        or row["candidate_id"] != _candidate_hash(row, metadata[row["base_id"]])
    ):
        raise ValueError("CANDIDATE_DATE_OR_SEAL_MISMATCH")


def _validate_documents(
    profile: dict[str, Any],
    registry: dict[str, Any],
    sidecar: dict[str, Any],
    h7: list[dict[str, str]],
    h15: list[dict[str, str]],
    support: SupportProposal,
) -> dict[str, Any]:
    """Structural review only, even for valid artifacts: never a generation permit."""
    support.validate()
    if (
        set(profile)
        != {
            "available_bins",
            "fold_id",
            "missing_bin_policy",
            "profile_kg_per_mu_by_7_day_bin",
            "reference_id",
            "train_row_set_hash",
            "validation_labels_used",
        }
        or profile["fold_id"] != "B"
        or profile["reference_id"] != method_config()["baseline_policy"]
        or profile["validation_labels_used"] is not False
        or profile["train_row_set_hash"]
        != "c8b2da43696071648ac8280569fc2e28d7fa4b987f0a63b9edaae22122cc717e"
        or profile["missing_bin_policy"] != "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE"
        or profile["available_bins"] != list(range(42))
        or set(profile["profile_kg_per_mu_by_7_day_bin"]) != {str(i) for i in range(42)}
    ):
        raise ValueError("PROFILE_SCHEMA_OR_VERSION_MISMATCH")
    for value in profile["profile_kg_per_mu_by_7_day_bin"].values():
        if type(value) not in (str, int, float) or not Decimal(str(value)).is_finite():
            raise ValueError("PROFILE_VALUE_INVALID")
        if Decimal(str(value)) < 0:
            raise ValueError("PROFILE_VALUE_INVALID")
    if (
        set(registry) != {"bases", "enrichment_hashes", "hash", "source_hash", "version"}
        or registry["version"] != "BASE_REGISTRY_V1"
        or registry["source_hash"] != SOURCE_AREA_SHA256
        or _compact_hash({k: v for k, v in registry.items() if k != "hash"}) != registry["hash"]
    ):
        raise ValueError("REGISTRY_SCHEMA_OR_PAYLOAD_MISMATCH")
    bases = {b["base_id"]: b for b in registry["bases"]}
    if len(registry["bases"]) != len(bases) or len(bases) != 39:
        raise ValueError("REGISTRY_BASE_MEMBERSHIP_MISMATCH")
    for b in bases.values():
        area = Decimal(str(b["productive_area_mu"]))
        if not area.is_finite() or area <= 0 or b["active"] is not True:
            raise ValueError("REGISTRY_BASE_AREA_INVALID")
    if set(sidecar) != {
        "base_metadata",
        "global_blockers",
        "origin_time_status",
        "physical_basis",
        "source_id",
        "source_sha256",
        "status",
    }:
        raise ValueError("C0_METADATA_SCHEMA_MISMATCH")
    metadata = {b["base_id"]: b for b in sidecar["base_metadata"]}
    if (
        set(metadata) != set(bases)
        or len(sidecar["base_metadata"]) != 39
        or sum(b["accepted_source_farm_count"] for b in metadata.values()) != 75
        or sidecar["status"] != "C0_CANDIDATE_ONLY"
        or sidecar["source_id"] != "SOURCE_002"
        or sidecar["source_sha256"] != CandidateScope().source_sha256
        or "UNRESOLVED_NINE_FARMS_SCOPE_NOT_PROVEN" not in sidecar["global_blockers"]
        or sidecar["origin_time_status"] != "NOT_REGISTERED_DATE_ONLY_NOT_HISTORICAL_ISSUANCE"
        or sidecar["physical_basis"]
        != "SOURCE002_RECORDED_MARKETABLE_NET_WEIGHT_PROFILE_EQUIVALENCE_NOT_PROVEN"
    ):
        raise ValueError("C0_METADATA_OR_UNRESOLVED_SCOPE_MISMATCH")
    for bid, b in metadata.items():
        if (
            b["base_name"] != bases[bid]["canonical_base_name"]
            or b["area_unit"] != "mu"
            or b["season"] != "2025-2026"
            or b["eligible_days"] != 254
            or b["historical_area_known_at"] != "NOT_PROVEN"
            or b["historical_area_structurally_valid"] is not True
            or b["full_admission_status"] != "BLOCKED"
            or b["residual_unresolved_farm_impact"]
            != "NOT_PROVEN_UNAFFECTED_NOT_LOCALLY_ATTRIBUTABLE"
            or not all(
                HEX.fullmatch(b[k])
                for k in ("accepted_member_identity_sha256", "historical_area_authority_row_sha256")
            )
        ):
            raise ValueError("C0_AREA_OR_LIMITATION_MISMATCH")
    for rows, days, count in ((h7, 7, 9672), (h15, 15, 9360)):
        for row in rows:
            _validate_member(row, metadata, days, support)
        expected = {
            (bid, (START - timedelta(days=1) + timedelta(days=i)).isoformat())
            for bid in bases
            for i in range(254 - days + 1)
        }
        if (
            len(rows) != count
            or len({r["candidate_id"] for r in rows}) != count
            or {(r["base_id"], r["origin_date"]) for r in rows} != expected
            or rows != sorted(rows, key=lambda r: (r["base_id"], r["origin_date"]))
        ):
            raise ValueError("C0_MEMBERSHIP_NOT_THE_REGISTERED_CANDIDATE_SET")
    return {
        "h7_candidate_count": len(h7),
        "h15_candidate_count": len(h15),
        "base_count": len(bases),
        "status": "VALIDATED_CANDIDATE_ONLY_EXECUTION_BLOCKED",
    }


def validate_frozen_inputs(paths: FrozenInputPaths, *, support: SupportProposal) -> dict[str, Any]:
    """Caller must separately have bounded read permission; no prediction or writes.

    Pinning is non-configurable. Do not invoke this on private inputs as part of
    development/CI. The only executed fixtures in this delivery are synthetic.
    """
    if type(paths) is not FrozenInputPaths or type(support) is not SupportProposal:
        raise ValueError("EXPLICIT_INPUT_AND_SUPPORT_REQUIRED")
    support.validate()
    specs = (
        (paths.profile, PROFILE_SHA256, "reference-B.json"),
        (paths.registry, REGISTRY_SHA256, "base-registry-v1.json"),
        (paths.h7, H7_SHA256, "h7-candidates.csv"),
        (paths.h15, H15_SHA256, "h15-candidates.csv"),
        (paths.base_metadata, BASE_METADATA_SHA256, "base-admission-metadata.json"),
    )
    if len({p for p, _, _ in specs}) != len(specs):
        raise ValueError("INPUT_PATHS_NOT_DISTINCT")
    raw = [_read_pinned(p, h, n) for p, h, n in specs]
    registry = _object(raw[1])
    if registry.get("hash") != REGISTRY_PAYLOAD_HASH:
        raise ValueError("PINNED_REGISTRY_PAYLOAD_MISMATCH")
    review = _validate_documents(
        _object(raw[0]),
        registry,
        _object(raw[4]),
        _candidate_rows(raw[2]),
        _candidate_rows(raw[3]),
        support,
    )
    body = {
        **review,
        **boundary(),
        "input_sha256": {n: h for _, h, n in specs},
        "support_proposal": {k: str(v) for k, v in asdict(support).items()},
        "origin_time_and_cutoff": "NOT_REGISTERED_DATE_ONLY_NOT_HISTORICAL_ISSUANCE",
    }
    return {**body, "review_sha256": _hash(canonical_bytes(body))}


def generate_real_predictions(*args: object, **kwargs: object) -> NoReturn:
    """No permit/flag/environment can enable real execution in this revision."""
    raise PermissionError(
        "REAL_PHASE_A_EXECUTION_DISABLED_SEPARATE_IMPLEMENTATION_AND_AUTH_REQUIRED"
    )


def rehearse_synthetic(*, fixture: str = "PAIR") -> dict[str, Any]:
    """Existing hermetic algorithms, no caller curves, real files or label inputs."""
    c0 = register_synthetic(Registration("SYNTHETIC-PHASE-A-ADAPTER-R1", fixture=fixture))
    seal = generate_synthetic(c0, permit=SyntheticPermit("A"))
    units = {u.sample.sample_id: u for u in c0.units}
    members = []
    for pair in seal.preparation.predictions.pairs:
        unit = units[pair.sample_id]
        curve = unit.curve
        failure = pair.failure
        if unit.sample.physical_basis != "ACTUAL_HARVEST_KG":
            failure = "PHYSICAL_BASIS_NOT_VERIFIED"
        baseline = pair.baseline if not failure else None
        candidate = pair.candidate if not failure else None
        full_candidate = generate_candidate(curve) if curve and not failure else None
        members.append(
            {
                "sample_id": pair.sample_id,
                "base_id": unit.sample.base_id,
                "window": unit.sample.window,
                "origin": unit.sample.origin.isoformat(),
                "cutoff": unit.sample.cutoff.isoformat(),
                "computed_at": unit.computed_at.isoformat(),
                "issued_at": unit.sample.issued_at.isoformat(),
                "clock_provenance": "EXPLICIT_SIMULATED_CLOCK_NOT_REAL_EXECUTION_TIME",
                "full_support_start": curve.support_start.isoformat() if curve else None,
                "full_support_end": curve.support_end.isoformat() if curve else None,
                "full_baseline_daily": [
                    {"date": r.day.isoformat(), "kg": str(r.kg)} for r in curve.baseline
                ]
                if curve and not failure
                else [],
                "full_candidate_daily": [
                    {"date": r.day.isoformat(), "kg": str(r.kg)} for r in full_candidate.rows
                ]
                if full_candidate
                else [],
                "daily_dates": [d.isoformat() for d in unit.sample.dates],
                "baseline_daily": [str(r.kg) for r in baseline.rows] if baseline else [],
                "candidate_daily": [str(r.kg) for r in candidate.rows] if candidate else [],
                "baseline_source_hash": curve.baseline_source_sha256 if curve else None,
                "candidate_source_hash": curve.baseline_source_sha256 if curve else None,
                "baseline_forecast_sha256": digest(baseline) if baseline else None,
                "candidate_forecast_sha256": digest(candidate) if candidate else None,
                "candidate_result_source_hash": candidate.source_sha256 if candidate else None,
                "failure": failure,
            }
        )
    body = {
        **boundary(),
        "data_class": "SYNTHETIC",
        "fixture": fixture,
        "members": members,
        "c0_sha256": c0.sha256,
        "prediction_seal_sha256": seal.sha256,
        "method_config_sha256": _hash(canonical_bytes(method_config())),
        "source_code_sha256": {
            n: _hash((Path(__file__).parent / n).read_bytes())
            for n in (
                "v019_real_phase_a_adapter.py",
                "v019_daily_curve.py",
                "v019_retrospective_entry.py",
                "v019_replay_preparation.py",
                "v019_synthetic_validation.py",
            )
        },
        "labels_read": False,
        "real_prediction_generated": False,
    }
    return {**body, "seal_sha256": _hash(canonical_bytes(body))}


def verify_synthetic_seal(value: dict[str, Any]) -> None:
    """Rebuild the hermetic rehearsal; a self-consistent forged hash is insufficient."""
    if value != rehearse_synthetic(fixture=value.get("fixture", "")):
        raise ValueError("SYNTHETIC_PHASE_A_SEAL_MISMATCH")
