"""Recover CDS job IDs by exact regional request; no new retrieval."""

import argparse
import json
from pathlib import Path

import cdsapi

from scripts.climate_source_r2 import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    client = cdsapi.Client(quiet=True, debug=False).client
    plan = json.loads((args.source / "retrieval-plan.json").read_text())
    matches = []
    jobs = client.get_jobs(limit=20, sortby="-created")
    for request_id in jobs.request_ids:
        remote = client.get_remote(request_id)
        if remote.collection_id != plan["dataset"]:
            continue
        request = remote.request
        for i, expected in enumerate(plan["requests"]):
            if request == expected:
                matches.append(
                    {
                        "batch": i,
                        "request_id": request_id,
                        "status": remote.status,
                        "exact_request_match": True,
                    }
                )
    if len(matches) != 5 or {m["batch"] for m in matches} != set(range(5)):
        raise ValueError("CDS_JOB_ID_EXACT_REQUEST_MATCH_INCOMPLETE")
    write_json(
        args.source / "cds-request-id-supplement.json", sorted(matches, key=lambda m: m["batch"])
    )
    print("CDS_REQUEST_ID_RECOVERY=PASS")


if __name__ == "__main__":
    main()
