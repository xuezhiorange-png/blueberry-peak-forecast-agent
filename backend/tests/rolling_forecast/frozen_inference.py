"""Explicit frozen S6 parameters on SYNTHETIC observations only; no fit or labels.

Optional local acceptance probe, not an importer or a production entry point.
Supply a server ModelReference JSON on stdin; prints only computed synthetic
curves, metadata and hashes. Never prints the input path or model parameters.
Run in two independent processes and compare stdout bytes.
"""

import sys
from datetime import timedelta

from backend.app.rolling_forecast.engine import forecast
from backend.app.rolling_forecast.identity import implementation_hash
from backend.app.rolling_forecast.model_artifacts import ModelReference, load
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest
from backend.tests.rolling_forecast.test_engine import inputs


def main():
    reference = ModelReference.model_validate_json(sys.stdin.read())
    pair = load(reference)
    calendar, area, origin, cutoff, observations = inputs()
    results = [
        forecast(
            calendar,
            area,
            origin + timedelta(days=i),
            cutoff + timedelta(days=i),
            observations,
            pair,
            "RESEARCH_SHADOW",
        )
        for i in (0, 1)
    ]
    body = {
        "data_class": "SYNTHETIC_OBSERVATIONS_WITH_EXPLICIT_FROZEN_MODEL",
        "model_provenance": reference.provenance,
        "model_file_sha256": reference.file_sha256,
        "fit_sha256": pair.fit_sha256,
        "training_last_date": pair.training_last_date,
        "implementation_hash": implementation_hash(),
        "synthetic_base_id": area.base_id,
        "results": results,
        "training_executed": False,
        "actuals_read": False,
        "scoring_executed": False,
        "production_accuracy_validated": False,
    }
    sys.stdout.buffer.write(canonical_bytes({**body, "proof_hash": digest(body)}))


if __name__ == "__main__":
    main()
