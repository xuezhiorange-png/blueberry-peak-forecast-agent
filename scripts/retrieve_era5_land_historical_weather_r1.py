"""Resume bounded CDS point requests; preserve immutable receipts and raw files."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.normalize_era5_land_historical_weather_r1 import audit_accumulations, read_native


def main() -> None:
    import cdsapi  # type: ignore[import-untyped]

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--max-active", type=int, default=3, choices=range(1, 5))
    args = p.parse_args()
    root = args.root
    manifest = json.loads((root / "request-manifest.json").read_text())
    if (
        digest({k: v for k, v in manifest.items() if k != "manifest_hash"})
        != manifest["manifest_hash"]
    ):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    client = cdsapi.Client(quiet=True, debug=False, timeout=60, retry_max=2)
    client.client.check_authentication()
    active: dict[str, Any] = {}
    pending = list(manifest["requests"])
    entries = {r["request_id"]: r["request"] for r in pending}
    while pending or active:
        while pending and len(active) < args.max_active:
            entry = pending.pop(0)
            key = entry["request_id"]
            raw = root / f"{key}.raw"
            done = root / f"{key}.completed.json"
            if done.exists():
                if file_hash(raw) != json.loads(done.read_text())["raw_sha256"]:
                    raise ValueError("RAW_HASH_MISMATCH")
                lat, lon = entry["request"]["area"][:2]
                if audit_accumulations(read_native(raw, str(lat), str(lon))):
                    raise ValueError("NATIVE_ACCUMULATION_NEGATIVE_DIFFERENCE_REVIEW_REQUIRED")
                continue
            receipt = root / f"{key}.submitted.json"
            if receipt.exists():
                remote = client.client.get_remote(
                    json.loads(receipt.read_text())["remote_request_id"]
                )
            else:
                first = root / "first-submission.json"
                if first.exists() and json.loads(first.read_text())["request_hash"] == key:
                    remote = client.client.get_remote(
                        json.loads(first.read_text())["remote_request_id"]
                    )
                else:
                    remote = client.client.submit(manifest["dataset"], entry["request"])
                write_json(receipt, {"remote_request_id": remote.request_id, "request_hash": key})
            active[key] = remote
        for key, remote in list(active.items()):
            status = remote.status
            if status == "failed":
                write_json(root / f"{key}.failed.json", {"status": status, "request_hash": key})
                raise RuntimeError("CDS_REQUEST_FAILED")
            if status == "successful":
                raw = root / f"{key}.raw"
                if raw.exists():
                    raise ValueError("UNRECEIPTED_RAW_FILE_REQUIRES_REVIEW")
                remote.download(str(raw))
                raw.chmod(0o400)
                write_json(
                    root / f"{key}.completed.json",
                    {
                        "request_hash": key,
                        "raw_sha256": file_hash(raw),
                        "filename": raw.name,
                        "remote_request_id": remote.request_id,
                    },
                )
                del active[key]
                lat, lon = entries[key]["area"][:2]
                if audit_accumulations(read_native(raw, str(lat), str(lon))):
                    raise ValueError("NATIVE_ACCUMULATION_NEGATIVE_DIFFERENCE_REVIEW_REQUIRED")
                print(json.dumps({"completed_request": key, "pending": len(pending)}), flush=True)
        if active:
            time.sleep(15)


if __name__ == "__main__":
    main()
