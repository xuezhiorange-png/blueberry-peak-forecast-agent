"""R3 immutable overlay, preflight gates and bounded CDS acquisition."""

import argparse
import copy
import json
import shutil
import time
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_source_artifact_correction_r3 import VERSION, gate, qualify, validate_policy
from scripts.era5_timeseries_source_r2 import validate_manifest
from scripts.normalize_era5_land_historical_weather_r2 import verified_source

CONFIG = Path("configs/era5_land_historical_weather_r3.json")
GRID_REVIEW = "5204323324"
RESUBMISSION_REQUIRED_STATUSES = {
    "cancelled",
    "dismissed",
    "expired",
    "failed",
    "not-retrievable",
    "not_retrievable",
    "server-failed",
    "server_failed",
}


class RecoveryFailure(RuntimeError):
    def __init__(self, reason: str, *, status: str | None = None, remote_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.remote_id = remote_id


def load(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    m = json.loads((root / "request-manifest.json").read_text())
    validate_manifest(m)
    policy = json.loads((root / "correction-policy.json").read_text())
    validate_policy(policy)
    source_hash = m["manifest_hash"]
    if "explicit_grid_review" in m:
        original = json.loads((root / "original-request-manifest.json").read_text())
        validate_manifest(original)
        source_hash = original["manifest_hash"]
        if m["explicit_grid_review"] != GRID_REVIEW or m["locations"] != original["locations"]:
            raise ValueError("GRID_QUERY_AUTHORIZATION_MISMATCH")
        old = {e["request_hash"]: e for e in original["requests"]}
        for entry in m["requests"]:
            previous = old[entry["original_request_hash"]]
            expected = copy.deepcopy(previous)
            if entry["query_mode"] == "EXPLICIT_FROZEN_GRID":
                expected["request"]["location"] = {
                    c: float(previous[f"expected_selected_grid_{c}"])
                    for c in ("latitude", "longitude")
                }
                expected["request_hash"] = digest(expected["request"])
            elif entry["query_mode"] != "REUSED_QUALIFIED_PROVIDER_POINT":
                raise ValueError("GRID_QUERY_AUTHORIZATION_MISMATCH")
            expected.update(
                original_request_hash=previous["request_hash"], query_mode=entry["query_mode"]
            )
            if entry != expected:
                raise ValueError("GRID_QUERY_PLAN_DRIFT")
        if len(m["requests"]) != len(original["requests"]):
            raise ValueError("GRID_QUERY_PLAN_DRIFT")
    if policy != json.loads(CONFIG.read_text()) or policy["source_manifest_r2_hash"] != source_hash:
        raise ValueError("FROZEN_CORRECTION_POLICY_MISMATCH")
    return m, policy


def prepare_grid_review(prior: Path, root: Path) -> None:
    """Reviewed replacement plan; never mutate rejected raw or original receipts."""
    original, policy = load(prior)
    revised = copy.deepcopy(original)
    reusable = []
    for entry in revised["requests"]:
        key = entry["request_hash"]
        qualified = (prior / f"{key}.r3-audit.json").exists()
        if qualified:
            gate(audit_one(prior, entry))
            reusable.append(key)
        else:
            entry["request"]["location"] = {
                c: float(entry[f"expected_selected_grid_{c}"]) for c in ("latitude", "longitude")
            }
            entry["request_hash"] = digest(entry["request"])
        entry["original_request_hash"] = key
        entry["query_mode"] = (
            "REUSED_QUALIFIED_PROVIDER_POINT" if qualified else "EXPLICIT_FROZEN_GRID"
        )
    revised["explicit_grid_review"] = GRID_REVIEW
    revised["manifest_hash"] = digest({k: v for k, v in revised.items() if k != "manifest_hash"})
    validate_manifest(revised)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "original-request-manifest.json", original)
    write_json(root / "request-manifest.json", revised)
    write_json(root / "correction-policy.json", policy)
    files = [
        {"name": p.name, "sha256": file_hash(p)} for p in sorted(prior.iterdir()) if p.is_file()
    ]
    write_json(root / "prior-preservation.json", {"files": files, "hash": digest(files)})
    for key in reusable:
        for suffix in ("raw", "completed.json", "submitted.json"):
            source = prior / f"{key}.{suffix}"
            if source.exists():
                shutil.copy2(source, root / source.name)
    load(root)


def prepare(prior: Path, root: Path) -> None:
    m = json.loads((prior / "request-manifest.json").read_text())
    validate_manifest(m)
    policy = json.loads(CONFIG.read_text())
    validate_policy(policy)
    if policy["source_manifest_r2_hash"] != m["manifest_hash"]:
        raise ValueError("SOURCE_PLAN_DRIFT")
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "request-manifest.json", m)
    write_json(root / "correction-policy.json", policy)
    preserved = []
    for path in sorted(prior.iterdir()):
        if path.is_file():
            preserved.append({"name": path.name, "sha256": file_hash(path)})
    write_json(root / "r2-preservation.json", {"files": preserved, "hash": digest(preserved)})
    for entry in m["requests"]:
        key = entry["request_hash"]
        if (prior / f"{key}.completed.json").exists():
            verified_source(prior, entry)
            for suffix in ("raw", "completed.json", "submitted.json"):
                source = prior / f"{key}.{suffix}"
                if source.exists():
                    shutil.copy2(source, root / source.name)


def audit_one(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    _, raw_audit = verified_source(root, entry)
    audit = qualify(raw_audit)
    audit["base_ids"] = entry["base_ids"]
    audit["expected_grid"] = {
        c: entry[f"expected_selected_grid_{c}"] for c in ("latitude", "longitude")
    }
    target = root / f"{entry['request_hash']}.r3-audit.json"
    if target.exists():
        if json.loads(target.read_text()) != audit:
            raise ValueError("SOURCE_AUDIT_REPLAY_MISMATCH")
    else:
        write_json(target, audit)
    return audit


def preflight(root: Path) -> dict[str, Any]:
    m, policy = load(root)
    audits = [
        audit_one(root, e)
        for e in m["requests"]
        if (root / f"{e['request_hash']}.completed.json").exists()
    ]
    for audit in audits:
        gate(audit)
    return {
        "status": "PASS",
        "raw_checked": len(audits),
        "policy_hash": digest(policy),
        "correction_version": VERSION,
    }


def _submitted_receipts(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = {e["request_hash"]: e for e in manifest["requests"]}
    receipts: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.submitted.json")):
        key = path.name.removesuffix(".submitted.json")
        receipt = json.loads(path.read_text())
        if key not in entries or receipt.get("request_hash") != key:
            raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
        remote_id = receipt.get("remote_request_id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ValueError("SUBMITTED_RECEIPT_IDENTITY_MISMATCH")
        receipts[key] = receipt
    return receipts


def _recovery_failure_from_exception(exc: Exception, remote_id: str | None) -> RecoveryFailure:
    text = str(exc).lower()
    if any(term in text for term in ("expired", "not retriev", "not found", "server failed")):
        return RecoveryFailure(
            "CDS_RESUBMISSION_AUTHORIZATION_REQUIRED",
            status="NOT_RETRIEVABLE",
            remote_id=remote_id,
        )
    return RecoveryFailure("CDS_REQUEST_OR_DOWNLOAD_FAILED", remote_id=remote_id)


def recover_submitted(root: Path) -> dict[str, Any]:
    """Recover only existing submitted jobs; this path can never submit a request."""
    m, policy = load(root)
    preflight_result = preflight(root)
    receipts = _submitted_receipts(root, m)
    pending = [
        e
        for e in m["requests"]
        if e["request_hash"] in receipts
        and not (root / f"{e['request_hash']}.completed.json").exists()
    ]
    if not pending:
        return {
            "status": "PASS",
            "submitted_receipt_count": len(receipts),
            "already_completed_count": len(receipts),
            "recovered_count": 0,
            "resubmitted": False,
            "policy_hash": digest(policy),
            "preflight": preflight_result,
        }

    import cdsapi  # type: ignore[import-untyped]

    active: dict[str, tuple[Any, str]] = {}
    phase = "AUTHENTICATE"
    current: str | None = None
    status: str | None = None
    remote_id: str | None = None
    try:
        client = cdsapi.Client(quiet=True, debug=False, timeout=60, retry_max=1)
        client.client.check_authentication()
        for entry in pending:
            key = entry["request_hash"]
            current = key
            phase = "QUERY_SUBMITTED"
            receipt = receipts[key]
            raw = root / f"{key}.raw"
            if raw.exists():
                raise RecoveryFailure("UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW")
            remote_id = receipt["remote_request_id"]
            try:
                remote = client.client.get_remote(remote_id)
            except Exception as exc:
                raise _recovery_failure_from_exception(exc, remote_id) from None
            active[key] = (remote, remote_id)

        while active:
            for key, (remote, remote_id) in list(active.items()):
                current = key
                phase = "POLL_SUBMITTED"
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
                if status != "successful":
                    continue
                phase = "DOWNLOAD_SUBMITTED"
                raw = root / f"{key}.raw"
                if raw.exists():
                    raise RecoveryFailure(
                        "UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW", remote_id=remote_id
                    )
                try:
                    remote.download(str(raw))
                except Exception as exc:
                    raise _recovery_failure_from_exception(exc, remote_id) from None
                raw.chmod(0o400)
                write_json(
                    root / f"{key}.completed.json",
                    {
                        "request_hash": key,
                        "remote_request_id": remote_id,
                        "filename": raw.name,
                        "raw_sha256": file_hash(raw),
                    },
                )
                phase = "SOURCE_GATE"
                audit = audit_one(root, {e["request_hash"]: e for e in pending}[key])
                gate(audit)
                del active[key]
                print(json.dumps({"recovered": key, "remaining": len(active)}), flush=True)
            if active:
                time.sleep(15)
    except Exception as exc:
        if isinstance(exc, RecoveryFailure):
            reason = exc.reason
            status = exc.status
            remote_id = exc.remote_id
        else:
            failure = _recovery_failure_from_exception(exc, None)
            reason = failure.reason
            status = failure.status
            remote_id = failure.remote_id
        write_json(
            root / f"stop-{time.time_ns()}.json",
            {
                "dataset_build_status": "BLOCKED",
                "blocker": reason,
                "phase": phase,
                "request_hash": current,
                "remote_request_id": remote_id,
                "cds_status": status,
                "exception_type": type(exc).__name__,
                "active_request_hashes": sorted(active),
                "pending_count": len(pending),
                "automatic_resubmission": False,
                "submitted_only_recovery": True,
                "partial_files_preserved": True,
            },
        )
        raise RuntimeError(reason) from None

    return {
        "status": "PASS",
        "submitted_receipt_count": len(receipts),
        "already_completed_count": len(receipts) - len(pending),
        "recovered_count": len(pending),
        "resubmitted": False,
        "policy_hash": digest(policy),
        "preflight": preflight_result,
    }


def retrieve(root: Path, max_active: int = 3) -> None:
    # Must finish raw, unit, grid, time, envelope checks BEFORE network activity.
    if any(root.glob("stop-*.json")):
        raise ValueError("PRIOR_RETRIEVAL_STOP_REQUIRES_REVIEW")
    print(json.dumps(preflight(root)), flush=True)
    import cdsapi

    m, _ = load(root)
    pending = [
        e for e in m["requests"] if not (root / f"{e['request_hash']}.completed.json").exists()
    ]
    active: dict[str, Any] = {}
    entries = {e["request_hash"]: e for e in pending}
    phase = "AUTHENTICATE"
    current = None
    try:
        client = cdsapi.Client(quiet=True, debug=False, timeout=60, retry_max=1)
        client.client.check_authentication()
        while pending or active:
            while pending and len(active) < max_active:
                e = pending.pop(0)
                current = e["request_hash"]
                phase = "SUBMIT_OR_RESUME"
                receipt = root / f"{current}.submitted.json"
                if receipt.exists():
                    remote = client.client.get_remote(
                        json.loads(receipt.read_text())["remote_request_id"]
                    )
                else:
                    remote = client.client.submit(m["source_product"], e["request"])
                    write_json(
                        receipt, {"request_hash": current, "remote_request_id": remote.request_id}
                    )
                active[current] = remote
            for key, remote in list(active.items()):
                current = key
                phase = "POLL"
                status = remote.status
                if status in {"failed", "dismissed", "cancelled"}:
                    raise ValueError("CDS_REQUEST_FAILED")
                if status != "successful":
                    continue
                phase = "DOWNLOAD"
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
                phase = "SOURCE_GATE"
                audit = audit_one(root, entries[key])
                gate(audit)
                del active[key]
                print(
                    json.dumps({"completed": key, "remaining": len(pending) + len(active)}),
                    flush=True,
                )
            if active:
                time.sleep(15)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "CDS_REQUEST_OR_DOWNLOAD_FAILED"
        # No raw exception, credentials or signed download URL in the durable report.
        if phase != "SOURCE_GATE" and reason not in {
            "CDS_REQUEST_FAILED",
            "UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW",
        }:
            reason = "CDS_REQUEST_OR_DOWNLOAD_FAILED"
        write_json(
            root / f"stop-{time.time_ns()}.json",
            {
                "dataset_build_status": "BLOCKED",
                "blocker": reason,
                "phase": phase,
                "request_hash": current,
                "exception_type": type(exc).__name__,
                "active_request_hashes": sorted(active),
                "pending_count": len(pending),
                "automatic_resubmission": False,
                "partial_files_preserved": True,
            },
        )
        raise RuntimeError(reason) from None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=("prepare", "prepare-grid-review", "preflight", "retrieve", "recover-submitted"),
    )
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--prior-root", type=Path)
    args = p.parse_args()
    if args.action in {"prepare", "prepare-grid-review"}:
        if args.prior_root is None:
            p.error("--prior-root required")
        if args.action == "prepare-grid-review":
            prepare_grid_review(args.prior_root, args.root)
        else:
            prepare(args.prior_root, args.root)
    elif args.action == "preflight":
        print(json.dumps(preflight(args.root)))
    elif args.action == "recover-submitted":
        print(json.dumps(recover_submitted(args.root)))
    else:
        retrieve(args.root)


if __name__ == "__main__":
    main()
