"""Run 39-base SYNTHETIC real-format A/B in separate processes and benchmark.

This fixture runner signs only SYNTHETIC permissions with ephemeral keys. It
does not provision real trust, discover paths or produce real study approvals.
"""

from __future__ import annotations

import argparse
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research.v019_synthetic_validation import digest
from backend.tests.area_yield.build_v019_real_shape_fixture import build, write


def run(output: Path) -> dict[str, Any]:
    # macOS /tmp is an alias for /private/tmp. Only this SYNTHETIC fixture
    # creator canonicalizes its chosen output; real input validation is intact.
    output = output.resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic()
    mp, mh, lp, lh, signer, grants = build(output / "inputs")
    inputs = cohort.load_inputs(mp, signer.context, grants, mh)
    c = cohort.candidates(inputs, signer.context)
    review = cohort.review_candidates(
        c, {r["candidate_id"]: {"status": "ADMIT", "reason": ""} for r in c["payload"]["members"]}
    )
    grants["PROTOCOL"] = signer.decision("PROTOCOL", digest(auth.restrictions()))
    grants["FORMAL_C0"] = signer.decision("FORMAL_C0", review["sha256"])
    formal = cohort.formalize(c, review, signer.context, grants)
    grants["IMPLEMENTATION_REVIEW"] = signer.decision("IMPLEMENTATION_REVIEW", auth.code_identity())
    subject_a = auth.phase_a_subject(formal["sha256"], mp, mh)
    grants["A_EXECUTION"] = signer.decision("A_EXECUTION", subject_a)
    grants["C0_SEAL_REVIEW"] = signer.decision("C0_SEAL_REVIEW", subject_a)
    write(
        output / "synthetic-roots.json",
        {"synthetic_only": True, "keys": signer.context.synthetic_roots},
    )
    write(output / "candidates.json", c)
    write(output / "review.json", review)
    write(output / "formal-c0.json", formal)
    write(output / "a-grants.json", grants)
    command = [sys.executable, "-m", "backend.research.v019_research_cli"]
    common = ["--mode", "SYNTHETIC", "--synthetic-roots", str(output / "synthetic-roots.json")]
    a_start = time.monotonic()
    subprocess.run(
        command
        + [
            "stage-a",
            *common,
            "--grants",
            str(output / "a-grants.json"),
            "--formal",
            str(output / "formal-c0.json"),
            "--formal-hash",
            formal["sha256"],
            "--inputs",
            str(mp),
            "--inputs-hash",
            mh,
            "--output",
            str(output / "a"),
        ],
        check=True,
    )
    a_seconds = time.monotonic() - a_start
    seal = auth.read_json(output / "a/phase-a.json")
    subprocess.run(
        command
        + [
            "verify-a",
            *common,
            "--grants",
            str(output / "a-grants.json"),
            "--formal-hash",
            formal["sha256"],
            "--inputs",
            str(mp),
            "--inputs-hash",
            mh,
            "--seal",
            str(output / "a/phase-a.json"),
            "--seal-hash",
            seal["sha256"],
            "--output",
            str(output / "a-verification"),
        ],
        check=True,
    )
    verification = auth.read_json(output / "a-verification/phase-a-verification.json")
    assert verification["prediction_sha256"] == seal["payload"]["prediction_sha256"]
    assert verification["member_count"] == 19032
    assert verification["labels_read"] is False
    grants["A_SEAL_REVIEW"] = signer.decision("A_SEAL_REVIEW", seal["sha256"])
    grants["B_LABEL_READ"] = signer.decision(
        "B_LABEL_READ", digest({"a_sha256": seal["sha256"], "path": str(lp), "label_sha256": lh})
    )
    grants["B_SCORING"] = signer.decision(
        "B_SCORING", digest({"a_sha256": seal["sha256"], "label_sha256": lh})
    )
    write(output / "b-grants.json", grants)
    b_start = time.monotonic()
    subprocess.run(
        command
        + [
            "stage-b",
            *common,
            "--grants",
            str(output / "b-grants.json"),
            "--seal",
            str(output / "a/phase-a.json"),
            "--seal-hash",
            seal["sha256"],
            "--labels",
            str(lp),
            "--labels-hash",
            lh,
            "--output",
            str(output / "b"),
        ],
        check=True,
    )
    b_seconds = time.monotonic() - b_start
    report = auth.read_json(output / "b/report.json")
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    parent_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    summary = {
        "data_class": "SYNTHETIC",
        "base_count": report["base_count"],
        "registered_count": report["registered_count"],
        "simulation_admitted_count": report["admitted_count"],
        "phase_a_seconds": a_seconds,
        "phase_b_seconds": b_seconds,
        "total_seconds": time.monotonic() - started,
        "child_peak_rss_bytes": rss_bytes,
        "parent_peak_rss_bytes": parent_rss if sys.platform == "darwin" else parent_rss * 1024,
        "memory_measurement": "PER_PROCESS_PEAKS_NOT_SIMULTANEOUS_TOTAL",
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "recorded_at": auth.now(),
        "prediction_content_sha256": seal["payload"]["prediction_sha256"],
        "a_seal_sha256": seal["sha256"],
        "report_sha256": report["report_sha256"],
        "source_code_sha256": auth.code_identity(),
        "groups": report["groups"],
        "numerical_example": next(
            r
            for r in report["members"]
            if r["base_id"] == "SYNTHETIC-20"
            and r["window"] == "H15_LOCAL"
            and r["target_start"] == "2026-01-01"
        ),
        "real_formally_admitted_c0_count": 0,
        "real_prediction_generated": False,
        "real_scoring_performed": False,
        "s3_formal_complete": False,
    }
    write(output / "run-summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output)
    print({k: v for k, v in summary.items() if k not in {"groups", "numerical_example"}})
