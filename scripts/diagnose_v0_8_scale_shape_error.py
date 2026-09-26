"""Run read-only scale/shape diagnostics on the frozen S8 private artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.area_yield.v08_s9_scale_shape_diagnosis import run_diagnosis

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = Path.home() / "Documents/blueberry-area-yield-artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--s8-root",
        type=Path,
        default=PRIVATE_ROOT / "v0-8-s8-canonical-training-oot-backtest-r1-replay-3",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=PRIVATE_ROOT / "v0-8-s9-scale-shape-diagnosis-r1",
    )
    args = parser.parse_args()
    result = run_diagnosis(
        repo_root=REPO_ROOT,
        s8_root=args.s8_root,
        artifact_root=args.artifact_root,
        config_path=REPO_ROOT / "configs/v0_8_s9_scale_shape_diagnosis_r1.json",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
