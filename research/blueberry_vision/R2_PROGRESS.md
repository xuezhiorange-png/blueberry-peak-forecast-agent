# Blueberry Vision R2 recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE

BRANCH=research/blueberry-vision-r2-offline-detection-counting

SOURCE_HEAD_SHA=88f052405d98210864d4f4d56b0da4bb62d5bd12

R2_START_HEAD_SHA=88f052405d98210864d4f4d56b0da4bb62d5bd12

BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a

## Durable state

M0 preflight complete: GitHub permissions.push=true; git push --dry-run successful;
R1 regression freshly ran 69 passed. Independent R2 worktree preserves R1 branch/files.
Current checkpoint commit uses `chore(vision-r2): checkpoint environment and R1 regression`;
its SHA is resolved from Git history and recorded at the next milestone, avoiding self-reference.
Evidence: `evidence/r2/environment.json` records versions, license metadata, actual stdout and source hashes.

| Milestone | Status | Durable commit / recovery identity |
| --- | --- | --- |
| M0 | COMPLETE | current checkpoint, resolve by commit subject above |
| M1 assets/adapter | IN_PROGRESS | not yet committed |
| M2 synthetic PNG/reference | IN_PROGRESS | not yet committed |
| M3 classical pixel detector | IN_PROGRESS | not yet committed |
| M4 CPU trainable baseline | IN_PROGRESS | not yet committed |
| M5 independent evaluator | IN_PROGRESS | not yet committed |
| M6 COCO/visual review | IN_PROGRESS | not yet committed |
| M7 complete CLI/CI/acceptance | PENDING | not yet committed |

Parallel code work is not a completed milestone. Only tested, committed checkpoints count.
Data state: no private/real orchard images, no database or current-season actual accessed;
all future images for this R2 are programmatically generated SYNTHETIC assets.
Production forecast, Harvest State and frozen version files remain unchanged.

## Resume from GitHub

Fetch origin with prune; audit live R2 HEAD and this file before resuming.
Use `python -m venv /tmp/blueberry-vision-r2-venv` and install the isolated
`research/blueberry_vision/requirements-r2.txt` after its M1 commit. Do not uv-sync production dependencies.
Next: finish M1 PNG/JPEG asset tests and versioned 2.0.0 adapter, commit/push M1;
then M2 generator, M3 pixels, M4 actual training, M5 evaluation, M6 report, M7 complete run.

Known blockers: none. M0 does not claim images/detectors/training are already implemented.
Ready/Merge/Tag/Release/Deploy remain unauthorized. Final HEAD belongs in the task receipt.
