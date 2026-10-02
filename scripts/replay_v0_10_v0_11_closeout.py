"""PUBLIC_CLOSEOUT_EVIDENCE_REPLAY; not historical training reproduction."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def verify(root: Path) -> dict[str, Any]:
    public = root / "artifacts/version-reconciliation"
    manifest = json.loads((public / "public-artifact-manifest.json").read_text())
    for item in manifest["files"]:
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("PUBLIC_PATH_INVALID")
        data = (root / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("PUBLIC_HASH_MISMATCH:" + str(path))
        text = data.decode()
        if any(value in text for value in ("/Users/", "file://", "/tmp/")):
            raise ValueError("PRIVATE_ABSOLUTE_PATH")
        if path.suffix == ".json":
            json.loads(text)
    matrix = json.loads((public / "version-reconciliation-matrix.json").read_text())
    assert len(matrix["requirements"]) >= 23
    assert all(r["status"] in matrix["states"] for r in matrix["requirements"])
    v10 = json.loads((root / "docs/v0-10/evidence/v0.10.0-research-closeout.json").read_text())
    v11 = json.loads(
        (root / "docs/v0-11/evidence/v0.11.0-current-status-and-handoff.json").read_text()
    )
    assert v10["lifecycle"] == "CLOSED_WITH_ORIGINAL_GATE_INCOMPLETE"
    assert v10["original_mechanistic_gate"] == "NOT_ESTABLISHED"
    assert not v10["complete"] and not v10["stable_predictive_gain"]
    assert v11["lifecycle"] == "READY_NOT_ISSUED"
    assert v11["real_forecast_count"] == 0 and not v11["version_complete"]
    assert not any(
        v11[k]
        for k in (
            "prospective_accuracy",
            "probability_calibration",
            "production_use_approved",
            "next_retrospective_search_authorized",
        )
    )
    identity = json.loads((public / "m0-model-identity.json").read_text())
    assert identity["model_id"] == "M0-ALL-HISTORY-REFERENCE-R1"
    assert identity["model_role"] == "REFERENCE_BASELINE"
    assert identity["approval_status"] == "RESEARCH_ONLY"
    with (public / "baseline-metrics.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert [int(r["count"]) for r in rows] == [22, 39, 61]
    for row in rows:
        for name, numerator in (
            ("WINDOW_TOTAL_WAPE", "total_error_numerator_kg"),
            ("FULL_DAILY_PREDICTION_WAPE", "daily_error_numerator_kg"),
            ("TIMING_SHAPE_MICRO_WAPE", "shape_error_numerator_kg"),
        ):
            assert math.isclose(
                float(row[name]),
                float(row[numerator]) / float(row["actual_total_kg"]),
                abs_tol=1e-12,
            )
    for key in (
        "actual_total_kg",
        "daily_error_numerator_kg",
        "total_error_numerator_kg",
        "shape_error_numerator_kg",
    ):
        assert math.isclose(
            float(rows[2][key]), float(rows[0][key]) + float(rows[1][key]), abs_tol=1e-6
        )
    with (public / "risk-coverage-width.csv").open() as stream:
        coverage = list(csv.DictReader(stream))
    assert len(coverage) == 36
    for row in coverage:
        count = int(row["valid_count"])
        assert count == sum(
            int(row[key]) for key in ("covered_count", "below_lower_count", "above_upper_count")
        )
        assert math.isclose(float(row["coverage"]), int(row["covered_count"]) / count)
        assert float(row["mean_width_kg"]) >= 0
    with (public / "risk-distribution-scores.csv").open() as stream:
        scores = list(csv.DictReader(stream))
    assert len(scores) == 36 and all(float(r["mean_crps_kg"]) >= 0 for r in scores)
    return {
        "status": "PASS",
        "level": "PUBLIC_CLOSEOUT_EVIDENCE_REPLAY",
        "verified_files": len(manifest["files"]),
        "historical_training_reproduced": False,
        "private_row_level_data_required": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), sort_keys=True))
