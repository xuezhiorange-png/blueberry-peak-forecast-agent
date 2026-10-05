"""Frozen daily-slot registry. No actual input, scoring, training or automatic scheduler."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.area_yield import v014_shadow_issuance as s
from backend.app.area_yield.data import digest
from backend.app.area_yield.v014_future_weather_features import require
from backend.app.pit.schemas import AreaRevisionInput

SCHEMA = "V0_14_PROSPECTIVE_COHORT_REGISTRY_V1"
METRIC_HASH = "e7447177ad2b48608faa00beb353dd1ff7827c55dea8ee9affdddd0af6885247"
FEATURE_HASH = "ac1f76a07b422420bbe9164802d419d531a7457ec5976d353af5d99cfc498059"
STATUSES = [
    "ISSUED",
    "NO_VALID_SCOPE_AUTHORITY",
    "NO_COMPLETE_WEATHER_RUN",
    "WEATHER_RUN_TOO_OLD",
    "LATE_CAPTURE_CUTOFF",
    "TECHNICAL_FAILURE",
    "MISSED_SLOT",
    "AUTHORITY_CONFLICT",
]
SEED = {
    "forecast_id": "v014_0401ef7c3939f69160b76f24",
    "cohort_id": s.COHORT_ID,
    "model_forecast_origin": "2026-10-06T00:00:00+08:00",
    "target_start_date": "2026-10-06",
    "target_end_date": "2026-10-20",
    "c0_prediction_hash": "6a42b06eaf6c718581cd34ae58c8fc33e73faa0bd8f16f8dd6a13b4cb105432f",
    "w1_prediction_hash": "d1fd7a5589f0ff1df7f38d9254ed71670ce51fda719cfb2fb33416342e7e03ba",
    "seal_hash": "a0a610d50d0be977076f3150d050b9a769e4d50753692a05217591e851a306c1",
    "issuance_package_hash": "e8fe9e1eaf0ce4f3ecce573218f5e5155c58dd9d88ab63758463f1f85e3ef039",
}
POLICY: dict[str, Any] = {
    "operations_policy_id": "V0_14_DAILY_1700_SHADOW_COHORT_OPS_R1",
    "timezone": "Asia/Shanghai",
    "first_slot": "2026-10-06",
    "last_slot": "2027-03-31",
    "scheduled_time": "17:00:00",
    "attempt_deadline": "17:15:00",
    "forecast_created_cutoff": "18:00:00",
    "minimum_lead_hours": 6,
    "max_provider_run_age_hours": 36,
    "retry_allowed": False,
    "backfill_allowed": False,
    "terminal_statuses": STATUSES,
    "area_priority": ["ACTUAL_PRODUCTIVE_AREA", "PLANTED_AREA", "REFERENCE_AREA"],
    "scope_base_id": s.BASE_ID,
    "target_season": "2026-2027",
    "feature_policy_hash": FEATURE_HASH,
    "model_hashes": s.MODEL_HASHES,
    "metric_contract_hash": METRIC_HASH,
    "cohort_id": s.COHORT_ID,
    "registry_schema": SCHEMA,
    "hash_chain": "SHA256_CANONICAL_RECORD_WITHOUT_RECORD_HASH;SEQUENCE;PREVIOUS_HASH",
    "weather_run_policy": "LATEST_COMPLETE_00_OR_12_RUN_DURING_SINGLE_ATTEMPT",
    "required_instantaneous_steps": 84,
    "required_fields": 256,
    "required_max_step": 360,
    "seed_class": "PRE_S4_SEED_PROSPECTIVE_ENTRY",
    "public_git_anchor_required": False,
    "external_trusted_timestamp": False,
    "actual_access_allowed": False,
}
POLICY_HASH = digest(POLICY)


def validate_policy(policy: dict[str, Any]) -> None:
    require(policy == POLICY, "NEW_COHORT_ID_OR_NEW_VERSION_REQUIRED")


def execution_gate(operation: str) -> None:
    require(
        operation in {"verify", "issue-slot", "record-missed-slot", "audit-registry"},
        "FORBIDDEN_EXECUTION",
    )


def slot_dates() -> list[str]:
    start, end = date.fromisoformat(POLICY["first_slot"]), date.fromisoformat(POLICY["last_slot"])
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def slot_id(day: str) -> str:
    require(day in slot_dates(), "SLOT_OUTSIDE_PROTOCOL")
    return f"v014_slot_{day}_asia-shanghai"


def slot_time(day: str, clock: str) -> datetime:
    slot_id(day)
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(clock), tzinfo=s.TZ)


def slot_origin(day: str) -> datetime:
    return slot_time(day, "00:00:00") + timedelta(days=1)


def validate_attempt(day: str, started: datetime) -> None:
    require(started.tzinfo is not None, "NAIVE_TIMESTAMP")
    require(
        slot_time(day, "17:00:00") <= started <= slot_time(day, "17:15:00"),
        "ATTEMPT_OUTSIDE_WINDOW",
    )


def validate_created(day: str, created: datetime) -> None:
    require(created.tzinfo is not None, "NAIVE_TIMESTAMP")
    require(
        slot_time(day, "17:00:00") <= created <= slot_time(day, "18:00:00"), "LATE_CAPTURE_CUTOFF"
    )
    require(
        s.model_origin(created) == slot_origin(day)
        and slot_origin(day) - created >= timedelta(hours=6),
        "SLOT_ORIGIN_MISMATCH",
    )


def select_scope(
    revisions: list[AreaRevisionInput], attempt: datetime, origin: datetime
) -> AreaRevisionInput:
    relevant = []
    ids: dict[str, str] = {}
    for r in revisions:
        require(r.payload_hash == r.computed_payload_hash(), "AREA_HASH_INVALID")
        require(r.recorded_at <= r.known_at, "AREA_TIME_INVALID")
        if r.base_id != s.BASE_ID or r.season != "2026-2027" or r.known_at > attempt:
            continue
        require(
            r.area_revision_id not in ids or ids[r.area_revision_id] == r.payload_hash,
            "AUTHORITY_CONFLICT",
        )
        ids[r.area_revision_id] = str(r.payload_hash)
        relevant.append(r)
    require(
        all(r.supersedes_revision_id is None or r.supersedes_revision_id in ids for r in relevant),
        "AUTHORITY_CONFLICT",
    )
    superseded = {r.supersedes_revision_id for r in relevant if r.supersedes_revision_id}
    eligible = {
        r.area_revision_id: r
        for r in relevant
        if r.area_revision_id not in superseded
        and r.area_type in POLICY["area_priority"]
        and r.effective_from <= origin
        and (r.effective_to is None or origin < r.effective_to)
    }
    for kind in POLICY["area_priority"]:
        matches = [r for r in eligible.values() if r.area_type == kind]
        require(len(matches) <= 1, "AUTHORITY_CONFLICT")
        if matches:
            return matches[0]
    raise ValueError("NO_VALID_SCOPE_AUTHORITY")


def read_scope_store(store: Path, attempt: datetime, origin: datetime) -> AreaRevisionInput:
    # This designated store contains AreaRevision files only, never harvest inputs.
    return select_scope(
        [
            AreaRevisionInput.model_validate_json(p.read_bytes())
            for p in sorted(store.rglob("area-revision.json"))
        ],
        attempt,
        origin,
    )


def line_bytes(record: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            record, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()


def self_record(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "record_hash": digest(body)}


def genesis(seed: dict[str, Any]) -> dict[str, Any]:
    require(seed == SEED, "SEED_IDENTITY_DRIFT")
    return self_record(
        {
            "schema": SCHEMA,
            "sequence": 0,
            "slot_id": "GENESIS",
            "slot_date": None,
            "status": "ISSUED",
            "previous_record_hash": None,
            "entry_class": POLICY["seed_class"],
            "operations_policy_hash": POLICY_HASH,
            **seed,
        }
    )


def manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "schema": SCHEMA,
        "cohort_id": s.COHORT_ID,
        "operations_policy_hash": POLICY_HASH,
        "genesis_record_hash": records[0]["record_hash"],
        "registry_head_hash": records[-1]["record_hash"],
        "record_count": len(records),
    }
    return {**body, "manifest_hash": digest(body)}


@contextmanager
def locked(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    require(not root.is_symlink(), "UNSAFE_REGISTRY_PATH")
    with (root / ".registry.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def write_head(root: Path, records: list[dict[str, Any]]) -> None:
    body = manifest(records)
    # Immutable checkpoints prevent unnoticed suffix deletion relative to retained head.
    checkpoints = root / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    s.write_immutable(checkpoints / f"{len(records) - 1:06d}.json", body)
    tmp = root / ".manifest.pending"
    with tmp.open("wb") as out:
        out.write(s.json_bytes(body))
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, root / "cohort-registry-manifest.json")


def initialize(root: Path, seed: dict[str, Any]) -> None:
    with locked(root):
        record = genesis(seed)
        path = root / "cohort-registry.jsonl"
        if path.exists():
            audit_registry(root)
            return
        with path.open("xb") as out:
            out.write(line_bytes(record))
            out.flush()
            os.fsync(out.fileno())
        write_head(root, [record])


def verify_package(root: Path, expected_hash: str | None = None) -> dict[str, Any]:
    m = s.read_json(root / "issuance-manifest.json")
    require(digest(m["files"]) == m["issuance_package_hash"], "PACKAGE_HASH_INVALID")
    if expected_hash is not None:
        require(m["issuance_package_hash"] == expected_hash, "PACKAGE_IDENTITY_DRIFT")
    names = {
        "scope-authority-snapshot.json",
        "weather-surface-manifest.json",
        "request-snapshot.json",
        "metric-contract.json",
        "c0-predictions.json",
        "w1-predictions.json",
        "prediction-seal.json",
        "cohort-entry.json",
    }
    require(
        len(m["files"]) == 8 and {e["name"] for e in m["files"]} == names, "PACKAGE_MEMBER_INVALID"
    )
    for entry in m["files"]:
        p = root / entry["name"]
        require(not p.is_symlink(), "UNSAFE_PACKAGE_PATH")
        raw = p.read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"],
            "PACKAGE_MEMBER_TAMPER",
        )
    seal = s.read_json(root / "prediction-seal.json")
    s.verify_seal(seal)
    require(
        seal["cohort_id"] == s.COHORT_ID
        and seal["schema"] == s.SEAL_SCHEMA
        and seal["metric_contract_hash"] == METRIC_HASH
        and seal["feature_policy_hash"] == FEATURE_HASH
        and seal["target_row_count"] == 15
        and seal["actual_read_before_seal"] is False
        and seal["scoring_before_seal"] is False
        and seal["shadow"] is True
        and seal["production"] is False,
        "SEAL_CONTRACT_DRIFT",
    )
    request = s.read_json(root / "request-snapshot.json")
    require(
        digest(request) == seal["request_hash"]
        and seal["forecast_id"] == "v014_" + digest(request)[:24],
        "REQUEST_IDENTITY_DRIFT",
    )
    require(
        digest(s.read_json(root / "metric-contract.json")) == METRIC_HASH, "METRIC_CONTRACT_DRIFT"
    )
    area = AreaRevisionInput.model_validate(s.read_json(root / "scope-authority-snapshot.json"))
    require(
        area.payload_hash == area.computed_payload_hash() == seal["scope_authority_hash"]
        and area.base_id == s.BASE_ID
        and area.season == "2026-2027"
        and area.area_type in POLICY["area_priority"],
        "SEALED_SCOPE_INVALID",
    )
    keys = None
    for role, identity in s.MODEL_HASHES.items():
        pred = s.read_json(root / f"{role}-predictions.json")
        require(
            seal[f"{role}_artifact_hash"] == request[f"{role}_artifact_hash"] == identity
            and digest(pred) == seal[f"{role}_prediction_hash"]
            and len(pred) == 15,
            "MODEL_OR_PREDICTION_DRIFT",
        )
        new_keys = [row[0] for row in pred]
        require(keys is None or keys == new_keys, "PAIR_TARGET_MISMATCH")
        keys = new_keys
    require(digest(keys) == seal["target_row_keys_hash"], "TARGET_KEY_DRIFT")
    created, origin = (
        datetime.fromisoformat(request[k]) for k in ("forecast_created_at", "model_forecast_origin")
    )
    s.verify_timing(created, origin, datetime.fromisoformat(seal["sealed_at"]))
    s.verify_area_time(area, created, origin)
    require(
        request["provider"] == "ECMWF_IFS_OPEN_DATA"
        and request["provider_issued_at"] <= request["provider_known_at"],
        "WEATHER_IDENTITY_INVALID",
    )
    weather = s.read_json(root / "weather-surface-manifest.json")
    s.verify_weather_receipt(
        {
            "issued_at": request["provider_issued_at"],
            "run_id": request["provider_run_id"],
            "acquisition_receipt": weather["acquisition_receipt"],
            "raw_manifest_sha256": weather["raw_manifest_sha256"],
        },
        created,
    )
    require(
        weather["raw_manifest_sha256"] == seal["weather_raw_manifest_hash"]
        and digest(weather["selected_base_features"]) == seal["selected_base_weather_feature_hash"],
        "WEATHER_MANIFEST_DRIFT",
    )
    require(
        keys
        == [row["key"] for row in s.target_rows(area, origin, weather["selected_base_features"])]
        and request["target_row_keys_hash"] == seal["target_row_keys_hash"],
        "TARGET_KEY_DRIFT",
    )
    if "slot_id" in request:
        require(request["operations_policy_hash"] == POLICY_HASH, "OPERATIONS_POLICY_DRIFT")
    require(
        request["target_start_date"] == origin.astimezone(s.TZ).date().isoformat()
        and request["target_end_date"]
        == (origin.astimezone(s.TZ).date() + timedelta(days=14)).isoformat(),
        "TARGET_WINDOW_INVALID",
    )
    return {
        **request,
        **seal,
        "model_forecast_origin": request["model_forecast_origin"],
        "issuance_package_hash": m["issuance_package_hash"],
    }


def verify_seed_package(root: Path) -> None:
    entry = verify_package(root, SEED["issuance_package_hash"])
    require(all(entry[k] == v for k, v in SEED.items()), "SEED_IDENTITY_DRIFT")


def audit_registry(root: Path, seed_package: Path | None = None) -> list[dict[str, Any]]:
    records = [
        json.loads(line) for line in (root / "cohort-registry.jsonl").read_bytes().splitlines()
    ]
    require(bool(records) and records[0] == genesis(SEED), "REGISTRY_HASH_CHAIN_INVALID")
    seen = set()
    for i, row in enumerate(records):
        require(
            row["record_hash"] == digest({k: v for k, v in row.items() if k != "record_hash"})
            and row["sequence"] == i
            and row["slot_id"] not in seen,
            "REGISTRY_HASH_CHAIN_INVALID",
        )
        seen.add(row["slot_id"])
        if not i:
            require(
                s.read_json(root / "checkpoints" / "000000.json") == manifest(records[:1]),
                "REGISTRY_HASH_CHAIN_INVALID",
            )
            continue
        require(
            row["previous_record_hash"] == records[i - 1]["record_hash"]
            and row["slot_date"] == slot_dates()[i - 1]
            and row["slot_id"] == slot_id(row["slot_date"])
            and row["status"] in STATUSES,
            "REGISTRY_HASH_CHAIN_INVALID",
        )
        if row["status"] == "ISSUED":
            package = verify_package(
                root / "slot-packages" / row["slot_id"], row["issuance_package_hash"]
            )
            require(
                all(package[k] == row[k] for k in row["issuance_identity_keys"]),
                "REGISTRY_PACKAGE_DRIFT",
            )
            validate_created(row["slot_date"], datetime.fromisoformat(row["forecast_created_at"]))
            require(
                datetime.fromisoformat(row["model_forecast_origin"])
                == slot_origin(row["slot_date"]),
                "SLOT_ORIGIN_MISMATCH",
            )
            verify_freshness(
                datetime.fromisoformat(row["provider_issued_at"]),
                datetime.fromisoformat(row["forecast_created_at"]),
            )
            claim = s.read_json(root / "attempts" / (row["slot_id"] + ".json"))
            started = datetime.fromisoformat(claim["attempt_started_at"])
            validate_attempt(row["slot_date"], started)
            require(
                row["attempt_started_at"]
                == started.isoformat()
                == package["issuance_session_started_at"]
                and started <= datetime.fromisoformat(row["forecast_created_at"]),
                "ATTEMPT_PROVENANCE_INVALID",
            )
        else:
            require(
                row["no_prediction_created"] is True
                and row["no_seal_created"] is True
                and "forecast_id" not in row,
                "NONISSUED_IDENTITY_INVALID",
            )
        require(
            s.read_json(root / "checkpoints" / f"{i:06d}.json") == manifest(records[: i + 1]),
            "REGISTRY_HASH_CHAIN_INVALID",
        )
    require(
        s.read_json(root / "cohort-registry-manifest.json") == manifest(records),
        "REGISTRY_HASH_CHAIN_INVALID",
    )
    require(
        len(list((root / "checkpoints").glob("*.json"))) == len(records),
        "REGISTRY_HASH_CHAIN_INVALID",
    )
    if seed_package is not None:
        verify_seed_package(seed_package)
    return records


def append_record(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    with locked(root):
        records = audit_registry(root)
        for row in records:
            if row["slot_id"] == body["slot_id"]:
                require(all(row[k] == v for k, v in body.items()), "SLOT_CONFLICT")
                return row
        require(body["slot_date"] == slot_dates()[len(records) - 1], "SLOT_ORDER_OR_BACKFILL")
        require(
            body["slot_id"] == slot_id(body["slot_date"]) and body["status"] in STATUSES,
            "INVALID_TERMINAL_RECORD",
        )
        if body["status"] != "ISSUED":
            require(
                body.get("no_prediction_created") is True
                and body.get("no_seal_created") is True
                and "forecast_id" not in body,
                "NONISSUED_IDENTITY_INVALID",
            )
        record = self_record(
            {**body, "sequence": len(records), "previous_record_hash": records[-1]["record_hash"]}
        )
        with (root / "cohort-registry.jsonl").open("ab") as out:
            out.write(line_bytes(record))
            out.flush()
            os.fsync(out.fileno())
        write_head(root, records + [record])
        return record


def nonissued(day: str, status: str, started: datetime | None, reason: str) -> dict[str, Any]:
    require(status in STATUSES and status != "ISSUED", "UNKNOWN_TERMINAL_STATUS")
    return {
        "schema": SCHEMA,
        "slot_id": slot_id(day),
        "slot_date": day,
        "status": status,
        "terminal_status": status,
        "attempt_started_at_or_null": started.isoformat() if started else None,
        "reason": reason,
        "area_authority_status": "NOT_ISSUED",
        "weather_status": "NOT_ISSUED",
        "no_prediction_created": True,
        "no_seal_created": True,
    }


def record_missed(root: Path, day: str, now: datetime) -> dict[str, Any]:
    require(now.tzinfo is not None and now > slot_time(day, "18:00:00"), "MISSED_TOO_EARLY")
    records = audit_registry(root)
    existing = next((r for r in records if r["slot_id"] == slot_id(day)), None)
    if existing is not None:
        return existing
    claim = root / "attempts" / (slot_id(day) + ".json")
    if claim.exists():
        started = datetime.fromisoformat(s.read_json(claim)["attempt_started_at"])
        # A crash can leave a sealed package; reconcile it rather than claim no seal exists.
        package = root / "slot-packages" / slot_id(day)
        require(not package.exists(), "INTERRUPTED_PACKAGE_REQUIRES_OPERATOR_AUDIT")
        return append_record(
            root,
            nonissued(day, "TECHNICAL_FAILURE", started, "INTERRUPTED_SINGLE_ATTEMPT;NO_RETRY"),
        )
    return append_record(root, nonissued(day, "MISSED_SLOT", None, "NO_ATTEMPT_BEFORE_CUTOFF"))


def claim_attempt(root: Path, day: str, started: datetime) -> None:
    validate_attempt(day, started)
    with locked(root):
        records = audit_registry(root)
        require(day == slot_dates()[len(records) - 1], "SLOT_ORDER_OR_BACKFILL")
        claims = root / "attempts"
        claims.mkdir(exist_ok=True)
        path = claims / (slot_id(day) + ".json")
        require(not path.exists(), "RETRY_FORBIDDEN")
        s.write_immutable(
            path, {"slot_id": slot_id(day), "attempt_started_at": started.isoformat()}
        )


def verify_freshness(issued: datetime, created: datetime) -> None:
    require(
        issued.tzinfo is not None
        and created.tzinfo is not None
        and timedelta(0) <= created - issued <= timedelta(hours=36),
        "WEATHER_RUN_TOO_OLD",
    )


def missing_due_slots(records: list[dict[str, Any]], now: datetime) -> list[str]:
    require(now.tzinfo is not None, "NAIVE_TIMESTAMP")
    present = {r["slot_date"] for r in records[1:]}
    return [d for d in slot_dates() if now > slot_time(d, "18:00:00") and d not in present]
