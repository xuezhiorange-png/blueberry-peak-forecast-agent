"""Bounded resumable official point-series retrieval; block immediately on source defects."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import file_hash, write_json
from scripts.era5_timeseries_source_r2 import read_source, source_gate, validate_manifest


def retrieve(root: Path, max_active: int) -> None:
    import cdsapi  # type: ignore[import-untyped]

    manifest = json.loads((root / "request-manifest.json").read_text())
    validate_manifest(manifest)
    client = cdsapi.Client(quiet=True, debug=False, timeout=60, retry_max=2)
    client.client.check_authentication()
    pending = list(manifest["requests"])
    entries = {r["request_hash"]: r for r in pending}
    active: dict[str, Any] = {}

    def qualify(key: str) -> None:
        receipt = json.loads((root / f"{key}.completed.json").read_text())
        raw = root / f"{key}.raw"
        if file_hash(raw) != receipt["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        _, audit = read_source(raw, entries[key])
        target = root / f"{key}.audit.json"
        if target.exists():
            if json.loads(target.read_text()) != audit:
                raise ValueError("SOURCE_AUDIT_REPLAY_MISMATCH")
        else:
            write_json(target, audit)
        source_gate(audit)

    # Revalidate every existing download before submitting additional work.
    for entry in pending:
        if (root / f"{entry['request_hash']}.completed.json").exists():
            qualify(entry["request_hash"])
    while pending or active:
        while pending and len(active) < max_active:
            entry = pending.pop(0)
            key = entry["request_hash"]
            if (root / f"{key}.completed.json").exists():
                continue
            receipt_path = root / f"{key}.submitted.json"
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                remote = client.client.get_remote(receipt["remote_request_id"])
            else:
                remote = client.client.submit(manifest["source_product"], entry["request"])
                write_json(
                    receipt_path, {"request_hash": key, "remote_request_id": remote.request_id}
                )
            active[key] = remote
        for key, remote in list(active.items()):
            status = remote.status
            if status == "failed":
                raise ValueError("CDS_REQUEST_FAILED")
            if status != "successful":
                continue
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
            del active[key]
            qualify(key)
            print(json.dumps({"completed": key, "pending": len(pending)}), flush=True)
        if active:
            time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--max-active", type=int, default=2, choices=range(1, 4))
    args = parser.parse_args()
    retrieve(args.root, args.max_active)


if __name__ == "__main__":
    main()
