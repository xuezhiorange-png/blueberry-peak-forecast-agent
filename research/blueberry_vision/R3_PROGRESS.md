# R3 recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION
BRANCH=research/blueberry-vision-r3-real-image-pilot
SOURCE_R2_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
R3_START_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a
PARENT_PR=719 (unchanged OPEN_DRAFT)

| Stage | Accepted state | Commit |
| --- | --- | --- |
| M0 | COMPLETE_PUSHED | `2772f6a68a3a3095c3e2883a70ae6de044ff989b` |
| M1 | COMPLETE_PUSHED | `a15c56d6634e69db3715b86e2b5e8f63bb28aee1` |
| M2 | COMPLETE_IN_CURRENT_CHECKPOINT | current checkpoint subject: `feat(vision-r3): add licensed ingestion quality and perceptual duplicate audit` |
| M3 | PENDING | pending own accepted checkpoint |
| M4 | PENDING | pending own accepted checkpoint |
| M5 | PENDING | pending own accepted checkpoint |
| M6 | PENDING | pending own accepted checkpoint |
| M7 | PENDING | pending own accepted checkpoint |

Current checkpoint parent `a15c56d6634e69db3715b86e2b5e8f63bb28aee1`. Own SHA intentionally not self-embedded;
next checkpoint/remote log/final receipt supplies it. Completed prior stages were
ordinary-pushed and remote HEAD verified; local parallel files are not milestones.
Actual commands/exit/stdout/facts: evidence/r3/m2_checkpoint.json.
R2 original271 fresh tests passed in M0, original232 artifact seal verified; all
inherited research bytes checked unchanged before every checkpoint.

Data status: 4 actual licensed public Commons JPG admitted for inference; missing per-fruit GT; further official annotated sources under review.
Known blockers: per-fruit public GT still sought; NC purpose/code-only and unknown license sources blocked.
No company/private orchard/DB/current-season actual access, no production forecast/
Harvest State/frozen model changes. Source purpose stays PUBLIC_EXTERNAL_BENCHMARK/
AUTHORIZED_ORCHARD_PILOT/SYNTHETIC_ENGINEERING, unknown date/identity stays unknown.
No automatic reviewed business labels, no count→kg, no real orchard approval.

Next: M3 independent annotation snapshots and explicit simulated two-annotator review; publisher labeled source acquisition continues..
Stage artifact paths: research/blueberry_vision/r3/contracts.py, research/blueberry_vision/r3/ingestion.py, research/blueberry_vision/r3/dedup.py, research/blueberry_vision/tests/test_r3_ingestion.py, research/blueberry_vision/tests/test_r3_dedup.py, research/blueberry_vision/r3/schema.json, research/blueberry_vision/docs/r3_ingestion.md, research/blueberry_vision/evidence/r3/dataset_admission.json, research/blueberry_vision/evidence/r3/image_quality_report.json, research/blueberry_vision/evidence/r3/duplicate_review.json.
R3 keeps compact indexes/metrics/evidence. M0 audits inherited42.67MB research tree;
never delete/rewrite R2 history or add duplicated full AP curves/bulk private images.
GitHub is durable; external data uses official source/license/hash indexes and
bounded reproducible downloads. No credentials/signed URLs stored publicly.

Restore: fetch --prune, audit real R3 HEAD/worktrees and this file, continue accepted
commits rather than reset/rebuild. Install independent requirements-r3.txt when
available (includes fixed R2 requirements), Python3.12.14 CPU. R3 CLI lives in
research.blueberry_vision.r3.cli; no R1/R2 schema/gate relaxation. Final stacked
Draft PR base R2; leave PR719/main/Ready/Merge/Tag/Release/Deploy unchanged.
