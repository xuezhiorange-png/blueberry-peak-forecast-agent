"""Independent process interfaces; REAL has no installed trust anchor."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_research_evaluation as scoring
from backend.research import v019_research_execution as phase_a
from backend.research.v019_daily_curve import canonical_bytes


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "formalize", "stage-a", "stage-b"))
    p.add_argument("--mode", required=True, choices=("REAL", "SYNTHETIC"))
    p.add_argument("--synthetic-roots", type=Path)
    p.add_argument("--grants", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--inputs", type=Path)
    p.add_argument("--inputs-hash")
    p.add_argument("--candidate", type=Path)
    p.add_argument("--review", type=Path)
    p.add_argument("--formal", type=Path)
    p.add_argument("--formal-hash")
    p.add_argument("--seal", type=Path)
    p.add_argument("--seal-hash")
    p.add_argument("--labels", type=Path)
    p.add_argument("--labels-hash")
    a = p.parse_args()
    ctx = auth.Context(a.mode)
    if a.mode == "SYNTHETIC":
        if a.synthetic_roots is None:
            p.error("explicit synthetic trust context required")
        root = auth.read_json(a.synthetic_roots)
        if set(root) != {"synthetic_only", "keys"} or root["synthetic_only"] is not True:
            p.error("synthetic-only root context required")
        ctx = auth.Context("SYNTHETIC", root["keys"])
    auth.roots(ctx)  # REAL denied BEFORE opening grants/inputs/C0/seal/labels.
    grants = auth.read_json(a.grants)
    if a.command == "prepare":
        if not a.inputs or not a.inputs_hash:
            p.error("inputs and exact file hash required")
        inputs = cohort.load_inputs(a.inputs, ctx, grants, a.inputs_hash)
        value = cohort.candidates(inputs, ctx)
        files = {"candidates.json": canonical_bytes(value)}
    elif a.command == "formalize":
        if not a.candidate or not a.review:
            p.error("complete candidate and review required")
        value = cohort.formalize(auth.read_json(a.candidate), auth.read_json(a.review), ctx, grants)
        files = {"formal-c0.json": canonical_bytes(value)}
    elif a.command == "stage-a":
        if not a.formal or not a.formal_hash or not a.inputs or not a.inputs_hash:
            p.error("formal C0, exact seal hash and inputs required")
        auth.require(ctx, grants, "A_EXECUTION", a.formal_hash)
        formal = auth.read_json(a.formal)
        if formal["sha256"] != a.formal_hash:
            raise ValueError("FORMAL_C0_HASH_MISMATCH")
        value = phase_a.run_a(a.inputs, a.inputs_hash, formal, ctx, grants)
        files = {"phase-a.json": canonical_bytes(value)}
    else:
        if not a.seal or not a.seal_hash or not a.labels or not a.labels_hash:
            p.error("A seal, labels and exact hashes required")
        value = scoring.run_b(a.seal, a.seal_hash, a.labels, a.labels_hash, ctx, grants)
        files = scoring.render(value)
    phase_a.write_artifacts(a.output, files, ctx=ctx, phase=a.command)
    print(a.output)


if __name__ == "__main__":
    main()
