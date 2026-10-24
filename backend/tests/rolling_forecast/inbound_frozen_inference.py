"""Optional local probe: pinned REAL_FROZEN_S6 parameters, synthetic inbound only.

Explicit ModelReference on stdin, no private discovery or labels. Run twice in
independent processes; stdout contains only synthetic inference, never parameters.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.rolling_forecast import engine, inbound, model_artifacts
from backend.app.rolling_forecast.identity import implementation_hash
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest
from backend.tests.rolling_forecast.inbound_fixture import body, fixture


def main():
    reference = model_artifacts.ModelReference.model_validate_json(sys.stdin.read())
    pair = model_artifacts.load(reference)
    with TemporaryDirectory(prefix="SYNTHETIC-s8-frozen-inference-") as directory:
        catalog = fixture(Path(directory))
        context = catalog.contexts[0]
        source = context.snapshots[0]
        # This scope binds a synthetic contract only, not a real source's gross/net meaning.
        source = source.model_copy(
            update={
                "target_binding": source.target_binding.model_copy(
                    update={"fit_sha256": pair.fit_sha256}
                )
            }
        )
        inbound.require_target(source, pair)
        results = []
        for offset in (0, 1):
            request = body(offset)
            origin = date.fromisoformat(request["origin_date"])
            cutoff = datetime.fromisoformat(request["origin_cutoff_at"])
            rows = inbound.load(context, source, origin, cutoff)
            results.append(
                engine.forecast(
                    context.calendar, context.area, origin, cutoff, rows, pair, "RESEARCH_SHADOW"
                )
            )
    value = dict(
        data_class="SYNTHETIC_INBOUND_WITH_EXPLICIT_FROZEN_MODEL",
        fit_sha256=pair.fit_sha256,
        model_file_sha256=reference.file_sha256,
        model_parameter_hashes={m: a.artifact_hash for m, a in pair.artifacts},
        implementation_hash=implementation_hash(),
        results=results,
        real_actuals_read=False,
        training_executed=False,
        scoring_executed=False,
        production_accuracy_validated=False,
    )
    sys.stdout.buffer.write(canonical_bytes({**value, "proof_hash": digest(value)}))


if __name__ == "__main__":
    main()
