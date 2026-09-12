"""Package reviewed historical yield facts and frozen Ridge; never fit or evaluate.

Writes a private operator-owned bundle, not a public data or model download.
Availability is the operator's actual publication date, not invented historical PIT.
"""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.area_yield.product import check_hash
from backend.app.area_yield.total_yield_r4 import emit, positive

MANIFESTS = {
    "three-season-r7": "44d9ff2f7fa88dd9c326aaa2c7ed3e736b9b4637df3633c3db69392625596581",
    "three-season-r7b": "611507ab99c697ab72921bc478c598cee3315ca4ec103632d6ea158d320efbea",
}


def read_checked(root: Path, stage: str, name: str) -> Any:
    manifest_bytes = (root / stage / "artifact_manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFESTS[stage]:
        raise ValueError("historical manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    raw = (root / stage / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest[name]:
        raise ValueError("historical artifact hash mismatch")
    return json.loads(raw)


def build(root: Path, available_on: date) -> dict[str, Any]:
    shape = read_checked(root, "three-season-r7", "origin_2_global_shape_model.json")
    check_hash(shape)
    qualification = read_checked(root, "three-season-r7b", "qualification.json")
    totals = read_checked(root, "three-season-r7b", "total_metrics_r7b.json")
    history = []
    for row in totals["per_farm"]:
        if row["model"] != "prior":
            continue  # Each observed farm is represented once, never sum model variants.
        q = qualification[row["farm"]]
        if not q["total_evaluable"] or q["season_completeness_status"] != "STRICT_ELIGIBLE":
            raise ValueError("complete area-bound history required")
        if available_on < date.fromisoformat(q["coverage_end"]):
            raise ValueError("publication precedes source coverage")
        if positive(row["area_mu"]) != positive(q["productive_area_mu"]):
            raise ValueError("area qualification mismatch")
        if emit(positive(row["actual_total"]) / positive(row["area_mu"])) != row["actual_yield"]:
            raise ValueError("historical yield provenance mismatch")
        history.append(
            {
                "farm": row["farm"],
                "season": q["season"],
                "end": q["coverage_end"],
                "available_on": str(available_on),
                "yield_kg_per_mu": row["actual_yield"],
                "completeness": q["season_completeness_status"],
                "area_basis": q["area_basis"],
                "source_hash": q["source_hash"],
                "historical_area_mu": row["area_mu"],
                "recorded_total_kg": row["actual_total"],
            }
        )
    payload = {
        "model_version": "AREA_YIELD_B1_SNAPSHOT_V1",
        "shape": shape,
        "shape_available_on": str(available_on),
        "history": sorted(history, key=lambda r: r["farm"]),
        "aliases": {"建水南庄农场": "建水南庄基地"},
        "alias_authority": "USER_CONFIRMED_R4_CANONICAL_IDENTITY_EQUIVALENCE",
        "source_manifest_hashes": MANIFESTS,
        "availability_basis": "OPERATOR_PUBLICATION_NOT_RETROACTIVE_PIT",
        "validation_result": "NO_CLEAR_WINNER",
        "product_engineering_policy": "B1",
    }
    payload["hash"] = digest(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--available-on", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.artifact_root, args.available_on)
    raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    with args.output.open("xb") as stream:
        args.output.chmod(0o600)
        stream.write(raw)
    print(hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
