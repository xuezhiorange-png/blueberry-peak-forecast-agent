# Blueberry Vision R2 recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE

BRANCH=research/blueberry-vision-r2-offline-detection-counting

SOURCE_HEAD_SHA=88f052405d98210864d4f4d56b0da4bb62d5bd12

R2_START_HEAD_SHA=88f052405d98210864d4f4d56b0da4bb62d5bd12

BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a

## Completed durable milestones

| Milestone | Status | Commit |
| --- | --- | --- |
| M0 | COMPLETE_PUSHED | `c570d929eb8843dc0b29bfc818d0740484156531` |
| M1 | COMPLETE_PUSHED | `073993a0e62a5394ba3e699992b8a8e926f8644f` |
| M2 | COMPLETE_IN_CURRENT_CHECKPOINT | resolve commit `feat(vision-r2): add synthetic image and annotation generator` after this commit |
| M3 | PENDING_CHECKPOINT | not yet a durable completed milestone |
| M4 | PENDING_CHECKPOINT | not yet a durable completed milestone |
| M5 | PENDING_CHECKPOINT | not yet a durable completed milestone |
| M6 | PENDING_CHECKPOINT | not yet a durable completed milestone |
| M7 | PENDING_CHECKPOINT | not yet a durable completed milestone |

Current checkpoint parent: `073993a0e62a5394ba3e699992b8a8e926f8644f`. Current checkpoint SHA is deliberately not
embedded in its own commit; the next checkpoint records it and the final receipt
supplies final HEAD. All COMPLETE_PUSHED milestones were ordinary-pushed and their
remote HEAD checked. A local parallel module is not a completed milestone.

Current stage evidence: `evidence/r2/m2_checkpoint.json`.
Actual test stdout/exit codes are preserved there. `feat(vision-r2): add synthetic image and annotation generator` is the checkpoint identity.

## Data and boundaries

Only generated synthetic pixels/references/CPU models are authorized and used.
Real company/orchard images, business database, current-season actual and historical
harvest labels were not accessed. R1 contracts/69 regressions remain preserved.
Production forecast, Harvest State and V0.15–V0.18 frozen files remain untouched.
Counts are visible fruit per image, never kg; synthetic color appearances are not
approved maturity labels. Synthetic results are not real accuracy.

Known blockers: none.

## Resume from GitHub

Fetch origin --prune, verify live branch HEAD, read this file and stage evidence;
do not reset to the instruction's old SHA or overwrite another worktree.
Create an isolated Python3.12 environment and install
`research/blueberry_vision/requirements-r2.txt`; do not alter production uv.lock.
Next step: M3 commit classical RGB pixel detector with frozen config and validation predictions..
Current accepted artifact paths: research/blueberry_vision/synthetic.py, research/blueberry_vision/tests/test_r2_synthetic.py, research/blueberry_vision/docs/r2_synthetic.md, research/blueberry_vision/evidence/r2/dataset_manifest.json, research/blueberry_vision/evidence/r2/generation_config.json, research/blueberry_vision/evidence/r2/dataset_asset_validation.json, research/blueberry_vision/evidence/r2/synthetic_examples.json, research/blueberry_vision/examples/r2/raw.
Future/pending stages must run their own tests and produce commit/push checkpoints.
Final scope: complete CLI and synthetic end-to-end results, Draft PR to main, inspect
available exact-head CI. Ready/Merge/Tag/Release/Deploy remain unauthorized.
