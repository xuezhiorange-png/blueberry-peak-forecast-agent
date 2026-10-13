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
| M2 | COMPLETE_PUSHED | `37f8156eebe5daa8f3f3d3bd4d9b55dd5e167ce3` |
| M3 | COMPLETE_PUSHED | `71bfa4289f5301900c828339b20ad236e6bb3e79` |
| M4 | COMPLETE_PUSHED | `dc6361dd25124bb4b55a3df5ffd25d52cca7a451` |
| M5 | COMPLETE_PUSHED | `834e98e441e45e81d1c67d0ee1149d5ef7a3d927` |
| M6 | COMPLETE_PUSHED | `bf7564307f719fd3ea5c90a5789b22e5719e4eb8` |
| M7 | COMPLETE_IN_CURRENT_CHECKPOINT | resolve commit `test(vision-r2): finalize research pipeline acceptance` after this commit |

Current checkpoint parent: `bf7564307f719fd3ea5c90a5789b22e5719e4eb8`. Current checkpoint SHA is deliberately not
embedded in its own commit; the next checkpoint records it and the final receipt
supplies final HEAD. All COMPLETE_PUSHED milestones were ordinary-pushed and their
remote HEAD checked. A local parallel module is not a completed milestone.

Current stage evidence: `evidence/r2/m7_checkpoint.json`.
Actual test stdout/exit codes are preserved there. `test(vision-r2): finalize research pipeline acceptance` is the checkpoint identity.

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
Next step: All M0–M7 engineering accepted. Verify final remote HEAD, create authorized Draft PR to main explicitly containing inherited R1, inspect exact-head CI/jobs, report results and STOP for independent owner review..
Current accepted artifact paths: research/blueberry_vision/cli.py, research/blueberry_vision/tests/test_r2_cli.py, research/blueberry_vision/tests/test_r2_acceptance.py, research/blueberry_vision/R2_README.md, .github/workflows/blueberry-vision-research.yml, research/blueberry_vision/evidence/r2/artifact_manifest.json, research/blueberry_vision/evidence/r2/independent_review.json, research/blueberry_vision/evidence/r2/image_evidence_index.json, research/blueberry_vision/evidence/r2/source_integrity.json, research/blueberry_vision/evidence/r2/known_limitations.md, research/blueberry_vision/evidence/r2/test_results.json, research/blueberry_vision/evidence/r2/e2e_acceptance.json, research/blueberry_vision/evidence/r2/r1_real_experiment_gate.json, research/blueberry_vision/evidence/r2/final_acceptance.md, research/blueberry_vision/evidence/r2/visual_report_manifest.json.
Future/pending stages must run their own tests and produce commit/push checkpoints.
Final scope: complete CLI and synthetic end-to-end results, Draft PR to main, inspect
available exact-head CI. Ready/Merge/Tag/Release/Deploy remain unauthorized.
