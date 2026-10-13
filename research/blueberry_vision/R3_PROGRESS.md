# R3 cloud recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION
BRANCH=research/blueberry-vision-r3-real-image-pilot
SOURCE_R2_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
R3_START_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a
PARENT_PR=719 (OPEN_DRAFT, unchanged)

| Stage | Accepted state | Checkpoint |
| --- | --- | --- |
| M0 | COMPLETE_IN_CURRENT_CHECKPOINT | chore(vision-r3): verify R2 baseline and isolated recovery |
| M1–M7 | PENDING | not accepted until own tests/evidence/commit/push |

Fresh R2 regression271 PASS in8.87s; original232 artifact hashes match.
Source/main/PR719 and clean worktrees verified; detailed evidence environment.json.
Current SHA is not embedded in its own content; resolve actual remote HEAD and
commit subject. Later checkpoints record earlier actual commit SHAs.

Only authorized public-license images and marked synthetic engineering fixtures
are used. No company/private orchard/database/current-season actual access.
R1/R2 files are preserved; R3 code belongs in r3/, new tests/evidence/docs.
Do not delete R2 large historical artifacts. Benchmark never approves orchard
accuracy, maturity labels or kg conversion.

Next M1: official source/license review and legal small samples. Then M2 import,
QA and perceptual candidates; M3 candidate review/adjudication; M4 grouped split/
seal; M5 R2 pixels-only inference and scoring only with qualified GT; M6 source/
license UI; M7 full acceptance and isolated CI. No real GT is fabricated.

Recover: fetch --prune, audit live R3 HEAD/worktrees and this progress; continue
accepted stages without reset/force push. Every milestone uses tests/evidence/
ordinary commit/push and exact remote SHA. Stack Draft PR on R2, leave PR719/main/
Ready/Merge/Tag/Release/Deploy untouched. GitHub is durable; public /tmp assets
require committed official source/license/hash indexes and reproduction commands.

Known blockers: qualified real GT being sought; Commons photos alone cannot score.
